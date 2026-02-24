from pathlib import Path

import pandas as pd

from src.run_history import append_run_history, calculate_drift_alerts, load_run_history


def test_append_and_load_run_history():
    history_path = Path("outputs") / "test_run_history.csv"
    if history_path.exists():
        history_path.unlink()

    append_run_history(
        {
            "mode": "cli",
            "input_file": "sample_a.xlsx",
            "status": "ok",
            "bid_updates": 10,
        },
        history_path=history_path,
    )
    append_run_history(
        {
            "mode": "ui",
            "input_file": "sample_b.xlsx",
            "status": "failed",
            "error": "boom",
        },
        history_path=history_path,
    )

    df = load_run_history(history_path=history_path)
    assert len(df) == 2
    assert list(df["mode"]) == ["cli", "ui"]
    assert list(df["input_file"]) == ["sample_a.xlsx", "sample_b.xlsx"]
    assert list(df["status"]) == ["ok", "failed"]
    history_path.unlink(missing_ok=True)


def test_calculate_drift_alerts_detects_large_change():
    rows = []
    for i in range(6):
        rows.append(
            {
                "timestamp": f"2026-02-24T10:0{i}:00",
                "status": "ok",
                "intent_clusters": 10 if i == 5 else 4,
                "negative_recommendations": 8 if i == 5 else 2,
                "type_b_bleeders": 12 if i == 5 else 5,
            }
        )
    df = pd.DataFrame(rows)
    alerts = calculate_drift_alerts(df, baseline_window=5)
    metrics = {alert["metric"] for alert in alerts}
    assert "intent_clusters" in metrics
    assert "negative_recommendations" in metrics
    assert "type_b_bleeders" in metrics
