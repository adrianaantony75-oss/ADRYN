import pandas as pd
import pytest

from adryn.core.customer import churn_analysis, customer_metrics
from adryn.core.decision_science import analyze_experiment, forecast_demand
from adryn.data.platform import AS_OF, generate_platform, validate_platform


@pytest.fixture(scope="module")
def ecosystem():
    return generate_platform(20261001)


def test_relational_integrity_and_temporal_censoring(ecosystem):
    assert validate_platform(ecosystem).failed_rows.sum() == 0
    assert pd.to_datetime(ecosystem["events"].event_date).max() <= AS_OF
    starts = ecosystem["subscriptions"].set_index("customer_id").start_date
    paid = ecosystem["events"].query("event_type == 'paid'").set_index("customer_id").event_date
    pd.testing.assert_series_equal(starts.sort_index(), paid.sort_index(), check_names=False)


def test_foreign_key_corruption_is_rejected(ecosystem):
    corrupt = {key: value.copy() for key, value in ecosystem.items()}
    corrupt["orders"].loc[0, "customer_id"] = "UNKNOWN"
    with pytest.raises(ValueError, match="customer_foreign_key"):
        validate_platform(corrupt)


def test_revenue_reconciles_and_cohorts_have_valid_denominators(ecosystem):
    output = customer_metrics(ecosystem)
    paid = ecosystem["orders"].query("payment_status == 'paid'").amount.sum()
    assert output["customer_360"].monetary.sum() == paid
    assert output["monthly_kpis"].collected_revenue.sum() == paid
    cohorts = output["cohort_retention"]
    assert cohorts.retention.between(0, 1).all()
    assert (cohorts.retained <= cohorts.cohort_size).all()


def test_churn_temporal_boundaries_and_current_eligibility(ecosystem):
    output, artifact = churn_analysis(ecosystem, 7)
    meta = artifact["metadata"]
    assert meta["training_last_label_end"] < meta["validation_first_cutoff"]
    assert meta["validation_first_cutoff"] < meta["test_first_cutoff"]
    active = ecosystem["subscriptions"].query("cancelled_at.isnull()")
    assert set(output["retention_queue"].customer_id) == set(active.customer_id)
    assert output["retention_queue"].churn_probability.between(0, 1).all()
    assert set(output["churn_metrics"].model) == {
        "Prevalence baseline",
        "Logistic regression",
        "Random forest",
    }


def test_forecast_holdout_and_baseline_selection(ecosystem):
    outputs = forecast_demand(ecosystem["activity"])
    backtests = outputs["forecast_backtests"]
    assert (backtests.origin < backtests.month).all()
    comparison = outputs["forecast_comparison"]
    selected = comparison.query("split == 'selection'").sort_values("mae").iloc[0].method
    assert (outputs["demand_forecast"].method == selected).all()
    assert len(outputs["demand_forecast"]) == 3


def test_experiment_includes_all_mature_assignments(ecosystem):
    result = analyze_experiment(ecosystem["experiment"], ecosystem["customers"])[
        "experiment_results"
    ]
    overall = result.query("segment == 'Overall'").iloc[0]
    assert (
        overall.control_n + overall.treatment_n
        == ecosystem["experiment"].eligible_for_analysis.sum()
    )
    assert overall.ci95_low <= overall.absolute_effect <= overall.ci95_high
    assert overall.required_per_arm_for_5pp > 1000
