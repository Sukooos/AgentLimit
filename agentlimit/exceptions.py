"""Custom exceptions for agentlimit."""


class AgentLimitError(Exception):
    """Base exception for all agentlimit errors."""


class BudgetExceededError(AgentLimitError):
    """Raised when an agent tries to spend beyond its budget limit."""


class RedisConnectionError(AgentLimitError):
    """Raised when Redis is unreachable."""


class UnknownModelError(AgentLimitError):
    """Raised when a model is not in the pricing table."""


class InvalidBudgetError(AgentLimitError):
    """Raised when budget values are negative or zero at init."""
