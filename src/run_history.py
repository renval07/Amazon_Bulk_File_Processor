from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_HISTORY_PATH = Path("outputs") / "run_history.csv"


def _default_record() -> dict[str, Any]:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": "",
        "input_file": "",
        "status": "",
        "error": "",
        "bid_updates": 0,
        "type_a_bleeders": 0,
        "type_b_bleeders": 0,
        "type_c_bleeders": 0,
        "cannibalization_issues": 0,
        "campaigns_analyzed": 0,
        "intent_clusters": 0,
        "negative_recommendations": 0,
        "runtime_seconds": 0.0,
    }


def append_run_history(record: dict[str, Any], history_path: str | Path = DEFAULT_HISTORY_PATH) -> Path:
    path = Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    row = _default_record()
    row.update(record or {})

    row_df = pd.DataFrame([row])
    if path.exists():
        existing = pd.read_csv(path)
        row_df = pd.concat([existing, row_df], ignore_index=True)
    row_df.to_csv(path, index=False)
    return path


def load_run_history(history_path: str | Path = DEFAULT_HISTORY_PATH) -> pd.DataFrame:
    path = Path(history_path)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def calculate_drift_alerts(history_df: pd.DataFrame, baseline_window: int = 5) -> list[dict[str, Any]]:
    if history_df.empty:
        return []

    successful = history_df[history_df.get("status", "") == "ok"].copy()
    if len(successful) < baseline_window + 1:
        return []

    successful["timestamp"] = pd.to_datetime(successful["timestamp"], errors="coerce")
    successful = successful.sort_values("timestamp", ascending=False)

    latest = successful.iloc[0]
    baseline = successful.iloc[1 : baseline_window + 1]
    metrics = ["intent_clusters", "negative_recommendations", "type_b_bleeders"]
    alerts = []

    for metric in metrics:
        if metric not in successful.columns:
            continue
        baseline_mean = float(pd.to_numeric(baseline[metric], errors="coerce").fillna(0).mean())
        latest_value = float(pd.to_numeric(pd.Series([latest[metric]]), errors="coerce").fillna(0).iloc[0])

        if baseline_mean == 0:
            if latest_value > 0:
                alerts.append(
                    {
                        "metric": metric,
                        "latest": latest_value,
                        "baseline_mean": baseline_mean,
                        "delta_pct": None,
                        "reason": "Baseline was zero; latest value is non-zero.",
                    }
                )
            continue

        delta_pct = ((latest_value - baseline_mean) / baseline_mean) * 100.0
        if abs(delta_pct) >= 50.0:
            alerts.append(
                {
                    "metric": metric,
                    "latest": latest_value,
                    "baseline_mean": round(baseline_mean, 2),
                    "delta_pct": round(delta_pct, 2),
                    "reason": "Absolute change is >= 50% vs rolling baseline.",
                }
            )

    return alerts
