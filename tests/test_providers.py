"""Tests for agentlimit.providers pricing and cost calculation."""

import pytest

from agentlimit import UnknownModelError
from agentlimit.providers import PRICING, calculate_cost, get_supported_models


class TestProviders:
    def test_pricing_table_has_openai(self):
        assert "openai" in PRICING

    def test_pricing_table_has_anthropic(self):
        assert "anthropic" in PRICING

    @pytest.mark.parametrize(
        ("model", "input_rate", "output_rate"),
        [
            ("claude-sonnet-4-6", 0.000003, 0.000015),
            ("claude-haiku-4-5-20251001", 0.000001, 0.000005),
            ("claude-haiku-4-5", 0.000001, 0.000005),
        ],
    )
    def test_anthropic_pricing_uses_current_model_ids(
        self,
        model,
        input_rate,
        output_rate,
    ):
        assert PRICING["anthropic"][model] == {
            "input": input_rate,
            "output": output_rate,
        }

    def test_calculate_cost_uses_input_and_output_prices(self):
        cost = calculate_cost(
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
        )
        assert cost == pytest.approx(0.00045)

    def test_calculate_cost_with_custom_pricing_override(self):
        custom_pricing = {"openai": {"gpt-4o-mini": {"input": 1.0, "output": 2.0}}}
        cost = calculate_cost(
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=2,
            output_tokens=3,
            custom_pricing=custom_pricing,
        )
        assert cost == pytest.approx(8.0)

    def test_calculate_cost_accepts_integer_numeric_string_token_counts(self):
        cost = calculate_cost(
            provider="openai",
            model="gpt-4o-mini",
            input_tokens="1000",
            output_tokens="500",
        )
        assert cost == pytest.approx(0.00045)

    @pytest.mark.parametrize(
        "bad_tokens",
        [float("nan"), float("inf"), 1.5, -1, True, None, "ten"],
    )
    def test_calculate_cost_rejects_invalid_input_token_counts(self, bad_tokens):
        with pytest.raises(ValueError, match="Token counts"):
            calculate_cost(
                provider="openai",
                model="gpt-4o-mini",
                input_tokens=bad_tokens,
            )

    @pytest.mark.parametrize(
        "bad_tokens",
        [float("nan"), float("inf"), 1.5, -1, True, None, "ten"],
    )
    def test_calculate_cost_rejects_invalid_output_token_counts(self, bad_tokens):
        with pytest.raises(ValueError, match="Token counts"):
            calculate_cost(
                provider="openai",
                model="gpt-4o-mini",
                output_tokens=bad_tokens,
            )

    def test_custom_pricing_requires_input_and_output_rates(self):
        with pytest.raises(ValueError, match="expected input and output"):
            calculate_cost(
                provider="test",
                model="model-a",
                input_tokens=1,
                custom_pricing={"test": {"model-a": {"input": 1.0}}},
            )

    def test_custom_pricing_rejects_negative_rates(self):
        with pytest.raises(ValueError, match="must be finite and non-negative"):
            calculate_cost(
                provider="test",
                model="model-a",
                input_tokens=1,
                custom_pricing={
                    "test": {"model-a": {"input": -1.0, "output": 0.0}}
                },
            )

    def test_custom_pricing_rejects_non_numeric_rates(self):
        with pytest.raises(ValueError, match="Invalid pricing rate"):
            calculate_cost(
                provider="test",
                model="model-a",
                input_tokens=1,
                custom_pricing={
                    "test": {"model-a": {"input": "cheap", "output": 0.0}}
                },
            )

    @pytest.mark.parametrize(
        "custom_pricing",
        [
            {"test": None},
            {"test": {"model-a": None}},
            {"test": {"model-a": []}},
        ],
    )
    def test_custom_pricing_rejects_malformed_shapes(self, custom_pricing):
        with pytest.raises(ValueError, match="Invalid pricing"):
            calculate_cost(
                provider="test",
                model="model-a",
                input_tokens=1,
                custom_pricing=custom_pricing,
            )

    @pytest.mark.parametrize(
        "bad_rate",
        [True, False, float("nan"), float("inf")],
    )
    def test_custom_pricing_rejects_invalid_rates_with_context(self, bad_rate):
        with pytest.raises(ValueError, match="[Pp]ricing rate"):
            calculate_cost(
                provider="test",
                model="model-a",
                input_tokens=1,
                custom_pricing={
                    "test": {"model-a": {"input": bad_rate, "output": 0.0}}
                },
            )

    def test_calculate_cost_raises_for_unknown_model(self):
        with pytest.raises(UnknownModelError):
            calculate_cost(
                provider="openai",
                model="does-not-exist",
                input_tokens=10,
                output_tokens=10,
            )

    def test_get_supported_models_returns_copy(self):
        models = get_supported_models()
        models["openai"]["gpt-4o"]["input"] = 999.0
        assert PRICING["openai"]["gpt-4o"]["input"] != 999.0
