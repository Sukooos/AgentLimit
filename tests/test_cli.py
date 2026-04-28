"""Tests for agentlimit.cli commands."""

from typer.testing import CliRunner

from agentlimit import UsageMeter
from agentlimit.cli import app

runner = CliRunner()


def _patch_redis(monkeypatch, redis_client):
    monkeypatch.setattr(
        "agentlimit.meter.Redis.from_url",
        lambda *args, **kwargs: redis_client,
    )


class TestCli:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        output = result.output.lower()
        assert "agentlimit" in output or "budget" in output

    def test_models_lists_supported_models(self):
        result = runner.invoke(app, ["models"])
        assert result.exit_code == 0
        output = result.output.lower()
        assert "openai" in output
        assert "anthropic" in output
        assert "gpt-4o" in output

    def test_status_shows_usage(self, monkeypatch, redis_client, redis_url):
        _patch_redis(monkeypatch, redis_client)
        meter = UsageMeter(
            redis_url=redis_url,
            agent_id="cli-agent",
            monthly_budget_usd=10.0,
            monthly_budget_tokens=2000,
        )
        meter.record(provider="openai", model="gpt-4o-mini", input_tokens=1000)

        result = runner.invoke(
            app,
            ["status", "--agent", "cli-agent", "--redis", redis_url],
        )
        assert result.exit_code == 0
        assert "Agent:         cli-agent" in result.output
        assert "USD Spent:" in result.output
        assert "Tokens Used:" in result.output
        assert "Status:        OK" in result.output

    def test_reset_clears_usage(self, monkeypatch, redis_client, redis_url):
        _patch_redis(monkeypatch, redis_client)
        meter = UsageMeter(
            redis_url=redis_url,
            agent_id="cli-agent",
            monthly_budget_usd=10.0,
            monthly_budget_tokens=1000,
        )
        meter.record(provider="openai", model="gpt-4o-mini", input_tokens=1000)
        prefix = "agentlimit:cli-agent:"
        assert float(redis_client.get(f"{prefix}usd_spent")) > 0

        result = runner.invoke(
            app,
            ["reset", "--agent", "cli-agent", "--redis", redis_url],
        )
        assert result.exit_code == 0
        assert "Budget reset for agent 'cli-agent'." in result.output
        assert float(redis_client.get(f"{prefix}usd_spent")) == 0.0
        assert int(redis_client.get(f"{prefix}tokens_spent")) == 0
