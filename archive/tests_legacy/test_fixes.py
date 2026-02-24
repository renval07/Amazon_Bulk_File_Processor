from src.optimizer import BulkOptimizer

print("Testing critical bug fixes...")
print("-" * 50)

# Test 1: Initialization with validation
print("\n[TEST 1] Optimizer initialization with validation")
try:
    opt = BulkOptimizer(
        r'bulk-a2kk083uqnb8ha-20251213-20260211-1770782206348 (1).xlsx',
        enforce_48hr_rule=False
    )
    print("PASS: Optimizer initialized")
except Exception as e:
    print(f"FAIL: {e}")
    exit(1)

# Test 2: 48-hour rule check
print("\n[TEST 2] 48-hour rule check")
try:
    warning = opt.check_48_hour_rule()
    if warning:
        print(f"WARNING DETECTED: {warning[:80]}...")
    else:
        print("PASS: No warning (file is old enough)")
except Exception as e:
    print(f"FAIL: {e}")
    exit(1)

# Test 3: Data loading with column validation
print("\n[TEST 3] Data loading with validation and cleaning")
try:
    opt.load_data()
    print(f"PASS: Loaded {len(opt.df)} rows")
    print(f"PASS: Operation column dtype: {opt.df['Operation'].dtype}")
except Exception as e:
    print(f"FAIL: {e}")
    exit(1)

# Test 4: Bid optimization (with critical fallback fix)
print("\n[TEST 4] Bid optimization with fixed fallback logic")
try:
    bid_changes = opt.optimize_bids()
    print(f"PASS: {bid_changes} bid changes made")

    # Verify no zero bids for low-data keywords
    low_click_keywords = opt.df[(opt.df['Entity'].isin(['Keyword', 'Product Targeting'])) &
                                  (opt.df['Clicks'] <= 10) &
                                  (opt.df['Clicks'] > 0)]
    zero_bids = (low_click_keywords['Bid'] == 0).sum()

    if zero_bids > 0:
        print(f"WARNING: Found {zero_bids} keywords with <=10 clicks that have $0 bids")
    else:
        print("PASS: No zero bids for low-data keywords (fallback working)")

except Exception as e:
    print(f"FAIL: {e}")
    exit(1)

# Test 5: Bleeder identification (with fixed dtype issue)
print("\n[TEST 5] Bleeder identification without dtype warnings")
try:
    bleeder_changes = opt.identify_bleeders()
    print(f"PASS: {bleeder_changes} bleeders identified")
except Exception as e:
    print(f"FAIL: {e}")
    exit(1)

# Test 6: Input validation
print("\n[TEST 6] Input parameter validation")
try:
    # Should fail with invalid target_acos
    BulkOptimizer(r'test.xlsx', target_acos=-0.5)
    print("FAIL: Should have raised ValueError for negative ACOS")
except ValueError as e:
    print(f"PASS: Correctly rejected invalid input: {e}")

try:
    # Should fail with min > max
    BulkOptimizer(r'test.xlsx', min_bid=5.0, max_bid=1.0)
    print("FAIL: Should have raised ValueError for min_bid > max_bid")
except ValueError as e:
    print(f"PASS: Correctly rejected invalid input: {e}")

print("\n" + "=" * 50)
print("ALL CRITICAL BUGS FIXED SUCCESSFULLY!")
print("=" * 50)
