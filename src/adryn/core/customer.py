"""Ledger-derived customer metrics and time-aware retention modeling."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.cluster import KMeans
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
    silhouette_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from adryn.data.platform import AS_OF

FEATURES = [
    "sessions",
    "learning_minutes",
    "days_since_activity",
    "support_tickets",
    "payment_failed",
    "monthly_price",
    "tenure_months",
]


def customer_metrics(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    customers, subscriptions, orders = (
        tables[x].copy() for x in ["customers", "subscriptions", "orders"]
    )
    paid = orders[orders.payment_status == "paid"].copy()
    paid["date"] = pd.to_datetime(paid.order_date)
    rfm = (
        paid.groupby("customer_id")
        .agg(
            last_payment=("date", "max"),
            frequency=("order_id", "count"),
            monetary=("amount", "sum"),
        )
        .reset_index()
    )
    rfm["recency_days"] = (AS_OF - rfm.last_payment).dt.days
    customer = customers.merge(rfm, on="customer_id", how="left").merge(
        subscriptions[["customer_id", "start_date", "cancelled_at", "monthly_price"]],
        how="left",
        on="customer_id",
    )
    for col in ["frequency", "monetary", "monthly_price"]:
        customer[col] = customer[col].fillna(0)
    customer["recency_days"] = customer.recency_days.fillna(
        (AS_OF - pd.to_datetime(customer.signup_date)).dt.days
    )
    customer["status"] = np.select(
        [customer.start_date.isna(), customer.cancelled_at.notna()],
        ["Trial", "Cancelled"],
        default="Active",
    )
    latest = tables["activity"].sort_values("month").groupby("customer_id").tail(1)
    customer = customer.merge(
        latest[["customer_id", "sessions", "support_tickets", "days_since_activity"]],
        how="left",
        on="customer_id",
    ).fillna({"sessions": 0, "support_tickets": 0, "days_since_activity": 30})
    cluster_features = ["recency_days", "frequency", "monetary", "sessions"]
    x = StandardScaler().fit_transform(np.log1p(customer[cluster_features]))
    km = KMeans(n_clusters=4, n_init=10, random_state=42).fit(x)
    segmentation = []
    for k in range(2, 7):
        candidate = km if k == 4 else KMeans(n_clusters=k, n_init=10, random_state=42).fit(x)
        segmentation.append(
            {
                "clusters": k,
                "silhouette": silhouette_score(
                    x, candidate.labels_, sample_size=min(800, len(x)), random_state=42
                ),
                "inertia": candidate.inertia_,
                "selected": k == 4,
                "selection_basis": "Four operational groups chosen for review capacity; silhouette is diagnostic, not an outcome claim",
            }
        )
    customer["cluster"] = km.labels_
    # Labels describe centroids rather than assigning a value judgement to arbitrary IDs.
    rank = customer.groupby("cluster").monetary.mean().sort_values().index
    labels = dict(zip(rank, ["Early journey", "Developing", "Established", "Core members"]))
    customer["segment"] = customer.cluster.map(labels)
    customer["r_score"] = pd.cut(
        customer.recency_days, [-1, 30, 60, 120, 365, np.inf], labels=[5, 4, 3, 2, 1]
    ).astype(int)
    customer["f_score"] = pd.cut(
        customer.frequency, [-1, 0, 2, 5, 11, np.inf], labels=[1, 2, 3, 4, 5]
    ).astype(int)
    customer["m_score"] = pd.cut(
        customer.monetary, [-1, 0, 100, 300, 800, np.inf], labels=[1, 2, 3, 4, 5]
    ).astype(int)
    customer["rfm_score"] = customer.r_score * 100 + customer.f_score * 10 + customer.m_score
    activity = tables["activity"].merge(
        customers[["customer_id", "region", "plan"]], on="customer_id", validate="many_to_one"
    )
    monthly = (
        activity.groupby(["month", "region", "plan"])
        .agg(
            billed_subscribers=("customer_id", "size"),
            sessions=("sessions", "sum"),
            support_tickets=("support_tickets", "sum"),
            failed_payments=("payment_failed", "sum"),
            billed_amount=("monthly_price", "sum"),
        )
        .reset_index()
    )
    ledger = orders.merge(customers[["customer_id", "region", "plan"]], on="customer_id")
    ledger["month"] = (
        pd.to_datetime(ledger.order_date)
        .dt.to_period("M")
        .dt.to_timestamp()
        .dt.strftime("%Y-%m-%d")
    )
    revenue = (
        ledger[ledger.payment_status == "paid"]
        .groupby(["month", "region", "plan"])
        .amount.sum()
        .rename("collected_revenue")
        .reset_index()
    )
    monthly = monthly.merge(revenue, how="left", on=["month", "region", "plan"]).fillna(
        {"collected_revenue": 0}
    )
    cohort = subscriptions.copy()
    cohort["cohort"] = pd.to_datetime(cohort.start_date).dt.to_period("M").astype(str)
    cohort_rows = []
    for start, group in cohort.groupby("cohort"):
        for age in range(30):
            end = pd.Period(start, "M").to_timestamp() + pd.offsets.MonthEnd(age + 1)
            if end > AS_OF:
                break
            retained = int(
                (group.cancelled_at.isna() | (pd.to_datetime(group.cancelled_at) > end)).sum()
            )
            cohort_rows.append(
                {
                    "cohort": start,
                    "age_months": age,
                    "cohort_size": len(group),
                    "retained": retained,
                    "retention": retained / len(group),
                }
            )
    return {
        "customer_360": customer.drop(columns=["cluster"]),
        "monthly_kpis": monthly,
        "cohort_retention": pd.DataFrame(cohort_rows),
        "segmentation_evaluation": pd.DataFrame(segmentation),
    }


def churn_analysis(
    tables: dict[str, pd.DataFrame], seed: int
) -> tuple[dict[str, pd.DataFrame], dict]:
    activity = tables["activity"].copy()
    end = pd.to_datetime(activity.month) + pd.offsets.MonthEnd(0)
    cancelled = activity.customer_id.map(
        tables["subscriptions"].set_index("customer_id").cancelled_at
    )
    cancelled = pd.to_datetime(cancelled)
    # Only members still subscribed at the feature cutoff are eligible for scoring.
    panel = activity[cancelled.isna() | (cancelled > end)].copy()
    panel["feature_cutoff"] = pd.to_datetime(panel.month) + pd.offsets.MonthEnd(0)
    panel["label_end"] = panel.feature_cutoff + pd.offsets.MonthEnd(1)
    cancellations = pd.to_datetime(
        panel.customer_id.map(tables["subscriptions"].set_index("customer_id").cancelled_at)
    )
    panel["churn_next_month"] = (cancellations.notna() & (cancellations <= panel.label_end)).astype(
        int
    )
    matured = panel[panel.label_end <= AS_OF].copy()
    train = matured[matured.label_end < "2026-02-01"]
    validation = matured[
        (matured.feature_cutoff >= "2026-02-01") & (matured.label_end < "2026-06-01")
    ]
    test = matured[matured.feature_cutoff >= "2026-06-01"]
    for split in (train, validation, test):
        if split.churn_next_month.nunique() != 2:
            raise ValueError("Insufficient mature churn outcomes for time-based evaluation.")
    candidates = {
        "Prevalence baseline": DummyClassifier(strategy="prior"),
        "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "Random forest": RandomForestClassifier(
            n_estimators=120, min_samples_leaf=20, max_depth=7, random_state=seed, n_jobs=1
        ),
    }
    fitted, validation_scores, reports = {}, {}, []
    for name, model in candidates.items():
        model.fit(train[FEATURES], train.churn_next_month)
        fitted[name] = model
        p = model.predict_proba(validation[FEATURES])[:, 1]
        validation_scores[name] = average_precision_score(validation.churn_next_month, p)
    winner = max(validation_scores, key=validation_scores.get)
    model = fitted[winner]
    vprob = model.predict_proba(validation[FEATURES])[:, 1]
    # Illustrative cost: $3 per unnecessary review, $39 per missed cancellation.
    thresholds = np.linspace(0.01, 0.8, 80)
    yv = validation.churn_next_month.to_numpy()
    costs = [
        float(3 * ((vprob >= t) & (yv == 0)).sum() + 39 * ((vprob < t) & (yv == 1)).sum())
        for t in thresholds
    ]
    threshold = float(thresholds[int(np.argmin(costs))])
    for name, fitted_model in fitted.items():
        for split_name, split in [("validation", validation), ("test", test)]:
            prob = fitted_model.predict_proba(split[FEATURES])[:, 1]
            y = split.churn_next_month.to_numpy()
            pred = prob >= threshold
            reports.append(
                {
                    "model": name,
                    "split": split_name,
                    "rows": len(y),
                    "customers": split.customer_id.nunique(),
                    "churn_rate": float(y.mean()),
                    "roc_auc": roc_auc_score(y, prob),
                    "average_precision": average_precision_score(y, prob),
                    "brier_score": brier_score_loss(y, prob),
                    "precision": precision_score(y, pred, zero_division=0),
                    "recall": recall_score(y, pred, zero_division=0),
                    "false_positives": int((pred & (y == 0)).sum()),
                    "false_negatives": int((~pred & (y == 1)).sum()),
                    "selected": name == winner,
                    "threshold": threshold,
                }
            )
    test_prob = model.predict_proba(test[FEATURES])[:, 1]
    predictions = test[["customer_id", "feature_cutoff", "churn_next_month"]].copy()
    predictions["probability"] = test_prob
    predictions["decile"] = pd.cut(test_prob, np.linspace(0, 1, 11), include_lowest=True).astype(
        str
    )
    calibration = (
        predictions.groupby("decile")
        .agg(
            predicted=("probability", "mean"),
            observed=("churn_next_month", "mean"),
            rows=("customer_id", "size"),
        )
        .reset_index()
    )
    importance = permutation_importance(
        model,
        test[FEATURES],
        test.churn_next_month,
        scoring="average_precision",
        n_repeats=5,
        random_state=seed,
    )
    feature_importance = pd.DataFrame(
        {
            "feature": FEATURES,
            "importance": importance.importances_mean,
            "std": importance.importances_std,
        }
    )
    current = panel[panel.feature_cutoff == AS_OF].copy()
    current["churn_probability"] = model.predict_proba(current[FEATURES])[:, 1]
    current["review_required"] = current.churn_probability >= threshold
    current["monthly_revenue_exposure"] = current.churn_probability * current.monthly_price
    current["value_12m_scenario"] = [
        float(price * sum((1 - p) ** m for m in range(1, 13)) * 0.75)
        for price, p in zip(current.monthly_price, current.churn_probability)
    ]
    current["suggested_action"] = np.select(
        [current.payment_failed > 0, current.support_tickets > 0, current.sessions < 5],
        [
            "Investigate payment failure",
            "Review unresolved service experience",
            "Review onboarding and engagement",
        ],
        default="Review customer history",
    )
    import shap

    background = train[FEATURES].sample(min(100, len(train)), random_state=seed)
    if winner == "Logistic regression":
        scaler = model.named_steps["standardscaler"]
        explainer = shap.LinearExplainer(
            model.named_steps["logisticregression"], scaler.transform(background)
        )
        shap_values = explainer.shap_values(scaler.transform(current[FEATURES]))
        base = float(explainer.expected_value)
        explanation_scale = "log_odds"
    elif winner == "Random forest":
        explainer = shap.TreeExplainer(
            model,
            data=background,
            model_output="probability",
            feature_perturbation="interventional",
        )
        shap_values = explainer.shap_values(current[FEATURES])[:, :, 1]
        base = float(explainer.expected_value[1])
        explanation_scale = "probability"
    else:
        shap_values = np.zeros((len(current), len(FEATURES)))
        base = float(current.churn_probability.iloc[0])
        explanation_scale = "probability"
    explanation_rows = []
    for row_idx, (_, row) in enumerate(current.iterrows()):
        for feature_idx, feature in enumerate(FEATURES):
            explanation_rows.append(
                {
                    "customer_id": row.customer_id,
                    "feature": feature,
                    "value": float(row[feature]),
                    "contribution": float(shap_values[row_idx, feature_idx]),
                    "base_value": base,
                    "scale": explanation_scale,
                }
            )
    drift = []
    for feature in FEATURES:
        result = ks_2samp(train[feature], current[feature])
        drift.append(
            {
                "feature": feature,
                "ks_statistic": result.statistic,
                "p_value": result.pvalue,
                "review_signal": bool(
                    result.statistic > 0.15 and result.pvalue < 0.05 / len(FEATURES)
                ),
            }
        )
    meta = {
        "selected_model": winner,
        "threshold": threshold,
        "train_rows": len(train),
        "validation_rows": len(validation),
        "test_rows": len(test),
        "features": FEATURES,
        "training_last_label_end": str(train.label_end.max().date()),
        "validation_first_cutoff": str(validation.feature_cutoff.min().date()),
        "test_first_cutoff": str(test.feature_cutoff.min().date()),
        "cost_false_positive": 3,
        "cost_false_negative": 39,
        "costs_are_assumptions": True,
        "synthetic": True,
    }
    return {
        "churn_metrics": pd.DataFrame(reports),
        "churn_predictions": predictions,
        "churn_calibration": calibration,
        "churn_importance": feature_importance,
        "retention_queue": current,
        "feature_drift": pd.DataFrame(drift),
        "churn_features": panel,
        "churn_explanations": pd.DataFrame(explanation_rows),
    }, {"model": model, "metadata": meta}
