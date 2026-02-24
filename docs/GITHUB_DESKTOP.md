# GitHub Desktop Workflow

Use this checklist to keep the repo clean and only push what is needed.

## Before Commit

1. Open GitHub Desktop and review changed files.
2. Keep only source/config/docs/test changes required for the feature or fix.
3. Exclude local runtime artifacts:
   - `outputs/`
   - `data/samples/*.xlsx`
   - `.streamlit/secrets.toml`
   - cache/temp files (`__pycache__`, `.pytest_cache`, `*.log`, `*.tmp`)
4. Confirm no credentials/tokens are in files.
5. Run tests:
   - `python -m pytest -q`

## Commit Format

Use short, clear messages:

- `feat: ...` new behavior
- `fix: ...` bug fix
- `chore: ...` repo/docs/config cleanup
- `test: ...` test-only changes

## Branching (Recommended)

1. Create a branch per change (example: `feat/unified-download`).
2. Commit in that branch.
3. Push branch and open PR to `main`.

If you work directly on `main`, keep commits small and focused.

## Files That Should Stay Tracked

- `src/` application code
- `tests/` automated tests
- `config/profiles/` runtime profiles
- `docs/` user/deployment docs
- `.github/workflows/` CI
- root project metadata (`README.md`, `ROADMAP.md`, `requirements*.txt`, `runtime.txt`, etc.)
