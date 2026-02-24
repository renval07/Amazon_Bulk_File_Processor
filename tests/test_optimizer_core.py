from io import BytesIO

import pytest

from src.optimizer import BulkOptimizer


def test_loads_required_sheet_and_columns(optimizer):
    assert optimizer.df is not None
    for col in ["Entity", "Impressions", "Clicks", "Spend", "Sales", "Bid"]:
        assert col in optimizer.df.columns


def test_48_hour_rule_returns_no_error_for_old_sample(optimizer):
    warning = optimizer.check_48_hour_rule()
    assert warning is None


def test_optimize_bids_updates_operation_and_preserves_low_data_bids(optimizer):
    _ = optimizer.optimize_bids()

    low_click_keywords = optimizer.df[
        (optimizer.df["Entity"].isin(["Keyword", "Product Targeting"]))
        & (optimizer.df["Clicks"] <= 10)
        & (optimizer.df["Clicks"] > 0)
    ]
    zero_bids = (low_click_keywords["Bid"] == 0).sum()
    assert zero_bids == 0


def test_identify_bleeders_returns_breakdown_dict(optimizer):
    optimizer.optimize_bids()
    result = optimizer.identify_bleeders()

    assert isinstance(result, dict)
    for key in ["type_a", "type_b", "type_c", "total"]:
        assert key in result


def test_validate_output_and_save_bytesio(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()
    is_valid, error_msg = optimizer.validate_output()
    assert is_valid, error_msg

    output = BytesIO()
    optimizer.save_optimized_file(output, include_analysis_sheets=False, amazon_upload_ready=True)
    output.seek(0)
    assert len(output.getvalue()) > 0


def test_markdown_report_can_skip_nlp(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()
    report = optimizer.generate_markdown_report(include_nlp=False)
    assert "NLP Analysis (Phase 3)" in report
    assert "Skipped for this run." in report


def test_input_validation_rejects_invalid_values(sample_file_path):
    with pytest.raises(ValueError):
        BulkOptimizer(str(sample_file_path), target_acos=-0.1)
    with pytest.raises(ValueError):
        BulkOptimizer(str(sample_file_path), min_bid=5.0, max_bid=1.0)
    with pytest.raises(ValueError):
        BulkOptimizer(str(sample_file_path), max_bid_change_pct=1.5)
    with pytest.raises(ValueError):
        BulkOptimizer(str(sample_file_path), bleeder_type_c_mode="unknown")
    with pytest.raises(ValueError):
        BulkOptimizer(str(sample_file_path), bleeder_type_c_percentile=1.5)
    with pytest.raises(ValueError):
        BulkOptimizer(str(sample_file_path), bleeder_segmentation_mode="bad_mode")
    with pytest.raises(ValueError):
        BulkOptimizer(str(sample_file_path), cold_start_mode="bad_mode")


def test_performance_metrics_record_and_read(optimizer):
    optimizer.record_stage_timing("demo_stage", 1.234)
    metrics = optimizer.get_performance_metrics()
    assert "demo_stage" in metrics
    assert metrics["demo_stage"] == pytest.approx(1.234, rel=1e-6)
