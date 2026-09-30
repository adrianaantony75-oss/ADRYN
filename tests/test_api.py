import json
from uuid import uuid4

from fastapi.testclient import TestClient

from adryn.api import app


def test_api_input_validation_and_health():
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    response = client.post("/predict/churn", json={"sessions": -1})
    assert response.status_code == 422
    assert client.post("/predict/support-theme", json={"text": ""}).status_code == 422
    assert client.post("/predict/support-theme", json={"text": "   "}).status_code == 422
    assert client.post(
        "/predict/support-theme", json={"text": "billing issue", "unknown": True}
    ).status_code == 422


def test_api_unavailable_publication_is_controlled(tmp_path, monkeypatch):
    monkeypatch.setenv("ADRYN_OUTPUT_DIR", str(tmp_path))
    (tmp_path / "current_run.json").write_text("{broken", encoding="utf-8")
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["model_ready"] is False
    response = client.post("/predict/support-theme", json={"text": "billing issue"})
    assert response.status_code == 503
    assert "Traceback" not in response.text


def test_api_metadata_alone_does_not_mean_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("ADRYN_OUTPUT_DIR", str(tmp_path))
    models = tmp_path / "models"
    models.mkdir()
    run_id = str(uuid4())
    from adryn.core.customer import FEATURES

    (tmp_path / "pipeline_summary.json").write_text(json.dumps({"run_id": run_id}))
    (models / "metadata.json").write_text(
        json.dumps({
            "run_id": run_id, "as_of": "2026-09-30", "threshold": 0.5, "features": FEATURES,
        })
    )
    client = TestClient(app)
    assert client.get("/health").json()["model_ready"] is False
    (models / "voice.joblib").write_bytes(b"broken model")
    assert client.post(
        "/predict/support-theme", json={"text": "billing issue"}
    ).status_code == 503
