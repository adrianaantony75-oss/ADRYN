import json
from uuid import uuid4

import pytest

from adryn.io import current_output
from adryn.reports import pipeline
from adryn.settings import Settings


def test_failed_run_preserves_published_snapshot(tmp_path, monkeypatch):
    settings = Settings(
        raw_data_dir=tmp_path / "raw",
        processed_data_dir=tmp_path / "processed",
        output_dir=tmp_path / "outputs",
    )
    settings.ensure_dirs()
    run_id = str(uuid4())
    prior = settings.output_dir / "snapshots" / run_id
    prior.mkdir(parents=True)
    (prior / "pipeline_summary.json").write_text(json.dumps({"run_id": run_id}))
    (settings.output_dir / "current_run.json").write_text(json.dumps({"run_id": run_id}))

    def fail(*args):
        raise RuntimeError("Injected model failure")

    monkeypatch.setattr(pipeline, "_run_pipeline", fail)
    with pytest.raises(RuntimeError, match="Injected model failure"):
        pipeline.run_pipeline(settings)
    assert current_output(settings.output_dir) == prior
    assert json.loads((prior / "pipeline_summary.json").read_text())["run_id"] == run_id
