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
