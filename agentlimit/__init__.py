"""agentlimit — Lightweight AI agent usage metering and budget enforcement."""

from .exceptions import (
    AgentLimitError,
    BudgetExceededError,
    InvalidBudgetError,
    RedisConnectionError,
    RedisDataError,
    UnknownModelError,
)
from .meter import UsageMeter, UsageStats
from .providers import PRICING, calculate_cost, get_supported_models

__version__ = "0.1.0"

__all__ = [
    "AgentLimitError",
    "BudgetExceededError",
    "InvalidBudgetError",
    "PRICING",
    "RedisConnectionError",
    "RedisDataError",
    "UnknownModelError",
    "UsageMeter",
    "UsageStats",
    "__version__",
    "calculate_cost",
    "get_supported_models",
]
