"""Monthly budget reset logic."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from redis import Redis


def should_reset(last_reset_ts: float) -> bool:
    """Check if a reset is needed based on calendar month boundary."""
    if last_reset_ts <= 0:
        return True

    try:
        last_reset = datetime.fromtimestamp(last_reset_ts, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return True

    now = datetime.now(timezone.utc)
    return (last_reset.year, last_reset.month) != (now.year, now.month)


def perform_reset(agent_id: str, redis_client: Redis) -> None:
    """Reset usd_spent, tokens_spent, alerts_sent and update last_reset timestamp."""
    prefix = f"agentlimit:{agent_id}:"
    pipe = redis_client.pipeline()
    pipe.set(f"{prefix}usd_spent", 0.0)
    pipe.set(f"{prefix}tokens_spent", 0)
    pipe.delete(f"{prefix}alerts_sent")
    pipe.set(f"{prefix}last_reset", time.time())
    pipe.execute()
