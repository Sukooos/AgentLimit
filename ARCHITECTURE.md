# agentlimit — Architecture Document

## Overview

agentlimit is a Python library for real-time AI agent usage metering and budget enforcement.
It is designed to be lightweight, self-hosted, and zero-dependency beyond Redis and redis-py.

All usage data stays in the developer's own Redis instance.
No external calls. No SaaS. No signup.

---

## Repository Structure

```
agentlimit/
├── agentlimit/
│   ├── __init__.py           # Public API exports
│   ├── meter.py              # Core UsageMeter class
│   ├── providers.py          # Provider pricing tables (OpenAI, Anthropic)
│   ├── alerts.py             # Alert system and threshold management
│   ├── exceptions.py         # Custom exceptions
│   ├── reset.py              # Monthly budget reset logic
│   └── cli.py                # CLI commands (agentlimit status, reset)
├── tests/
│   ├── conftest.py           # Shared fixtures (fake Redis, mock providers)
│   ├── test_meter.py         # UsageMeter unit tests
│   ├── test_alerts.py        # Alert threshold tests
│   ├── test_providers.py     # Pricing calculation tests
│   ├── test_reset.py         # Monthly reset tests
│   └── test_cli.py           # CLI integration tests
├── docs/
│   ├── PRD.md                # Product Requirements Document
│   ├── ARCHITECTURE.md       # This file
│   └── CHANGELOG.md          # Version history
├── pyproject.toml            # Package config, dependencies, build
├── README.md                 # Quickstart, usage examples, install
└── .github/
    └── workflows/
        └── test.yml          # CI — run pytest on push
```

---

## Module Responsibilities

### `meter.py` — Core
The main class developers interact with. Owns all orchestration logic.

Responsibilities:
- Initialize connection to Redis
- Validate budget config on init
- Check if agent can spend before LLM call (`can_spend`)
- Record actual usage after LLM call (`record`)
- Trigger alert checks after each record
- Expose current usage stats (`get_usage`)
- Handle monthly reset via `reset.py`

```python
class UsageMeter:
    def __init__(
        self,
        redis_url: str,
        agent_id: str,
        monthly_budget_usd: float | None = None,
        monthly_budget_tokens: int | None = None,
        alert_thresholds: list[float] = [0.8, 0.9, 1.0],
        on_alert: Callable | None = None,
    ): ...

    def can_spend(self, estimated_cost_usd: float) -> bool: ...
    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        tokens_used: int = 0,
    ) -> None: ...
    def get_usage(self) -> UsageStats: ...
    def reset(self) -> None: ...
```

---

### `providers.py` — Pricing
Stores token pricing per model per provider.
Converts tokens → USD based on input/output token counts.

```python
PRICING = {
    "openai": {
        "gpt-4o":        {"input": 0.0000025, "output": 0.000010},
        "gpt-4o-mini":   {"input": 0.00000015, "output": 0.0000006},
    },
    "anthropic": {
        "claude-sonnet-4-6":         {"input": 0.000003, "output": 0.000015},
        "claude-haiku-4-5-20251001": {"input": 0.000001, "output": 0.000005},
        "claude-haiku-4-5":          {"input": 0.000001, "output": 0.000005},
    }
}

def calculate_cost(
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> float: ...
def get_supported_models() -> dict: ...
```

Developers can pass `custom_pricing` dict to override or extend.
For exact split-priced USD accounting, callers pass input and output token
counts. Total-only `tokens_used` is retained for token budgets and is priced
conservatively as output tokens when no split counts are available.

---

### `alerts.py` — Alert System
Manages threshold checks and alert deduplication.
Ensures each threshold fires only once per budget period.

```python
class AlertManager:
    def check_and_fire(
        self,
        agent_id: str,
        current_pct: float,
        thresholds: list[float],
        on_alert: Callable,
        redis_client: Redis,
    ) -> None: ...
```

Alert deduplication is Redis-backed:
- Key: `agentlimit:{agent_id}:alerts_sent`
- Type: Redis Set
- Contains: thresholds already fired this period (e.g. "0.8", "0.9")
- Reset: cleared on monthly budget reset

---

### `exceptions.py` — Custom Exceptions

```python
class AgentLimitError(Exception): ...          # Base exception
class BudgetExceededError(AgentLimitError): ... # Budget is 100% used
class RedisConnectionError(AgentLimitError): ... # Cannot reach Redis
class UnknownModelError(AgentLimitError): ...    # Model not in pricing table
class InvalidBudgetError(AgentLimitError): ...   # Budget <= 0 or invalid config
```

Design principle: always fail loudly.
If Redis is unreachable, raise — do not silently skip metering.

---

### `reset.py` — Monthly Reset
Handles automatic budget reset at the start of each calendar month.

Logic:
- On each `record()` call, check `agentlimit:{agent_id}:last_reset` in Redis
- If last reset was in a previous calendar month → trigger reset
- Reset clears: `usd_spent`, `token_spent`, `alerts_sent`
- Updates `last_reset` to current timestamp

```python
def should_reset(last_reset_ts: float) -> bool: ...
def perform_reset(agent_id: str, redis_client: Redis) -> None: ...
```

---

### `cli.py` — CLI
Built with Typer. Single entrypoint: `agentlimit`

Commands:
```
agentlimit status   --agent <id> --redis <url>   # Show current usage
agentlimit reset    --agent <id> --redis <url>   # Manual reset
agentlimit models                                # List supported models + pricing
```

---

## Redis Data Structure

All keys are namespaced under `agentlimit:{agent_id}:*`

```
agentlimit:{agent_id}:usd_spent       → float   Current month USD spend
agentlimit:{agent_id}:tokens_spent    → int     Current month token count
agentlimit:{agent_id}:alerts_sent     → set     Thresholds already fired
agentlimit:{agent_id}:last_reset      → float   Unix timestamp of last reset
```

No TTL set on keys — reset is managed by the library, not Redis expiry.
This gives full control over reset timing (calendar month vs rolling 30 days).

---

## Data Flow

### Happy path — agent within budget

```
Developer calls can_spend(estimated_cost=0.05)
    → meter reads usd_spent from Redis
    → usd_spent + 0.05 < monthly_budget_usd
    → returns True

Developer calls LLM API
    → gets response with token usage

Developer calls record(provider, model, input_tokens, output_tokens, tokens_used)
    → meter calculates actual cost via providers.py
    → meter checks last_reset → no reset needed
    → meter increments usd_spent and tokens_spent in one Redis transaction
    → meter calls alert_manager.check_and_fire()
    → no threshold crossed → no alert
```

### Budget exceeded path

```
Developer calls can_spend(estimated_cost=0.05)
    → usd_spent + 0.05 >= monthly_budget_usd
    → returns False

Developer checks return value → skips LLM call
    OR
Developer ignores return value → calls record() anyway
    → record() raises BudgetExceededError
```

### Alert fired path

```
Developer calls record(...)
    → usd_spent now at 82% of budget
    → alert_manager checks: 0.8 threshold not yet in alerts_sent set
    → fires on_alert callback with event object
    → adds "0.8" to alerts_sent set in Redis
    → next record() at 84% → 0.8 already in set → no re-fire
```

---

## Design Decisions

### Why Redis and not in-memory?
In-memory state is lost on process restart. Agents often run across multiple
processes or restarts. Redis gives persistent, atomic counters that survive restarts.

### Why a Redis transaction for usage counters?
`record(...)` updates USD and token counters together in one Redis transaction,
so a connection failure during execution does not leave a partially recorded
call. The budget check remains separate from the post-call record step.

### Why fail loudly on Redis connection error?
Silent failure would mean metering is skipped without the developer knowing.
An agent could blow through its entire budget with no tracking.
Loud failure forces developers to handle Redis availability explicitly.

### Why calendar month reset and not rolling 30 days?
Aligns with how LLM providers bill (calendar month).
Makes it easy for developers to correlate agentlimit usage with their OpenAI/Anthropic invoices.

### Why Typer for CLI and not Click or argparse?
Typer generates clean help text automatically and integrates well with type hints.
Less boilerplate than Click for a small CLI like this.

---

## Dependencies

```toml
[project]
dependencies = [
    "redis>=5.0.0",
    "typer>=0.12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
    "fakeredis>=2.0.0",   # For testing without real Redis
    "ruff>=0.4.0",        # Linting
]
```

---

## Testing Strategy

- Use `fakeredis` for all unit tests — no real Redis needed in CI
- Every public method on UsageMeter has unit tests
- Alert deduplication tested explicitly — ensure threshold only fires once
- Monthly reset tested with mocked timestamps
- CLI tested via Typer's test client

Target coverage: 80% minimum, 90%+ for core meter.py

---

## V1 Constraints (Explicitly Out of Scope)

- No web dashboard
- No multi-tenant support
- No database backend alternative to Redis
- No built-in Slack/email integration (developer defines callback)
- No streaming token counting (developer passes final token count)
- No per-request cost breakdown (only cumulative tracking)

---

## Future — V2 Considerations

- Multi-agent budget pooling (shared budget across agent fleet)
- Streaming support (estimate cost mid-stream)
- Additional providers: Gemini, Mistral, Cohere
- Built-in alert integrations: Slack webhook, email
- Web dashboard (read-only, connects to same Redis)
