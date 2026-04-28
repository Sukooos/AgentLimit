"""Alert system and threshold management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from redis import Redis
from redis.exceptions import RedisError

from .exceptions import RedisConnectionError


@dataclass
class AlertEvent:
    """Event object passed to alert callbacks."""

    agent_id: str
    percent: float
    threshold: float
    current_usd: float
    budget_usd: float


class AlertManager:
    """Manages threshold checks and alert deduplication via Redis."""

    def check_and_fire(
        self,
        agent_id: str,
        current_pct: float,
        thresholds: list[float],
        on_alert: Callable[[AlertEvent], None],
        redis_client: Redis,
        current_usd: float = 0.0,
        budget_usd: float = 0.0,
    ) -> None:
        """Check thresholds and fire alerts (once per threshold per period)."""
        if not thresholds:
            return

        alerts_key = f"agentlimit:{agent_id}:alerts_sent"
        normalized_thresholds = sorted(set(thresholds))

        try:
            for threshold in normalized_thresholds:
                if threshold <= 0 or threshold > 1:
                    raise ValueError("Alert thresholds must be between 0 and 1.")
                if current_pct < threshold:
                    continue

                threshold_key = f"{threshold:.4f}"
                is_new_alert = redis_client.sadd(alerts_key, threshold_key)
                if not is_new_alert:
                    continue

                event = AlertEvent(
                    agent_id=agent_id,
                    percent=round(current_pct * 100, 2),
                    threshold=threshold,
                    current_usd=current_usd,
                    budget_usd=budget_usd,
                )
                try:
                    on_alert(event)
                except Exception:
                    # Keep retries possible if callback fails.
                    redis_client.srem(alerts_key, threshold_key)
                    raise
        except RedisError as exc:
            raise RedisConnectionError(str(exc)) from exc
