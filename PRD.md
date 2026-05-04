# agentlimit — Product Requirements Document (PRD)

**Version:** 1.0  
**Author:** Muhammad Raja Zahran  
**Status:** Draft  
**Last Updated:** April 2026

---

## 1. Overview

agentlimit is a lightweight, self-hosted Python library for AI agent usage metering and budget enforcement. Developers install it via pip, integrate it into their existing agent code, and connect it to their own Redis instance — no third-party SaaS, no data leaving their infrastructure.

**Problem**

AI agents running on OpenAI or Anthropic APIs can silently overspend. Most teams find out they exceeded their budget after the invoice arrives — not before. There is no lightweight, self-hosted solution for real-time budget enforcement at the agent level.

**Solution**

agentlimit provides a simple decorator and context manager that tracks token usage and USD spend per agent in Redis, checks budget before each LLM call, stops the agent when limits are hit, and sends alerts at configurable thresholds.

---

## 2. Target Users

### Primary — V1
- Backend and AI engineers building agents with OpenAI or Anthropic APIs who need cost control without signing up for a SaaS product
- Startups and indie developers running agents in production who want to prevent surprise billing
- Companies with data privacy requirements that cannot send usage data to third-party monitoring tools

### Secondary — V2+
- Teams using other LLM providers (Gemini, Mistral, Cohere)
- Platform teams managing multiple agents across departments

---

## 3. Goals & Non-Goals

### Goals
- Zero-config setup — working in under 10 lines of code
- Real-time budget enforcement, not post-hoc reporting
- Self-hosted — all data stays in the developer's own Redis
- Support both USD-based and token-based budget limits
- Built-in alert system with developer-defined callbacks
- Support OpenAI and Anthropic out of the box

### Non-Goals for V1
- Dashboard or web UI — CLI and logs only
- Multi-tenant SaaS infrastructure
- Support for non-Redis backends (in-memory, PostgreSQL, etc.)
- Agent orchestration or workflow management
- Fine-grained per-request cost breakdown

---

## 4. Feature Specification

| Feature | V1 | V2 |
|---|---|---|
| Budget tracking per agent (USD) | ✅ | — |
| Budget tracking per agent (tokens) | ✅ | — |
| Spend check before LLM call | ✅ | — |
| Auto-stop when limit reached | ✅ | — |
| Alert at 80%, 90%, 100% threshold | ✅ | — |
| Developer-defined alert callbacks | ✅ | — |
| OpenAI provider support | ✅ | — |
| Anthropic provider support | ✅ | — |
| Monthly budget reset (auto) | ✅ | — |
| CLI to inspect agent usage | ✅ | — |
| Multi-agent budget pooling | — | 🔜 |
| Gemini / Mistral support | — | 🔜 |
| Slack built-in integration | — | 🔜 |
| Web dashboard | — | 🔜 |

---

## 5. Technical Specification

### 5.1 Installation

```bash
pip install agentlimit
```

### 5.2 Core API

```python
from agentlimit import UsageMeter

meter = UsageMeter(
    redis_url="redis://localhost:6379",
    agent_id="my-agent",
    monthly_budget_usd=100.00,       # USD-based limit
    monthly_budget_tokens=500_000,   # token-based limit (optional)
)

# Check before calling LLM
if meter.can_spend(estimated_cost_usd=0.05):
    response = openai.chat.completions.create(...)
    meter.record(
        provider='openai',
        model='gpt-4o',
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens,
        tokens_used=response.usage.total_tokens
    )
else:
    raise BudgetExceededError("Monthly budget reached")
```

For exact split-priced USD accounting, callers should provide `input_tokens`
and `output_tokens`. `tokens_used` is still accepted for token-budget accounting;
when it is provided without split counts, AgentLimit conservatively prices the
total as output tokens.

### 5.3 Alert System

```python
def my_alert_handler(event):
    print(f"Agent {event.agent_id} at {event.percent}% of budget")
    # Send to Slack, email, PagerDuty — developer defines this

meter = UsageMeter(
    redis_url="redis://localhost:6379",
    agent_id="my-agent",
    monthly_budget_usd=100.00,
    alert_thresholds=[0.8, 0.9, 1.0],   # 80%, 90%, 100%
    on_alert=my_alert_handler
)
```

### 5.4 Decorator Pattern (Alternative)

```python
@meter.track(estimated_cost=0.05)
def call_llm(prompt):
    return openai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
```

### 5.5 Redis Data Structure

```
# Key pattern
agentlimit:{agent_id}:usd_spent        → float   (current month spend)
agentlimit:{agent_id}:tokens_spent     → int     (current month tokens)
agentlimit:{agent_id}:alerts_sent      → set     (thresholds already alerted)
agentlimit:{agent_id}:last_reset       → timestamp

# TTL: auto-reset at end of calendar month
```

### 5.6 Built-in Pricing Reference

agentlimit ships with a built-in pricing table for common models. Developers can override with custom pricing.

```python
PRICING = {
    "openai": {
        "gpt-4o":        {"input": 0.0000025,  "output": 0.000010},
        "gpt-4o-mini":   {"input": 0.00000015, "output": 0.0000006},
        "gpt-3.5-turbo": {"input": 0.0000005,  "output": 0.0000015},
    },
    "anthropic": {
        "claude-sonnet-4-6":          {"input": 0.000003, "output": 0.000015},
        "claude-haiku-4-5-20251001":  {"input": 0.000001, "output": 0.000005},
        "claude-haiku-4-5":           {"input": 0.000001, "output": 0.000005},
    }
}
```

### 5.7 CLI

```bash
# Check current usage for an agent
agentlimit status --agent my-agent --redis redis://localhost:6379

# Output:
# Agent:         my-agent
# Month:         April 2026
# USD Spent:     $34.21 / $100.00 (34.2%)
# Tokens Used:   182,400 / 500,000
# Status:        OK

# Manual reset
agentlimit reset --agent my-agent --redis redis://localhost:6379

# List supported models and pricing
agentlimit models
```

---

## 6. Error Handling

| Exception | When |
|---|---|
| `BudgetExceededError` | Agent tries to spend beyond limit |
| `RedisConnectionError` | Redis is unreachable — fail loudly, never silently skip |
| `UnknownModelError` | Model not in pricing table and no custom pricing provided |
| `InvalidBudgetError` | Budget values are negative or zero at init |

Design principle: **always fail loudly**. Silent failure means metering is skipped without the developer knowing.

---

## 7. Differentiators

| | agentlimit | Helicone / LangSmith |
|---|---|---|
| Hosting | Self-hosted (your Redis) | SaaS (data sent to their servers) |
| Privacy | 100% — no external calls | Usage data sent to vendor |
| Setup | `pip install`, done | Signup, API key, SDK config |
| Budget enforcement | Real-time, pre-call | Reporting only (post-hoc) |
| Cost | Free | Paid tiers |

---

## 8. Milestones & Timeline

| Timeline | Milestone | Deliverable |
|---|---|---|
| Week 1–2 | Core implementation | UsageMeter class, Redis integration, OpenAI + Anthropic pricing |
| Week 3 | Alert system + CLI | Threshold alerts, callback system, CLI status/reset/models commands |
| Week 4 | Tests + docs + publish | pytest suite, README, PyPI publish, GitHub release |

---

## 9. Success Metrics — V1

- Published to PyPI as `agentlimit`
- README with quickstart runnable in under 5 minutes
- Minimum 10 GitHub stars in first month
- Zero critical bugs reported in first 2 weeks after publish
- Test coverage minimum 80%

---

## 10. Open Questions

- Should monthly reset be calendar month or rolling 30 days?
- Should concurrent agents be able to share one budget pool in V1?
- PyPI package name: `agentlimit` or `agent-limit`?
