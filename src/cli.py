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
    from .run_history import append_run_history, calculate_drift_alerts, load_run_history
    from .settings import load_runtime_profile
except ImportError:  # pragma: no cover
    from optimizer import BulkOptimizer
    from run_history import append_run_history, calculate_drift_alerts, load_run_history
    from settings import load_runtime_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Amazon PPC Bulk Optimizer CLI"
    )
    parser.add_argument(
        "--env",
        choices=["local", "dev", "prod"],
        default=None,
        help="Runtime environment profile (default: APP_ENV or local)",
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", help="Path to one Amazon bulk .xlsx file")
    input_group.add_argument(
        "--input-dir",
        help="Directory containing bulk .xlsx files for batch processing",
    )
    parser.add_argument(
        "--pattern",
        default="*.xlsx",
        help="Filename pattern for --input-dir mode (default: *.xlsx)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search subdirectories when using --input-dir",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop batch processing on first file failure",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for generated output files (default comes from selected --env profile)",
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
    parser.add_argument(
        "--bleeder-type-c-mode",
        choices=["fixed", "percentile", "zscore"],
        default="fixed",
        help="Type C low-volume detection mode (default: fixed)",
    )
    parser.add_argument(
        "--bleeder-type-c-impressions-threshold",
        type=int,
        default=100,
        help="Type C fixed-mode max impressions threshold (default: 100)",
    )
    parser.add_argument(
        "--bleeder-type-c-percentile",
        type=float,
        default=0.25,
        help="Type C percentile mode cutoff as decimal (default: 0.25)",
    )
    parser.add_argument(
        "--bleeder-type-c-z-threshold",
        type=float,
        default=-1.0,
        help="Type C zscore mode cutoff on log impressions (default: -1.0)",
    )
    parser.add_argument(
        "--cold-start-step-up",
        type=float,
        default=0.02,
        help="Cold-start bid increase for low-volume zero-click terms (default: 0.02)",
    )
    parser.add_argument(
        "--disable-cold-start",
        action="store_true",
        help="Disable cold-start bid step-up logic",
    )
    return parser


def _sanitize_stem(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return cleaned or "bulk_file"


def _run_single_file(args: argparse.Namespace, input_path: Path, output_dir: Path, history_path: str):
    input_stem = _sanitize_stem(input_path.stem)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"[INFO] Initializing optimizer for: {input_path.name}")
    stage_timings = {}
    run_start = time.perf_counter()
    try:
        optimizer = BulkOptimizer(
            str(input_path),
            filename=input_path.name,
            target_acos=args.target_acos,
            min_bid=args.min_bid,
            max_bid=args.max_bid,
            enforce_48hr_rule=not args.disable_48hr_rule,
            bleeder_type_c_mode=args.bleeder_type_c_mode,
            bleeder_type_c_impressions_threshold=args.bleeder_type_c_impressions_threshold,
            bleeder_type_c_percentile=args.bleeder_type_c_percentile,
            bleeder_type_c_z_threshold=args.bleeder_type_c_z_threshold,
            cold_start_step_up_amount=args.cold_start_step_up,
            cold_start_enable=not args.disable_cold_start,
        )

        warning = optimizer.check_48_hour_rule()
        if warning:
            print(f"[WARNING] {warning}")

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
            return 2, {"file": str(input_path), "status": "failed", "error": error_msg}

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
            f"C={bleeder_results.get('type_c', 0)}, "
            f"ColdStart={bleeder_results.get('cold_start_stepups', 0)}"
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

        result = {
            "file": str(input_path),
            "status": "ok",
            "error": "",
            "bid_updates": int(bid_changes),
            "type_a_bleeders": int(bleeder_results.get("type_a", 0)),
            "type_b_bleeders": int(bleeder_results.get("type_b", 0)),
            "type_c_bleeders": int(bleeder_results.get("type_c", 0)),
            "cannibalization_issues": int(len(cannibalization)),
            "campaigns_analyzed": int(len(budget_recs)),
            "intent_clusters": int(search_term_clusters.get("n_clusters", 0)),
            "negative_recommendations": int(
                len(product_target_results.get("negative_recommendations", pd.DataFrame()))
            ),
            "runtime_seconds": round(float(stage_timings.get("total_runtime", 0.0)), 2),
        }
        run_history_path = append_run_history(
            {
                "mode": "cli",
                "input_file": input_path.name,
                **result,
            },
            history_path=history_path,
        )
        drift_alerts = calculate_drift_alerts(load_run_history(run_history_path))
        if drift_alerts:
            print("\n[WARNING] Drift alerts detected vs recent runs:")
            for alert in drift_alerts:
                delta_text = "n/a" if alert["delta_pct"] is None else f"{alert['delta_pct']:+.2f}%"
                print(
                    f"  - {alert['metric']}: latest={alert['latest']}, "
                    f"baseline={alert['baseline_mean']}, delta={delta_text}"
                )
        return 0, result
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        result = {"file": str(input_path), "status": "failed", "error": str(exc)}
        append_run_history(
            {"mode": "cli", "input_file": input_path.name, **result},
            history_path=history_path,
        )
        return 2, result
    except Exception as exc:  # pragma: no cover
        print(f"[ERROR] Unexpected failure: {exc}")
        result = {"file": str(input_path), "status": "failed", "error": str(exc)}
        append_run_history(
            {"mode": "cli", "input_file": input_path.name, **result},
            history_path=history_path,
        )
        return 1, result


def _discover_batch_files(input_dir: Path, pattern: str, recursive: bool):
    globber = input_dir.rglob if recursive else input_dir.glob
    return sorted(path for path in globber(pattern) if path.is_file())


def run_cli(args: argparse.Namespace) -> int:
    profile = load_runtime_profile(args.env)
    output_dir = Path(args.output_dir or profile["default_output_dir"]).expanduser().resolve()
    history_path = profile["run_history_path"]
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Runtime profile: {profile['name']}")

    if args.input:
        input_path = Path(args.input).expanduser().resolve()
        if not input_path.exists():
            print(f"[ERROR] Input file not found: {input_path}")
            return 2
        code, _ = _run_single_file(args, input_path, output_dir, history_path)
        return code

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[ERROR] Input directory not found: {input_dir}")
        return 2

    files = _discover_batch_files(input_dir, args.pattern, args.recursive)
    if not files:
        print(f"[ERROR] No files matched pattern '{args.pattern}' in: {input_dir}")
        return 2

    print(f"[INFO] Batch mode: found {len(files)} file(s)")
    results = []
    failures = 0
    for index, path in enumerate(files, start=1):
        print("")
        print(f"[INFO] Processing file {index}/{len(files)}: {path.name}")
        code, details = _run_single_file(args, path, output_dir, history_path)
        details["exit_code"] = code
        results.append(details)
        if code != 0:
            failures += 1
            if args.fail_fast:
                print("[ERROR] Stopping batch because --fail-fast is enabled.")
                break

    summary_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = output_dir / f"batch_summary_{summary_timestamp}.csv"
    pd.DataFrame(results).to_csv(summary_path, index=False)
    print("")
    print(f"[INFO] Batch summary saved: {summary_path}")
    print(f"[INFO] Batch results: {len(results) - failures} succeeded, {failures} failed")
    return 0 if failures == 0 else 1


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(run_cli(args))


if __name__ == "__main__":
    main()
