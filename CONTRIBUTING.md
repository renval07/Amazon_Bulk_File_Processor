# Contributing Guide

## Setup

1. Install runtime dependencies:
```bash
pip install -r requirements.txt
```
2. Install development/test dependencies:
```bash
pip install -r requirements-dev.txt
```
3. Run tests:
```bash
python -m pytest tests/
```

## Development Rules

- Keep `ROADMAP.md` updated when milestones change.
- Keep `README.md` and `SUMMARY.md` aligned with behavior changes.
- Add or update pytest coverage for all behavior changes.
- Avoid committing sample account data or generated output files.

## Pull Request Checklist

- [ ] Tests pass locally (`python -m pytest tests/`)
- [ ] Documentation updated (`README.md`, `SUMMARY.md`, `ROADMAP.md` as needed)
- [ ] No generated artifacts committed (`outputs/`, caches, local files)
- [ ] Feature flags/threshold defaults are documented when changed
