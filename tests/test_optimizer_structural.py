import pandas as pd


def test_detect_cannibalization_returns_dataframe(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()
    result = optimizer.detect_cannibalization()
    assert isinstance(result, pd.DataFrame)


def test_optimize_budgets_returns_dataframe(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()
    result = optimizer.optimize_budgets()
    assert isinstance(result, pd.DataFrame)
