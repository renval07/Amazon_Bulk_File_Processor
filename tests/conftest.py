from pathlib import Path

import pytest

from src.optimizer import BulkOptimizer


@pytest.fixture
def sample_file_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "data"
        / "samples"
        / "bulk-a2kk083uqnb8ha-20251213-20260211-1770782206348 (1).xlsx"
    )


@pytest.fixture
def optimizer(sample_file_path: Path) -> BulkOptimizer:
    opt = BulkOptimizer(str(sample_file_path), enforce_48hr_rule=False, enable_logging=False)
    opt.load_data()
    return opt
