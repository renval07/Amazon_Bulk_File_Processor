from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from src.optimizer import BulkOptimizer


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
    for col in ["Product", "Entity", "Operation", "Product Targeting Expression", "Match Type", "State"]:
        assert col in exported.columns
    if not exported.empty:
        assert exported["State"].astype(str).str.lower().eq("enabled").all()


def test_negative_recommendations_exclude_auto_target_buckets(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()

    result = optimizer.analyze_product_targets()
    recs = result["negative_recommendations"]

    if len(recs) == 0:
        pytest.skip("No negative recommendations produced for this fixture")

    expr = recs["Product Targeting Expression"].fillna("").astype(str).str.strip().str.lower()
    assert not expr.isin(BulkOptimizer.AUTO_TARGET_BUCKETS).any()


def test_negative_product_export_filters_auto_target_buckets(optimizer):
    recommendations = pd.DataFrame(
        {
            "Ad_Type": ["Sponsored Products", "Sponsored Products"],
            "Campaign ID": [123, 123],
            "Ad Group ID": [456, 456],
            "Campaign Name (Informational only)": ["Camp A", "Camp A"],
            "Ad Group Name (Informational only)": ["Group A", "Group A"],
            "Product Targeting Expression": ["close-match", 'asin="B08JD776XX"'],
        }
    )

    output = BytesIO()
    optimizer.export_negative_product_targets_bulk_file(recommendations, output)
    output.seek(0)

    exported = pd.read_excel(output, sheet_name="Negative Product Targets")
    expr = exported["Product Targeting Expression"].fillna("").astype(str).str.strip().str.lower()

    assert len(exported) == 1
    assert expr.iloc[0] == 'asin="b08jd776xx"'


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

    class FakeKMeans:
        def __init__(self, n_clusters, random_state=42, n_init=10):
            _ = random_state
            _ = n_init
            self.n_clusters = n_clusters

        def fit_predict(self, embeddings):
            n = len(embeddings)
            return np.array([i % self.n_clusters for i in range(n)])

    monkeypatch.setattr("src.optimizer.SentenceTransformer", FakeModel)
    monkeypatch.setattr("src.optimizer.KMeans", FakeKMeans)
    monkeypatch.setattr("src.optimizer.silhouette_score", lambda *_args, **_kwargs: 0.42)
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

    class FakeKMeans:
        def __init__(self, n_clusters, random_state=42, n_init=10):
            _ = random_state
            _ = n_init
            self.n_clusters = n_clusters

        def fit_predict(self, embeddings):
            n = len(embeddings)
            return np.array([i % self.n_clusters for i in range(n)])

    monkeypatch.setattr("src.optimizer.SentenceTransformer", FakeModel)
    monkeypatch.setattr("src.optimizer.KMeans", FakeKMeans)
    monkeypatch.setattr("src.optimizer.silhouette_score", lambda *_args, **_kwargs: 0.35)
    clusters = optimizer.cluster_search_terms(n_clusters=3, min_cluster_size=5)

    output = BytesIO()
    optimizer.export_negative_keywords_bulk_file(clusters, output, min_spend=5, max_acos=1.5)
    output.seek(0)
    exported = pd.read_excel(output, sheet_name="Negative Keywords")

    for col in [
        "Product",
        "Entity",
        "Operation",
        "Campaign ID",
        "Ad Group ID",
        "Keyword Text",
        "Match Type",
        "State",
    ]:
        assert col in exported.columns
    if not exported.empty:
        assert exported["Campaign ID"].notna().all()
        assert exported["Ad Group ID"].notna().all()
        assert exported["State"].astype(str).str.lower().eq("enabled").all()


def test_negative_keywords_can_filter_to_low_intent_clusters(optimizer):
    sp = optimizer.original_sheets.get("SP Search Term Report", pd.DataFrame()).copy()
    valid = sp[
        sp["Customer Search Term"].notna()
        & sp["Campaign ID"].notna()
        & sp["Ad Group ID"].notna()
    ]
    if len(valid) < 2:
        pytest.skip("Need at least two valid search terms for low-intent filter test")

    term_a = str(valid.iloc[0]["Customer Search Term"])
    term_b = str(valid.iloc[1]["Customer Search Term"])

    clusters = pd.DataFrame(
        {
            "Customer Search Term": [term_a, term_b],
            "Cluster": [0, 1],
            "Spend": [20.0, 20.0],
            "Sales": [0.0, 0.0],
            "ACOS": [2.0, 2.0],
        }
    )
    cluster_summary = pd.DataFrame(
        {
            "Cluster": [0, 1],
            "Performance_Category": ["Low-Performing Intent", "High-Performing Intent"],
        }
    )

    output = BytesIO()
    optimizer.export_negative_keywords_bulk_file(
        {"clusters": clusters, "cluster_summary": cluster_summary, "n_clusters": 2},
        output,
        min_spend=5,
        max_acos=1.5,
        require_low_intent_cluster=True,
    )
    output.seek(0)
    exported = pd.read_excel(output, sheet_name="Negative Keywords")

    if not exported.empty:
        exported_terms = set(exported["Keyword Text"].astype(str).tolist())
        assert term_a in exported_terms
        assert term_b not in exported_terms
