# AgentLimit

Budget enforcement and usage metering for AI agents.  
Self-hosted, Redis-backed, zero data leaves your infrastructure.

## Install

```bash
pip install agentlimit
```

## Local Redis for development

AgentLimit stores usage in Redis. For local testing, start Redis with Docker:

```bash
docker run --rm -p 6379:6379 redis:7
```

Use `redis://localhost:6379` in examples below.

## Quickstart (manual record)

```python
from agentlimit import BudgetExceededError, UsageMeter

meter = UsageMeter(
    redis_url="redis://localhost:6379",
    agent_id="my-agent",
    monthly_budget_usd=100.0,
    monthly_budget_tokens=500_000,
)

if not meter.can_spend(estimated_cost_usd=0.05):
    raise BudgetExceededError("Monthly budget reached")

# call your LLM here
meter.record(
    provider="openai",
    model="gpt-4o-mini",
    input_tokens=1200,
    output_tokens=500,
)
```

## End-to-end smoke test

```python
from agentlimit import UsageMeter

meter = UsageMeter(
    redis_url="redis://localhost:6379",
    agent_id="demo-agent",
    monthly_budget_usd=1.0,
)

meter.record(
    provider="openai",
    model="gpt-4o-mini",
    input_tokens=1000,
    output_tokens=500,
)

usage = meter.get_usage()
print(usage.usd_spent)
print(usage.tokens_spent)
```

Then inspect the same agent through the CLI:

```bash
agentlimit status --agent demo-agent --redis redis://localhost:6379
```

## Auto-instrument OpenAI SDK

```python
from openai import OpenAI
from agentlimit import UsageMeter

client = OpenAI()
meter = UsageMeter(
    redis_url="redis://localhost:6379",
    agent_id="support-bot",
    monthly_budget_usd=100.0,
)

meter.instrument_openai_client(client)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "hello"}],
)
# usage is recorded automatically
```

## Auto-instrument Anthropic SDK

```python
from anthropic import Anthropic
from agentlimit import UsageMeter

client = Anthropic()
meter = UsageMeter(
    redis_url="redis://localhost:6379",
    agent_id="research-bot",
    monthly_budget_usd=100.0,
)

meter.instrument_anthropic_client(client)

response = client.messages.create(
    model="claude-haiku-4",
    max_tokens=256,
    messages=[{"role": "user", "content": "hello"}],
)
# usage is recorded automatically
```

## SDK instrumentation limitations

Auto-instrumentation currently wraps:

- OpenAI: `client.chat.completions.create(...)`
- Anthropic: `client.messages.create(...)`

The wrapped SDK call must return usage metadata. AgentLimit raises a `ValueError`
if usage or model information is missing, because silently skipping metering
would break budget enforcement. If your SDK response shape differs, use manual
`meter.record(...)` with explicit token counts.

## Alert callbacks

```python
from agentlimit import AlertEvent, UsageMeter

def on_alert(event: AlertEvent) -> None:
    print(
        f"{event.agent_id} reached {event.percent}% "
        f"of its ${event.budget_usd:.2f} budget"
    )

meter = UsageMeter(
    redis_url="redis://localhost:6379",
    agent_id="support-bot",
    monthly_budget_usd=10.0,
    alert_thresholds=[0.8, 0.9, 1.0],
    on_alert=on_alert,
)
```

## CLI

```bash
agentlimit status --agent my-agent --redis redis://localhost:6379
agentlimit reset --agent my-agent --redis redis://localhost:6379
agentlimit models
```

## Pricing and enforcement notes

Built-in pricing is a convenience table for common OpenAI and Anthropic models.
Provider pricing changes over time, so production users should verify rates and
use `custom_pricing` when exact billing accuracy matters.

Redis counter updates are atomic. The pre-call `can_spend(...)` check and the
post-call `record(...)` update are not a reservation system, so highly concurrent
agents can still race between checking and recording. AgentLimit fails loudly
when Redis is unavailable or usage data is malformed instead of silently skipping
metering.
