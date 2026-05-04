"""CLI commands for agentlimit."""

from __future__ import annotations

from datetime import datetime

import typer

from .exceptions import AgentLimitError
from .meter import UsageMeter
from .providers import get_supported_models

app = typer.Typer(
    name="agentlimit",
    help="Budget enforcement and usage metering for AI agents.",
)


@app.command()
def status(
    agent: str = typer.Option(..., "--agent", help="Agent ID"),
    redis: str = typer.Option("redis://localhost:6379", "--redis", help="Redis URL"),
) -> None:
    """Show current usage for an agent."""
    try:
        meter = UsageMeter(redis_url=redis, agent_id=agent)
        usage = meter.get_usage()
    except (AgentLimitError, ValueError) as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from exc

    month_label = datetime.now().strftime("%B %Y")
    typer.echo(f"Agent:         {usage.agent_id}")
    typer.echo(f"Month:         {month_label}")

    if usage.monthly_budget_usd is not None and usage.percent_usd is not None:
        typer.echo(
            "USD Spent:     "
            f"${usage.usd_spent:,.2f} / ${usage.monthly_budget_usd:,.2f} "
            f"({usage.percent_usd:.1f}%)"
        )
    else:
        typer.echo(f"USD Spent:     ${usage.usd_spent:,.2f}")

    if usage.monthly_budget_tokens is not None and usage.percent_tokens is not None:
        typer.echo(
            "Tokens Used:   "
            f"{usage.tokens_spent:,} / {usage.monthly_budget_tokens:,} "
            f"({usage.percent_tokens:.1f}%)"
        )
    else:
        typer.echo(f"Tokens Used:   {usage.tokens_spent:,}")

    status_value = "OK"
    if (usage.percent_usd is not None and usage.percent_usd >= 100) or (
        usage.percent_tokens is not None and usage.percent_tokens >= 100
    ):
        status_value = "LIMIT_REACHED"

    typer.echo(f"Status:        {status_value}")


@app.command()
def reset(
    agent: str = typer.Option(..., "--agent", help="Agent ID"),
    redis: str = typer.Option("redis://localhost:6379", "--redis", help="Redis URL"),
) -> None:
    """Manually reset budget for an agent."""
    try:
        meter = UsageMeter(redis_url=redis, agent_id=agent)
        meter.reset()
    except (AgentLimitError, ValueError) as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Budget reset for agent '{agent}'.")


@app.command()
def models() -> None:
    """List supported models and pricing."""
    pricing = get_supported_models()
    for provider, models_map in pricing.items():
        typer.echo(provider)
        for model, price in models_map.items():
            typer.echo(
                f"  {model}: input={price['input']:.10f}, output={price['output']:.10f}"
            )
