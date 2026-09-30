from pathlib import Path

import pandas as pd

from adryn.data.synthetic import generate_enterprise_data


def test_synthetic_generator_repeats_for_same_seed(tmp_path: Path) -> None:
    first = generate_enterprise_data(tmp_path / "first", seed=19)
    second = generate_enterprise_data(tmp_path / "second", seed=19)

    for dataset in ("customers", "orders", "contracts", "ai_reviews"):
        left = pd.read_csv(getattr(first, dataset))
        right = pd.read_csv(getattr(second, dataset))
        pd.testing.assert_frame_equal(left, right)
