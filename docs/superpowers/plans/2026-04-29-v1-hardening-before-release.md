# V1 Hardening Before Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing V1 package before the first PyPI release without adding V2 features.

**Architecture:** Keep the current small package structure. Add release gates around packaging and CI, strengthen validation where bad data could lead to confusing failures, expand edge-case tests, and make README instructions runnable for first-time users. Publishing remains outside this plan.

**Tech Stack:** Python package using Hatchling, Redis/redis-py, Typer CLI, pytest, fakeredis, ruff, GitHub Actions, build, twine.

---

## File Structure

- Modify `pyproject.toml`: add PyPI project URLs, add Python 3.13 classifier, and add packaging tools to dev dependencies.
- Modify `.github/workflows/test.yml`: add Python 3.13 to CI and add package build plus metadata check steps.
- Modify `agentlimit/exceptions.py`: add `RedisDataError` for malformed Redis-stored numeric values.
- Modify `agentlimit/__init__.py`: export `RedisDataError`.
- Modify `agentlimit/meter.py`: validate decorator estimates early and wrap malformed Redis values in `RedisDataError`.
- Modify `agentlimit/providers.py`: reject malformed, negative, NaN, and infinite custom pricing rates.
- Modify `agentlimit/cli.py`: convert user-facing `ValueError` failures into clean CLI errors.
- Modify `tests/test_meter.py`: add hardening tests for validation, malformed Redis data, and async SDK wrapping.
- Modify `tests/test_providers.py`: add custom pricing validation tests.
- Modify `tests/test_cli.py`: add CLI validation error tests.
- Modify `README.md`: add runnable local Redis quickstart, alert callback example, pricing notes, SDK instrumentation limitations, and release-state caveats.
- Create `docs/RELEASE_CHECKLIST.md`: document the hardening and release-prep gates.

---

### Task 1: Packaging Metadata And CI Build Gate

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Update package metadata and dev tooling**

In `pyproject.toml`, add project URLs after the `authors` block:

```toml
[project.urls]
Homepage = "https://github.com/Sukooos/AgentLimit"
Repository = "https://github.com/Sukooos/AgentLimit"
Issues = "https://github.com/Sukooos/AgentLimit/issues"
```

Add the Python 3.13 classifier in the existing `classifiers` list:

```toml
    "Programming Language :: Python :: 3.13",
```

Add build tools to `[project.optional-dependencies].dev`:

```toml
    "build>=1.2.0",
    "twine>=5.0.0",
```

- [ ] **Step 2: Add build and metadata checks to CI**

In `.github/workflows/test.yml`, change the matrix to:

```yaml
        python-version: ["3.10", "3.11", "3.12", "3.13"]
```

After the `Test` step, add:

```yaml
      - name: Build package
        run: python -m build

      - name: Check package metadata
        run: python -m twine check dist/*
```

- [ ] **Step 3: Run package build check locally**

Run:

```powershell
.\venv\Scripts\python.exe -m build
.\venv\Scripts\python.exe -m twine check dist/*
```

Expected:

```text
Successfully built agentlimit-0.1.0.tar.gz and agentlimit-0.1.0-py3-none-any.whl
PASSED
```

If `build` or `twine` is missing, run:

```powershell
.\venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Then rerun the build and twine commands.

- [ ] **Step 4: Run CI-equivalent local checks**

Run:

```powershell
.\venv\Scripts\python.exe -m ruff check agentlimit tests
.\venv\Scripts\python.exe -m pytest
```

Expected:

```text
All checks passed!
27 passed
```

The exact pytest duration can differ.

- [ ] **Step 5: Commit packaging gate**

Run:

```powershell
git add pyproject.toml .github\workflows\test.yml
git commit -m "chore: add package build gate"
```

---

### Task 2: API And Redis Data Hardening

**Files:**
- Modify: `agentlimit/exceptions.py`
- Modify: `agentlimit/__init__.py`
- Modify: `agentlimit/meter.py`
- Test: `tests/test_meter.py`

- [ ] **Step 1: Write failing tests for API validation and malformed Redis data**

In `tests/test_meter.py`, change the import to:

```python
from agentlimit import BudgetExceededError, InvalidBudgetError, RedisDataError, UsageMeter
```

Add these tests to `TestUsageMeterInit`:

```python
    def test_rejects_empty_agent_id(self, monkeypatch, redis_client, redis_url):
        monkeypatch.setattr(
            "agentlimit.meter.Redis.from_url",
            lambda *args, **kwargs: redis_client,
        )

        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            UsageMeter(redis_url=redis_url, agent_id="   ")

    def test_malformed_stored_budget_raises_data_error(
        self,
        monkeypatch,
        redis_client,
        redis_url,
    ):
        monkeypatch.setattr(
            "agentlimit.meter.Redis.from_url",
            lambda *args, **kwargs: redis_client,
        )
        redis_client.set("agentlimit:agent-b:monthly_budget_usd", "not-a-number")

        with pytest.raises(RedisDataError, match="monthly_budget_usd"):
            UsageMeter(redis_url=redis_url, agent_id="agent-b")
```

Add these tests to `TestUsageMeterCore`:

```python
    def test_can_spend_rejects_negative_estimate(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)

        with pytest.raises(ValueError, match="estimated_cost_usd cannot be negative"):
            meter.can_spend(-0.01)

    def test_track_rejects_negative_estimated_cost(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)

        with pytest.raises(ValueError, match="estimated_cost cannot be negative"):
            meter.track(estimated_cost=-0.01)

    def test_record_rejects_negative_tokens(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)

        with pytest.raises(ValueError, match="Token counts cannot be negative"):
            meter.record(
                provider="openai",
                model="gpt-4o-mini",
                input_tokens=-1,
            )

    def test_malformed_usage_value_raises_data_error(
        self,
        meter_factory,
        redis_client,
    ):
        meter = meter_factory(monthly_budget_usd=10.0)
        redis_client.set("agentlimit:agent-a:usd_spent", "not-a-number")

        with pytest.raises(RedisDataError, match="usd_spent"):
            meter.get_usage()

    def test_malformed_last_reset_raises_data_error(
        self,
        meter_factory,
        redis_client,
    ):
        meter = meter_factory(monthly_budget_usd=10.0)
        redis_client.set("agentlimit:agent-a:last_reset", "not-a-timestamp")

        with pytest.raises(RedisDataError, match="last_reset"):
            meter.get_usage()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_meter.py -v
```

Expected before implementation:

```text
FAILED tests/test_meter.py::TestUsageMeterInit::test_malformed_stored_budget_raises_data_error
FAILED tests/test_meter.py::TestUsageMeterCore::test_track_rejects_negative_estimated_cost
FAILED tests/test_meter.py::TestUsageMeterCore::test_malformed_usage_value_raises_data_error
FAILED tests/test_meter.py::TestUsageMeterCore::test_malformed_last_reset_raises_data_error
```

- [ ] **Step 3: Add `RedisDataError`**

In `agentlimit/exceptions.py`, add after `RedisConnectionError`:

```python
class RedisDataError(AgentLimitError):
    """Raised when stored Redis data cannot be parsed."""
```

In `agentlimit/__init__.py`, import it:

```python
    RedisDataError,
```

Add it to `__all__`:

```python
    "RedisDataError",
```

- [ ] **Step 4: Harden parsing and decorator validation**

In `agentlimit/meter.py`, change the exceptions import to:

```python
from .exceptions import (
    BudgetExceededError,
    InvalidBudgetError,
    RedisConnectionError,
    RedisDataError,
)
```

In `UsageMeter.__init__`, replace the stored budget parsing blocks with:

```python
            if monthly_budget_usd is None:
                stored_usd = self._redis.get(self._monthly_budget_usd_key)
                monthly_budget_usd = (
                    self._parse_float_value(stored_usd, "monthly_budget_usd")
                    if stored_usd is not None
                    else None
                )
            if monthly_budget_tokens is None:
                stored_tokens = self._redis.get(self._monthly_budget_tokens_key)
                monthly_budget_tokens = (
                    self._parse_int_value(stored_tokens, "monthly_budget_tokens")
                    if stored_tokens is not None
                    else None
                )
```

At the start of `track`, add:

```python
        if estimated_cost < 0:
            raise ValueError("estimated_cost cannot be negative.")
```

In `_maybe_auto_reset`, replace `if should_reset(float(raw)):` with:

```python
            if should_reset(self._parse_float_value(raw, "last_reset")):
```

Replace `_read_float` and `_read_int` with:

```python
    def _read_float(self, key: str) -> float:
        try:
            raw = self._redis.get(key)
        except RedisError as exc:
            raise RedisConnectionError(str(exc)) from exc
        if raw is None:
            return 0.0
        field_name = key.rsplit(":", maxsplit=1)[-1]
        return self._parse_float_value(raw, field_name)

    def _read_int(self, key: str) -> int:
        try:
            raw = self._redis.get(key)
        except RedisError as exc:
            raise RedisConnectionError(str(exc)) from exc
        if raw is None:
            return 0
        field_name = key.rsplit(":", maxsplit=1)[-1]
        return self._parse_int_value(raw, field_name)
```

Add these static helpers before `_read_attr`:

```python
    @staticmethod
    def _parse_float_value(raw_value: object, field_name: str) -> float:
        try:
            return float(raw_value)
        except (TypeError, ValueError) as exc:
            raise RedisDataError(
                f"Invalid numeric value for {field_name}: {raw_value}"
            ) from exc

    @staticmethod
    def _parse_int_value(raw_value: object, field_name: str) -> int:
        try:
            return int(float(raw_value))
        except (TypeError, ValueError) as exc:
            raise RedisDataError(
                f"Invalid integer value for {field_name}: {raw_value}"
            ) from exc
```

- [ ] **Step 5: Run meter tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_meter.py -v
```

Expected:

```text
19 passed
```

The exact count can be higher if more meter tests are added during execution.

- [ ] **Step 6: Run lint**

Run:

```powershell
.\venv\Scripts\python.exe -m ruff check agentlimit tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 7: Commit API and Redis hardening**

Run:

```powershell
git add agentlimit\exceptions.py agentlimit\__init__.py agentlimit\meter.py tests\test_meter.py
git commit -m "fix: harden usage meter validation"
```

---

### Task 3: Provider Pricing And CLI Error Hardening

**Files:**
- Modify: `agentlimit/providers.py`
- Modify: `agentlimit/cli.py`
- Test: `tests/test_providers.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for custom pricing validation**

In `tests/test_providers.py`, add these tests to `TestProviders`:

```python
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
```

- [ ] **Step 2: Write failing tests for clean CLI validation errors**

In `tests/test_cli.py`, add these tests to `TestCli`:

```python
    def test_status_shows_clean_error_for_empty_agent(self):
        result = runner.invoke(app, ["status", "--agent", ""])

        assert result.exit_code == 1
        assert "Error: agent_id cannot be empty." in result.output

    def test_reset_shows_clean_error_for_empty_agent(self):
        result = runner.invoke(app, ["reset", "--agent", ""])

        assert result.exit_code == 1
        assert "Error: agent_id cannot be empty." in result.output
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_providers.py tests\test_cli.py -v
```

Expected before implementation:

```text
FAILED tests/test_providers.py::TestProviders::test_custom_pricing_rejects_negative_rates
FAILED tests/test_providers.py::TestProviders::test_custom_pricing_rejects_non_numeric_rates
FAILED tests/test_cli.py::TestCli::test_status_shows_clean_error_for_empty_agent
FAILED tests/test_cli.py::TestCli::test_reset_shows_clean_error_for_empty_agent
```

- [ ] **Step 4: Harden custom pricing parsing**

In `agentlimit/providers.py`, add this import:

```python
from math import isfinite
```

Add this helper above `_build_pricing`:

```python
def _coerce_rate(provider: str, model: str, token_type: str, raw_rate: object) -> float:
    try:
        rate = float(raw_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid pricing rate for {provider}/{model} {token_type}: {raw_rate}"
        ) from exc

    if not isfinite(rate) or rate < 0:
        raise ValueError(
            f"Pricing rate for {provider}/{model} {token_type} "
            "must be finite and non-negative."
        )
    return rate
```

In `_build_pricing`, replace the assignment with:

```python
            provider_models[model] = {
                "input": _coerce_rate(provider, model, "input", rates["input"]),
                "output": _coerce_rate(provider, model, "output", rates["output"]),
            }
```

- [ ] **Step 5: Harden CLI exception handling**

In `agentlimit/cli.py`, change both command exception handlers from:

```python
    except AgentLimitError as exc:
```

to:

```python
    except (AgentLimitError, ValueError) as exc:
```

- [ ] **Step 6: Run provider and CLI tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_providers.py tests\test_cli.py -v
```

Expected:

```text
15 passed
```

The exact count can be higher if more provider or CLI tests are added during execution.

- [ ] **Step 7: Run lint**

Run:

```powershell
.\venv\Scripts\python.exe -m ruff check agentlimit tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 8: Commit provider and CLI hardening**

Run:

```powershell
git add agentlimit\providers.py agentlimit\cli.py tests\test_providers.py tests\test_cli.py
git commit -m "fix: harden pricing and cli errors"
```

---

### Task 4: SDK Instrumentation Coverage

**Files:**
- Modify: `tests/test_meter.py`
- Modify: `README.md`

- [ ] **Step 1: Add async and missing-path instrumentation tests**

In `tests/test_meter.py`, add this import:

```python
import asyncio
```

Add this test client after `_OpenAIClient`:

```python
class _AsyncOpenAIClient:
    def __init__(self, response):
        self._response = response
        self.chat = _Obj(completions=_Obj(create=self._create))

    async def _create(self, *args, **kwargs):
        return self._response
```

Add these tests to `TestSdkInstrumentation`:

```python
    def test_async_openai_instrumentation_records_usage(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0, monthly_budget_tokens=5000)
        response = _Obj(
            model="gpt-4o-mini",
            usage=_Obj(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
        )
        client = _AsyncOpenAIClient(response)

        meter.instrument_openai_client(client)
        asyncio.run(client.chat.completions.create(model="gpt-4o-mini", messages=[]))

        usage = meter.get_usage()
        assert usage.tokens_spent == 1500
        assert usage.usd_spent == pytest.approx(0.00045)

    def test_openai_instrumentation_rejects_missing_path(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)

        with pytest.raises(ValueError, match="OpenAI client missing chat.completions"):
            meter.instrument_openai_client(_Obj())

    def test_anthropic_instrumentation_rejects_missing_path(self, meter_factory):
        meter = meter_factory(monthly_budget_usd=10.0)

        with pytest.raises(ValueError, match="Anthropic client missing messages"):
            meter.instrument_anthropic_client(_Obj())
```

- [ ] **Step 2: Run SDK instrumentation tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_meter.py::TestSdkInstrumentation -v
```

Expected:

```text
7 passed
```

The exact count can be higher if more SDK instrumentation tests are added during execution.

- [ ] **Step 3: Document SDK instrumentation limitations**

In `README.md`, add this section after the Anthropic auto-instrumentation example:

```markdown
## SDK instrumentation limitations

Auto-instrumentation currently wraps:

- OpenAI: `client.chat.completions.create(...)`
- Anthropic: `client.messages.create(...)`

The wrapped SDK call must return usage metadata. AgentLimit raises a `ValueError`
if usage or model information is missing, because silently skipping metering
would break budget enforcement. If your SDK response shape differs, use manual
`meter.record(...)` with explicit token counts.
```

- [ ] **Step 4: Run docs-adjacent checks**

Run:

```powershell
.\venv\Scripts\python.exe -m ruff check agentlimit tests
.\venv\Scripts\python.exe -m pytest tests\test_meter.py -v
```

Expected:

```text
All checks passed!
22 passed
```

The exact pytest count can be higher after earlier tasks.

- [ ] **Step 5: Commit SDK coverage and documentation**

Run:

```powershell
git add tests\test_meter.py README.md
git commit -m "test: cover sdk instrumentation edges"
```

---

### Task 5: README Quickstart And Release Checklist

**Files:**
- Modify: `README.md`
- Create: `docs/RELEASE_CHECKLIST.md`

- [ ] **Step 1: Add local Redis setup to README**

In `README.md`, add this section before `## Quickstart (manual record)`:

````markdown
## Local Redis for development

AgentLimit stores usage in Redis. For local testing, start Redis with Docker:

```bash
docker run --rm -p 6379:6379 redis:7
```

Use `redis://localhost:6379` in examples below.
````

- [ ] **Step 2: Add an end-to-end smoke test to README**

In `README.md`, add this section after the manual record quickstart:

````markdown
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
````

- [ ] **Step 3: Add alert callback example to README**

In `README.md`, add this section before `## CLI`:

````markdown
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
````

- [ ] **Step 4: Add pricing and concurrency notes to README**

In `README.md`, add this section after `## CLI`:

```markdown
## Pricing and enforcement notes

Built-in pricing is a convenience table for common OpenAI and Anthropic models.
Provider pricing changes over time, so production users should verify rates and
use `custom_pricing` when exact billing accuracy matters.

Redis counter updates are atomic. The pre-call `can_spend(...)` check and the
post-call `record(...)` update are not a reservation system, so highly concurrent
agents can still race between checking and recording. AgentLimit fails loudly
when Redis is unavailable or usage data is malformed instead of silently skipping
metering.
```

- [ ] **Step 5: Add release checklist**

Create `docs/RELEASE_CHECKLIST.md`:

```markdown
# Release Checklist

Use this checklist before publishing `v0.1.0`.

## Hardening Gate

- `.\venv\Scripts\python.exe -m ruff check agentlimit tests` passes.
- `.\venv\Scripts\python.exe -m pytest` passes.
- `.\venv\Scripts\python.exe -m build` creates wheel and source distribution.
- `.\venv\Scripts\python.exe -m twine check dist/*` passes.
- GitHub Actions `Tests` workflow passes on `main`.
- README includes local Redis setup, quickstart, CLI usage, alert callbacks, SDK limitations, pricing notes, and concurrency notes.
- Known V1 limitations are documented before release.

## Release Preparation Gate

- Publish to TestPyPI.
- Install from TestPyPI in a clean virtual environment.
- Run an import smoke test from the TestPyPI install.
- Publish to PyPI.
- Create git tag `v0.1.0`.
- Create GitHub release notes summarizing V1 scope and limitations.
```

- [ ] **Step 6: Run documentation sanity checks**

Run:

```powershell
rg -n "Local Redis|End-to-end smoke test|Alert callbacks|Pricing and enforcement notes|SDK instrumentation limitations" README.md
rg -n "Hardening Gate|Release Preparation Gate" docs\RELEASE_CHECKLIST.md
```

Expected:

```text
README.md contains all five section names.
docs\RELEASE_CHECKLIST.md contains both gate names.
```

- [ ] **Step 7: Commit docs hardening**

Run:

```powershell
git add README.md docs\RELEASE_CHECKLIST.md
git commit -m "docs: harden release readiness docs"
```

---

### Task 6: Final Hardening Verification

**Files:**
- Read: `agentlimit/*.py`
- Read: `tests/*.py`
- Read: `README.md`
- Read: `docs/RELEASE_CHECKLIST.md`
- Read: `.github/workflows/test.yml`

- [ ] **Step 1: Run full lint**

Run:

```powershell
.\venv\Scripts\python.exe -m ruff check agentlimit tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 2: Run full tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest
```

Expected:

```text
passed
```

There must be zero failures and zero errors. Cache permission warnings are acceptable only if they do not affect test results.

- [ ] **Step 3: Run package build and metadata check**

Run:

```powershell
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
.\venv\Scripts\python.exe -m build
.\venv\Scripts\python.exe -m twine check dist/*
```

Expected:

```text
Successfully built agentlimit-0.1.0.tar.gz and agentlimit-0.1.0-py3-none-any.whl
PASSED
```

- [ ] **Step 4: Verify git history is split by concern**

Run:

```powershell
git log --oneline --max-count=8
git status -sb
```

Expected:

```text
Recent commits include package build gate, usage meter validation, pricing/CLI errors, SDK instrumentation coverage, and release readiness docs.
Working tree is clean.
```

- [ ] **Step 5: Push the hardening branch or main**

If working directly on `main`, run:

```powershell
git push
```

Expected:

```text
main -> main
```

If implementation is done on a feature branch, push that branch and open a PR instead.

- [ ] **Step 6: Check GitHub Actions**

Run:

```powershell
gh run list --limit 3
```

Expected:

```text
The newest Tests workflow for the pushed commit completes with success.
```

If the newest workflow is still running, wait and re-check:

```powershell
gh run watch
```

- [ ] **Step 7: Mark release preparation as the next work item**

Do not publish to TestPyPI or PyPI in this plan. After CI is green, start a new release-preparation plan covering:

```text
TestPyPI publish
clean install smoke test
PyPI publish
git tag v0.1.0
GitHub release notes
```

---

## Self-Review

- Spec coverage: API hardening is covered by Tasks 2, 3, and 4. Redis correctness is covered by Task 2. Packaging readiness is covered by Tasks 1 and 6. Documentation hardening is covered by Tasks 4 and 5. Test and CI hardening is covered by Tasks 1 through 6. Release publishing remains out of scope.
- Placeholder scan: the plan contains concrete file paths, commands, expected outputs, and code snippets for every code-changing task.
- Type consistency: new public exception is named `RedisDataError` in tests, exports, and implementation. Existing public method names remain unchanged. New helper names are `_parse_float_value`, `_parse_int_value`, and `_coerce_rate`.
