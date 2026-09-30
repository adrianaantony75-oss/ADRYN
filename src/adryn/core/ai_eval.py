from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

FEATURES = ["model_name", "prompt_category", "severity", "contains_sensitive_context", "latency_ms"]
REVIEW_THRESHOLD = 0.20


def prioritize_review_risk(ai_reviews: pd.DataFrame, random_seed: int) -> tuple[pd.DataFrame, dict]:
    data = ai_reviews.copy()
    y = data["human_disagreed"].astype(int)
    x = data[FEATURES]
    stratify = y if y.nunique() > 1 else None
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, random_state=random_seed, stratify=stratify
    )
    categorical = ["model_name", "prompt_category", "severity", "contains_sensitive_context"]
    numeric = ["latency_ms"]
    model = Pipeline(
        steps=[
            (
                "prep",
                ColumnTransformer(
                    transformers=[
                        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
                        ("num", "passthrough", numeric),
                    ]
                ),
            ),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=160, class_weight="balanced", random_state=random_seed
                ),
            ),
        ]
    )
    model.fit(x_train, y_train)
    risk_scores = model.predict_proba(x)[:, 1]
    scored = data.copy()
    scored["review_risk_score"] = risk_scores.round(4)
    scored["review_priority"] = pd.cut(
        scored["review_risk_score"],
        bins=[-0.01, 0.20, 0.45, 0.70, 1.0],
        labels=["low", "medium", "high", "critical"],
    )
    probabilities = model.predict_proba(x_test)[:, 1]
    predictions = (probabilities >= REVIEW_THRESHOLD).astype(int)
    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision": float(precision_score(y_test, predictions, zero_division=0)),
        "recall": float(recall_score(y_test, predictions, zero_division=0)),
        "f1": float(f1_score(y_test, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, probabilities)) if y_test.nunique() > 1 else 0.5,
        "test_rows": len(y_test),
        "positive_test_rows": int(y_test.sum()),
        "review_threshold": REVIEW_THRESHOLD,
    }
    importance = permutation_importance(
        model, x_test, y_test, n_repeats=8, random_state=random_seed, scoring="roc_auc"
    )
    metrics["feature_importance"] = pd.DataFrame(
        {
            "feature": FEATURES,
            "importance_mean": importance.importances_mean,
            "importance_std": importance.importances_std,
        }
    ).sort_values("importance_mean", ascending=False)
    group_rows = []
    for group_value in sorted(x_test["contains_sensitive_context"].unique()):
        mask = x_test["contains_sensitive_context"] == group_value
        group_rows.append(
            {
                "sensitive_context": str(group_value),
                "test_rows": int(mask.sum()),
                "observed_disagreement_rate": float(y_test[mask].mean()),
                "predicted_escalation_rate": float(predictions[mask].mean()),
                "precision": float(
                    precision_score(y_test[mask], predictions[mask], zero_division=0)
                ),
                "recall": float(recall_score(y_test[mask], predictions[mask], zero_division=0)),
            }
        )
    metrics["group_evaluation"] = pd.DataFrame(group_rows)
    return scored.sort_values("review_risk_score", ascending=False), metrics
