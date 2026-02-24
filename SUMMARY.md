# Project Working Summary

Authoritative roadmap: `ROADMAP.md`

## Purpose
This project is an Amazon PPC bulk file analyzer and optimizer with upload-ready exports.

It ingests Amazon bulk Excel files, applies bid optimization and bleeder detection, runs structural + NLP analysis, and generates files you can upload back to Seller Central.

## Current State
- Status in code: feature-complete through Phase 3 (NLP Intelligence).
- Main app: Streamlit UI with end-to-end workflow and 6 download outputs.
- Core engine: `src/optimizer.py` (`BulkOptimizer` class).
- Tests: pytest-based suite in `tests/` with legacy script runners archived.
- Automation: CLI supports both single-file and batch folder processing with summary export.
- CI: GitHub Actions workflow runs pytest on push/PR.
- Deployment: Dockerized runtime and environment profiles (`local`/`dev`/`prod`) are implemented.
- Online app readiness: Streamlit Cloud entrypoint and config are in place (`streamlit_app.py`, `.streamlit/config.toml`).

## Key Files
- `src/app.py`: Streamlit UI, orchestrates full pipeline and download generation.
- `streamlit_app.py`: root Streamlit entrypoint for local/Cloud deploy.
- `src/cli.py`: Command-line entrypoint for non-UI and automation workflows.
- `src/optimizer.py`: all optimization/analysis logic.
- `src/settings.py`: runtime profile loader (`APP_ENV` + profile files).
- `src/run_history.py`: persistent run history and drift alert logic.
- `README.md`: user-level overview and run instructions.
- `ROADMAP.md`: authoritative project roadmap and milestone log.
- `tests/`: active pytest suite for automated validation.

## End-to-End Workflow
1. User provides `.xlsx` bulk file via Streamlit UI or CLI.
2. Optimizer validates config and checks 48-hour attribution safety from filename date range.
3. Loads `Sponsored Products Campaigns` sheet and cleans numeric/operation columns.
4. Runs RPC bid optimization with safety rails.
5. Runs keyword/product-target bleeder detection.
6. Runs structural analysis:
   - Cannibalization detection
   - Budget recommendations
7. Runs NLP analysis:
   - Product target statistical analysis
   - Search term intent clustering
8. Validates output integrity.
9. Generates downloads:
   - Amazon upload Excel (clean sheets)
   - Full analysis Excel (reports included)
   - Markdown analysis report
   - Optimization log text
   - Negative product targets Excel
   - Negative keywords Excel
10. In CLI batch mode, writes a batch summary CSV with per-file outcomes.
11. Records run history and checks drift against recent successful baseline.
12. Supports configurable low-volume handling mode (`fixed`, `percentile`, `zscore`) and optional cold-start bid step-up.

## Implemented Features (Code-Verified)
- RPC-based bid optimization (`optimize_bids`)
- 48-hour attribution rule (`check_48_hour_rule`)
- Bid safety rails (min/max bids, ±20% change bounds, low-data handling)
- Keyword/Product Target bleeder detection (`identify_bleeders`)
- User-friendly keyword classifications (Low Engagement, High-Cost Non-Converter, Low Visibility)
- Cold-start step-up for low-visibility zero-click terms (default +$0.02, configurable)
- Test More report for low-volume terms (`generate_test_more_report`)
- Output integrity validation (`validate_output`)
- Amazon upload-safe export + full analysis export (`save_optimized_file`)
- Cannibalization report (`detect_cannibalization`)
- Budget recommendation engine (`optimize_budgets`)
- Product target analysis with bleeder types + savings estimate (`analyze_product_targets`)
- Search term clustering via sentence-transformers + KMeans (`cluster_search_terms`)
- Negative product target export (`export_negative_product_targets_bulk_file`)
- Negative keyword export (`export_negative_keywords_bulk_file`)
- Markdown reporting (`generate_markdown_report`)
- Internal timestamped optimization log (`_log`, `get_optimization_log`)

## Dependencies
From `requirements.txt`:
- pandas==2.3.3
- streamlit==1.53.1
- openpyxl==3.1.5
- xlsxwriter==3.2.9
- scipy==1.17.0
- scikit-learn==1.8.0
- sentence-transformers==5.2.2

## Important Operational Notes
- Expected sheet: `Sponsored Products Campaigns` is required.
- 48-hour rule depends on filename pattern like `YYYYMMDD-YYYYMMDD`.
- NLP clustering requires search term report sheets in the workbook (`SP Search Term Report` and/or `SB Search Term Report`).
- Amazon upload file intentionally excludes analysis/problematic sheets; full analysis file includes added reports.
- Advanced optimization thresholds are configurable from Streamlit sidebar (`Advanced Thresholds`).
- NLP stage can be toggled per run in UI for restricted environments.

## Gaps / Risks To Address Next
- Large-file performance and model-loading latency remain potential bottlenecks.
- Drift thresholds are currently static and may need tuning per account size.

## Suggested Immediate Next Sprint
1. Add lightweight observability for memory/runtime on large batch runs.
2. Add richer trend visualizations for historical run comparisons.
3. Tune drift alert sensitivity and allow per-account overrides.
