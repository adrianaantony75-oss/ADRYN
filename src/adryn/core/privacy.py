from __future__ import annotations

import re

import pandas as pd

PII_PATTERNS = {
    "email": re.compile(r"email|e-mail", re.IGNORECASE),
    "phone": re.compile(r"phone|mobile|cell", re.IGNORECASE),
    "name": re.compile(r"name", re.IGNORECASE),
}


def detect_pii_columns(dataset_name: str, df: pd.DataFrame) -> pd.DataFrame:
    findings = []
    for column in df.columns:
        matched = [kind for kind, pattern in PII_PATTERNS.items() if pattern.search(column)]
        if matched:
            non_empty = int(df[column].fillna("").astype(str).str.strip().ne("").sum())
            findings.append(
                {
                    "dataset": dataset_name,
                    "column": column,
                    "pii_type": ",".join(matched),
                    "non_empty_values": non_empty,
                    "risk_level": "high" if non_empty > 0 else "low",
                }
            )
    return pd.DataFrame(
        findings, columns=["dataset", "column", "pii_type", "non_empty_values", "risk_level"]
    )


def build_privacy_twin(customers: pd.DataFrame) -> pd.DataFrame:
    twin = customers[["customer_id", "region", "consent_status"]].copy()
    twin["privacy_state"] = twin["consent_status"].map(
        {"granted": "usable", "revoked": "restricted", "unknown": "review"}
    ).fillna("review")
    twin["requires_human_review"] = twin["privacy_state"].isin(["restricted", "review"])
    return twin
