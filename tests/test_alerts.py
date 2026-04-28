"""Tests for agentlimit.alerts threshold behavior."""

import pytest

from agentlimit.alerts import AlertManager


class TestAlertManager:
    def test_alerts_fire_once_per_threshold(self, redis_client):
        manager = AlertManager()
        events: list[tuple[float, float]] = []

        def on_alert(event):
            events.append((event.threshold, event.percent))

        manager.check_and_fire(
            agent_id="agent-a",
            current_pct=0.85,
            thresholds=[0.8, 0.9],
            on_alert=on_alert,
            redis_client=redis_client,
            current_usd=8.5,
            budget_usd=10.0,
        )
        manager.check_and_fire(
            agent_id="agent-a",
            current_pct=0.86,
            thresholds=[0.8, 0.9],
            on_alert=on_alert,
            redis_client=redis_client,
            current_usd=8.6,
            budget_usd=10.0,
        )
        manager.check_and_fire(
            agent_id="agent-a",
            current_pct=0.95,
            thresholds=[0.8, 0.9],
            on_alert=on_alert,
            redis_client=redis_client,
            current_usd=9.5,
            budget_usd=10.0,
        )

        assert events == [(0.8, 85.0), (0.9, 95.0)]

    def test_failed_callback_can_retry(self, redis_client):
        manager = AlertManager()

        def broken_callback(_event):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            manager.check_and_fire(
                agent_id="agent-b",
                current_pct=0.8,
                thresholds=[0.8],
                on_alert=broken_callback,
                redis_client=redis_client,
                current_usd=8.0,
                budget_usd=10.0,
            )

        events = []

        def good_callback(event):
            events.append(event.threshold)

        manager.check_and_fire(
            agent_id="agent-b",
            current_pct=0.8,
            thresholds=[0.8],
            on_alert=good_callback,
            redis_client=redis_client,
            current_usd=8.0,
            budget_usd=10.0,
        )

        assert events == [0.8]
