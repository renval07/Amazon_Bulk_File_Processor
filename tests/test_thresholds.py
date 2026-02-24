from src.optimizer import BulkOptimizer


def test_high_min_clicks_reduces_bid_updates(sample_file_path):
    default_opt = BulkOptimizer(str(sample_file_path), enforce_48hr_rule=False, enable_logging=False)
    default_opt.load_data()
    default_changes = default_opt.optimize_bids()

    strict_opt = BulkOptimizer(
        str(sample_file_path),
        enforce_48hr_rule=False,
        enable_logging=False,
        optimization_min_clicks=1000,
    )
    strict_opt.load_data()
    strict_changes = strict_opt.optimize_bids()

    assert strict_changes <= default_changes


def test_type_c_threshold_controls_ghost_keyword_count(sample_file_path):
    low_threshold_opt = BulkOptimizer(
        str(sample_file_path),
        enforce_48hr_rule=False,
        enable_logging=False,
        bleeder_type_c_impressions_threshold=10,
    )
    low_threshold_opt.load_data()
    low_threshold_opt.optimize_bids()
    low_result = low_threshold_opt.identify_bleeders()

    high_threshold_opt = BulkOptimizer(
        str(sample_file_path),
        enforce_48hr_rule=False,
        enable_logging=False,
        bleeder_type_c_impressions_threshold=500,
    )
    high_threshold_opt.load_data()
    high_threshold_opt.optimize_bids()
    high_result = high_threshold_opt.identify_bleeders()

    assert high_result["type_c"] >= low_result["type_c"]
