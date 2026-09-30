"""Forecast validation, randomized onboarding analysis and support intelligence."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chisquare, norm, ttest_ind
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline

from adryn.data.platform import AS_OF, START


def _design(index: np.ndarray) -> np.ndarray:
    return np.column_stack([index, np.sin(2 * np.pi * index / 12), np.cos(2 * np.pi * index / 12)])


def _forecast(values: np.ndarray, horizon: int, method: str) -> np.ndarray:
    if method == "Last month":
        return np.repeat(values[-1], horizon)
    if method == "Seasonal naive":
        return np.resize(values[-12:], horizon)
    model = Ridge(alpha=10).fit(_design(np.arange(len(values))), values)
    return np.clip(model.predict(_design(np.arange(len(values), len(values) + horizon))), 0, None)


def forecast_demand(activity: pd.DataFrame) -> dict[str, pd.DataFrame]:
    monthly = (
        activity.groupby("month")
        .sessions.sum()
        .reindex(pd.date_range(START, AS_OF, freq="MS").strftime("%Y-%m-%d"), fill_value=0)
    )
    y = monthly.to_numpy(dtype=float)
    methods = ["Last month", "Seasonal naive", "Trend + annual seasonality"]
    rows = []
    # Selection origins and final evaluation origin are disjoint; all use a 3-month horizon.
    for origin in [15, 18, 21, 24, 27]:
        for method in methods:
            prediction = _forecast(y[:origin], 3, method)
            for step, estimate in enumerate(prediction):
                actual = y[origin + step]
                rows.append(
                    {
                        "origin": monthly.index[origin - 1],
                        "month": monthly.index[origin + step],
                        "method": method,
                        "horizon": step + 1,
                        "actual": actual,
                        "forecast": estimate,
                        "error": actual - estimate,
                        "absolute_error": abs(actual - estimate),
                        "split": "final_holdout" if origin == 27 else "selection",
                    }
                )
    backtest = pd.DataFrame(rows)
    comparison = (
        backtest.groupby(["split", "method"])
        .agg(
            mae=("absolute_error", "mean"),
            total_error=("absolute_error", "sum"),
            actual_total=("actual", "sum"),
            bias=("error", "mean"),
        )
        .reset_index()
    )
    comparison["wape"] = comparison.total_error / comparison.actual_total
    selection = comparison[comparison.split == "selection"]
    winner = str(selection.loc[selection.mae.idxmin(), "method"])
    estimates = _forecast(y, 3, winner)
    errors = backtest[(backtest.method == winner) & (backtest.split == "selection")]
    # Empirical residual bands are descriptive with few origins, not calibrated coverage claims.
    lower, upper = np.quantile(errors.error, [0.1, 0.9])
    forecasts = pd.DataFrame(
        {
            "month": pd.date_range(AS_OF + pd.Timedelta(days=1), periods=3, freq="MS").strftime(
                "%Y-%m-%d"
            ),
            "forecast": estimates,
            "lower_empirical": np.maximum(0, estimates + lower),
            "upper_empirical": np.maximum(0, estimates + upper),
            "method": winner,
        }
    )
    comparison["selected"] = comparison.method == winner
    history = monthly.rename("sessions").rename_axis("month").reset_index()
    history["yoy_change"] = history.sessions.pct_change(12)
    return {
        "demand_history": history,
        "forecast_backtests": backtest,
        "forecast_comparison": comparison,
        "demand_forecast": forecasts,
    }


def analyze_experiment(
    experiment: pd.DataFrame, customers: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    data = experiment[experiment.eligible_for_analysis].merge(
        customers[["customer_id", "region", "plan"]], on="customer_id", validate="one_to_one"
    )
    rows = []
    for name, group in [("Overall", data), *list(data.groupby("region"))]:
        control, treatment = (group[group.treatment == arm] for arm in (0, 1))
        if min(len(control), len(treatment)) < 2:
            continue
        pc, pt = control.retained_60d.mean(), treatment.retained_60d.mean()
        effect = float(pt - pc)
        se = float(np.sqrt(pc * (1 - pc) / len(control) + pt * (1 - pt) / len(treatment)))
        low, high = effect - 1.96 * se, effect + 1.96 * se
        p_value = float(2 * norm.sf(abs(effect) / se)) if se else 1.0
        srm = float(chisquare([len(control), len(treatment)]).pvalue)
        guardrail = ttest_ind(treatment.support_60d, control.support_60d, equal_var=False)
        guardrail_delta = float(treatment.support_60d.mean() - control.support_60d.mean())
        guardrail_se = np.sqrt(
            treatment.support_60d.var() / len(treatment) + control.support_60d.var() / len(control)
        )
        guardrail_high = float(guardrail_delta + 1.96 * guardrail_se)
        required = int(np.ceil(2 * (norm.ppf(0.975) + norm.ppf(0.8)) ** 2 * 0.5 * 0.5 / 0.05**2))
        decision = "Continue evidence collection"
        if srm < 0.01:
            decision = "Investigate assignment imbalance"
        elif high < 0:
            decision = "Do not roll out: retention harm signal"
        elif low > 0.03 and guardrail_high < 0.2 and min(len(control), len(treatment)) >= required:
            decision = "Consider rollout after operational review"
        rows.append(
            {
                "segment": name,
                "control_n": len(control),
                "treatment_n": len(treatment),
                "control_rate": pc,
                "treatment_rate": pt,
                "absolute_effect": effect,
                "ci95_low": low,
                "ci95_high": high,
                "p_value": p_value,
                "relative_effect": effect / pc if pc else np.nan,
                "sample_ratio_p": srm,
                "required_per_arm_for_5pp": required,
                "guardrail_ticket_delta": guardrail_delta,
                "guardrail_ci95_high": guardrail_high,
                "guardrail_p": float(guardrail.pvalue),
                "decision": decision
                if name == "Overall"
                else "Exploratory; no segment rollout decision",
            }
        )
    return {"experiment_results": pd.DataFrame(rows)}


def customer_voice(tickets: pd.DataFrame, seed: int) -> tuple[dict[str, pd.DataFrame], object]:
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
    train_index, test_index = next(splitter.split(tickets, groups=tickets.customer_id))
    train, test = tickets.iloc[train_index], tickets.iloc[test_index]
    classifier = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2), LogisticRegression(max_iter=600)
    )
    classifier.fit(train.text, train.theme)
    predictions = classifier.predict(test.text)
    metrics = pd.DataFrame(
        [
            {
                "model": "TF-IDF + logistic regression",
                "train_customers": train.customer_id.nunique(),
                "test_customers": test.customer_id.nunique(),
                "test_tickets": len(test),
                "accuracy": accuracy_score(test.theme, predictions),
                "macro_f1": f1_score(test.theme, predictions, average="macro"),
                "majority_baseline_accuracy": float((test.theme == train.theme.mode()[0]).mean()),
                "limitation": "Generated templates occur in both splits; synthetic classification scores do not establish real-language quality.",
            }
        ]
    )
    scored = tickets.copy()
    scored["predicted_theme"] = classifier.predict(tickets.text)
    scored["confidence"] = classifier.predict_proba(tickets.text).max(axis=1)
    scored["needs_review"] = scored.confidence < 0.75
    scored["evaluation_split"] = "train"
    scored.loc[test_index, "evaluation_split"] = "test"
    scored["month"] = pd.to_datetime(scored.created_at).dt.to_period("M").astype(str)
    trends = (
        scored.groupby(["month", "predicted_theme"])
        .agg(
            tickets=("ticket_id", "size"),
            affected_customers=("customer_id", "nunique"),
            avg_resolution_hours=("resolution_hours", "mean"),
        )
        .reset_index()
    )
    trends["share"] = trends.tickets / trends.groupby("month").tickets.transform("sum")
    current_month = AS_OF.to_period("M").strftime("%Y-%m")
    previous_month = (AS_OF.to_period("M") - 1).strftime("%Y-%m")
    emerging = []
    recent, prior = scored[scored.month == current_month], scored[scored.month == previous_month]
    for theme in sorted(scored.predicted_theme.unique()):
        n1, n0 = len(recent), len(prior)
        c1, c0 = (
            int((recent.predicted_theme == theme).sum()),
            int((prior.predicted_theme == theme).sum()),
        )
        rate1, rate0 = c1 / max(n1, 1), c0 / max(n0, 1)
        pooled = (c1 + c0) / max(n1 + n0, 1)
        se = np.sqrt(pooled * (1 - pooled) * (1 / max(n1, 1) + 1 / max(n0, 1)))
        p = float(2 * norm.sf(abs(rate1 - rate0) / se)) if se and n1 and n0 else 1.0
        emerging.append(
            {
                "theme": theme,
                "current_tickets": c1,
                "previous_tickets": c0,
                "share_change_pp": (rate1 - rate0) * 100,
                "p_value": p,
                "investigate": bool(rate1 - rate0 > 0.05 and p < 0.05 / 4),
                "interpretation": "Repeated tickets are not independent; descriptive investigation signal only",
            }
        )
    return {
        "voice_tickets": scored,
        "voice_metrics": metrics,
        "voice_trends": trends,
        "voice_emerging_issues": pd.DataFrame(emerging),
    }, classifier
