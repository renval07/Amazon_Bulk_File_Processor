import streamlit as st
import pandas as pd
import os
import sys
import time
from io import BytesIO

# Add src to path to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from optimizer import BulkOptimizer

st.set_page_config(page_title="Amazon PPC Bulk Optimizer", layout="wide")

st.title("Amazon PPC Bulk Optimizer")
st.markdown("Automate your Amazon PPC bid management using Revenue-Per-Click (RPC) and Z-Score statistical optimization.")

# Sidebar Configuration
st.sidebar.header("Configuration")
target_acos = st.sidebar.slider("Target ACOS (%)", 5, 100, 30) / 100.0
min_bid = st.sidebar.number_input("Min Bid ($)", value=0.10, step=0.01)
max_bid = st.sidebar.number_input("Max Bid ($)", value=5.00, step=0.10)

st.sidebar.header("Safety Settings")
enforce_48hr = st.sidebar.checkbox(
    "Enforce 48-Hour Rule",
    value=True,
    help="Block optimization if file data is less than 48 hours old (recommended to avoid incomplete attribution)"
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
        "Type A Min Impressions",
        min_value=0,
        value=1000,
        step=50,
        help="Minimum impressions before low-CTR Type A bleeder logic is applied.",
    )
    bleeder_type_a_z_threshold = st.slider(
        "Type A Z-Score Threshold",
        min_value=-4.0,
        max_value=0.0,
        value=-1.5,
        step=0.1,
        help="More negative is stricter. Terms below this Z-score are considered low CTR outliers.",
    )
    bleeder_type_b_clicks_std_multiplier = st.slider(
        "Type B Click StdDev Multiplier",
        min_value=0.5,
        max_value=5.0,
        value=2.0,
        step=0.1,
        help="Higher values are stricter for click-heavy zero-sale Type B bleeders.",
    )
    bleeder_type_c_impressions_threshold = st.number_input(
        "Type C Max Impressions",
        min_value=1,
        value=100,
        step=10,
        help="Terms below this impression count are flagged as ghost keywords (Type C).",
    )

uploaded_file = st.file_uploader("Upload Bulk File (.xlsx)", type=["xlsx"])

if uploaded_file:
    st.info(f"Loaded: {uploaded_file.name}")
    
    try:
        # Initialize Optimizer with the file-like object directly
        optimizer = BulkOptimizer(
            uploaded_file,
            filename=uploaded_file.name,
            target_acos=target_acos,
            min_bid=min_bid,
            max_bid=max_bid,
            enforce_48hr_rule=enforce_48hr,
            optimization_min_clicks=optimization_min_clicks,
            max_bid_change_pct=max_bid_change_pct,
            bleeder_type_a_impressions_threshold=bleeder_type_a_impressions_threshold,
            bleeder_type_a_z_threshold=bleeder_type_a_z_threshold,
            bleeder_type_b_clicks_std_multiplier=bleeder_type_b_clicks_std_multiplier,
            bleeder_type_c_impressions_threshold=bleeder_type_c_impressions_threshold,
        )

        # 48-Hour Rule Check
        try:
            warning = optimizer.check_48_hour_rule()
            if warning:
                st.warning(warning)
            else:
                st.success("File date check passed (or no date found in filename).")
        except ValueError as e:
            st.error(str(e))
            st.info("Tip: You can disable the 48-hour rule in Safety Settings (not recommended).")
            st.stop()

        if st.button("Run Optimization"):
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
                status_text.text("Identifying bleeders (Z-Score analysis)...")
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
                status_text.text("Running NLP analysis (product targets & search term clustering)...")
                progress_bar.progress(70)
                step_start = time.perf_counter()
                product_target_results = optimizer.analyze_product_targets()
                search_term_clusters = optimizer.cluster_search_terms()
                stage_timings['nlp_analysis'] = time.perf_counter() - step_start

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
                optimizer.save_optimized_file(analysis_output, include_analysis_sheets=True, amazon_upload_ready=False)
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
                    negative_keywords_output
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
                col2.metric("Type A Bleeders", bleeder_results['type_a'], help="Low CTR (Impression Bloat)")
                col3.metric("Type B Bleeders", bleeder_results['type_b'], help="High Clicks, Zero Sales")
                col4.metric("Type C Ghosts", bleeder_results['type_c'], help="Low Volume (flagged for testing)")

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

                # Generate markdown report
                markdown_report = optimizer.generate_markdown_report()

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
                        use_container_width=True,
                        help="Clean file with only Amazon-recognized sheets. Upload this to Amazon Seller Central."
                    )
                    st.caption("⬆️ For Amazon upload")

                with col_dl2:
                    st.download_button(
                        label="Analysis Report",
                        data=markdown_report,
                        file_name=f"optimization_report_{timestamp}.md",
                        mime="text/markdown",
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
                        use_container_width=True,
                        help="Complete Excel file with all sheets including Test More Report and Budget Recommendations."
                    )
                    st.caption("📊 Complete data")

                # Row 2: Phase 3 negative recommendation files
                st.write("")  # Spacing
                col_dl4, col_dl5, col_dl6 = st.columns(3)

                with col_dl4:
                    st.download_button(
                        label="Negative Product Targets",
                        data=negative_products_output,
                        file_name=f"negative_product_targets_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        help="ASINs to add to negative product targeting. Upload to Amazon to block wasteful product targets."
                    )
                    st.caption("🚫 Block wasteful ASINs")

                with col_dl5:
                    st.download_button(
                        label="Negative Keywords",
                        data=negative_keywords_output,
                        file_name=f"negative_keywords_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        help="Search terms to add to negative keywords. Upload to Amazon to block wasteful search traffic."
                    )
                    st.caption("🚫 Block wasteful terms")

                with col_dl6:
                    st.download_button(
                        label="Optimization Log",
                        data=optimizer.get_optimization_log(),
                        file_name=f"optimization_log_{timestamp}.txt",
                        mime="text/plain",
                        use_container_width=True,
                        help="Plain-text audit log with timestamped optimization events."
                    )
                    st.caption("🧾 Audit log export")

                # Info messages
                info_messages = []
                if bleeder_results['type_c'] > 0:
                    info_messages.append(f"{bleeder_results['type_c']} ghost keywords (Type C) flagged in 'Test More Report' sheet")
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

            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.stop()
                
    except Exception as e:
        st.error(f"An error occurred: {e}")
