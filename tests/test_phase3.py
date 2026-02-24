from io import BytesIO

import numpy as np
import pandas as pd
import pytest


def test_product_target_analysis_returns_expected_shapes(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()

    result = optimizer.analyze_product_targets()

    assert isinstance(result["bleeder_counts"], dict)
    assert isinstance(result["negative_recommendations"], pd.DataFrame)
    assert isinstance(result["performance_analysis"], pd.DataFrame)
    assert isinstance(result["savings_estimate"], (int, float))


def test_negative_product_targets_export_schema(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()

    result = optimizer.analyze_product_targets()
    output = BytesIO()
    optimizer.export_negative_product_targets_bulk_file(result["negative_recommendations"], output)
    output.seek(0)

    exported = pd.read_excel(output, sheet_name="Negative Product Targets")
    for col in ["Product", "Entity", "Operation", "Product Targeting Expression", "Match Type"]:
        assert col in exported.columns


def test_search_term_clustering_with_mock_model(monkeypatch, optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()

    class FakeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        def encode(self, terms, show_progress_bar=False):
            _ = show_progress_bar
            n = len(terms)
            return np.array([[float(i % 7), float((i * 2) % 11), float((i * 3) % 13)] for i in range(n)])

    monkeypatch.setattr("src.optimizer.SentenceTransformer", FakeModel)
    clusters = optimizer.cluster_search_terms(n_clusters=4, min_cluster_size=5)

    assert isinstance(clusters["clusters"], pd.DataFrame)
    assert isinstance(clusters["cluster_summary"], pd.DataFrame)
    assert clusters["n_clusters"] == 4


def test_negative_keywords_export_schema_with_mock_clusters(monkeypatch, optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()

    class FakeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        def encode(self, terms, show_progress_bar=False):
            _ = show_progress_bar
            n = len(terms)
            return np.array([[float(i % 5), float((i * 2) % 7), float((i * 3) % 9)] for i in range(n)])

    monkeypatch.setattr("src.optimizer.SentenceTransformer", FakeModel)
    clusters = optimizer.cluster_search_terms(n_clusters=3, min_cluster_size=5)

    output = BytesIO()
    optimizer.export_negative_keywords_bulk_file(clusters, output, min_spend=5, max_acos=1.5)
    output.seek(0)
    exported = pd.read_excel(output, sheet_name="Negative Keywords")

    for col in ["Product", "Entity", "Operation", "Keyword Text", "Match Type"]:
        assert col in exported.columns
