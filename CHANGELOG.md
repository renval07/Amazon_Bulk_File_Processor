# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- CLI mode via `python -m src.cli` with documented flags.
- Streamlit optimization log download (`.txt`).
- Run-level timing metrics in UI and CLI.
- Advanced configurable thresholds in Streamlit sidebar and optimizer wiring.
- Pytest-based automated suite under `tests/`.
- GitHub collaboration files: `LICENSE`, `CONTRIBUTING.md`, PR template.

### Changed
- Reorganized repository layout for GitHub readiness (`docs/`, `data/samples/`, archived legacy docs/tests).
- Pinned runtime dependencies in `requirements.txt`.
- Added `requirements-dev.txt` and `pytest.ini`.

### Archived
- Legacy script-style test runners moved to `archive/tests_legacy/`.
- Historical status docs moved to `archive/docs/`.

## [4.0.0] - 2026-02-11

### Added
- Phase 3 NLP intelligence features:
  - Product target analysis with bleeder classification.
  - Search term intent clustering.
  - Negative product target export.
  - Negative keyword export.
  - Estimated savings reporting.
