import streamlit as st
import pandas as pd
import os
import sys
import time
import json
import hashlib
from io import BytesIO

# Add src to path to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from optimizer import BulkOptimizer
from run_history import append_run_history, calculate_drift_alerts, load_run_history
from settings import load_runtime_profile

st.set_page_config(page_title="Amazon PPC Bulk Optimizer", layout="wide")
runtime_profile = load_runtime_profile()
history_path = runtime_profile["run_history_path"]
profile_ui = runtime_profile.get("ui", {})


def _read_excel_sheet_from_buffer(buffer: BytesIO, sheet_name: str) -> pd.DataFrame:
    """Reads one sheet from an in-memory Excel buffer."""
    return pd.read_excel(BytesIO(buffer.getvalue()), sheet_name=sheet_name)


def _build_budget_updates_upload_df(
    campaign_sheet_df: pd.DataFrame,
    budget_recs: pd.DataFrame,
) -> pd.DataFrame:
    """Builds Amazon-compatible campaign budget updates from budget recommendations."""
    required_cols = list(campaign_sheet_df.columns) if not campaign_sheet_df.empty else [
        "Product", "Entity", "Operation", "Campaign ID", "Campaign Name", "Daily Budget"
    ]
    if campaign_sheet_df.empty or budget_recs.empty:
        return pd.DataFrame(columns=required_cols)
    if "Suggested_Budget" not in budget_recs.columns:
        return pd.DataFrame(columns=required_cols)

    rec_campaign_col = None
    for candidate in ["Campaign Name", "Campaign Name (Informational only)"]:
        if candidate in budget_recs.columns:
            rec_campaign_col = candidate
            break
    if rec_campaign_col is None:
        return pd.DataFrame(columns=required_cols)

    campaign_rows = campaign_sheet_df.copy()
    if "Entity" in campaign_rows.columns:
        campaign_rows = campaign_rows[
            campaign_rows["Entity"].fillna("").astype(str).str.strip().str.lower() == "campaign"
        ]
    if campaign_rows.empty:
        return pd.DataFrame(columns=required_cols)

    def campaign_key(df: pd.DataFrame, cols):
        key = pd.Series("", index=df.index, dtype="object")
        for col in cols:
            if col in df.columns:
                values = (
                    df[col]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace({"nan": "", "NaN": "", "None": "", "none": ""})
                )
                key = key.where(key != "", values)
        return key

    campaign_rows["_campaign_key"] = campaign_key(
        campaign_rows, ["Campaign Name", "Campaign Name (Informational only)"]
    )
    recs = budget_recs[[rec_campaign_col, "Suggested_Budget"]].copy()
    recs["_campaign_key"] = (
        recs[rec_campaign_col]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "NaN": "", "None": "", "none": ""})
    )
    recs = recs[recs["_campaign_key"] != ""]
    recs = recs.drop_duplicates("_campaign_key", keep="first")

    merged = campaign_rows.merge(recs[["_campaign_key", "Suggested_Budget"]], on="_campaign_key", how="inner")
    if merged.empty:
        return pd.DataFrame(columns=required_cols)

    if "Daily Budget" in merged.columns:
        current_budget = pd.to_numeric(merged["Daily Budget"], errors="coerce")
        suggested_budget = pd.to_numeric(merged["Suggested_Budget"], errors="coerce")
        changed_mask = (current_budget - suggested_budget).abs().fillna(0) > 1e-6
        merged = merged[changed_mask]
        if merged.empty:
            return pd.DataFrame(columns=required_cols)
        merged["Daily Budget"] = suggested_budget.loc[merged.index]
    if "Operation" in merged.columns:
        merged["Operation"] = "Update"

    return merged.reindex(columns=required_cols, fill_value="")


def _safe_sheet_name(name: str) -> str:
    """Returns an Excel-compatible sheet name (<=31 chars)."""
    cleaned = str(name).strip() or "Sheet1"
    invalid = ['\\', '/', '*', '?', ':', '[', ']']
    for ch in invalid:
        cleaned = cleaned.replace(ch, "_")
    return cleaned[:31]

st.title("Amazon PPC Bulk Optimizer")
st.markdown("Automate your Amazon PPC bid management using Revenue-Per-Click (RPC) and Z-Score statistical optimization.")
st.caption(f"Environment Profile: {runtime_profile['name']}")

# Sidebar Configuration
st.sidebar.header("Configuration")
target_acos = st.sidebar.slider("Target ACOS (%)", 5, 100, int(profile_ui.get("target_acos", 0.30) * 100)) / 100.0
min_bid = st.sidebar.number_input("Min Bid ($)", value=float(profile_ui.get("min_bid", 0.02)), step=0.01)
max_bid = st.sidebar.number_input("Max Bid ($)", value=float(profile_ui.get("max_bid", 5.00)), step=0.10)

st.sidebar.header("Safety Settings")
run_nlp_analysis = st.sidebar.checkbox(
    "Run NLP Analysis",
    value=bool(profile_ui.get("run_nlp_analysis", True)),
    help="Disable this if model download is restricted in your environment."
)

st.sidebar.header("Unified Download")
bundle_include_bids = st.sidebar.checkbox("Include Bid Updates", value=True)
bundle_include_negative_products = st.sidebar.checkbox("Include Negative Products", value=True)
bundle_include_negative_keywords = st.sidebar.checkbox("Include Negative Keywords", value=True)
bundle_include_budget_updates = st.sidebar.checkbox(
    "Include Budget Updates (Suggested)",
    value=False,
    help="Adds campaign budget update rows where suggested budget differs from current.",
)

with st.sidebar.expander("Advanced Thresholds", expanded=False):
    optimization_min_clicks = st.number_input(
        "Min Clicks for Optimization",
        min_value=0,
        value=10,
        step=1,
        help="Only entities above this click threshold receive RPC bid optimization updates.",
    )
    max_bid_change_pct = st.slider(
        "Max Bid Change per Run (%)",
        min_value=1,
        max_value=100,
        value=20,
        step=1,
        help="Caps bid movement in either direction for each optimization run.",
    ) / 100.0
    bleeder_type_a_impressions_threshold = st.number_input(
        "Low Engagement Min Impressions",
        min_value=0,
        value=1000,
        step=50,
        help="Minimum impressions before Low Engagement logic is applied.",
    )
    bleeder_type_a_z_threshold = st.slider(
        "Low Engagement Z-Score Threshold",
        min_value=-4.0,
        max_value=0.0,
        value=-1.5,
        step=0.1,
        help="More negative is stricter. Terms below this Z-score are considered low CTR outliers.",
    )
    bleeder_type_b_clicks_std_multiplier = st.slider(
        "High-Cost Non-Converter StdDev Multiplier",
        min_value=0.5,
        max_value=5.0,
        value=2.0,
        step=0.1,
        help="Higher values are stricter for click-heavy zero-sale terms.",
    )
    bleeder_type_c_mode = st.selectbox(
        "Low Visibility Mode",
        options=["fixed", "percentile", "zscore"],
        index=0,
        help="Choose how low-volume terms are detected.",
    )
    bleeder_type_c_impressions_threshold = 100
    bleeder_type_c_percentile = 0.25
    bleeder_type_c_z_threshold = -1.0
    if bleeder_type_c_mode == "fixed":
        bleeder_type_c_impressions_threshold = st.number_input(
            "Low Visibility Max Impressions",
            min_value=1,
            value=100,
            step=10,
            help="Terms below this impression count are flagged as low visibility.",
        )
    elif bleeder_type_c_mode == "percentile":
        bleeder_type_c_percentile = st.slider(
            "Low Visibility Percentile",
            min_value=0.05,
            max_value=0.50,
            value=0.25,
            step=0.05,
            help="Flags terms at or below this impression percentile.",
        )
    else:
        bleeder_type_c_z_threshold = st.slider(
            "Low Visibility Z-Score Threshold",
            min_value=-3.0,
            max_value=0.0,
            value=-1.0,
            step=0.1,
            help="Uses log-impression z-score; more negative is stricter.",
        )
    bleeder_segmentation_mode = st.selectbox(
        "Bleeder Segmentation Mode",
        options=["none", "match_type", "campaign"],
        index=0,
        help="Compute Type A/B baselines by segment instead of account-wide when enough rows exist.",
    )
    segmentation_min_entities = st.number_input(
        "Segmentation Min Entities",
        min_value=5,
        value=25,
        step=5,
        help="Segments below this size fall back to account-wide baselines.",
    )
    confidence_enable = st.checkbox(
        "Enable Confidence Gating",
        value=True,
        help="Adds confidence checks before Type A/B bleeder actions.",
    )
    type_a_confidence_level = st.selectbox(
        "Type A Confidence Level",
        options=[0.80, 0.85, 0.90, 0.95, 0.99],
        index=3,
        format_func=lambda x: f"{int(x * 100)}%",
        help="Wilson confidence level for low-CTR certainty check.",
        disabled=not confidence_enable,
    )
    type_b_min_spend = st.number_input(
        "Type B Min Spend ($)",
        min_value=0.0,
        value=5.0,
        step=1.0,
        help="Minimum spend required before Type B non-converter downgrade can trigger.",
        disabled=not confidence_enable,
    )
    cold_start_enable = st.checkbox(
        "Enable Cold-Start Step-Up",
        value=True,
        help="Increase bids for low-volume zero-click terms to collect data.",
    )
    cold_start_mode = st.selectbox(
        "Cold-Start Mode",
        options=["fixed", "ladder"],
        index=0,
        help="Ladder mode applies larger step-ups for earlier-stage low-volume terms.",
    )
    cold_start_step_up_amount = st.number_input(
        "Cold-Start Step-Up ($)",
        min_value=0.00,
        value=0.02,
        step=0.01,
        help="Bid increment applied to eligible low-volume zero-click terms.",
    )
    cold_start_ladder_cap = st.number_input(
        "Cold-Start Ladder Cap ($)",
        min_value=0.00,
        value=0.08,
        step=0.01,
        help="Maximum single-run ladder increment when cold-start mode is ladder.",
        disabled=(cold_start_mode != "ladder"),
    )
    cold_start_stalled_impressions = st.number_input(
        "Cold-Start Stalled Impressions",
        min_value=0,
        value=300,
        step=25,
        help="No-click terms at/above this impression level are flagged for negate/pause review.",
    )
    negative_keywords_low_intent_only = st.checkbox(
        "Negative Keywords: Low-Intent Clusters Only",
        value=True,
        help="Only export negative keywords from clusters categorized as Low-Performing Intent.",
    )

uploaded_file = st.file_uploader("Upload Bulk File (.xlsx)", type=["xlsx"])

if uploaded_file:
    st.info(f"Loaded: {uploaded_file.name}")

    uploaded_bytes = uploaded_file.getvalue()
    file_hash = hashlib.sha256(uploaded_bytes).hexdigest()
    run_config = {
        "target_acos": target_acos,
        "min_bid": min_bid,
        "max_bid": max_bid,
        "run_nlp_analysis": run_nlp_analysis,
        "optimization_min_clicks": optimization_min_clicks,
        "max_bid_change_pct": max_bid_change_pct,
        "bleeder_type_a_impressions_threshold": bleeder_type_a_impressions_threshold,
        "bleeder_type_a_z_threshold": bleeder_type_a_z_threshold,
        "bleeder_type_b_clicks_std_multiplier": bleeder_type_b_clicks_std_multiplier,
        "bleeder_type_c_impressions_threshold": bleeder_type_c_impressions_threshold,
        "bleeder_type_c_mode": bleeder_type_c_mode,
        "bleeder_type_c_percentile": bleeder_type_c_percentile,
        "bleeder_type_c_z_threshold": bleeder_type_c_z_threshold,
        "bleeder_segmentation_mode": bleeder_segmentation_mode,
        "segmentation_min_entities": int(segmentation_min_entities),
        "confidence_enable": confidence_enable,
        "type_a_confidence_level": type_a_confidence_level,
        "type_b_min_spend": type_b_min_spend,
        "cold_start_enable": cold_start_enable,
        "cold_start_mode": cold_start_mode,
        "cold_start_step_up_amount": cold_start_step_up_amount,
        "cold_start_ladder_cap": cold_start_ladder_cap,
        "cold_start_stalled_impressions": int(cold_start_stalled_impressions),
        "negative_keywords_low_intent_only": negative_keywords_low_intent_only,
    }
    run_signature = hashlib.sha256(
        f"{file_hash}:{json.dumps(run_config, sort_keys=True)}".encode("utf-8")
    ).hexdigest()
    cached_result = st.session_state.get("last_run_result")
    has_cached_result = bool(cached_result and cached_result.get("run_signature") == run_signature)

    try:
        # Initialize optimizer from file bytes so reruns are deterministic.
        optimizer = BulkOptimizer(
            BytesIO(uploaded_bytes),
            filename=uploaded_file.name,
            target_acos=target_acos,
            min_bid=min_bid,
            max_bid=max_bid,
            enforce_48hr_rule=False,
            optimization_min_clicks=optimization_min_clicks,
            max_bid_change_pct=max_bid_change_pct,
            bleeder_type_a_impressions_threshold=bleeder_type_a_impressions_threshold,
            bleeder_type_a_z_threshold=bleeder_type_a_z_threshold,
            bleeder_type_b_clicks_std_multiplier=bleeder_type_b_clicks_std_multiplier,
            bleeder_type_c_impressions_threshold=bleeder_type_c_impressions_threshold,
            bleeder_type_c_mode=bleeder_type_c_mode,
            bleeder_type_c_percentile=bleeder_type_c_percentile,
            bleeder_type_c_z_threshold=bleeder_type_c_z_threshold,
            bleeder_segmentation_mode=bleeder_segmentation_mode,
            segmentation_min_entities=int(segmentation_min_entities),
            confidence_enable=confidence_enable,
            type_a_confidence_level=type_a_confidence_level,
            type_b_min_spend=type_b_min_spend,
            cold_start_step_up_amount=cold_start_step_up_amount,
            cold_start_enable=cold_start_enable,
            cold_start_mode=cold_start_mode,
            cold_start_ladder_cap=cold_start_ladder_cap,
            cold_start_stalled_impressions=int(cold_start_stalled_impressions),
        )

        # 48-hour file freshness advisory (warning only).
        warning = optimizer.check_48_hour_rule()
        if warning:
            st.warning(warning)
        else:
            st.success("File date check passed (or no date found in filename).")

        run_clicked = st.button("Run Optimization")
        if run_clicked:
            progress_bar = st.progress(0)
            status_text = st.empty()
            stage_timings = {}
            run_start = time.perf_counter()

            try:
                # Step 1: Load Data
                status_text.text("Loading bulk file...")
                progress_bar.progress(20)
                step_start = time.perf_counter()
                optimizer.load_data()
                stage_timings['load_data'] = time.perf_counter() - step_start

                # Step 2: RPC Optimization
                status_text.text("Running RPC bid optimization...")
                progress_bar.progress(40)
                step_start = time.perf_counter()
                bid_changes = optimizer.optimize_bids()
                stage_timings['optimize_bids'] = time.perf_counter() - step_start

                # Step 3: Bleeder Detection
                status_text.text("Identifying low-performance patterns...")
                progress_bar.progress(50)
                step_start = time.perf_counter()
                bleeder_results = optimizer.identify_bleeders()
                stage_timings['identify_bleeders'] = time.perf_counter() - step_start

                # Step 4: Structural Analysis (Phase 2)
                status_text.text("Running structural analysis (cannibalization & budgets)...")
                progress_bar.progress(60)
                step_start = time.perf_counter()
                cannibalization = optimizer.detect_cannibalization()
                budget_recs = optimizer.optimize_budgets()
                stage_timings['structural_analysis'] = time.perf_counter() - step_start

                # Step 5: NLP Analysis (Phase 3)
                progress_bar.progress(70)
                if run_nlp_analysis:
                    status_text.text("Running NLP analysis (product targets & search term clustering)...")
                    step_start = time.perf_counter()
                    product_target_results = optimizer.analyze_product_targets()
                    search_term_clusters = optimizer.cluster_search_terms()
                    stage_timings['nlp_analysis'] = time.perf_counter() - step_start
                else:
                    status_text.text("Skipping NLP analysis...")
                    product_target_results = {
                        "bleeder_counts": {"type_a": 0, "type_b": 0, "type_c": 0, "type_d": 0},
                        "negative_recommendations": pd.DataFrame(),
                        "performance_analysis": pd.DataFrame(),
                        "savings_estimate": 0,
                    }
                    search_term_clusters = {"clusters": pd.DataFrame(), "cluster_summary": pd.DataFrame(), "n_clusters": 0}
                    stage_timings['nlp_analysis'] = 0.0

                # Step 6: Validation
                status_text.text("Validating output...")
                progress_bar.progress(80)
                step_start = time.perf_counter()
                is_valid, error_msg = optimizer.validate_output()
                stage_timings['validate_output'] = time.perf_counter() - step_start
                if not is_valid:
                    st.error(f"Validation failed: {error_msg}")
                    st.stop()

                # Step 7: Save files
                status_text.text("Generating output files...")
                progress_bar.progress(85)
                step_start = time.perf_counter()

                # Generate Amazon upload file (clean, no analysis sheets)
                amazon_output = BytesIO()
                optimizer.save_optimized_file(amazon_output, include_analysis_sheets=False, amazon_upload_ready=True)
                amazon_output.seek(0)

                # Generate full analysis file (with all reports)
                analysis_output = BytesIO()
                optimizer.save_optimized_file(
                    analysis_output,
                    include_analysis_sheets=True,
                    amazon_upload_ready=False,
                    cannibalization_report=cannibalization,
                    budget_report=budget_recs,
                )
                analysis_output.seek(0)

                # Generate Phase 3 negative recommendation files
                status_text.text("Generating negative keyword recommendations...")
                progress_bar.progress(92)

                # Negative Product Targets
                negative_products_output = BytesIO()
                optimizer.export_negative_product_targets_bulk_file(
                    product_target_results['negative_recommendations'],
                    negative_products_output
                )
                negative_products_output.seek(0)

                # Negative Keywords
                negative_keywords_output = BytesIO()
                optimizer.export_negative_keywords_bulk_file(
                    search_term_clusters,
                    negative_keywords_output,
                    require_low_intent_cluster=negative_keywords_low_intent_only,
                )
                negative_keywords_output.seek(0)
                stage_timings['generate_outputs'] = time.perf_counter() - step_start
                stage_timings['total_runtime'] = time.perf_counter() - run_start

                for stage_name, duration in stage_timings.items():
                    optimizer.record_stage_timing(stage_name, duration)

                progress_bar.progress(100)
                status_text.text("Complete!")

                st.success("Optimization Complete!")

                # Display metrics - Core Optimization
                st.subheader("Core Optimization Results")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("RPC Bid Updates", bid_changes)
                col2.metric("Low Engagement", bleeder_results['type_a'], help="High impressions and low CTR outliers")
                col3.metric("High-Cost Non-Converters", bleeder_results['type_b'], help="High-click terms with zero sales")
                col4.metric("Low Visibility", bleeder_results['type_c'], help="Low-volume terms flagged for testing")
                st.metric(
                    "Cold-Start Step-Ups",
                    bleeder_results.get('cold_start_stepups', 0),
                    help="Low-volume zero-click terms with +$0.02 (or configured) bid increase",
                )
                if bleeder_results.get('cold_start_stalled', 0) > 0:
                    st.caption(
                        f"Stalled No-Click Terms Flagged: {bleeder_results.get('cold_start_stalled', 0)}"
                    )

                with st.expander("View Bid Optimization Details"):
                    if optimizer.df is not None:
                        if 'Operation' in optimizer.df.columns:
                            updated_rows = optimizer.df[optimizer.df['Operation'] == 'Update'].copy()
                        else:
                            updated_rows = pd.DataFrame()
                        if updated_rows.empty:
                            st.info("No bid updates were applied in this run.")
                        else:
                            def first_non_empty(df, candidates):
                                result = pd.Series("", index=df.index, dtype="object")
                                for col in candidates:
                                    if col in df.columns:
                                        candidate = (
                                            df[col]
                                            .fillna("")
                                            .astype(str)
                                            .str.strip()
                                            .replace({"nan": "", "NaN": "", "None": "", "none": ""})
                                        )
                                        result = result.where(result != "", candidate)
                                return result

                            display_df = pd.DataFrame(index=updated_rows.index)
                            display_df["Campaign"] = first_non_empty(
                                updated_rows,
                                ["Campaign Name", "Campaign Name (Informational only)"],
                            )
                            display_df["Ad Group"] = first_non_empty(
                                updated_rows,
                                ["Ad Group Name", "Ad Group Name (Informational only)"],
                            )
                            display_df["Target"] = first_non_empty(
                                updated_rows,
                                [
                                    "Keyword Text",
                                    "Product Targeting Expression",
                                    "Keyword or Product Targeting",
                                    "Resolved Product Targeting Expression (Informational only)",
                                ],
                            )
                            display_df["Entity"] = first_non_empty(updated_rows, ["Entity"])
                            display_df["Match Type"] = first_non_empty(updated_rows, ["Match Type"])
                            display_df["Impressions"] = updated_rows.get("Impressions", 0)
                            display_df["Clicks"] = updated_rows.get("Clicks", 0)
                            display_df["Spend"] = updated_rows.get("Spend", 0)
                            display_df["Sales"] = updated_rows.get("Sales", 0)
                            display_df["Bid"] = updated_rows.get("Bid", 0)
                            display_df["Classification"] = first_non_empty(updated_rows, ["Bleeder_Type"])

                            # Fallback label if target text is unavailable.
                            display_df["Target"] = display_df["Target"].where(
                                display_df["Target"].str.strip() != "",
                                "(target not provided in source row)",
                            )

                            if 'Spend' in updated_rows.columns:
                                display_df = display_df.sort_values('Spend', ascending=False)
                            st.dataframe(display_df.head(200), use_container_width=True)
                            st.caption(f"Showing top {min(200, len(updated_rows))} of {len(updated_rows)} updated rows.")

                # Display metrics - Structural Analysis (Phase 2)
                st.subheader("Structural Analysis (Phase 2)")
                col5, col6 = st.columns(2)

                cannibalization_count = len(cannibalization) if not cannibalization.empty else 0
                col5.metric(
                    "Cannibalization Issues",
                    cannibalization_count,
                    help="Keywords appearing in multiple ad groups (internal competition)"
                )

                campaign_count = len(budget_recs) if not budget_recs.empty else 0
                col6.metric(
                    "Campaigns Analyzed",
                    campaign_count,
                    help="Campaigns with budget recommendations based on ROAS"
                )

                # Cannibalization Details
                if not cannibalization.empty:
                    with st.expander(f"⚠️ View Cannibalization Report ({len(cannibalization)} issues found)"):
                        st.warning("These keywords appear in multiple ad groups and may be competing against each other:")
                        # Show top 10 by severity
                        display_cols = [col for col in ['Normalized_Keyword', 'Ad_Group_Count', 'Total_Spend', 'ACOS', 'Bid_Variance']
                                       if col in cannibalization.columns]
                        st.dataframe(cannibalization[display_cols].head(10), use_container_width=True)
                        st.info("Full report available in 'Cannibalization Report' sheet of downloaded file.")

                # Budget Recommendations
                if not budget_recs.empty:
                    with st.expander(f"💰 View Budget Recommendations ({len(budget_recs)} campaigns)"):
                        # Show summary by category
                        if 'Category' in budget_recs.columns:
                            category_counts = budget_recs['Category'].value_counts()
                            st.write("**Campaign Performance Breakdown:**")
                            for category, count in category_counts.items():
                                st.write(f"- {category}: {count} campaigns")

                        # Show top and bottom performers
                        st.write("**Top 5 Performers (Highest ROAS):**")
                        display_cols = [col for col in ['Campaign Name', 'ROAS', 'ACOS', 'Spend', 'Sales', 'Recommendation']
                                       if col in budget_recs.columns]
                        st.dataframe(budget_recs[display_cols].head(5), use_container_width=True)

                        st.write("**Bottom 5 Performers (Lowest ROAS):**")
                        st.dataframe(budget_recs[display_cols].tail(5), use_container_width=True)

                        st.info("Full recommendations available in 'Budget Recommendations' sheet of downloaded file.")

                # Display metrics - NLP Analysis (Phase 3)
                st.subheader("NLP Analysis (Phase 3)")
                col7, col8, col9, col10 = st.columns(4)

                product_bleeder_counts = product_target_results.get('bleeder_counts', {})
                n_clusters = search_term_clusters.get('n_clusters', 0)
                savings_estimate = product_target_results.get('savings_estimate', 0)
                negative_product_count = len(product_target_results.get('negative_recommendations', pd.DataFrame()))

                col7.metric(
                    "Product Target Bleeders",
                    product_bleeder_counts.get('type_b', 0),
                    help="Non-converting ASINs recommended for negative targeting"
                )

                col8.metric(
                    "Intent Clusters Found",
                    n_clusters,
                    help="Search terms grouped by customer intent using NLP"
                )

                col9.metric(
                    "Negative Recommendations",
                    negative_product_count,
                    help="Total ASINs recommended for negative targeting"
                )

                col10.metric(
                    "Est. Monthly Savings",
                    f"${savings_estimate:,.0f}",
                    help="Estimated monthly savings from blocking wasteful ASINs"
                )

                append_run_history(
                    {
                        "mode": "ui",
                        "input_file": uploaded_file.name,
                        "status": "ok",
                        "error": "",
                        "bid_updates": int(bid_changes),
                        "type_a_bleeders": int(bleeder_results.get("type_a", 0)),
                        "type_b_bleeders": int(bleeder_results.get("type_b", 0)),
                        "type_c_bleeders": int(bleeder_results.get("type_c", 0)),
                        "cannibalization_issues": int(cannibalization_count),
                        "campaigns_analyzed": int(campaign_count),
                        "intent_clusters": int(n_clusters),
                        "negative_recommendations": int(negative_product_count),
                        "runtime_seconds": round(float(stage_timings.get("total_runtime", 0.0)), 2),
                    },
                    history_path=history_path,
                )

                if not run_nlp_analysis:
                    st.info("NLP analysis is disabled for this run. Enable 'Run NLP Analysis' in the sidebar for clustering and negative recommendations.")

                # Product Target Analysis Details
                product_analysis_df = product_target_results.get('performance_analysis', pd.DataFrame())
                if not product_analysis_df.empty and product_bleeder_counts.get('type_b', 0) > 0:
                    with st.expander(f"🎯 View Product Target Bleeders ({product_bleeder_counts.get('type_b', 0)} ASINs)"):
                        st.warning("These ASINs are getting clicks but no conversions - recommend adding to negative targeting:")

                        # Show Type B bleeders (highest priority)
                        type_b_bleeders = product_analysis_df[product_analysis_df['Bleeder_Type'] == 'Type B: Non-Converting']
                        if not type_b_bleeders.empty:
                            display_cols = [col for col in ['Customer Search Term', 'Clicks', 'Spend', 'Sales', 'ACOS', 'Conversion Rate', 'Severity_Score']
                                           if col in type_b_bleeders.columns]
                            st.dataframe(type_b_bleeders[display_cols].head(10), use_container_width=True)
                            st.info("Download 'Negative Product Targets' file to upload these to Amazon.")

                # Search Term Clustering Details
                cluster_summary = search_term_clusters.get('cluster_summary', pd.DataFrame())
                if not cluster_summary.empty:
                    with st.expander(f"🔍 View Intent Clusters ({n_clusters} clusters)"):
                        st.write("**Search terms grouped by customer intent:**")

                        # Show cluster performance
                        display_cols = [col for col in ['Term_Count', 'Spend', 'Sales', 'ROAS', 'ACOS', 'CTR', 'Performance_Category', 'Representative_Terms']
                                       if col in cluster_summary.columns]
                        st.dataframe(cluster_summary[display_cols], use_container_width=True)

                        # Highlight insights
                        high_perf = cluster_summary[cluster_summary['Performance_Category'] == 'High-Performing Intent']
                        low_perf = cluster_summary[cluster_summary['Performance_Category'] == 'Low-Performing Intent']

                        if not high_perf.empty:
                            st.success(f"**{len(high_perf)} high-performing intents** - Consider scaling these search term themes!")
                        if not low_perf.empty:
                            st.warning(f"**{len(low_perf)} low-performing intents** - Consider adding these to negative keywords")

                # Show optimization log
                with st.expander("Performance Metrics"):
                    perf_df = pd.DataFrame(
                        [{'Stage': stage, 'Seconds': round(seconds, 2)} for stage, seconds in stage_timings.items()]
                    )
                    st.dataframe(perf_df, use_container_width=True, hide_index=True)

                with st.expander("View Optimization Log"):
                    st.code(optimizer.get_optimization_log(), language=None)

                with st.expander("Historical Run Tracking"):
                    history_df = load_run_history(history_path=history_path)
                    if history_df.empty:
                        st.info("No historical runs recorded yet.")
                    else:
                        history_df = history_df.sort_values("timestamp", ascending=False)
                        st.dataframe(history_df.head(20), use_container_width=True, hide_index=True)

                        successful = history_df[history_df["status"] == "ok"].copy()
                        if len(successful) >= 2:
                            latest = successful.iloc[0]
                            previous = successful.iloc[1]
                            st.write("**Latest vs Previous Successful Run**")
                            col_hist1, col_hist2, col_hist3 = st.columns(3)
                            col_hist1.metric(
                                "Bid Updates Delta",
                                int(latest["bid_updates"]),
                                int(latest["bid_updates"] - previous["bid_updates"]),
                            )
                            col_hist2.metric(
                                "Bleeders Delta",
                                int(latest["type_a_bleeders"] + latest["type_b_bleeders"] + latest["type_c_bleeders"]),
                                int(
                                    (latest["type_a_bleeders"] + latest["type_b_bleeders"] + latest["type_c_bleeders"])
                                    - (previous["type_a_bleeders"] + previous["type_b_bleeders"] + previous["type_c_bleeders"])
                                ),
                            )
                            col_hist3.metric(
                                "Runtime Delta (s)",
                                round(float(latest["runtime_seconds"]), 2),
                                round(float(latest["runtime_seconds"] - previous["runtime_seconds"]), 2),
                            )

                        alerts = calculate_drift_alerts(history_df)
                        if alerts:
                            st.warning("Potential model/output drift detected (vs recent baseline):")
                            drift_df = pd.DataFrame(alerts)
                            st.dataframe(drift_df, use_container_width=True, hide_index=True)

                # Generate markdown report
                markdown_report = optimizer.generate_markdown_report(
                    include_nlp=run_nlp_analysis,
                    cannibalization=cannibalization,
                    budget_recs=budget_recs,
                    product_results=product_target_results,
                    cluster_results=search_term_clusters,
                )

                # Download buttons
                st.subheader("Download Files")
                timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')

                # Row 1: Core optimization files
                col_dl1, col_dl2, col_dl3 = st.columns(3)

                with col_dl1:
                    st.download_button(
                        label="Amazon Upload",
                        data=amazon_output,
                        file_name=f"amazon_upload_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        on_click="ignore",
                        use_container_width=True,
                        help="Upload-ready file with updated entries only (non-updated rows removed)."
                    )
                    st.caption("⬆️ For Amazon upload")

                with col_dl2:
                    st.download_button(
                        label="Analysis Report",
                        data=markdown_report,
                        file_name=f"optimization_report_{timestamp}.md",
                        mime="text/markdown",
                        on_click="ignore",
                        use_container_width=True,
                        help="Human-readable optimization report with all insights and recommendations."
                    )
                    st.caption("📄 Markdown report")

                with col_dl3:
                    st.download_button(
                        label="Full Excel File",
                        data=analysis_output,
                        file_name=f"full_analysis_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        on_click="ignore",
                        use_container_width=True,
                        help="Complete Excel file with all sheets including Test More Report and Budget Recommendations."
                    )
                    st.caption("📊 Complete data")

                # Unified upload bundle options
                st.write("")  # Spacing
                st.markdown("**Unified Upload File**")
                st.caption(
                    "Bundle contents are controlled in the sidebar under 'Unified Download'."
                )

                # Build combined workbook based on selected components.
                combined_output = BytesIO()
                included_parts = []

                amazon_bids_df = _read_excel_sheet_from_buffer(amazon_output, "Sponsored Products Campaigns")
                negative_products_df = _read_excel_sheet_from_buffer(negative_products_output, "Negative Product Targets")
                negative_keywords_df = _read_excel_sheet_from_buffer(negative_keywords_output, "Negative Keywords")
                campaign_sheet_df = optimizer.original_sheets.get("Sponsored Products Campaigns", pd.DataFrame()).copy()
                budget_updates_df = _build_budget_updates_upload_df(campaign_sheet_df, budget_recs)

                with pd.ExcelWriter(combined_output, engine="xlsxwriter") as writer:
                    if bundle_include_bids:
                        amazon_bids_df.to_excel(
                            writer,
                            sheet_name=_safe_sheet_name("Sponsored Products Campaigns"),
                            index=False,
                        )
                        included_parts.append(f"Bid Updates ({len(amazon_bids_df)})")
                    if bundle_include_negative_products:
                        negative_products_df.to_excel(
                            writer,
                            sheet_name=_safe_sheet_name("Negative Product Targets"),
                            index=False,
                        )
                        included_parts.append(f"Negative Products ({len(negative_products_df)})")
                    if bundle_include_negative_keywords:
                        negative_keywords_df.to_excel(
                            writer,
                            sheet_name=_safe_sheet_name("Negative Keywords"),
                            index=False,
                        )
                        included_parts.append(f"Negative Keywords ({len(negative_keywords_df)})")
                    if bundle_include_budget_updates:
                        budget_updates_df.to_excel(
                            writer,
                            sheet_name=_safe_sheet_name("SP Campaign Budgets"),
                            index=False,
                        )
                        included_parts.append(f"Budget Updates ({len(budget_updates_df)})")

                    if not included_parts:
                        pd.DataFrame({"Info": ["No sections selected for export"]}).to_excel(
                            writer, sheet_name="Read Me", index=False
                        )

                combined_output.seek(0)

                col_dl4, col_dl5 = st.columns(2)
                with col_dl4:
                    st.download_button(
                        label="Unified Upload Bundle",
                        data=combined_output,
                        file_name=f"amazon_unified_upload_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        on_click="ignore",
                        use_container_width=True,
                        help="Single workbook with selected sections: bids, negatives, and optional budget updates.",
                    )
                    if included_parts:
                        st.caption(" + ".join(included_parts))
                    else:
                        st.caption("No sections selected")

                with col_dl5:
                    st.download_button(
                        label="Optimization Log",
                        data=optimizer.get_optimization_log(),
                        file_name=f"optimization_log_{timestamp}.txt",
                        mime="text/plain",
                        on_click="ignore",
                        use_container_width=True,
                        help="Plain-text audit log with timestamped optimization events."
                    )
                    st.caption("🧾 Audit log export")

                # Info messages
                info_messages = []
                if bleeder_results['type_c'] > 0:
                    info_messages.append(f"{bleeder_results['type_c']} low-visibility terms flagged in 'Test More Report' sheet")
                if bleeder_results.get('cold_start_stepups', 0) > 0:
                    info_messages.append(f"{bleeder_results['cold_start_stepups']} low-volume terms received cold-start bid step-up")
                if bleeder_results.get('cold_start_stalled', 0) > 0:
                    info_messages.append(
                        f"{bleeder_results['cold_start_stalled']} stalled no-click terms flagged for negate/pause review"
                    )
                if cannibalization_count > 0:
                    info_messages.append(f"{cannibalization_count} cannibalization issues found in 'Cannibalization Report' sheet")
                if campaign_count > 0:
                    info_messages.append(f"{campaign_count} campaigns analyzed in 'Budget Recommendations' sheet")
                if negative_product_count > 0:
                    info_messages.append(f"{negative_product_count} product targets recommended for negative targeting (Phase 3)")
                if n_clusters > 0:
                    info_messages.append(f"{n_clusters} search term intent clusters identified using NLP (Phase 3)")

                if info_messages:
                    st.info("Additional insights included:\n" + "\n".join(f"- {msg}" for msg in info_messages))

                st.session_state["last_run_result"] = {
                    "run_signature": run_signature,
                    "timestamp": timestamp,
                    "uploaded_file_name": uploaded_file.name,
                    "bid_changes": int(bid_changes),
                    "bleeder_results": bleeder_results,
                    "cannibalization_count": int(cannibalization_count),
                    "campaign_count": int(campaign_count),
                    "negative_product_count": int(negative_product_count),
                    "n_clusters": int(n_clusters),
                    "savings_estimate": float(savings_estimate),
                    "run_nlp_analysis": bool(run_nlp_analysis),
                    "info_messages": info_messages,
                    "stage_timings": stage_timings,
                    "amazon_output_bytes": amazon_output.getvalue(),
                    "analysis_output_bytes": analysis_output.getvalue(),
                    "negative_products_output_bytes": negative_products_output.getvalue(),
                    "negative_keywords_output_bytes": negative_keywords_output.getvalue(),
                    "markdown_report": markdown_report,
                    "optimization_log": optimizer.get_optimization_log(),
                    "budget_updates_df": budget_updates_df,
                }

            except Exception as e:
                append_run_history(
                    {
                        "mode": "ui",
                        "input_file": uploaded_file.name,
                        "status": "failed",
                        "error": str(e),
                    },
                    history_path=history_path,
                )
                st.error(f"An error occurred: {e}")
                st.stop()

        if (not run_clicked) and has_cached_result:
            cached = cached_result
            st.success("Showing cached optimization results for the current file and settings.")
            st.caption("Run Optimization again only when you change thresholds, NLP mode, or input file.")

            st.subheader("Core Optimization Results")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("RPC Bid Updates", cached.get("bid_changes", 0))
            bleeder = cached.get("bleeder_results", {})
            col2.metric("Low Engagement", bleeder.get("type_a", 0))
            col3.metric("High-Cost Non-Converters", bleeder.get("type_b", 0))
            col4.metric("Low Visibility", bleeder.get("type_c", 0))

            st.subheader("NLP/Structure Snapshot")
            col5, col6, col7, col8 = st.columns(4)
            col5.metric("Cannibalization Issues", cached.get("cannibalization_count", 0))
            col6.metric("Campaigns Analyzed", cached.get("campaign_count", 0))
            col7.metric("Negative Recommendations", cached.get("negative_product_count", 0))
            col8.metric("Intent Clusters", cached.get("n_clusters", 0))

            st.subheader("Download Files")
            timestamp = cached.get("timestamp", pd.Timestamp.now().strftime('%Y%m%d_%H%M%S'))
            amazon_output = BytesIO(cached.get("amazon_output_bytes", b""))
            analysis_output = BytesIO(cached.get("analysis_output_bytes", b""))
            negative_products_output = BytesIO(cached.get("negative_products_output_bytes", b""))
            negative_keywords_output = BytesIO(cached.get("negative_keywords_output_bytes", b""))
            markdown_report = cached.get("markdown_report", "")

            col_dl1, col_dl2, col_dl3 = st.columns(3)
            with col_dl1:
                st.download_button(
                    label="Amazon Upload",
                    data=amazon_output,
                    file_name=f"amazon_upload_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    on_click="ignore",
                    use_container_width=True,
                    help="Cached upload-ready file with updated entries only.",
                )
                st.caption("⬆️ For Amazon upload")
            with col_dl2:
                st.download_button(
                    label="Analysis Report",
                    data=markdown_report,
                    file_name=f"optimization_report_{timestamp}.md",
                    mime="text/markdown",
                    on_click="ignore",
                    use_container_width=True,
                    help="Cached markdown report.",
                )
                st.caption("📄 Markdown report")
            with col_dl3:
                st.download_button(
                    label="Full Excel File",
                    data=analysis_output,
                    file_name=f"full_analysis_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    on_click="ignore",
                    use_container_width=True,
                    help="Cached full Excel analysis output.",
                )
                st.caption("📊 Complete data")

            # Unified bundle from cached outputs.
            combined_output = BytesIO()
            included_parts = []
            amazon_bids_df = _read_excel_sheet_from_buffer(amazon_output, "Sponsored Products Campaigns")
            negative_products_df = _read_excel_sheet_from_buffer(negative_products_output, "Negative Product Targets")
            negative_keywords_df = _read_excel_sheet_from_buffer(negative_keywords_output, "Negative Keywords")
            budget_updates_df = cached.get("budget_updates_df", pd.DataFrame())
            if not isinstance(budget_updates_df, pd.DataFrame):
                budget_updates_df = pd.DataFrame()

            with pd.ExcelWriter(combined_output, engine="xlsxwriter") as writer:
                if bundle_include_bids:
                    amazon_bids_df.to_excel(
                        writer,
                        sheet_name=_safe_sheet_name("Sponsored Products Campaigns"),
                        index=False,
                    )
                    included_parts.append(f"Bid Updates ({len(amazon_bids_df)})")
                if bundle_include_negative_products:
                    negative_products_df.to_excel(
                        writer,
                        sheet_name=_safe_sheet_name("Negative Product Targets"),
                        index=False,
                    )
                    included_parts.append(f"Negative Products ({len(negative_products_df)})")
                if bundle_include_negative_keywords:
                    negative_keywords_df.to_excel(
                        writer,
                        sheet_name=_safe_sheet_name("Negative Keywords"),
                        index=False,
                    )
                    included_parts.append(f"Negative Keywords ({len(negative_keywords_df)})")
                if bundle_include_budget_updates:
                    budget_updates_df.to_excel(
                        writer,
                        sheet_name=_safe_sheet_name("SP Campaign Budgets"),
                        index=False,
                    )
                    included_parts.append(f"Budget Updates ({len(budget_updates_df)})")
                if not included_parts:
                    pd.DataFrame({"Info": ["No sections selected for export"]}).to_excel(
                        writer, sheet_name="Read Me", index=False
                    )

            combined_output.seek(0)
            col_dl4, col_dl5 = st.columns(2)
            with col_dl4:
                st.download_button(
                    label="Unified Upload Bundle",
                    data=combined_output,
                    file_name=f"amazon_unified_upload_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    on_click="ignore",
                    use_container_width=True,
                    help="Single workbook with selected sections using cached run outputs.",
                )
                if included_parts:
                    st.caption(" + ".join(included_parts))
                else:
                    st.caption("No sections selected")
            with col_dl5:
                st.download_button(
                    label="Optimization Log",
                    data=cached.get("optimization_log", ""),
                    file_name=f"optimization_log_{timestamp}.txt",
                    mime="text/plain",
                    on_click="ignore",
                    use_container_width=True,
                    help="Cached optimization log from the latest run.",
                )
                st.caption("🧾 Audit log export")

            cached_info = cached.get("info_messages", [])
            if cached_info:
                st.info("Additional insights included:\n" + "\n".join(f"- {msg}" for msg in cached_info))

    except Exception as e:
        append_run_history(
            {
                "mode": "ui",
                "input_file": uploaded_file.name,
                "status": "failed",
                "error": str(e),
            },
            history_path=history_path,
        )
        st.error(f"An error occurred: {e}")
