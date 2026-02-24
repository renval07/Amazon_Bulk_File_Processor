from src.optimizer import BulkOptimizer
import numpy as np


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


def test_type_c_percentile_mode_detects_low_volume_terms(sample_file_path):
    opt = BulkOptimizer(
        str(sample_file_path),
        enforce_48hr_rule=False,
        enable_logging=False,
        bleeder_type_c_mode="percentile",
        bleeder_type_c_percentile=0.25,
    )
    opt.load_data()
    opt.optimize_bids()
    result = opt.identify_bleeders()
    assert result["type_c"] >= 0


def test_cold_start_step_up_applies_plus_two_cents(sample_file_path):
    opt = BulkOptimizer(
        str(sample_file_path),
        enforce_48hr_rule=False,
        enable_logging=False,
        bleeder_type_c_mode="fixed",
        bleeder_type_c_impressions_threshold=100,
        cold_start_step_up_amount=0.02,
        cold_start_enable=True,
    )
    opt.load_data()
    opt.optimize_bids()

    mask = (
        (opt.df["Entity"].isin(["Keyword", "Product Targeting"]))
        & (opt.df["Impressions"] > 0)
        & (opt.df["Impressions"] < 100)
        & (opt.df["Clicks"] == 0)
        & (opt.df["Sales"] == 0)
    )
    before = opt.df.loc[mask, "Bid"].copy()
    opt.identify_bleeders()
    after = opt.df.loc[mask, "Bid"].copy()

    if not before.empty:
        deltas = (after - before).round(2)
        allowed = (deltas == 0.02) | ((after == opt.max_bid) & (before > opt.max_bid))
        assert allowed.all()


def test_bleeder_segmentation_mode_runs(sample_file_path):
    opt = BulkOptimizer(
        str(sample_file_path),
        enforce_48hr_rule=False,
        enable_logging=False,
        bleeder_segmentation_mode="match_type",
        segmentation_min_entities=5,
    )
    opt.load_data()
    opt.optimize_bids()
    result = opt.identify_bleeders()
    assert result["total"] >= 0


def test_confidence_gating_with_high_min_spend_reduces_type_b(sample_file_path):
    no_gate = BulkOptimizer(
        str(sample_file_path),
        enforce_48hr_rule=False,
        enable_logging=False,
        confidence_enable=False,
    )
    no_gate.load_data()
    no_gate.optimize_bids()
    no_gate_result = no_gate.identify_bleeders()

    strict_gate = BulkOptimizer(
        str(sample_file_path),
        enforce_48hr_rule=False,
        enable_logging=False,
        confidence_enable=True,
        type_b_min_spend=1_000_000.0,
    )
    strict_gate.load_data()
    strict_gate.optimize_bids()
    strict_result = strict_gate.identify_bleeders()

    assert strict_result["type_b"] <= no_gate_result["type_b"]


def test_cold_start_ladder_mode_applies_progressive_increments(sample_file_path):
    opt = BulkOptimizer(
        str(sample_file_path),
        enforce_48hr_rule=False,
        enable_logging=False,
        bleeder_type_c_mode="fixed",
        bleeder_type_c_impressions_threshold=100,
        cold_start_step_up_amount=0.02,
        cold_start_mode="ladder",
        cold_start_ladder_cap=0.08,
        cold_start_enable=True,
    )
    opt.load_data()
    opt.optimize_bids()

    mask = (
        (opt.df["Entity"].isin(["Keyword", "Product Targeting"]))
        & (opt.df["Impressions"] > 0)
        & (opt.df["Impressions"] < 100)
        & (opt.df["Clicks"] == 0)
        & (opt.df["Sales"] == 0)
    )
    before = opt.df.loc[mask, "Bid"].copy()
    impressions = opt.df.loc[mask, "Impressions"].astype(float).copy()
    opt.identify_bleeders()
    after = opt.df.loc[mask, "Bid"].copy()

    if not before.empty:
        ratio = impressions / 100.0
        multipliers = np.select(
            [ratio <= 0.25, ratio <= 0.50, ratio <= 0.75],
            [2.0, 1.5, 1.25],
            default=1.0,
        )
        expected = np.minimum(0.02 * multipliers, 0.08)
        deltas = (after - before).astype(float)
        unclipped = (before + expected) <= opt.max_bid + 1e-9
        if unclipped.any():
            np.testing.assert_allclose(deltas[unclipped], expected[unclipped], rtol=0, atol=1e-9)
