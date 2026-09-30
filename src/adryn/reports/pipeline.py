from __future__ import annotations

import json
from uuid import uuid4

import pandas as pd

from adryn.core.ai_eval import prioritize_review_risk
from adryn.core.analytics import analyze_order_drift, compare_model_groups, detect_order_anomalies
from adryn.core.intelligence import (
    build_ambiguity_lab,
    build_evidence_graph,
    build_failure_genome,
    build_mirror_summary,
    build_powerbi_tables,
    build_shadow_reviewer,
)
from adryn.core.privacy import build_privacy_twin, detect_pii_columns
from adryn.core.quality import run_quality_checks
from adryn.core.reconciliation import reconcile_contracts
from adryn.data.synthetic import generate_enterprise_data
from adryn.io import read_table
from adryn.settings import Settings


def run_pipeline(settings: Settings) -> dict:
    """Publish a complete immutable output snapshot with one atomic pointer update."""
    run_id = str(uuid4())
    snapshots = settings.output_dir / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    building = snapshots / f".building-{run_id}"
    building.mkdir()
    stage = settings.model_copy(update={"output_dir": building})
    summary = _run_pipeline(stage, run_id)
    building.rename(snapshots / run_id)
    pointer = settings.output_dir / f".current-{run_id}.json"
    pointer.write_text(json.dumps({"run_id": run_id}, indent=2), encoding="utf-8")
    pointer.replace(settings.output_dir / "current_run.json")
    return summary


def _run_pipeline(settings: Settings, run_id: str) -> dict:
    paths = generate_enterprise_data(settings.raw_data_dir, settings.random_seed)
    customers = read_table(paths.customers)
    orders = read_table(paths.orders)
    contracts = read_table(paths.contracts)
    ai_reviews = read_table(paths.ai_reviews)

    quality = run_quality_checks(customers, orders)
    pii = pd.concat(
        [
            detect_pii_columns("customers", customers),
            detect_pii_columns("orders", orders),
            detect_pii_columns("contracts", contracts),
            detect_pii_columns("ai_reviews", ai_reviews),
        ],
        ignore_index=True,
    )
    privacy_twin = build_privacy_twin(customers)
    reconciled = reconcile_contracts(contracts)
    scored_reviews, ai_metrics = prioritize_review_risk(ai_reviews, settings.random_seed)
    order_anomalies = detect_order_anomalies(orders, settings.random_seed)
    drift = analyze_order_drift(orders)
    model_comparison = compare_model_groups(ai_reviews)
    feature_importance = ai_metrics.pop("feature_importance")
    group_evaluation = ai_metrics.pop("group_evaluation")
    mirror = build_mirror_summary(quality.findings, pii)
    shadow = build_shadow_reviewer(scored_reviews)
    failure_genome = build_failure_genome(quality.findings, reconciled, scored_reviews)
    evidence_graph = build_evidence_graph(quality.findings, pii, reconciled)
    ambiguity_lab = build_ambiguity_lab(scored_reviews)

    summary = {
        "run_id": run_id,
        "seed": settings.random_seed,
        "customers_rows": len(customers),
        "orders_rows": len(orders),
        "quality_findings": len(quality.findings),
        "pii_findings": len(pii),
        "privacy_records_requiring_review": int(privacy_twin["requires_human_review"].sum()),
        "contract_records_requiring_review": int(reconciled["requires_review"].sum()),
        "ai_reviews_scored": len(scored_reviews),
        "anomalous_orders": int(order_anomalies["is_anomaly"].sum()),
        "ambiguous_ai_reviews": len(ambiguity_lab),
        "evidence_edges": len(evidence_graph),
        "failure_modes": len(failure_genome),
        "ai_eval_accuracy": float(ai_metrics["accuracy"]),
        "ai_eval_precision": float(ai_metrics["precision"]),
        "ai_eval_recall": float(ai_metrics["recall"]),
        "ai_eval_f1": float(ai_metrics["f1"]),
        "ai_eval_roc_auc": float(ai_metrics["roc_auc"]),
        "ai_eval_test_rows": int(ai_metrics["test_rows"]),
        "ai_eval_review_threshold": float(ai_metrics["review_threshold"]),
    }
    tables = {
        "quality_findings": quality.findings,
        "data_profile": quality.profile,
        "pii_findings": pii,
        "privacy_twin": privacy_twin,
        "contract_reconciliation": reconciled,
        "ai_review_priorities": scored_reviews,
        "mirror_summary": mirror,
        "shadow_reviewer": shadow,
        "failure_genome": failure_genome,
        "evidence_graph_edges": evidence_graph,
        "ambiguity_lab": ambiguity_lab,
        "order_anomalies": order_anomalies,
        "order_drift": drift,
        "model_comparison": model_comparison,
        "ai_feature_importance": feature_importance,
        "ai_group_evaluation": group_evaluation,
    }
    powerbi = build_powerbi_tables(summary, mirror, failure_genome)
    powerbi["powerbi_review_fact"] = scored_reviews[
        [
            "review_id",
            "model_name",
            "prompt_category",
            "severity",
            "human_disagreed",
            "review_risk_score",
            "review_priority",
        ]
    ].copy()
    powerbi["powerbi_contract_fact"] = reconciled[
        [
            "contract_id",
            "customer_id",
            "value_delta",
            "status_mismatch",
            "value_mismatch",
            "requires_review",
        ]
    ].copy()
    powerbi["powerbi_quality_fact"] = quality.findings.copy()
    for table in [*tables.values(), *powerbi.values()]:
        table.insert(0, "run_id", summary["run_id"])
    for name, table in tables.items():
        table.to_csv(settings.output_dir / f"{name}.csv", index=False)
    for name, table in powerbi.items():
        table.to_csv(settings.output_dir / f"{name}.csv", index=False)
    (settings.output_dir / "pipeline_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    _write_executive_brief(summary, settings.output_dir / "executive_brief.md")
    from adryn.reports.presentation import write_executive_deck

    write_executive_deck(
        summary, drift, model_comparison, settings.output_dir / "ADRYN_Executive_Brief.pptx"
    )
    from adryn.reports.business import run_business_analysis

    summary["business"] = run_business_analysis(settings, summary["run_id"])
    (settings.output_dir / "pipeline_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def _write_executive_brief(summary: dict, path) -> None:
    lines = [
        "# ADRYN Executive Brief",
        "",
        "All figures in this brief were generated by the local ADRYN pipeline.",
        "",
        f"- Customers assessed: {summary['customers_rows']}",
        f"- Orders assessed: {summary['orders_rows']}",
        f"- Data-quality findings: {summary['quality_findings']}",
        f"- PII findings: {summary['pii_findings']}",
        f"- Privacy records requiring review: {summary['privacy_records_requiring_review']}",
        f"- Contract records requiring review: {summary['contract_records_requiring_review']}",
        f"- AI review decisions scored: {summary['ai_reviews_scored']}",
        f"- Ambiguous AI reviews for lab analysis: {summary['ambiguous_ai_reviews']}",
        f"- Evidence graph edges: {summary['evidence_edges']}",
        f"- Failure modes detected: {summary['failure_modes']}",
        f"- AI disagreement model accuracy: {summary['ai_eval_accuracy']:.3f}",
        f"- AI disagreement model precision: {summary['ai_eval_precision']:.3f}",
        f"- AI disagreement model recall: {summary['ai_eval_recall']:.3f}",
        f"- AI disagreement model F1: {summary['ai_eval_f1']:.3f}",
        f"- AI risk model ROC AUC: {summary['ai_eval_roc_auc']:.3f}",
        f"- AI risk model recall at {summary['ai_eval_review_threshold']:.2f} threshold: {summary['ai_eval_recall']:.3f}",
        f"- Order anomalies flagged: {summary['anomalous_orders']}",
        "- Model comparison and drift checks are exploratory, unadjusted signals.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
