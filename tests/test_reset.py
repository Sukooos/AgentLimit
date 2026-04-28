"""Tests for agentlimit.reset monthly logic."""

from datetime import datetime, timedelta, timezone

from agentlimit.reset import perform_reset, should_reset


class TestReset:
    def test_should_reset_when_month_changed(self):
        now = datetime.now(timezone.utc)
        first_day_this_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        previous_month_dt = first_day_this_month - timedelta(days=1)

        assert should_reset(previous_month_dt.timestamp()) is True

    def test_should_not_reset_within_same_month(self):
        now = datetime.now(timezone.utc)
        assert should_reset(now.timestamp()) is False

    def test_perform_reset_clears_usage_and_alerts(self, redis_client):
        prefix = "agentlimit:reset-agent:"
        redis_client.set(f"{prefix}usd_spent", 12.34)
        redis_client.set(f"{prefix}tokens_spent", 1234)
        redis_client.sadd(f"{prefix}alerts_sent", "0.8")
        redis_client.set(f"{prefix}last_reset", 1.0)

        perform_reset("reset-agent", redis_client)

        assert float(redis_client.get(f"{prefix}usd_spent")) == 0.0
        assert int(redis_client.get(f"{prefix}tokens_spent")) == 0
        assert redis_client.scard(f"{prefix}alerts_sent") == 0
        assert float(redis_client.get(f"{prefix}last_reset")) > 1.0
