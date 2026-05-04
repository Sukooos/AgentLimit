"""Provider pricing tables and cost calculation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from math import isfinite

from .exceptions import UnknownModelError

PRICING: dict[str, dict[str, dict[str, float]]] = {
    "openai": {
        "gpt-4o": {"input": 0.0000025, "output": 0.000010},
        "gpt-4o-mini": {"input": 0.00000015, "output": 0.0000006},
        "gpt-3.5-turbo": {"input": 0.0000005, "output": 0.0000015},
    },
    "anthropic": {
        "claude-sonnet-4": {"input": 0.000003, "output": 0.000015},
        "claude-haiku-4": {"input": 0.00000025, "output": 0.00000125},
    },
}


def _coerce_token_count(raw_value: object) -> int:
    if isinstance(raw_value, bool) or raw_value is None:
        raise ValueError("Token counts must be finite non-negative integers.")

    try:
        token_count = Decimal(raw_value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            "Token counts must be finite non-negative integers."
        ) from exc

    if (
        not token_count.is_finite()
        or token_count < 0
        or token_count != token_count.to_integral_value()
    ):
        raise ValueError("Token counts must be finite non-negative integers.")

    return int(token_count)


def _coerce_rate(provider: str, model: str, token_type: str, raw_rate: object) -> float:
    if isinstance(raw_rate, bool):
        raise ValueError(
            f"Invalid pricing rate for {provider}/{model} {token_type}: {raw_rate}"
        )

    try:
        rate = float(raw_rate)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid pricing rate for {provider}/{model} {token_type}: {raw_rate}"
        ) from exc

    if not isfinite(rate) or rate < 0:
        raise ValueError(
            f"Pricing rate for {provider}/{model} {token_type} "
            "must be finite and non-negative."
        )
    return rate


def _build_pricing(
    custom_pricing: dict | None,
) -> dict[str, dict[str, dict[str, float]]]:
    pricing = deepcopy(PRICING)
    if custom_pricing is None:
        return pricing
    if not isinstance(custom_pricing, Mapping):
        raise ValueError("Invalid pricing; custom_pricing must be a mapping.")

    for provider, models in custom_pricing.items():
        if not isinstance(models, Mapping):
            raise ValueError(
                f"Invalid pricing for {provider}; expected model mapping."
            )

        provider_models = pricing.setdefault(provider, {})
        for model, rates in models.items():
            if not isinstance(rates, Mapping):
                raise ValueError(
                    "Invalid pricing for "
                    f"{provider}/{model}; expected input and output."
                )
            if "input" not in rates or "output" not in rates:
                raise ValueError(
                    "Invalid pricing for "
                    f"{provider}/{model}; expected input and output."
                )
            provider_models[model] = {
                "input": _coerce_rate(provider, model, "input", rates["input"]),
                "output": _coerce_rate(provider, model, "output", rates["output"]),
            }
    return pricing


def calculate_cost(
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    custom_pricing: dict | None = None,
) -> float:
    """Calculate USD cost for a given model and token usage."""
    input_token_count = _coerce_token_count(input_tokens)
    output_token_count = _coerce_token_count(output_tokens)

    pricing = _build_pricing(custom_pricing)
    if provider not in pricing:
        raise UnknownModelError(f"Unknown provider: {provider}")
    if model not in pricing[provider]:
        raise UnknownModelError(f"Unknown model '{model}' for provider '{provider}'")

    model_pricing = pricing[provider][model]
    return (input_token_count * model_pricing["input"]) + (
        output_token_count * model_pricing["output"]
    )


def get_supported_models() -> dict[str, dict[str, dict[str, float]]]:
    """Return the full pricing table."""
    return deepcopy(PRICING)
