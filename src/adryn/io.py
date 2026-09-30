import json
from pathlib import Path

import pandas as pd


def read_table(path: Path) -> pd.DataFrame:
    """Preserve business codes such as NA (North America); only blanks are null."""
    return pd.read_csv(path, keep_default_na=False, na_values=[""])


def current_output(root: Path) -> Path:
    manifest = root / "current_run.json"
    if not manifest.exists():
        return root
    run_id = json.loads(manifest.read_text(encoding="utf-8"))["run_id"]
    from uuid import UUID

    run_id = str(UUID(run_id))
    snapshot = root / "snapshots" / run_id
    if not (snapshot / "pipeline_summary.json").exists():
        raise ValueError("Published analysis snapshot is unavailable.")
    return snapshot
