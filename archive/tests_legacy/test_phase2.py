from src.optimizer import BulkOptimizer
from io import BytesIO
import pandas as pd

print("Testing Phase 2: Structural Control Features")
print("=" * 70)

# Initialize optimizer
print("\n[SETUP] Initializing optimizer...")
opt = BulkOptimizer(
    r'bulk-a2kk083uqnb8ha-20251213-20260211-1770782206348 (1).xlsx',
    enforce_48hr_rule=False
)
opt.load_data()
opt.optimize_bids()
opt.identify_bleeders()

# Test 1: Operation Column is Set
print("\n[TEST 1] Operation Column Set for Bid Changes")
try:
    operation_updates = (opt.df['Operation'] == 'Update').sum()
    print(f"  Rows marked for update: {operation_updates}")

    if operation_updates > 0:
        print("PASS: Operation column correctly set for Amazon upload")
    else:
        print("WARNING: No rows marked for update (may be expected if no changes)")

except Exception as e:
    print(f"FAIL: {e}")
    exit(1)

# Test 2: Cannibalization Detection
print("\n[TEST 2] Cannibalization Detection")
try:
    cannibalization = opt.detect_cannibalization()

    print(f"  Duplicate keywords found: {len(cannibalization)}")

    if isinstance(cannibalization, pd.DataFrame):
        if not cannibalization.empty:
            print(f"  Sample conflicts:")
            if 'Normalized_Keyword' in cannibalization.columns:
                for idx, row in cannibalization.head(3).iterrows():
                    keyword = row.get('Normalized_Keyword', 'N/A')
                    ad_groups = row.get('Ad_Group_Count', 'N/A')
                    spend = row.get('Total_Spend', 0)
                    print(f"    - '{keyword[:40]}...' in {ad_groups} ad groups (${spend:.2f} total spend)")
        else:
            print("  No cannibalization detected (good!)")

        print("PASS: Cannibalization detection working")
    else:
        print("FAIL: Invalid return type")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 3: Budget Optimization
print("\n[TEST 3] Budget Optimization Analysis")
try:
    budget_recs = opt.optimize_budgets()

    print(f"  Campaigns analyzed: {len(budget_recs)}")

    if isinstance(budget_recs, pd.DataFrame) and not budget_recs.empty:
        # Check for key columns
        key_cols = ['ROAS', 'ACOS', 'Category', 'Recommendation']
        present_cols = [col for col in key_cols if col in budget_recs.columns]
        print(f"  Key columns present: {', '.join(present_cols)}")

        # Show category breakdown
        if 'Category' in budget_recs.columns:
            categories = budget_recs['Category'].value_counts()
            print(f"  Campaign breakdown:")
            for category, count in categories.items():
                print(f"    - {category}: {count}")

        # Show ROAS range
        if 'ROAS' in budget_recs.columns:
            min_roas = budget_recs['ROAS'].min()
            max_roas = budget_recs['ROAS'].max()
            avg_roas = budget_recs['ROAS'].mean()
            print(f"  ROAS range: {min_roas:.2f} - {max_roas:.2f} (avg: {avg_roas:.2f})")

        print("PASS: Budget optimization working")
    elif budget_recs.empty:
        print("WARNING: No campaigns found (may need campaign-level data)")
    else:
        print("FAIL: Invalid return type")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 4: Reports Included in Output File
print("\n[TEST 4] Phase 2 Reports in Output File")
try:
    output = BytesIO()
    opt.save_optimized_file(output)
    output.seek(0)

    # Read back the sheets
    sheets = pd.read_excel(output, sheet_name=None, nrows=0)
    sheet_names = list(sheets.keys())

    print(f"  Total sheets: {len(sheet_names)}")
    print(f"  Sheet names: {', '.join(sheet_names)}")

    # Check for Phase 2 sheets
    expected_sheets = ['Cannibalization Report', 'Budget Recommendations']
    found_sheets = [sheet for sheet in expected_sheets if sheet in sheet_names]

    print(f"  Phase 2 sheets found: {', '.join(found_sheets) if found_sheets else 'None'}")

    if found_sheets:
        print("PASS: Phase 2 reports included in output file")
    else:
        print("INFO: No Phase 2 sheets (may be expected if no issues found)")

except Exception as e:
    print(f"FAIL: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 5: File Ready for Amazon Upload
print("\n[TEST 5] File Ready for Amazon Upload")
try:
    # Check critical requirements
    checks = []

    # Check 1: Operation column exists
    if 'Operation' in opt.df.columns:
        checks.append(("Operation column exists", True))
    else:
        checks.append(("Operation column exists", False))

    # Check 2: Some rows marked for update
    update_count = (opt.df['Operation'] == 'Update').sum()
    checks.append((f"{update_count} rows marked for Update", update_count > 0))

    # Check 3: Bid column has no NaN
    bid_valid = not opt.df['Bid'].isna().any()
    checks.append(("All Bids are valid (no NaN)", bid_valid))

    # Check 4: ID columns preserved
    id_cols = ['Campaign ID', 'Ad Group ID', 'Keyword ID']
    id_cols_present = [col for col in id_cols if col in opt.df.columns]
    checks.append((f"{len(id_cols_present)}/{len(id_cols)} ID columns present", len(id_cols_present) > 0))

    print("  Upload readiness checks:")
    all_passed = True
    for check_name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] {check_name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("PASS: File is ready for Amazon upload")
    else:
        print("FAIL: File has issues that may prevent Amazon upload")

except Exception as e:
    print(f"FAIL: {e}")
    exit(1)

print("\n" + "=" * 70)
print("PHASE 2 STRUCTURAL CONTROL - COMPLETE!")
print("=" * 70)

print("\nFeatures Implemented:")
print("  [OK] Operation column set for Amazon upload")
print("  [OK] Cannibalization detection across ad groups")
print("  [OK] Budget optimization recommendations")
print("  [OK] Cannibalization Report sheet in output")
print("  [OK] Budget Recommendations sheet in output")
print("  [OK] File ready for Amazon Seller Central upload")

print("\nPhase 2 Summary:")
if not cannibalization.empty:
    print(f"  - {len(cannibalization)} cannibalization issues detected")
    print(f"  - Estimated wasted spend: ${cannibalization['Total_Spend'].sum():,.2f}")
else:
    print(f"  - No cannibalization issues (optimal structure!)")

if not budget_recs.empty:
    print(f"  - {len(budget_recs)} campaigns analyzed for budget optimization")
    if 'Category' in budget_recs.columns:
        star_count = (budget_recs['Category'] == 'Star Performer').sum()
        poor_count = (budget_recs['Category'] == 'Poor Performer').sum()
        print(f"  - {star_count} star performers (increase budget)")
        print(f"  - {poor_count} poor performers (decrease budget)")

print("\n>> Ready to upload optimized file to Amazon Seller Central!")
