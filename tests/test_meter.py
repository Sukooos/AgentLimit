"""Tests for agentlimit.meter UsageMeter behavior."""

from datetime import datetime, timedelta, timezone

import pytest

from agentlimit import (
    BudgetExceededError,
    InvalidBudgetError,
    RedisDataError,
    UsageMeter,
)


@pytest.fixture()
def meter_factory(monkeypatch, redis_client, redis_url):
    monkeypatch.setattr(
        "agentlimit.meter.Redis.from_url",
        lambda *args, **kwargs: redis_client,
    )

    def _create(**kwargs):
        return UsageMeter(redis_url=redis_url, agent_id="agent-a", **kwargs)

    return _create


class _Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _OpenAIClient:
    def __init__(self, response):
        self._response = response
        self.chat = _Obj(completions=_Obj(create=self._create))

    def _create(self, *args, **kwargs):
        return self._response


class _AnthropicClient:
    def __init__(self, response):
        self._response = response
        self.messages = _Obj(create=self._create)

    def _create(self, *args, **kwargs):
        return self._response


class TestUsageMeterInit:
    def test_rejects_invalid_budgets(self, meter_factory):
        with pytest.raises(InvalidBudgetError):
            meter_factory(monthly_budget_usd=0)
        with pytest.raises(InvalidBudgetError):
            meter_factory(monthly_budget_tokens=-1)

    def test_rejects_empty_agent_id(self, monkeypatch, redis_client, redis_url):
        monkeypatch.setattr(
            "agentlimit.meter.Redis.from_url",
            lambda *args, **kwargs: redis_client,
        )

        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            UsageMeter(redis_url=redis_url, agent_id="   ")

    def test_malformed_stored_budget_raises_data_error(
        self,
        monkeypatch,
        redis_client,
        redis_url,
    ):
        monkeypatch.setattr(
            "agentlimit.meter.Redis.from_url",
            lambda *args, **kwargs: redis_client,
        )
        redis_client.set("agentlimit:agent-b:monthly_budget_usd", "not-a-number")

        with pytest.raises(RedisDataError, match="monthly_budget_usd"):
            UsageMeter(redis_url=redis_url, agent_id="agent-b")


class TestUsageMeterCore:
    def test_can_spend_rejects_negative_estimate(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)

        with pytest.raises(ValueError, match="estimated_cost_usd cannot be negative"):
            meter.can_spend(-0.01)

    def test_track_rejects_negative_estimated_cost(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)

        with pytest.raises(ValueError, match="estimated_cost cannot be negative"):
            meter.track(estimated_cost=-0.01)

    def test_record_rejects_negative_tokens(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)

        with pytest.raises(ValueError, match="Token counts cannot be negative"):
            meter.record(
                provider="openai",
                model="gpt-4o-mini",
                input_tokens=-1,
            )

    def test_malformed_usage_value_raises_data_error(
        self,
        meter_factory,
        redis_client,
    ):
        meter = meter_factory(monthly_budget_usd=10.0)
        redis_client.set("agentlimit:agent-a:usd_spent", "not-a-number")

        with pytest.raises(RedisDataError, match="usd_spent"):
            meter.get_usage()

    def test_malformed_last_reset_raises_data_error(
        self,
        meter_factory,
        redis_client,
    ):
        meter = meter_factory(monthly_budget_usd=10.0)
        redis_client.set("agentlimit:agent-a:last_reset", "not-a-timestamp")

        with pytest.raises(RedisDataError, match="last_reset"):
            meter.get_usage()

    def test_can_spend_within_and_over_budget(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)
        assert meter.can_spend(1.0) is True

        meter.record(
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=20_000_000,
            output_tokens=0,
        )
        assert meter.can_spend(8.0) is False

    def test_record_updates_usage(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0, monthly_budget_tokens=2000)
        meter.record(
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
        )
        usage = meter.get_usage()
        assert usage.tokens_spent == 1500
        assert usage.usd_spent == pytest.approx(0.00045)
        assert usage.percent_usd == pytest.approx(0.0045)
        assert usage.percent_tokens == pytest.approx(75.0)

    def test_record_raises_when_budget_exceeded(self, meter_factory):
        meter = meter_factory(
            monthly_budget_usd=1.0,
            custom_pricing={"test": {"model-a": {"input": 1.0, "output": 0.0}}},
        )
        with pytest.raises(BudgetExceededError):
            meter.record(
                provider="test",
                model="model-a",
                input_tokens=2,
                output_tokens=0,
            )

        usage = meter.get_usage()
        assert usage.usd_spent == 0.0
        assert usage.tokens_spent == 0

    def test_record_enforces_token_budget(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=100.0, monthly_budget_tokens=5)
        meter.record(
            provider="openai",
            model="gpt-4o-mini",
            tokens_used=5,
        )
        with pytest.raises(BudgetExceededError):
            meter.record(
                provider="openai",
                model="gpt-4o-mini",
                tokens_used=1,
            )

    def test_alerts_fire_once_per_threshold(self, meter_factory):
        events = []

        def on_alert(event):
            events.append(event.threshold)

        meter = meter_factory(
            monthly_budget_usd=10.0,
            alert_thresholds=[0.5, 0.8, 1.0],
            on_alert=on_alert,
            custom_pricing={"test": {"model-a": {"input": 1.0, "output": 0.0}}},
        )
        meter.record(provider="test", model="model-a", input_tokens=6)
        meter.record(provider="test", model="model-a", input_tokens=2)
        meter.record(provider="test", model="model-a", input_tokens=2)

        assert events == [0.5, 0.8, 1.0]

    def test_auto_reset_happens_on_month_boundary(self, meter_factory, redis_client):
        now = datetime.now(timezone.utc)
        first_day_this_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        previous_month_dt = first_day_this_month - timedelta(days=1)

        prefix = "agentlimit:agent-a:"
        redis_client.set(f"{prefix}usd_spent", 7.5)
        redis_client.set(f"{prefix}tokens_spent", 999)
        redis_client.sadd(f"{prefix}alerts_sent", "0.8")
        redis_client.set(f"{prefix}last_reset", previous_month_dt.timestamp())

        meter = meter_factory(monthly_budget_usd=10.0, monthly_budget_tokens=2000)
        usage = meter.get_usage()
        assert usage.usd_spent == 0.0
        assert usage.tokens_spent == 0
        assert redis_client.scard(f"{prefix}alerts_sent") == 0

    def test_track_decorator_checks_budget_before_call(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=1.0)

        @meter.track(estimated_cost=2.0)
        def run_task():
            return "ok"

        with pytest.raises(BudgetExceededError):
            run_task()


class TestSdkInstrumentation:
    def test_openai_instrumentation_records_usage(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0, monthly_budget_tokens=5000)
        response = _Obj(
            model="gpt-4o-mini",
            usage=_Obj(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
        )
        client = _OpenAIClient(response)

        meter.instrument_openai_client(client)
        client.chat.completions.create(model="gpt-4o-mini", messages=[])

        usage = meter.get_usage()
        assert usage.tokens_spent == 1500
        assert usage.usd_spent == pytest.approx(0.00045)

    def test_openai_instrumentation_is_idempotent(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0, monthly_budget_tokens=5000)
        response = _Obj(
            model="gpt-4o-mini",
            usage=_Obj(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
        )
        client = _OpenAIClient(response)

        meter.instrument_openai_client(client)
        meter.instrument_openai_client(client)
        client.chat.completions.create(model="gpt-4o-mini", messages=[])

        usage = meter.get_usage()
        assert usage.tokens_spent == 1500
        assert usage.usd_spent == pytest.approx(0.00045)

    def test_anthropic_instrumentation_records_usage(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0, monthly_budget_tokens=5000)
        response = _Obj(
            model="claude-haiku-4",
            usage=_Obj(input_tokens=1000, output_tokens=500),
        )
        client = _AnthropicClient(response)

        meter.instrument_anthropic_client(client)
        client.messages.create(model="claude-haiku-4", max_tokens=256, messages=[])

        usage = meter.get_usage()
        assert usage.tokens_spent == 1500
        assert usage.usd_spent == pytest.approx(0.000875)

    def test_openai_instrumentation_fails_loudly_without_usage(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)
        response = _Obj(model="gpt-4o-mini", usage=None)
        client = _OpenAIClient(response)

        meter.instrument_openai_client(client)
        with pytest.raises(ValueError):
            client.chat.completions.create(model="gpt-4o-mini", messages=[])
