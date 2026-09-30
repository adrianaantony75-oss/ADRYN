from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kruskal, ks_2samp, ttest_ind
from sklearn.ensemble import IsolationForest


def detect_order_anomalies(orders: pd.DataFrame, seed: int) -> pd.DataFrame:
    result = orders.copy()
    model = IsolationForest(contamination=0.03, random_state=seed)
    features = np.log1p(result[["amount"]].clip(lower=0))
    model.fit(features)
    result["anomaly_score"] = (-model.score_samples(features)).round(5)
    result["is_anomaly"] = model.predict(features) == -1
    result["anomaly_reason"] = np.where(
        result["is_anomaly"], "order_amount_pattern", "within_expected_pattern"
    )
    return result.sort_values("anomaly_score", ascending=False)


def analyze_order_drift(orders: pd.DataFrame) -> pd.DataFrame:
    dated = orders.assign(order_date=pd.to_datetime(orders["order_date"], errors="coerce"))
    dated = dated.dropna(subset=["order_date", "amount"]).sort_values("order_date")
    if len(dated) < 20:
        return pd.DataFrame([{"metric": "order_amount", "status": "insufficient_data"}])
    midpoint = dated["order_date"].median()
    earlier = dated.loc[dated["order_date"] <= midpoint, "amount"]
    later = dated.loc[dated["order_date"] > midpoint, "amount"]
    test = ks_2samp(earlier, later)
    pooled_std = np.sqrt((earlier.var(ddof=1) + later.var(ddof=1)) / 2)
    effect = (later.mean() - earlier.mean()) / pooled_std if pooled_std else 0.0
    return pd.DataFrame(
        [
            {
                "metric": "order_amount",
                "split_date": midpoint.date().isoformat(),
                "earlier_rows": len(earlier),
                "later_rows": len(later),
                "earlier_mean": round(float(earlier.mean()), 2),
                "later_mean": round(float(later.mean()), 2),
                "ks_statistic": round(float(test.statistic), 5),
                "p_value": round(float(test.pvalue), 6),
                "standardized_effect": round(float(effect), 5),
                "status": "distribution_shift_signal"
                if test.pvalue < 0.05
                else "no_detected_shift",
                "interpretation": "Unadjusted temporal comparison; not a causal estimate.",
            }
        ]
    )


def compare_model_groups(reviews: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model_name, group in reviews.groupby("model_name"):
        outcomes = group["human_disagreed"].astype(float)
        rows.append(
            {
                "model_name": model_name,
                "reviews": len(group),
                "disagreements": int(outcomes.sum()),
                "disagreement_rate": round(float(outcomes.mean()), 5),
                "rate_se": round(
                    float(np.sqrt(outcomes.mean() * (1 - outcomes.mean()) / len(group))), 5
                ),
                "rate_ci95_low": round(
                    max(
                        0.0,
                        float(
                            outcomes.mean()
                            - 1.96 * np.sqrt(outcomes.mean() * (1 - outcomes.mean()) / len(group))
                        ),
                    ),
                    5,
                ),
                "rate_ci95_high": round(
                    min(
                        1.0,
                        float(
                            outcomes.mean()
                            + 1.96 * np.sqrt(outcomes.mean() * (1 - outcomes.mean()) / len(group))
                        ),
                    ),
                    5,
                ),
            }
        )
    table = pd.DataFrame(rows)
    if len(table) >= 2:
        groups = [
            g["human_disagreed"].astype(float).to_numpy() for _, g in reviews.groupby("model_name")
        ]
        if len(groups) == 2:
            test_name = "welch_t_test"
            test = ttest_ind(*groups, equal_var=False)
        else:
            test_name = "kruskal_wallis"
            test = kruskal(*groups)
        table["test_name"] = test_name
        table["omnibus_p_value"] = round(float(test.pvalue), 6)
    else:
        table["test_name"] = "not_tested"
        table["omnibus_p_value"] = np.nan
    table["interpretation"] = (
        "Observational model comparison; differences do not establish causation."
    )
    return table
