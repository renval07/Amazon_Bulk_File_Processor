from pathlib import Path

import pytest

from src.optimizer import BulkOptimizer


@pytest.fixture
def sample_file_path() -> Path:
    samples_dir = Path(__file__).resolve().parents[1] / "data" / "samples"
    preferred = samples_dir / "bulk-a1qcnuwp2122gg-20260125-20260224-1771933499436.xlsx"
    if preferred.exists():
        return preferred

    candidates = sorted(samples_dir.glob("bulk-*.xlsx"))
    if not candidates:
        candidates = sorted(samples_dir.glob("*.xlsx"))
    if not candidates:
        raise FileNotFoundError(f"No sample .xlsx files found in {samples_dir}")
    return candidates[0]


@pytest.fixture
def optimizer(sample_file_path: Path) -> BulkOptimizer:
    opt = BulkOptimizer(str(sample_file_path), enforce_48hr_rule=False, enable_logging=False)
    opt.load_data()
    return opt
