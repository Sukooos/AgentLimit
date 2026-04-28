# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

agentlimit is a self-hosted Python library for real-time AI agent usage metering and budget enforcement, backed by Redis. No SaaS, no external calls — all data stays in the developer's own Redis instance.

## Build & Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_meter.py

# Run a specific test
pytest tests/test_meter.py::test_can_spend_within_budget -v

# Coverage
pytest --cov=agentlimit --cov-report=term-missing

# Lint
ruff check agentlimit/ tests/

# CLI (after install)
agentlimit status --agent my-agent --redis redis://localhost:6379
agentlimit reset --agent my-agent --redis redis://localhost:6379
agentlimit models
```

## Architecture

**Core flow:** `UsageMeter.can_spend()` reads current spend from Redis → returns bool → developer calls LLM → `UsageMeter.record()` calculates cost via `providers.py`, atomically increments Redis counters (INCRBYFLOAT/INCRBY), checks monthly reset via `reset.py`, then triggers `AlertManager.check_and_fire()`.

**Module map:**
- `meter.py` — Orchestrator. `UsageMeter` class owns `can_spend`, `record`, `get_usage`, `reset`. All Redis reads/writes go through here.
- `providers.py` — Pricing tables (OpenAI, Anthropic) and `calculate_cost(provider, model, tokens)`. Supports `custom_pricing` override.
- `alerts.py` — `AlertManager` checks thresholds, deduplicates via Redis Set (`alerts_sent`), fires `on_alert` callback once per threshold per period.
- `reset.py` — Calendar-month reset logic. Checked on every `record()`. Clears `usd_spent`, `tokens_spent`, `alerts_sent`.
- `exceptions.py` — `BudgetExceededError`, `RedisConnectionError`, `UnknownModelError`, `InvalidBudgetError`. All inherit from `AgentLimitError`.
- `cli.py` — Typer-based CLI with `status`, `reset`, `models` commands.

**Redis key pattern:** `agentlimit:{agent_id}:usd_spent|tokens_spent|alerts_sent|last_reset`

**Design principle:** Always fail loudly. Redis unreachable = raise, never silently skip metering.

## Testing

- Use `fakeredis` for all tests — no real Redis required
- Target: 80% minimum coverage, 90%+ for `meter.py`
- Alert deduplication must be tested explicitly (threshold fires only once per period)
- Monthly reset tested with mocked timestamps

## Dependencies

Runtime: `redis>=5.0.0`, `typer>=0.12.0`
Dev: `pytest>=8.0.0`, `pytest-cov>=5.0.0`, `fakeredis>=2.0.0`, `ruff>=0.4.0`
