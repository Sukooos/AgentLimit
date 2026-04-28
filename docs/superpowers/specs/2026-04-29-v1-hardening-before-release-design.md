# V1 Hardening Before Release Design

Date: 2026-04-29
Status: Proposed

## Context

AgentLimit already has the first V1 implementation on `main`: the Redis-backed
`UsageMeter`, provider pricing, alert thresholds, monthly reset, CLI commands,
tests, CI, and product documentation. The next goal is not to add new features.
The next goal is to reduce release risk before publishing `v0.1.0`.

This design intentionally prioritizes hardening before PyPI release. Publishing
is deferred until the existing V1 behavior is reviewed, tested, documented, and
packaged cleanly.

## Goals

- Make the existing V1 API safe enough for first external users.
- Verify Redis behavior around counters, resets, alert dedupe, and failures.
- Confirm package metadata, build output, and install behavior are release-ready.
- Improve docs so a developer can run a Redis-backed quickstart without guessing.
- Expand tests around edge cases that could cause overspend, undercounting, or
  confusing failures.
- Keep the scope focused on V1 quality, not V2 feature expansion.

## Non-Goals

- No new providers beyond the existing OpenAI and Anthropic pricing table.
- No dashboard, SaaS service, or non-Redis backend.
- No multi-agent pooled budgets.
- No built-in Slack, email, or PagerDuty integrations.
- No PyPI publish until the hardening checklist passes.

## Recommended Sequence

### 1. API Hardening

Review the public API surface:

- `UsageMeter.__init__`
- `UsageMeter.can_spend`
- `UsageMeter.record`
- `UsageMeter.get_usage`
- `UsageMeter.reset`
- `UsageMeter.track`
- `UsageMeter.instrument_openai_client`
- `UsageMeter.instrument_anthropic_client`
- `calculate_cost`
- public exceptions and exports in `agentlimit.__init__`

The review should look for ambiguous argument names, missing validation,
surprising behavior, and cases where the API could silently undercount usage.
Any breaking API change should happen before `v0.1.0`, not after.

### 2. Redis Correctness Review

Review Redis semantics and tests for:

- atomic increments for USD and token counters
- reset behavior at calendar-month boundaries
- manual reset behavior
- alert threshold deduplication
- callback failure handling
- Redis connection failures
- behavior when stored Redis values are missing or malformed

The key product promise is real-time budget enforcement. Any failure mode that
allows silent unmetered spend should either raise loudly or be documented as an
explicit limitation.

### 3. Packaging Readiness

Validate the package as a Python distribution:

- Confirm wheel and source distribution build successfully.
- Confirm `twine check` passes.
- Confirm package metadata is complete enough for PyPI.
- Add project URLs if missing.
- Confirm README renders as package long description.
- Confirm a clean install can import `agentlimit` and run the CLI entrypoint.

This phase does not publish. It only proves publish readiness.

### 4. Documentation Hardening

Improve documentation for first users:

- Add a local Redis setup path, preferably with Docker.
- Add an end-to-end quickstart that records usage and checks status.
- Add alert callback example.
- Clarify OpenAI and Anthropic auto-instrumentation limitations.
- Clarify that pricing tables can become stale and custom pricing can override
  built-in values.
- Add a short release checklist or contributor section if useful.

Docs should optimize for a developer installing the package for the first time.
They should not assume the reader has read the PRD or architecture document.

### 5. Test And CI Hardening

Expand coverage where release risk is highest:

- invalid inputs and empty agent IDs
- custom pricing validation
- unknown providers and unknown models
- Redis failure paths
- SDK instrumentation edge cases
- CLI error handling
- package build verification in CI

CI should continue to run lint and tests. If practical, add a build check so
packaging failures are caught before release.

## Release Gate

The project is ready to move from hardening to release preparation when all of
these are true:

- Local tests pass.
- Lint passes.
- Package build passes.
- `twine check` passes.
- CI passes on `main`.
- README has a runnable quickstart.
- Known V1 limitations are documented.
- No unresolved API decisions remain that would require a breaking change before
  `v0.1.0`.

After this gate, the next plan should cover TestPyPI, PyPI, git tag `v0.1.0`,
and GitHub release notes.

## Risks

- Provider pricing may be outdated by the time users install the package.
  Mitigation: document custom pricing and treat built-in pricing as convenience,
  not billing authority.
- SDK instrumentation may not cover all current and future SDK response shapes.
  Mitigation: document supported paths and fail loudly when usage is missing.
- Redis counter updates are atomic, but pre-call budget checks and post-call
  records are not a reservation system. Mitigation: document this limitation and
  avoid claiming strict concurrency reservation semantics.
- Publishing before metadata and install checks pass could create a bad first
  release. Mitigation: enforce the release gate above.

## Success Criteria

- A developer can install the package locally, start Redis, record usage, and
  inspect usage through the CLI using README instructions.
- The test suite covers the most likely release-breaking edge cases.
- Package build and metadata checks are automated or at least documented.
- The project has a clear, short release checklist for `v0.1.0`.
- The next step after this work is release preparation, not more unspecified
  hardening.
