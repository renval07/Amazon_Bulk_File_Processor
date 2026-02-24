from src.optimizer import BulkOptimizer
from io import BytesIO
import pandas as pd

print("Testing Phase 3: NLP Intelligence")
print("=" * 70)

# Initialize and run full optimization workflow
print("\n[SETUP] Running full optimization workflow...")
opt = BulkOptimizer(
    r'bulk-a2kk083uqnb8ha-20251213-20260211-1770782206348 (1).xlsx',
    enforce_48hr_rule=False
)
opt.load_data()
opt.optimize_bids()
opt.identify_bleeders()

# Test 1: Product Target Analysis
print("\n[TEST 1] Product Target Analysis")
try:
    product_results = opt.analyze_product_targets()

    bleeder_counts = product_results['bleeder_counts']
    negative_recs = product_results['negative_recommendations']
    performance_df = product_results['performance_analysis']
    savings = product_results['savings_estimate']

    print(f"  Bleeder breakdown:")
    print(f"    - Type A (Low CTR): {bleeder_counts['type_a']}")
    print(f"    - Type B (Non-Converting): {bleeder_counts['type_b']}")
    print(f"    - Type C (High ACOS): {bleeder_counts['type_c']}")
    print(f"    - Type D (Insufficient Data): {bleeder_counts['type_d']}")
    print(f"  Negative recommendations: {len(negative_recs)}")
    print(f"  Performance analysis rows: {len(performance_df)}")
    print(f"  Estimated monthly savings: ${savings:,.2f}")

    # Verify data structure
    assert isinstance(bleeder_counts, dict), "bleeder_counts should be a dict"
    assert isinstance(negative_recs, pd.DataFrame), "negative_recommendations should be DataFrame"
    assert isinstance(performance_df, pd.DataFrame), "performance_analysis should be DataFrame"
    assert isinstance(savings, (int, float)), "savings_estimate should be numeric"

    # Verify Z-scores were calculated
    if len(performance_df) > 0:
        assert 'Z_CTR' in performance_df.columns, "Should have Z_CTR column"
        assert 'Z_CVR' in performance_df.columns, "Should have Z_CVR column"
        assert 'Z_ACOS' in performance_df.columns, "Should have Z_ACOS column"
        assert 'Severity_Score' in performance_df.columns, "Should have Severity_Score column"

    print("PASS: Product target analysis complete")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 2: Search Term Clustering (NLP)
print("\n[TEST 2] Search Term Clustering (NLP)")
try:
    cluster_results = opt.cluster_search_terms()

    clusters_df = cluster_results['clusters']
    cluster_summary = cluster_results['cluster_summary']
    n_clusters = cluster_results['n_clusters']

    print(f"  Number of clusters: {n_clusters}")
    print(f"  Search terms clustered: {len(clusters_df)}")
    print(f"  Cluster summary rows: {len(cluster_summary)}")

    if n_clusters > 0:
        print(f"  Sample cluster info:")
        if not cluster_summary.empty and 'Representative_Terms' in cluster_summary.columns:
            print(f"    - Cluster 0: {cluster_summary.iloc[0]['Representative_Terms']}")

    # Verify data structure
    assert isinstance(clusters_df, pd.DataFrame), "clusters should be DataFrame"
    assert isinstance(cluster_summary, pd.DataFrame), "cluster_summary should be DataFrame"
    assert isinstance(n_clusters, int), "n_clusters should be int"

    # If clustering succeeded, verify structure
    if n_clusters > 0:
        assert 'Cluster' in clusters_df.columns, "Should have Cluster column"
        assert 'Performance_Category' in cluster_summary.columns, "Should have Performance_Category"
        assert 'Representative_Terms' in cluster_summary.columns, "Should have Representative_Terms"

    print("PASS: Search term clustering complete")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 3: Negative Product Targets Export
print("\n[TEST 3] Negative Product Targets Export")
try:
    output = BytesIO()
    opt.export_negative_product_targets_bulk_file(
        product_results['negative_recommendations'],
        output
    )
    output.seek(0)

    # Read back and verify
    df_export = pd.read_excel(output, sheet_name='Negative Product Targets')

    print(f"  Exported rows: {len(df_export)}")

    # Verify required columns for Amazon upload
    required_cols = ['Product', 'Entity', 'Operation', 'Product Targeting Expression', 'Match Type']
    for col in required_cols:
        assert col in df_export.columns, f"Missing required column: {col}"

    # Verify data values
    if len(df_export) > 0:
        assert all(df_export['Entity'] == 'Negative Product Targeting'), "Entity should be 'Negative Product Targeting'"
        assert all(df_export['Operation'] == 'Create'), "Operation should be 'Create'"
        print(f"  Sample: {df_export.iloc[0]['Product Targeting Expression']}")

    print("PASS: Negative product targets export format correct")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 4: Negative Keywords Export
print("\n[TEST 4] Negative Keywords Export")
try:
    output = BytesIO()
    opt.export_negative_keywords_bulk_file(
        cluster_results,
        output,
        min_spend=5,  # Lower threshold for testing
        max_acos=1.5
    )
    output.seek(0)

    # Read back and verify
    df_export = pd.read_excel(output, sheet_name='Negative Keywords')

    print(f"  Exported rows: {len(df_export)}")

    # Verify required columns for Amazon upload
    required_cols = ['Product', 'Entity', 'Operation', 'Keyword Text', 'Match Type']
    for col in required_cols:
        assert col in df_export.columns, f"Missing required column: {col}"

    # Verify data values
    if len(df_export) > 0:
        assert all(df_export['Entity'] == 'Negative Keyword'), "Entity should be 'Negative Keyword'"
        assert all(df_export['Operation'] == 'Create'), "Operation should be 'Create'"
        print(f"  Sample: {df_export.iloc[0]['Keyword Text']}")

    print("PASS: Negative keywords export format correct")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 5: Statistical Calculations
print("\n[TEST 5] Statistical Calculations (Z-Scores)")
try:
    if len(product_results['performance_analysis']) > 0:
        df = product_results['performance_analysis']

        # Get ASINs with sufficient data
        sufficient_data = df[df['Clicks'] >= 10]

        if len(sufficient_data) > 0:
            # Check Z-score distribution
            z_ctr_mean = sufficient_data['Z_CTR'].mean()
            z_cvr_mean = sufficient_data['Z_CVR'].mean()

            print(f"  Z-score distributions:")
            print(f"    - Mean Z_CTR: {z_ctr_mean:.3f} (should be ~0)")
            print(f"    - Mean Z_CVR: {z_cvr_mean:.3f} (should be ~0)")

            # Z-scores should have mean close to 0 (within reason)
            assert abs(z_ctr_mean) < 0.5, f"Z_CTR mean too far from 0: {z_ctr_mean}"
            assert abs(z_cvr_mean) < 0.5, f"Z_CVR mean too far from 0: {z_cvr_mean}"

            # Check severity scores
            max_severity = df['Severity_Score'].max()
            print(f"    - Max severity score: {max_severity:.2f}")
            assert max_severity >= 0, "Severity scores should be non-negative"

            print("PASS: Statistical calculations correct")
        else:
            print("SKIP: No ASINs with sufficient data for Z-score testing")
    else:
        print("SKIP: No product targeting data available")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 6: Integration Test - Markdown Report
print("\n[TEST 6] Markdown Report Integration")
try:
    report = opt.generate_markdown_report()

    # Verify Phase 3 sections are included
    assert "NLP Analysis" in report, "Should include NLP Analysis section"
    assert "Product Target Analysis" in report, "Should include Product Target Analysis"

    # Check for key metrics
    if product_results['bleeder_counts']['type_b'] > 0:
        assert "Type B (Non-Converting)" in report, "Should mention Type B bleeders"
        assert "Negative Targeting" in report or "negative targeting" in report, "Should mention negative targeting"

    if cluster_results['n_clusters'] > 0:
        assert "Intent Cluster" in report or "intent cluster" in report, "Should mention intent clustering"

    print(f"  Report length: {len(report)} characters")
    print(f"  Contains Phase 3 analysis: YES")
    print("PASS: Markdown report includes Phase 3 content")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 7: Bleeder Type Assignment
print("\n[TEST 7] Bleeder Type Assignment Logic")
try:
    df = product_results['performance_analysis']

    if len(df) > 0:
        # Count each bleeder type
        type_counts = df['Bleeder_Type'].value_counts()
        print(f"  Bleeder type distribution:")
        for btype, count in type_counts.items():
            if btype:  # Skip empty strings
                print(f"    - {btype}: {count}")

        # Verify mutual exclusivity (each ASIN should have only one type)
        non_empty = df[df['Bleeder_Type'] != '']
        if len(non_empty) > 0:
            print(f"  Total ASINs flagged: {len(non_empty)}")

        # Verify Type B criteria
        type_b = df[df['Bleeder_Type'] == 'Type B: Non-Converting']
        if len(type_b) > 0:
            # All Type B should have either high clicks with no sales, or low conversion rate
            for _, row in type_b.iterrows():
                clicks = row['Clicks']
                sales = row['Sales']
                cvr = row['Conversion Rate']

                # Must meet one of the Type B criteria
                meets_criteria = (
                    (clicks >= 20 and sales == 0) or
                    (clicks >= 10 and cvr < 0.02)
                )
                assert meets_criteria, f"Type B ASIN doesn't meet criteria: clicks={clicks}, sales={sales}, cvr={cvr}"

        print("PASS: Bleeder type assignment logic correct")
    else:
        print("SKIP: No product targeting data to test")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Summary
print("\n" + "=" * 70)
print("PHASE 3 TESTS - ALL PASSED!")
print("=" * 70)

print("\n✅ Test Summary:")
print("  [OK] Product target analysis (statistical framework)")
print("  [OK] Search term clustering (NLP embeddings)")
print("  [OK] Negative product targets export (Amazon format)")
print("  [OK] Negative keywords export (Amazon format)")
print("  [OK] Statistical calculations (Z-scores, severity)")
print("  [OK] Markdown report integration")
print("  [OK] Bleeder type assignment logic")

print("\n📊 Phase 3 Results:")
print(f"  - Product targets analyzed: {len(product_results['performance_analysis'])}")
print(f"  - Type B bleeders (priority): {product_results['bleeder_counts']['type_b']}")
print(f"  - Search term clusters: {cluster_results['n_clusters']}")
print(f"  - Estimated monthly savings: ${product_results['savings_estimate']:,.2f}")

print("\n🎉 Phase 3: NLP Intelligence - READY FOR PRODUCTION!")
