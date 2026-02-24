# First Release Checklist

Use this checklist before your initial GitHub release/public push.

## Repository Readiness

- [ ] Confirm repository name and description.
- [ ] Confirm default branch naming (`main` recommended).
- [ ] Add remote origin and push branch.
- [ ] Verify `.gitignore` excludes local outputs, caches, and sensitive files.

## Project Metadata

- [ ] Confirm `README.md` reflects current usage (UI + CLI).
- [ ] Confirm `LICENSE` is correct for your intended use.
- [ ] Confirm `CONTRIBUTING.md` is aligned with your workflow.
- [ ] Confirm `CHANGELOG.md` has a release entry.

## Data & Secrets Safety

- [ ] Ensure no real account exports/sensitive `.xlsx` files are tracked.
- [ ] Ensure no credentials or local config files are tracked (`.env`, editor secrets).
- [ ] Verify `data/samples/` contains only safe sample data or placeholders.

## Quality Gate

- [ ] Run tests: `python -m pytest tests/`
- [ ] Run CLI smoke test:
  - `python -m src.cli --input "data/samples/<sample>.xlsx" --output-dir "outputs/release_smoke" --skip-nlp`
- [ ] Run UI smoke test:
  - `streamlit run src/app.py`
  - Upload a sample file and verify key downloads are generated.

## Optional (When GitHub Hosted)

- [ ] Add CI workflow to run pytest on push/PR.
- [ ] Add repository topics and labels.
- [ ] Add branch protection rules for `main`.
- [ ] Create first tag/release notes (for example `v4.1.0`).
