# Amazon PPC Bulk Optimizer Roadmap

Last Updated: 2026-02-24
Owner: Project Team
Status: Authoritative roadmap (single source of truth)

## 1. Product Goal
Build a reliable Amazon PPC bulk-file optimization platform that is safe for production uploads and fast enough for repeat weekly operations.

## 2. Current Baseline (Implemented)
- Streamlit workflow for upload, optimization, analysis, and downloads
- RPC bid optimization with safety rails and update tagging
- 48-hour attribution safety check
- Bleeder detection for keywords/product targets
- Structural analysis (cannibalization + budget recommendations)
- NLP analysis (product target analysis + search term intent clustering)
- Amazon-ready export files (main upload + negative products + negative keywords)
- Markdown optimization report generation

## 3. Roadmap Priorities

### P0 - Documentation and Reliability (Now)
- Status: Complete (2026-02-24)
- [x] Consolidate docs around this roadmap + `README.md` + `SUMMARY.md`
- [x] Replace script-style tests with `pytest` test suite
- [x] Add CI test run (GitHub Actions or equivalent)
- [x] Pin dependency versions for reproducible installs

Exit Criteria:
- One documentation source of truth
- Automated test pass on every change
- Reproducible environment setup

### P1 - Optimization Controls and Automation (Next)
- Status: Complete (2026-02-24)
- [x] Add advanced configurable thresholds in UI
- [x] Add CLI mode for batch/non-UI use
- [x] Add downloadable optimization log export
- [x] Add run-level timing/performance metrics

Exit Criteria:
- Power users can tune thresholds without code edits
- Workflow is runnable from CLI for automation
- Users can export logs and see processing bottlenecks

### P2 - Scale and Multi-Account Operations (Later)
- [ ] Batch process multiple bulk files in one run
- [ ] Historical run tracking and comparison dashboard
- [ ] Basic drift monitoring on model-dependent outputs

Exit Criteria:
- Multi-account workflows require minimal manual repetition
- Trends and run-over-run results are visible

### P3 - Deployment and Packaging (Later)
- [ ] Dockerized runtime for consistent deployment
- [ ] Environment profiles (local/dev/prod)
- [ ] Release checklist + versioned changelog

Exit Criteria:
- Repeatable deployment path with minimal manual setup

## 4. Backlog Candidates
- Data visualizations for metric trends
- Email/notification hooks for long runs
- More granular unit tests around statistical methods

## 5. Governance
- This file is the authoritative roadmap.
- Historical phase/status docs are archived in `archive/docs/`.
- Any roadmap change should update:
  - this file (`ROADMAP.md`)
  - impact summary in `SUMMARY.md` if architecture/workflow changes

## 6. Milestone Log
- 2026-02-24: Archived stale status docs into `archive/docs/` and created `archive/docs/README.md`.
- 2026-02-24: Created authoritative `ROADMAP.md` and aligned `README.md` + `SUMMARY.md` references.
- 2026-02-24: Started pytest migration by adding baseline tests in `tests/` (`conftest.py`, core, structural).
- 2026-02-24: Verified pytest baseline with `python -m pytest tests/` (7 passed).
- 2026-02-24: Pinned direct project dependencies in `requirements.txt` for reproducible setup.
- 2026-02-24: Added Streamlit download for text optimization audit log (`Optimization Log` button).
- 2026-02-24: Added `pytest.ini` to disable cache provider in OneDrive environment; pytest runs cleanly.
- 2026-02-24: Added CLI mode (`src/cli.py`) and documented CLI commands/flags in `README.md`.
- 2026-02-24: Replaced script-style tests with pytest suite and archived legacy test runners to `archive/tests_legacy/`.
- 2026-02-24: Added configurable advanced thresholds in Streamlit UI and wired them into `BulkOptimizer`.
- 2026-02-24: Added run-level timing metrics in Streamlit and CLI with stage breakdown reporting.
- 2026-02-24: Reorganized repository layout for GitHub readiness (`docs/`, `data/samples/`) and added `.gitignore`.
- 2026-02-24: Added GitHub collaboration basics (`LICENSE`, `CONTRIBUTING.md`, `.github/PULL_REQUEST_TEMPLATE.md`).
- 2026-02-24: Added release management docs (`CHANGELOG.md`, `RELEASE_CHECKLIST.md`).
- 2026-02-24: Added GitHub Actions CI workflow to run pytest on push/PR (`.github/workflows/ci.yml`).
