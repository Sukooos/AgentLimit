"""Core UsageMeter class; main interface for agentlimit."""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from redis import Redis
from redis.exceptions import RedisError

from .alerts import AlertEvent, AlertManager
from .exceptions import (
    BudgetExceededError,
    InvalidBudgetError,
    RedisConnectionError,
    RedisDataError,
)
from .providers import calculate_cost
from .reset import perform_reset, should_reset


@dataclass
class UsageStats:
    """Current usage statistics for an agent."""

    agent_id: str
    usd_spent: float
    tokens_spent: int
    monthly_budget_usd: float | None
    monthly_budget_tokens: int | None
    percent_usd: float | None
    percent_tokens: float | None


class UsageMeter:
    """Tracks token usage and USD spend per agent in Redis."""

    def __init__(
        self,
        redis_url: str,
        agent_id: str,
        monthly_budget_usd: float | None = None,
        monthly_budget_tokens: int | None = None,
        alert_thresholds: list[float] | None = None,
        on_alert: Callable[[AlertEvent], None] | None = None,
        custom_pricing: dict | None = None,
    ) -> None:
        if not agent_id.strip():
            raise ValueError("agent_id cannot be empty.")

        if monthly_budget_usd is not None and monthly_budget_usd <= 0:
            raise InvalidBudgetError("monthly_budget_usd must be greater than zero.")
        if monthly_budget_tokens is not None and monthly_budget_tokens <= 0:
            raise InvalidBudgetError("monthly_budget_tokens must be greater than zero.")

        self.agent_id = agent_id
        self.custom_pricing = custom_pricing
        self.alert_thresholds = sorted(set(alert_thresholds or [0.8, 0.9, 1.0]))
        if any(threshold <= 0 or threshold > 1 for threshold in self.alert_thresholds):
            raise ValueError("Alert thresholds must be between 0 and 1.")

        self._on_alert = on_alert
        self._alert_manager = AlertManager()

        self._prefix = f"agentlimit:{agent_id}:"
        self._usd_spent_key = f"{self._prefix}usd_spent"
        self._tokens_spent_key = f"{self._prefix}tokens_spent"
        self._last_reset_key = f"{self._prefix}last_reset"
        self._monthly_budget_usd_key = f"{self._prefix}monthly_budget_usd"
        self._monthly_budget_tokens_key = f"{self._prefix}monthly_budget_tokens"

        try:
            self._redis = Redis.from_url(redis_url, decode_responses=True)
            self._redis.ping()

            self._redis.setnx(self._usd_spent_key, 0.0)
            self._redis.setnx(self._tokens_spent_key, 0)
            self._redis.setnx(self._last_reset_key, time.time())

            if monthly_budget_usd is not None:
                self._redis.set(self._monthly_budget_usd_key, monthly_budget_usd)
            if monthly_budget_tokens is not None:
                self._redis.set(self._monthly_budget_tokens_key, monthly_budget_tokens)

            if monthly_budget_usd is None:
                stored_usd = self._redis.get(self._monthly_budget_usd_key)
                monthly_budget_usd = (
                    self._parse_float_value(stored_usd, "monthly_budget_usd")
                    if stored_usd is not None
                    else None
                )
            if monthly_budget_tokens is None:
                stored_tokens = self._redis.get(self._monthly_budget_tokens_key)
                monthly_budget_tokens = (
                    self._parse_int_value(stored_tokens, "monthly_budget_tokens")
                    if stored_tokens is not None
                    else None
                )
        except RedisError as exc:
            raise RedisConnectionError(str(exc)) from exc

        self.monthly_budget_usd = monthly_budget_usd
        self.monthly_budget_tokens = monthly_budget_tokens

    def __enter__(self) -> UsageMeter:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def track(self, estimated_cost: float) -> Callable:
        """Decorator that checks budget before calling the wrapped function."""
        if estimated_cost < 0:
            raise ValueError("estimated_cost cannot be negative.")

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args: object, **kwargs: object):
                if not self.can_spend(estimated_cost):
                    raise BudgetExceededError(
                        f"Agent '{self.agent_id}' monthly budget would be exceeded."
                    )
                return func(*args, **kwargs)

            return wrapper

        return decorator

    def instrument_openai_client(self, client: object) -> object:
        """Wrap OpenAI chat completion create() to auto-record usage."""
        completions = self._resolve_path(
            client,
            ["chat", "completions"],
            "OpenAI client missing chat.completions.",
        )
        self._instrument_create(
            create_owner=completions,
            recorder=self._record_openai_response,
            error_prefix="OpenAI",
        )
        return client

    def instrument_anthropic_client(self, client: object) -> object:
        """Wrap Anthropic messages create() to auto-record usage."""
        messages = self._resolve_path(
            client,
            ["messages"],
            "Anthropic client missing messages.",
        )
        self._instrument_create(
            create_owner=messages,
            recorder=self._record_anthropic_response,
            error_prefix="Anthropic",
        )
        return client

    def can_spend(self, estimated_cost_usd: float) -> bool:
        """Check if the agent can afford the estimated cost without exceeding budget."""
        if estimated_cost_usd < 0:
            raise ValueError("estimated_cost_usd cannot be negative.")

        self._maybe_auto_reset()
        usage = self.get_usage()

        if (
            self.monthly_budget_usd is not None
            and usage.usd_spent + estimated_cost_usd > self.monthly_budget_usd
        ):
            return False
        if (
            self.monthly_budget_tokens is not None
            and usage.tokens_spent >= self.monthly_budget_tokens
        ):
            return False
        return True

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        tokens_used: int = 0,
    ) -> None:
        """Record actual usage after an LLM call."""
        if input_tokens < 0 or output_tokens < 0 or tokens_used < 0:
            raise ValueError("Token counts cannot be negative.")

        if tokens_used > 0 and input_tokens == 0 and output_tokens == 0:
            # Backward-compatible path when caller only has total tokens.
            input_tokens = tokens_used

        total_tokens = tokens_used or (input_tokens + output_tokens)
        call_cost = calculate_cost(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            custom_pricing=self.custom_pricing,
        )

        self._maybe_auto_reset()
        usage = self.get_usage()
        projected_usd = usage.usd_spent + call_cost
        projected_tokens = usage.tokens_spent + total_tokens

        if (
            self.monthly_budget_usd is not None
            and projected_usd > self.monthly_budget_usd
        ):
            raise BudgetExceededError(
                f"Agent '{self.agent_id}' exceeded USD budget "
                f"({projected_usd:.4f} > {self.monthly_budget_usd:.4f})."
            )
        if (
            self.monthly_budget_tokens is not None
            and projected_tokens > self.monthly_budget_tokens
        ):
            raise BudgetExceededError(
                f"Agent '{self.agent_id}' exceeded token budget "
                f"({projected_tokens} > {self.monthly_budget_tokens})."
            )

        try:
            self._redis.incrbyfloat(self._usd_spent_key, call_cost)
            self._redis.incrby(self._tokens_spent_key, total_tokens)
        except RedisError as exc:
            raise RedisConnectionError(str(exc)) from exc

        if self._on_alert and self.monthly_budget_usd:
            current_usd = usage.usd_spent + call_cost
            current_pct = current_usd / self.monthly_budget_usd
            self._alert_manager.check_and_fire(
                agent_id=self.agent_id,
                current_pct=current_pct,
                thresholds=self.alert_thresholds,
                on_alert=self._on_alert,
                redis_client=self._redis,
                current_usd=current_usd,
                budget_usd=self.monthly_budget_usd,
            )

    def get_usage(self) -> UsageStats:
        """Return current usage statistics."""
        self._maybe_auto_reset()
        usd_spent = self._read_float(self._usd_spent_key)
        tokens_spent = self._read_int(self._tokens_spent_key)

        percent_usd = None
        if self.monthly_budget_usd:
            percent_usd = (usd_spent / self.monthly_budget_usd) * 100

        percent_tokens = None
        if self.monthly_budget_tokens:
            percent_tokens = (tokens_spent / self.monthly_budget_tokens) * 100

        return UsageStats(
            agent_id=self.agent_id,
            usd_spent=usd_spent,
            tokens_spent=tokens_spent,
            monthly_budget_usd=self.monthly_budget_usd,
            monthly_budget_tokens=self.monthly_budget_tokens,
            percent_usd=percent_usd,
            percent_tokens=percent_tokens,
        )

    def reset(self) -> None:
        """Manually reset the budget for this agent."""
        try:
            perform_reset(self.agent_id, self._redis)
        except RedisError as exc:
            raise RedisConnectionError(str(exc)) from exc

    def _maybe_auto_reset(self) -> None:
        try:
            raw = self._redis.get(self._last_reset_key)
            if raw is None:
                self._redis.set(self._last_reset_key, time.time())
                return

            if should_reset(self._parse_float_value(raw, "last_reset")):
                perform_reset(self.agent_id, self._redis)
        except RedisError as exc:
            raise RedisConnectionError(str(exc)) from exc

    def _read_float(self, key: str) -> float:
        try:
            raw = self._redis.get(key)
        except RedisError as exc:
            raise RedisConnectionError(str(exc)) from exc
        if raw is None:
            return 0.0
        field_name = key.rsplit(":", maxsplit=1)[-1]
        return self._parse_float_value(raw, field_name)

    def _read_int(self, key: str) -> int:
        try:
            raw = self._redis.get(key)
        except RedisError as exc:
            raise RedisConnectionError(str(exc)) from exc
        if raw is None:
            return 0
        field_name = key.rsplit(":", maxsplit=1)[-1]
        return self._parse_int_value(raw, field_name)

    def _instrument_create(
        self,
        create_owner: object,
        recorder: Callable[[object, dict[str, Any]], None],
        error_prefix: str,
    ) -> None:
        original_create = getattr(create_owner, "create", None)
        if original_create is None or not callable(original_create):
            raise ValueError(f"{error_prefix} client create() not found.")

        if getattr(original_create, "__agentlimit_wrapped__", False):
            return

        if inspect.iscoroutinefunction(original_create):

            @wraps(original_create)
            async def wrapped_create(*args: Any, **kwargs: Any):
                response = await original_create(*args, **kwargs)
                recorder(response, kwargs)
                return response

        else:

            @wraps(original_create)
            def wrapped_create(*args: Any, **kwargs: Any):
                response = original_create(*args, **kwargs)
                recorder(response, kwargs)
                return response

        setattr(wrapped_create, "__agentlimit_wrapped__", True)
        setattr(create_owner, "create", wrapped_create)

    def _record_openai_response(
        self,
        response: object,
        kwargs: dict[str, Any],
    ) -> None:
        usage = self._read_attr(response, "usage")
        if usage is None:
            raise ValueError("OpenAI response missing usage.")

        model = self._resolve_model(response=response, kwargs=kwargs)
        input_tokens = self._parse_tokens(self._read_attr(usage, "prompt_tokens"))
        output_tokens = self._parse_tokens(self._read_attr(usage, "completion_tokens"))
        total_tokens = self._parse_tokens(self._read_attr(usage, "total_tokens"))
        if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
            raise ValueError("OpenAI response usage has no token counts.")

        self.record(
            provider="openai",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_used=total_tokens,
        )

    def _record_anthropic_response(
        self,
        response: object,
        kwargs: dict[str, Any],
    ) -> None:
        usage = self._read_attr(response, "usage")
        if usage is None:
            raise ValueError("Anthropic response missing usage.")

        model = self._resolve_model(response=response, kwargs=kwargs)
        input_tokens = self._parse_tokens(self._read_attr(usage, "input_tokens"))
        output_tokens = self._parse_tokens(self._read_attr(usage, "output_tokens"))
        if input_tokens == 0 and output_tokens == 0:
            raise ValueError("Anthropic response usage has no token counts.")

        self.record(
            provider="anthropic",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _resolve_model(self, response: object, kwargs: dict[str, Any]) -> str:
        model = kwargs.get("model")
        if model is None:
            model = self._read_attr(response, "model")
        if not model:
            raise ValueError("Model is required to record usage.")
        return str(model)

    def _resolve_path(
        self,
        root: object,
        path: list[str],
        missing_message: str,
    ) -> object:
        node: object | None = root
        for item in path:
            node = self._read_attr(node, item)
            if node is None:
                raise ValueError(missing_message)
        return node

    @staticmethod
    def _parse_float_value(raw_value: object, field_name: str) -> float:
        try:
            return float(raw_value)
        except (TypeError, ValueError) as exc:
            raise RedisDataError(
                f"Invalid numeric value for {field_name}: {raw_value}"
            ) from exc

    @staticmethod
    def _parse_int_value(raw_value: object, field_name: str) -> int:
        try:
            return int(float(raw_value))
        except (TypeError, ValueError) as exc:
            raise RedisDataError(
                f"Invalid integer value for {field_name}: {raw_value}"
            ) from exc

    @staticmethod
    def _read_attr(source: object | None, field: str) -> object | None:
        if source is None:
            return None
        if isinstance(source, dict):
            return source.get(field)
        return getattr(source, field, None)

    @staticmethod
    def _parse_tokens(raw_value: object | None) -> int:
        if raw_value is None:
            return 0
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid token count: {raw_value}") from exc
        if value < 0:
            raise ValueError("Token counts cannot be negative.")
        return value
