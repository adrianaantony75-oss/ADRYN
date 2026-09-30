from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adryn.reports.pipeline import run_pipeline
from adryn.settings import Settings


@pytest.fixture(scope="module")
def product_output(tmp_path_factory):
    root = tmp_path_factory.mktemp("product")
    settings = Settings(
        raw_data_dir=root / "raw",
        processed_data_dir=root / "processed",
        output_dir=root / "outputs",
    )
    settings.ensure_dirs()
    run_pipeline(settings)
    from adryn.io import current_output

    return current_output(settings.output_dir)


def test_all_business_views_and_region_filter(product_output, monkeypatch):
    monkeypatch.setenv("ADRYN_OUTPUT_DIR", str(product_output))
    from adryn.product import PAGES

    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "app" / "streamlit_app.py"), default_timeout=20
    ).run()
    assert not app.exception
    app.multiselect(key="region_filter").set_value(["NA"]).run()
    assert not app.exception
    for page in PAGES:
        app.radio(key="business_page").set_value(page).run()
        assert not app.exception, f"{page}: {app.exception}"
    app.radio(key="business_page").set_value("Customer 360").run()
    next(field for field in app.text_input if field.label == "Reviewer").set_value("QA analyst")
    next(field for field in app.text_area if field.label == "Evidence and next action").set_value(
        "Investigate the billing history."
    )
    next(button for button in app.button if button.label == "Save review").click().run()
    assert not app.exception
    assert any(message.value == "Review recorded." for message in app.success)
    next(field for field in app.selectbox if field.label == "Workspace").set_value(
        "Trust operations"
    ).run()
    for page in [
        "Overview",
        "Data quality",
        "Privacy",
        "Contracts",
        "AI reviews",
        "Evidence & signals",
    ]:
        app.radio(key="trust_page").set_value(page).run()
        assert not app.exception, f"{page}: {app.exception}"


def test_prediction_api_matches_current_member_score(product_output, monkeypatch):
    from fastapi.testclient import TestClient

    from adryn.api import app
    from adryn.core.customer import FEATURES
    from adryn.io import read_table

    monkeypatch.setenv("ADRYN_OUTPUT_DIR", str(product_output))
    row = read_table(product_output / "retention_queue.csv").iloc[0]
    data = {key: int(row[key]) if key != "monthly_price" else float(row[key]) for key in FEATURES}
    response = TestClient(app).post("/predict/churn", json=data)
    assert response.status_code == 200
    assert response.json()["churn_probability"] == pytest.approx(row.churn_probability)


def test_dashboard_handles_broken_publication(tmp_path, monkeypatch):
    monkeypatch.setenv("ADRYN_OUTPUT_DIR", str(tmp_path))
    (tmp_path / "current_run.json").write_text("{broken", encoding="utf-8")
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "app" / "streamlit_app.py"), default_timeout=20
    ).run()
    assert not app.exception
    assert any("published analysis is unavailable" in message.value for message in app.error)
