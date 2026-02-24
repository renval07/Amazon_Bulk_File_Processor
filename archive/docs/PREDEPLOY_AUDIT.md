# Pre-Deployment Audit (Streamlit-First)

Date: 2026-02-24  
Scope: End-to-end technical audit of UI/optimizer/tests/deployment assets and PPC logic quality.

## Executive Summary

Status: **Deployable with targeted hardening**.

The core optimization workflow is stable and test-backed, but there are specific risks that should be resolved before production Streamlit deployment:

1. NLP dependencies are heavy and loaded too early, increasing startup/build risk.
2. Expensive analysis is recomputed multiple times per run, adding latency and failure surface.
3. Streamlit results are not persisted in session state, so reruns are fragile.
4. Documentation and test discovery have drift issues that can confuse operators.

## Evidence Collected

- `python -m pytest tests -q`: **29 passed, 1 skipped**.
- `python -m pytest -q` from repo root fails due archive script tests (`archive/tests_legacy/test_fixes.py`) executing `exit(1)`.
- Runtime baseline on sample file (`bulk-a2kk083uqnb8ha-20260125-20260224-1771933500225.xlsx`):
  - Skip NLP: **9.32s total** (load 5.37s, output generation 3.92s).
  - With NLP enabled in restricted network: **11.45s total** and clustering fallback due model download failure.
- Import timing: `import src.optimizer` takes about **6.87s**.
- Local package footprint (approx):
  - `torch` 448.6 MB
  - `transformers` 88.5 MB
  - `scipy` 110.4 MB
  - `sklearn` 39.5 MB

## Technical Findings (Prioritized)

### High Priority

1. NLP stack is eagerly imported at module load.
- `src/optimizer.py:7-9` imports `sentence_transformers` and sklearn globally.
- Impact: slower cold starts, larger deployment footprint, more build/runtime failures.
- Recommendation: lazy import inside `cluster_search_terms()` and make NLP an optional dependency group.

2. Duplicate heavy computation per run.
- `src/app.py:329-351` computes outputs once, then `src/app.py:629` calls `generate_markdown_report()`.
- `src/optimizer.py:673,694,739,776` re-runs cannibalization/budget/product/NLP analysis while generating report.
- `src/optimizer.py:610,616` re-runs cannibalization/budget again during full Excel write.
- Impact: extra latency and repeated network/model failures.
- Recommendation: cache stage results in memory and pass into report/export functions (no recompute).

3. UI state is not persisted.
- `src/app.py:257` uses `st.button("Run Optimization")` with no `st.session_state` result store.
- Impact: reruns can clear computed artifacts; fragile UX under Streamlit rerun model.
- Recommendation: persist run payloads (dataframes, bytes, timings) in session state keyed by upload hash.

### Medium Priority

4. Test discovery booby-trap in archive folder.
- `archive/tests_legacy/test_fixes.py:16,28,38,59,68` contains `exit(...)` at module scope.
- Impact: `pytest` at repo root is unreliable for new contributors.
- Recommendation: rename archive scripts to non-test names or add `norecursedirs = archive` to `pytest.ini`.

5. Documentation drift on 48-hour rule behavior.
- README still says blocking behavior (`README.md:10,146,219,329`), but runtime is advisory (`src/app.py:236,251`, `src/cli.py:68`).
- Impact: operator confusion and incorrect expectations.
- Recommendation: update README tables and troubleshooting text to advisory wording.

6. Global `.gitignore` excludes all `.xlsx`.
- `.gitignore:42-43` ignores workbook files globally.
- Impact: reproducible sample-driven testing in GitHub is harder unless exceptions are explicit.
- Recommendation: keep privacy-safe small fixture files under `tests/fixtures/` with explicit allow-list rules.

### Low Priority

7. Entry-point import style is workable but brittle.
- `streamlit_app.py:10` uses `from app import *` plus path manipulation.
- Recommendation: import a single `run_app()` function from `src.app` for cleaner startup contracts.

## How To Make The Project Lighter (Without Losing Features)

1. Split dependencies into tiers:
- `requirements-core.txt`: pandas, streamlit, openpyxl, xlsxwriter.
- `requirements-nlp.txt`: sentence-transformers, scikit-learn, scipy (and torch transitively).
- Keep full install for local power users; deploy core-only as default.

2. Lazy-load NLP only when needed:
- Move NLP imports/model load inside clustering path.
- Default `Run NLP Analysis` to `False` in cloud profile, user can opt in.

3. Stop recomputing analytics:
- Store `cannibalization`, `budget_recs`, `product_target_results`, `search_term_clusters` once.
- Feed these cached objects into report/export generation.

4. Use session-state artifact cache:
- Store final downloadable buffers and tables after a successful run.
- Prevent rework during widget updates/download clicks.

5. Optional: remove CLI from deployment surface:
- If Streamlit-only is now the direction, keep CLI code but do not include CLI docs/flows in cloud UX.

## PPC / Growth Audit: Where Logic Falls Short

1. Account-wide thresholds are too coarse.
- Current z-score and click thresholds are computed globally across all targets.
- Gap: no segmentation by campaign type, match type, branded/non-branded, or placement intent.
- Improvement: compute thresholds per segment to avoid over/under-reacting.

2. No explicit significance/confidence framework.
- Current logic uses hard click/impression cutoffs and std multipliers.
- Gap: weak statistical confidence under sparse data.
- Improvement: add Bayesian or Wilson-confidence gating for action eligibility.

3. Cold-start is one-step, not lifecycle-managed.
- Current policy: +$0.02 for low-volume zero-click terms.
- Gap: no run-based ladder, cooldown, or stop conditions.
- Improvement: multi-step ladder with max steps, rollback rule, and “graduate/pause/negate” exits.

4. Negative keyword generation does not truly use intent-cluster performance.
- `src/optimizer.py:1586-1588` selects by spend/ACOS only.
- Gap: NLP clustering is computed but not strongly used for decisioning.
- Improvement: make cluster category + cluster-level waste score part of negative decision rule.

5. Budget recommendations are simplistic for scaling.
- Fixed +50/+20/0/-50 rules are easy but blunt.
- Gap: no impression share, budget caps, or saturation logic.
- Improvement: budget pacing model with min/max bounds and campaign objective awareness.

6. Missing high-value growth loop features.
- No search-term promotion workflow (query -> exact keyword).
- No negation conflict checks against already exact/phrase winners.
- No prioritization queue by expected incremental profit.

## Recommended Pre-Deploy Plan (7-10 Days)

### Phase A (Stability/Speed)
1. Implement lazy NLP imports + optional dependency tier.
2. Add run-result cache object and remove duplicate recompute paths.
3. Persist outputs in `st.session_state`.
4. Fix pytest archive discovery issue.

### Phase B (PPC Quality)
1. Add segmented threshold mode (campaign/match type).
2. Add confidence-gated decision layer.
3. Upgrade cold-start into step-up lifecycle policy.
4. Tie negative keyword decisions to cluster-level performance signals.

### Phase C (Deployment)
1. Add `runtime.txt` (pin Python for Streamlit Cloud consistency).
2. Update README/deployment docs to match advisory 48-hour behavior and optional NLP mode.
3. Run final smoke: upload, optimize, unified export, and sample re-upload validation.

## Deployment Readiness Verdict

- Today: **70/100** (functional but heavier and less deterministic than ideal).
- After Phase A: **85/100**.
- After Phase A+B: **90+/100** with stronger PPC decision quality and better scale reliability.
