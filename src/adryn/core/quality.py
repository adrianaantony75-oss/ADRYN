from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class QualityResult:
    findings: pd.DataFrame
    profile: pd.DataFrame


def profile_dataframe(name: str, df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in df.columns:
        series = df[column]
        rows.append(
            {
                "dataset": name,
                "column": column,
                "dtype": str(series.dtype),
                "rows": len(df),
                "missing_count": int(
                    series.isna().sum() + (series.astype(str).str.strip() == "").sum()
                ),
                "unique_count": int(series.nunique(dropna=True)),
            }
        )
    return pd.DataFrame(rows)


def run_quality_checks(customers: pd.DataFrame, orders: pd.DataFrame) -> QualityResult:
    findings = []

    duplicate_customers = customers[customers.duplicated("customer_id", keep=False)]
    for _, row in duplicate_customers.iterrows():
        findings.append(
            {
                "rule_id": "DQ-CUSTOMER-DUPLICATE",
                "entity_id": row["customer_id"],
                "severity": "high",
                "finding": "Duplicate customer_id detected",
            }
        )

    invalid_email_mask = ~customers["email"].fillna("").map(
        lambda value: bool(EMAIL_RE.match(value))
    )
    for _, row in customers[invalid_email_mask].iterrows():
        findings.append(
            {
                "rule_id": "DQ-CUSTOMER-EMAIL",
                "entity_id": row["customer_id"],
                "severity": "medium",
                "finding": "Invalid or missing email address",
            }
        )

    missing_phone = customers["phone"].fillna("").astype(str).str.strip() == ""
    for _, row in customers[missing_phone].iterrows():
        findings.append(
            {
                "rule_id": "DQ-CUSTOMER-PHONE",
                "entity_id": row["customer_id"],
                "severity": "low",
                "finding": "Missing phone number",
            }
        )

    amount_q3 = orders["amount"].quantile(0.75)
    amount_iqr = amount_q3 - orders["amount"].quantile(0.25)
    outlier_threshold = amount_q3 + 3 * amount_iqr
    for _, row in orders[orders["amount"] > outlier_threshold].iterrows():
        findings.append(
            {
                "rule_id": "DQ-ORDER-AMOUNT-OUTLIER",
                "entity_id": row["order_id"],
                "severity": "medium",
                "finding": f"Order amount exceeds outlier threshold {outlier_threshold:.2f}",
            }
        )

    profile = pd.concat(
        [profile_dataframe("customers", customers), profile_dataframe("orders", orders)],
        ignore_index=True,
    )
    return QualityResult(
        findings=pd.DataFrame(findings, columns=["rule_id", "entity_id", "severity", "finding"]),
        profile=profile,
    )
