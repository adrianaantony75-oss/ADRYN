import pandas as pd

from adryn.core.analytics import analyze_order_drift, compare_model_groups, detect_order_anomalies
from adryn.core.privacy import build_privacy_twin, detect_pii_columns
from adryn.core.reconciliation import reconcile_contracts


def test_privacy_detection_and_twin_keep_review_state() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": ["A", "B", "C"],
            "full_name": ["A Person", "B Person", "C Person"],
            "email": ["a@example.test", "b@example.test", "c@example.test"],
            "region": ["EU", "NA", "APAC"],
            "consent_status": ["granted", "revoked", "unknown"],
        }
    )
    findings = detect_pii_columns("customers", customers)
    twin = build_privacy_twin(customers)

    assert set(findings["column"]) == {"full_name", "email"}
    assert twin["requires_human_review"].tolist() == [False, True, True]


def test_reconciliation_marks_value_and_status_differences() -> None:
    contracts = pd.DataFrame(
        {
            "contract_id": ["C1", "C2"],
            "customer_id": ["A", "B"],
            "crm_contract_value": [1000.0, 1000.0],
            "erp_contract_value": [1000.0, 1200.0],
            "crm_status": ["active", "active"],
            "erp_status": ["active", "expired"],
        }
    )
    result = reconcile_contracts(contracts)

    assert result["requires_review"].tolist() == [False, True]
    assert result.loc[1, "value_delta"] == -200.0


def test_anomaly_and_temporal_checks_return_measured_signals() -> None:
    orders = pd.DataFrame(
        {
            "order_id": [f"O{i}" for i in range(40)],
            "order_date": pd.date_range("2026-01-01", periods=40).astype(str),
            "amount": [10.0] * 39 + [10000.0],
        }
    )
    anomalies = detect_order_anomalies(orders, seed=7)
    drift = analyze_order_drift(orders)

    assert anomalies["is_anomaly"].sum() >= 1
    assert anomalies.iloc[0]["order_id"] == "O39"
    assert drift.loc[0, "earlier_rows"] + drift.loc[0, "later_rows"] == 40
    assert drift.loc[0, "status"] in {"distribution_shift_signal", "no_detected_shift"}


def test_model_comparison_is_explicitly_observational() -> None:
    reviews = pd.DataFrame(
        {
            "model_name": ["m1"] * 4 + ["m2"] * 4,
            "human_disagreed": [False, False, False, True, True, True, False, True],
        }
    )
    result = compare_model_groups(reviews)

    assert len(result) == 2
    assert result["omnibus_p_value"].notna().all()
    assert (result["rate_ci95_low"] <= result["disagreement_rate"]).all()
    assert (result["rate_ci95_high"] >= result["disagreement_rate"]).all()
    assert result["interpretation"].str.contains("do not establish causation").all()
