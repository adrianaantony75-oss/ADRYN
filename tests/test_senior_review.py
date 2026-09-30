import json
from uuid import uuid4

import joblib
import pandas as pd
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from sklearn.dummy import DummyClassifier

from adryn import cli as cli_module
from adryn.api import app
from adryn.core.customer import FEATURES
from adryn.core.intelligence import build_mirror_summary
from adryn.core.privacy import build_privacy_twin, detect_pii_columns
from adryn.core.quality import run_quality_checks
from adryn.data.platform import generate_platform, validate_platform
from adryn.db.postgres import store_pipeline_run, validate_run_tables


@pytest.fixture(scope="module")
def platform():
    return generate_platform(20261001, customer_count=100)


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), -float("inf")])
def test_ingestion_rejects_nonfinite_invoice_amount(platform, amount):
    tables = {name: frame.copy() for name, frame in platform.items()}
    tables["orders"].loc[0, "amount"] = amount
    with pytest.raises(ValueError, match="positive_amount"):
        validate_platform(tables)


def test_ingestion_rejects_multiple_subscriptions_per_customer(platform):
    tables = {name: frame.copy() for name, frame in platform.items()}
    duplicate = tables["subscriptions"].iloc[[0]].copy()
    duplicate["subscription_id"] = "DIFFERENT-SUBSCRIPTION-ID"
    tables["subscriptions"] = pd.concat([tables["subscriptions"], duplicate], ignore_index=True)
    with pytest.raises(ValueError, match="unique_customer_subscription"):
        validate_platform(tables)


def test_database_write_refuses_ambient_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("ADRYN_DATABASE_URL", "postgresql://ambient:dummy@localhost/other")
    writes = []
    monkeypatch.setattr(cli_module, "init_database", lambda settings: writes.append(True))
    result = CliRunner().invoke(cli_module.cli, ["init-db"])
    assert result.exit_code == 1
    assert not writes


def test_incomplete_business_snapshot_rejected_before_connect(monkeypatch):
    from adryn.db import postgres
    from adryn.settings import Settings

    connected = []

    def connect(*args, **kwargs):
        connected.append(True)
        raise RuntimeError("Connection should not be attempted")

    monkeypatch.setattr(postgres.psycopg, "connect", connect)
    summary = {"run_id": str(uuid4()), "business": {"customers": 1}}
    with pytest.raises(ValueError, match="Missing required"):
        store_pipeline_run(Settings(database_url="unused-test-value"), summary, {})
    assert not connected


def test_prediction_refuses_metadata_from_another_run(tmp_path, monkeypatch):
    monkeypatch.setenv("ADRYN_OUTPUT_DIR", str(tmp_path))
    run_id = str(uuid4())
    (tmp_path / "pipeline_summary.json").write_text(json.dumps({"run_id": run_id}))
    models = tmp_path / "models"
    models.mkdir()
    (models / "metadata.json").write_text(json.dumps({
        "run_id": str(uuid4()), "as_of": "2026-09-30", "threshold": 0.5,
        "features": FEATURES,
    }))
    model = DummyClassifier().fit(pd.DataFrame([[1] * 7, [2] * 7], columns=FEATURES), [0, 1])
    joblib.dump(model, models / "churn.joblib")
    payload = dict(zip(FEATURES, [1, 10, 1, 0, 0, 19, 1]))
    assert TestClient(app).post("/predict/churn", json=payload).status_code == 503


@pytest.mark.parametrize("status", [None, "unexpected", ""])
def test_unknown_consent_requires_review(status):
    result = build_privacy_twin(pd.DataFrame([
        {"customer_id": "C1", "region": "NA", "consent_status": status}
    ]))
    assert bool(result.iloc[0].requires_human_review)


def test_clean_data_and_no_pii_preserve_empty_output_schema():
    quality = run_quality_checks(
        pd.DataFrame([{"customer_id": "C1", "email": "a@example.test", "phone": "123"}]),
        pd.DataFrame([{"order_id": "O1", "amount": 19}]),
    )
    pii = detect_pii_columns("aggregate", pd.DataFrame({"amount": [19]}))
    assert build_mirror_summary(quality.findings, pii).empty


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonstandard_nonfinite_json_returns_client_error(value):
    payload = dict(zip(FEATURES, [1, 10, 1, 0, 0, value, 1]))
    response = TestClient(app, raise_server_exceptions=False).post(
        "/predict/churn", content=json.dumps(payload), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert all("input" not in error for error in response.json()["detail"])


def test_loader_rejects_mixed_run_rows():
    run_id = str(uuid4())
    tables = {
        "quality_findings": pd.DataFrame({"run_id": [str(uuid4())]}),
        "evidence_graph_edges": pd.DataFrame(),
    }
    with pytest.raises(ValueError, match="Mixed or missing run identifiers"):
        validate_run_tables({"run_id": run_id}, tables)


def test_database_write_uses_literal_project_file(tmp_path, monkeypatch):
    from adryn.settings import Settings

    monkeypatch.setattr(cli_module, "PROJECT_ROOT", tmp_path)
    url = "postgresql://local:fake${VALUE}@localhost/adryn"
    (tmp_path / ".env").write_text(f"ADRYN_DATABASE_URL={url}\n")
    monkeypatch.setenv("ADRYN_DATABASE_URL", "postgresql://ambient:dummy@localhost/other")
    captured = []
    monkeypatch.setattr(cli_module, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(cli_module, "init_database", lambda settings: captured.append(settings))
    result = CliRunner().invoke(cli_module.cli, ["init-db"])
    assert result.exit_code == 0
    assert captured[0].database_url == url
    assert url not in repr(captured[0])
    assert url not in result.output
