# Release Checklist

Use this checklist before publishing `v0.1.0`.

## Hardening Gate

- Create and activate a dev virtual environment.
- `python -m pip install -e ".[dev]"` completes.
- `python -m ruff check agentlimit tests` passes.
- `python -m pytest` passes.
- `python -m build` creates wheel and source distribution.
- `python -m twine check dist/*` passes.
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
