from pathlib import Path

import pandas as pd
from pptx import Presentation

from adryn.reports.pipeline import run_pipeline
from adryn.settings import Settings


def test_pipeline_generates_computed_outputs(tmp_path: Path) -> None:
    settings = Settings(
        random_seed=123,
        raw_data_dir=tmp_path / "raw",
        processed_data_dir=tmp_path / "processed",
        output_dir=tmp_path / "outputs",
    )
    settings.ensure_dirs()

    summary = run_pipeline(settings)
    from adryn.io import current_output

    settings.output_dir = current_output(settings.output_dir)

    assert summary["customers_rows"] > 500
    assert summary["orders_rows"] > 1500
    assert summary["quality_findings"] > 0
    assert summary["pii_findings"] > 0
    assert summary["contract_records_requiring_review"] > 0
    assert summary["ambiguous_ai_reviews"] > 0
    assert summary["evidence_edges"] > 0
    assert summary["failure_modes"] > 0
    anomalies = pd.read_csv(settings.output_dir / "order_anomalies.csv")
    assert summary["anomalous_orders"] == int(anomalies["is_anomaly"].sum())
    assert len(anomalies) == summary["orders_rows"]
    assert 0 <= summary["ai_eval_roc_auc"] <= 1
    assert summary["ai_eval_recall"] > 0
    assert 0 <= summary["ai_eval_accuracy"] <= 1
    assert (settings.output_dir / "pipeline_summary.json").exists()
    assert (settings.output_dir / "executive_brief.md").exists()
    assert (settings.output_dir / "powerbi_kpis.csv").exists()
    assert (settings.output_dir / "evidence_graph_edges.csv").exists()
    assert (settings.output_dir / "order_drift.csv").exists()
    assert (settings.output_dir / "powerbi_review_fact.csv").exists()
    assert (settings.output_dir / "ai_feature_importance.csv").exists()
    assert (settings.output_dir / "ai_group_evaluation.csv").exists()
    assert (settings.output_dir / "ADRYN_Executive_Brief.pptx").exists()
    assert len(Presentation(settings.output_dir / "ADRYN_Executive_Brief.pptx").slides) == 4
    exported = pd.read_csv(settings.output_dir / "evidence_graph_edges.csv")
    assert exported["run_id"].nunique() == 1
    assert exported["run_id"].iloc[0] == summary["run_id"]
    from adryn.io import read_table

    customers = read_table(settings.output_dir / "customer_360.csv")
    monthly = read_table(settings.output_dir / "monthly_kpis.csv")
    assert set(customers.region) == {"NA", "EU", "APAC", "LATAM"}
    assert customers.monetary.sum() == monthly.collected_revenue.sum()
    assert summary["business"]["collected_revenue"] == monthly.collected_revenue.sum()
