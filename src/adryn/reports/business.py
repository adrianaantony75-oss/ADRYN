from __future__ import annotations

import hashlib
import json
import platform
from datetime import UTC, datetime
from importlib.metadata import version

import joblib
import pandas as pd

from adryn.core.customer import churn_analysis, customer_metrics
from adryn.core.decision_science import analyze_experiment, customer_voice, forecast_demand
from adryn.data.platform import AS_OF, validate_platform
from adryn.io import read_table
from adryn.settings import Settings


def run_business_analysis(settings: Settings, run_id: str) -> dict:
    source = settings.raw_data_dir / "platform"
    tables = {p.stem: read_table(p) for p in source.glob("*.csv")}
    validation = validate_platform(tables)
    crm = read_table(settings.raw_data_dir / "customers.csv")
    clean_crm = crm.drop_duplicates("customer_id").copy()
    invalid_email = ~clean_crm.email.fillna("").str.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    clean_crm.loc[invalid_email, "email"] = None
    clean_crm.to_csv(settings.processed_data_dir / "customers.csv", index=False)
    quarantine = crm[crm.duplicated("customer_id", keep="first")].copy()
    quarantine["reason"] = "Duplicate CRM customer key; first identical record retained"
    quarantine.to_csv(settings.processed_data_dir / "customer_quarantine.csv", index=False)
    paid = tables["orders"].query("payment_status == 'paid'")
    naive_revenue = paid.merge(crm[["customer_id"]], on="customer_id").amount.sum()
    remediation = pd.DataFrame(
        [
            {
                "rule": "duplicate_customer_key",
                "affected_rows": len(quarantine),
                "action": "Quarantine duplicate projection rows",
                "impact": "Prevent duplicated revenue when joining customer attributes",
                "measured_revenue_overcount_avoided": float(naive_revenue - paid.amount.sum()),
            },
            {
                "rule": "invalid_email",
                "affected_rows": int(invalid_email.sum()),
                "action": "Set invalid email to null pending source correction",
                "impact": "Exclude malformed addresses from contact eligibility",
                "measured_revenue_overcount_avoided": 0.0,
            },
        ]
    )
    outputs = customer_metrics(tables)
    outputs["quality_remediation"] = remediation
    churn, artifact = churn_analysis(tables, settings.random_seed)
    outputs.update(churn)
    outputs.update(forecast_demand(tables["activity"]))
    outputs.update(analyze_experiment(tables["experiment"], tables["customers"]))
    voice, voice_model = customer_voice(tables["tickets"], settings.random_seed)
    outputs.update(voice)
    outputs["platform_validation"] = validation
    for name, source_name in {
        "subscription_events": "events",
        "subscription_orders": "orders",
        "subscription_activity": "activity",
        "subscription_contracts": "subscriptions",
        "subscription_customers": "customers",
        "onboarding_assignments": "experiment",
    }.items():
        outputs[name] = tables[source_name]
    outputs["customer_360"] = outputs["customer_360"].merge(
        churn["retention_queue"][
            [
                "customer_id",
                "churn_probability",
                "monthly_revenue_exposure",
                "value_12m_scenario",
                "suggested_action",
                "review_required",
            ]
        ],
        on="customer_id",
        how="left",
        validate="one_to_one",
    )
    output = settings.output_dir
    for name, frame in outputs.items():
        frame = frame.copy()
        frame.insert(0, "run_id", run_id)
        frame.to_csv(output / f"{name}.csv", index=False)
    models = output / "models"
    models.mkdir(exist_ok=True)
    joblib.dump(artifact["model"], models / "churn.joblib")
    joblib.dump(voice_model, models / "voice.joblib")
    metadata = artifact["metadata"] | {
        "run_id": run_id,
        "as_of": AS_OF.date().isoformat(),
        "seed": settings.random_seed,
        "created_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "sklearn": version("scikit-learn"),
        "source_hashes": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.glob("*.csv"))
        },
    }
    (models / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    ledger = outputs["subscription_orders"]
    current = outputs["customer_360"]
    summary = {
        "run_id": run_id,
        "as_of": AS_OF.date().isoformat(),
        "synthetic": True,
        "company": "ADRYN Learning",
        "customers": len(current),
        "active_subscribers": int((current.status == "Active").sum()),
        "collected_revenue": float(ledger.loc[ledger.payment_status == "paid", "amount"].sum()),
        "current_mrr": float(current.loc[current.status == "Active", "monthly_price"].sum()),
        "retention_reviews": int(churn["retention_queue"].review_required.sum()),
        "selected_churn_model": metadata["selected_model"],
        "experiment_decision": outputs["experiment_results"].iloc[0].decision,
        "forecast_method": outputs["demand_forecast"].iloc[0].method,
    }
    (output / "business_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_decision_brief(output, summary, outputs)
    tracking = output / "evaluation"
    tracking.mkdir(parents=True, exist_ok=True)
    (tracking / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for name in ["churn_metrics", "forecast_comparison", "experiment_results", "voice_metrics"]:
        outputs[name].to_csv(tracking / f"{name}.csv", index=False)
    return summary


def _write_decision_brief(output, summary, tables):
    chosen = tables["churn_metrics"].query("selected and split == 'test'").iloc[0]
    experiment = tables["experiment_results"].query("segment == 'Overall'").iloc[0]
    forecast = tables["forecast_comparison"].query("selected and split == 'final_holdout'").iloc[0]
    monthly = tables["monthly_kpis"].groupby("month").sum(numeric_only=True)
    current, previous = monthly.iloc[-1], monthly.iloc[-2]
    difference = current.collected_revenue - previous.collected_revenue
    brief = f"""# ADRYN Learning: decision brief

Snapshot: {summary["as_of"]}. Run: {summary["run_id"]}. All records and outcomes are synthetic. USD amounts are derived from generated invoices; they are not real company results.

## Business position
The scenario contains {summary["customers"]:,} customers and {summary["active_subscribers"]:,} active subscribers. Current MRR is ${summary["current_mrr"]:,.0f}. Cumulative collections are ${summary["collected_revenue"]:,.0f}. September collections are ${current.collected_revenue:,.0f}, a change of ${difference:+,.0f} from August. September has {int(current.failed_payments):,} failed billing attempts.

Decision: investigate failed payments through the customer billing history. Collection changes are descriptive; this analysis does not establish their cause.

## Retention review
{summary["selected_churn_model"]} won on validation average precision. On {int(chosen.rows):,} held-out customer-month observations, average precision is {chosen.average_precision:.3f}, ROC AUC is {chosen.roc_auc:.3f}, precision is {chosen.precision:.3f}, and recall is {chosen.recall:.3f}. The current queue contains {summary["retention_reviews"]:,} review candidates at the validation-selected threshold.

Decision: use this as a synthetic review-workload demonstration. Inspect model calibration, SHAP and customer evidence before recording an action. No prevented churn or saved revenue is claimed.

## Demand planning
The selected method is {summary["forecast_method"]}. Final held-out MAE is {forecast.mae:,.1f} sessions/month and WAPE is {forecast.wape:.1%}. The published forecast covers three months. Empirical residual bands come from four earlier origins and do not establish calibrated coverage.

Decision: compare the capacity scenario to the forecast and residual range. Acquire more time history before relying on the model for real capacity commitments.

## Onboarding experiment
There are {int(experiment.control_n):,} control and {int(experiment.treatment_n):,} treatment assignments with mature 60-day outcomes. The absolute retention difference is {experiment.absolute_effect * 100:+.2f} percentage points; the approximate 95% interval is [{experiment.ci95_low * 100:.2f}, {experiment.ci95_high * 100:.2f}]. The planning requirement is {int(experiment.required_per_arm_for_5pp):,} members per arm for a five-point effect.

Decision: {experiment.decision}. Regional results are exploratory. Individual uplift is deferred because this sample does not support reliable treatment targeting.

## Customer voice and trust
Support themes link to affected customers and ticket evidence. Template-based classification can score highly without demonstrating real-language usefulness. Review the latest issue-share changes and validate routing against human labels before external use.

The duplicate-CRM join diagnostic measures ${tables["quality_remediation"].measured_revenue_overcount_avoided.sum():,.0f} of synthetic revenue overcount avoided by using unique customer keys. This is a data-quality calculation, not a realized financial saving.

## Delivery boundaries
The local workspace, API and analysis are implementation artifacts. PostgreSQL connectivity, Docker execution, an actual Power BI Desktop report and authenticated shared deployment require separate verification. The legacy presentation covers trust operations; this brief covers the expanded business analysis.
"""
    (output / "decision_brief.md").write_text(brief, encoding="utf-8")
