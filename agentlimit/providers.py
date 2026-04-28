"""Provider pricing tables and cost calculation."""

from __future__ import annotations

from copy import deepcopy

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


def _build_pricing(
    custom_pricing: dict | None,
) -> dict[str, dict[str, dict[str, float]]]:
    pricing = deepcopy(PRICING)
    if not custom_pricing:
        return pricing

    for provider, models in custom_pricing.items():
        provider_models = pricing.setdefault(provider, {})
        for model, rates in models.items():
            if "input" not in rates or "output" not in rates:
                raise ValueError(
                    "Invalid pricing for "
                    f"{provider}/{model}; expected input and output."
                )
            provider_models[model] = {
                "input": float(rates["input"]),
                "output": float(rates["output"]),
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
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts cannot be negative.")

    pricing = _build_pricing(custom_pricing)
    if provider not in pricing:
        raise UnknownModelError(f"Unknown provider: {provider}")
    if model not in pricing[provider]:
        raise UnknownModelError(f"Unknown model '{model}' for provider '{provider}'")

    model_pricing = pricing[provider][model]
    return (input_tokens * model_pricing["input"]) + (
        output_tokens * model_pricing["output"]
    )


def get_supported_models() -> dict[str, dict[str, dict[str, float]]]:
    """Return the full pricing table."""
    return deepcopy(PRICING)
