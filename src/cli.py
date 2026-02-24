import argparse
import re
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd

try:
    from .optimizer import BulkOptimizer
except ImportError:  # pragma: no cover
    from optimizer import BulkOptimizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Amazon PPC Bulk Optimizer CLI"
    )
    parser.add_argument("--input", required=True, help="Path to Amazon bulk .xlsx file")
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory for generated output files (default: outputs)",
    )
    parser.add_argument(
        "--target-acos",
        type=float,
        default=0.30,
        help="Target ACOS as decimal (default: 0.30 for 30%%)",
    )
    parser.add_argument("--min-bid", type=float, default=0.10, help="Minimum bid floor")
    parser.add_argument("--max-bid", type=float, default=5.00, help="Maximum bid ceiling")
    parser.add_argument(
        "--disable-48hr-rule",
        action="store_true",
        help="Disable 48-hour attribution safety rule",
    )
    parser.add_argument(
        "--skip-nlp",
        action="store_true",
        help="Skip Phase 3 NLP analysis and negative recommendation files",
    )
    parser.add_argument(
        "--n-clusters",
        type=int,
        default=None,
        help="Optional fixed cluster count for search term clustering",
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=5,
        help="Minimum terms required for clustering (default: 5)",
    )
    parser.add_argument(
        "--negative-keyword-min-spend",
        type=float,
        default=10.0,
        help="Minimum spend threshold for negative keyword recommendations (default: 10)",
    )
    parser.add_argument(
        "--negative-keyword-max-acos",
        type=float,
        default=1.5,
        help="Max ACOS threshold for negative keyword recommendations (default: 1.5 = 150%%)",
    )
    return parser


def _sanitize_stem(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return cleaned or "bulk_file"


def run_cli(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}")
        return 2

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    input_stem = _sanitize_stem(input_path.stem)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("[INFO] Initializing optimizer...")
    stage_timings = {}
    run_start = time.perf_counter()
    optimizer = BulkOptimizer(
        str(input_path),
        filename=input_path.name,
        target_acos=args.target_acos,
        min_bid=args.min_bid,
        max_bid=args.max_bid,
        enforce_48hr_rule=not args.disable_48hr_rule,
    )

    try:
        warning = optimizer.check_48_hour_rule()
        if warning:
            print(f"[WARNING] {warning}")
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 2

    print("[INFO] Loading data...")
    step_start = time.perf_counter()
    optimizer.load_data()
    stage_timings["load_data"] = time.perf_counter() - step_start

    print("[INFO] Running core optimization...")
    step_start = time.perf_counter()
    bid_changes = optimizer.optimize_bids()
    bleeder_results = optimizer.identify_bleeders()
    cannibalization = optimizer.detect_cannibalization()
    budget_recs = optimizer.optimize_budgets()
    stage_timings["core_and_structural"] = time.perf_counter() - step_start

    product_target_results = {
        "bleeder_counts": {"type_a": 0, "type_b": 0, "type_c": 0, "type_d": 0},
        "negative_recommendations": pd.DataFrame(),
        "performance_analysis": pd.DataFrame(),
        "savings_estimate": 0,
    }
    search_term_clusters = {"clusters": pd.DataFrame(), "cluster_summary": pd.DataFrame(), "n_clusters": 0}

    if not args.skip_nlp:
        print("[INFO] Running NLP analysis...")
        step_start = time.perf_counter()
        product_target_results = optimizer.analyze_product_targets()
        search_term_clusters = optimizer.cluster_search_terms(
            n_clusters=args.n_clusters, min_cluster_size=args.min_cluster_size
        )
        stage_timings["nlp_analysis"] = time.perf_counter() - step_start
    else:
        print("[INFO] Skipping NLP analysis (--skip-nlp enabled)")
        stage_timings["nlp_analysis"] = 0.0

    step_start = time.perf_counter()
    is_valid, error_msg = optimizer.validate_output()
    stage_timings["validate_output"] = time.perf_counter() - step_start
    if not is_valid:
        print(f"[ERROR] Validation failed: {error_msg}")
        return 2

    print("[INFO] Saving output files...")
    step_start = time.perf_counter()
    amazon_path = output_dir / f"amazon_upload_{input_stem}.xlsx"
    analysis_path = output_dir / f"full_analysis_{input_stem}.xlsx"
    report_path = output_dir / f"optimization_report_{input_stem}_{timestamp}.md"
    log_path = output_dir / f"optimization_log_{input_stem}_{timestamp}.txt"

    final_amazon_path = optimizer.save_optimized_file(
        str(amazon_path), include_analysis_sheets=False, amazon_upload_ready=True
    )
    final_analysis_path = optimizer.save_optimized_file(
        str(analysis_path), include_analysis_sheets=True, amazon_upload_ready=False
    )

    output_paths = [Path(final_amazon_path), Path(final_analysis_path), report_path, log_path]

    if not args.skip_nlp:
        negative_products_path = output_dir / f"negative_product_targets_{input_stem}_{timestamp}.xlsx"
        negative_keywords_path = output_dir / f"negative_keywords_{input_stem}_{timestamp}.xlsx"

        negative_products_buffer = BytesIO()
        optimizer.export_negative_product_targets_bulk_file(
            product_target_results["negative_recommendations"],
            negative_products_buffer,
        )
        negative_products_path.write_bytes(negative_products_buffer.getvalue())

        negative_keywords_buffer = BytesIO()
        optimizer.export_negative_keywords_bulk_file(
            search_term_clusters,
            negative_keywords_buffer,
            min_spend=args.negative_keyword_min_spend,
            max_acos=args.negative_keyword_max_acos,
        )
        negative_keywords_path.write_bytes(negative_keywords_buffer.getvalue())
        output_paths.extend([negative_products_path, negative_keywords_path])
    stage_timings["generate_outputs"] = time.perf_counter() - step_start
    stage_timings["total_runtime"] = time.perf_counter() - run_start

    for stage_name, duration in stage_timings.items():
        optimizer.record_stage_timing(stage_name, duration)

    markdown_report = optimizer.generate_markdown_report(include_nlp=not args.skip_nlp)
    report_path.write_text(markdown_report, encoding="utf-8")
    log_path.write_text(optimizer.get_optimization_log(), encoding="utf-8")

    print("")
    print("[DONE] Optimization complete")
    print(f"  Bid updates: {bid_changes}")
    print(
        "  Bleeders: "
        f"A={bleeder_results.get('type_a', 0)}, "
        f"B={bleeder_results.get('type_b', 0)}, "
        f"C={bleeder_results.get('type_c', 0)}"
    )
    print(f"  Cannibalization issues: {len(cannibalization)}")
    print(f"  Campaigns analyzed for budgets: {len(budget_recs)}")
    if not args.skip_nlp:
        print(
            "  NLP summary: "
            f"clusters={search_term_clusters.get('n_clusters', 0)}, "
            f"negative products={len(product_target_results.get('negative_recommendations', pd.DataFrame()))}"
        )

    print("\nGenerated files:")
    for path in output_paths:
        print(f"  - {path}")

    print("\nRun timings:")
    for stage_name, seconds in stage_timings.items():
        print(f"  - {stage_name}: {seconds:.2f}s")

    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(run_cli(args))


if __name__ == "__main__":
    main()
