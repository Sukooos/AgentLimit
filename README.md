# AgentLimit

Budget enforcement and usage metering for AI agents.  
Self-hosted, Redis-backed, zero data leaves your infrastructure.

## Install

```bash
pip install agentlimit
```

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

## CLI

```bash
agentlimit status --agent my-agent --redis redis://localhost:6379
agentlimit reset --agent my-agent --redis redis://localhost:6379
agentlimit models
```
