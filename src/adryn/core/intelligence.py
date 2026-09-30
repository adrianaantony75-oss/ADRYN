from __future__ import annotations

import pandas as pd

SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def build_mirror_summary(
    quality_findings: pd.DataFrame, pii_findings: pd.DataFrame
) -> pd.DataFrame:
    quality_by_rule = quality_findings.groupby(["rule_id", "severity"], as_index=False).size()
    quality_by_rule["signal_family"] = "data_quality"
    quality_by_rule = quality_by_rule.rename(columns={"rule_id": "signal", "size": "finding_count"})

    pii_by_column = pii_findings.groupby(["dataset", "column", "risk_level"], as_index=False).size()
    pii_by_column["signal_family"] = "privacy"
    pii_by_column["signal"] = pii_by_column["dataset"] + "." + pii_by_column["column"]
    pii_by_column = pii_by_column.rename(
        columns={"risk_level": "severity", "size": "finding_count"}
    )[["signal", "severity", "finding_count", "signal_family"]]

    return pd.concat(
        [quality_by_rule[["signal", "severity", "finding_count", "signal_family"]], pii_by_column],
        ignore_index=True,
    )


def build_shadow_reviewer(scored_reviews: pd.DataFrame) -> pd.DataFrame:
    shadow = scored_reviews.copy()
    shadow["shadow_decision"] = shadow["review_risk_score"].map(
        lambda score: "escalate" if score >= 0.45 else "sample"
    )
    shadow["human_alignment"] = shadow["human_disagreed"].map(
        lambda disagreed: "needs_review" if disagreed else "aligned"
    )
    return shadow[
        [
            "review_id",
            "model_name",
            "prompt_category",
            "severity",
            "review_risk_score",
            "review_priority",
            "shadow_decision",
            "human_alignment",
        ]
    ]


def build_failure_genome(
    quality_findings: pd.DataFrame, reconciled_contracts: pd.DataFrame, scored_reviews: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for severity, count in quality_findings["severity"].value_counts().items():
        rows.append(
            {
                "failure_family": "data_quality",
                "failure_mode": f"{severity}_severity_quality",
                "occurrences": int(count),
                "risk_weight": SEVERITY_WEIGHT.get(severity, 1),
            }
        )

    rows.append(
        {
            "failure_family": "reconciliation",
            "failure_mode": "contract_mismatch",
            "occurrences": int(reconciled_contracts["requires_review"].sum()),
            "risk_weight": 3,
        }
    )
    rows.append(
        {
            "failure_family": "ai_evaluation",
            "failure_mode": "human_disagreement",
            "occurrences": int(scored_reviews["human_disagreed"].sum()),
            "risk_weight": 4,
        }
    )
    genome = pd.DataFrame(rows)
    genome["weighted_risk"] = genome["occurrences"] * genome["risk_weight"]
    return genome.sort_values("weighted_risk", ascending=False)


def build_evidence_graph(
    quality_findings: pd.DataFrame, pii_findings: pd.DataFrame, reconciled_contracts: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for _, finding in quality_findings.iterrows():
        rows.append(
            {
                "source_node": finding["rule_id"],
                "relationship": "flags",
                "target_node": finding["entity_id"],
                "evidence_type": "quality_finding",
                "weight": SEVERITY_WEIGHT.get(finding["severity"], 1),
            }
        )
    for _, finding in pii_findings.iterrows():
        rows.append(
            {
                "source_node": f"{finding['dataset']}.{finding['column']}",
                "relationship": "contains",
                "target_node": finding["pii_type"],
                "evidence_type": "privacy_signal",
                "weight": 3 if finding["risk_level"] == "high" else 1,
            }
        )
    for _, contract in reconciled_contracts[reconciled_contracts["requires_review"]].iterrows():
        rows.append(
            {
                "source_node": contract["contract_id"],
                "relationship": "requires_review_for",
                "target_node": contract["customer_id"],
                "evidence_type": "reconciliation_signal",
                "weight": 3,
            }
        )
    return pd.DataFrame(rows)


def build_ambiguity_lab(scored_reviews: pd.DataFrame) -> pd.DataFrame:
    ambiguous = scored_reviews[
        scored_reviews["review_risk_score"].between(0.35, 0.65, inclusive="both")
    ].copy()
    ambiguous["ambiguity_reason"] = "risk_score_near_decision_boundary"
    return ambiguous[
        [
            "review_id",
            "model_name",
            "prompt_category",
            "severity",
            "review_risk_score",
            "ambiguity_reason",
        ]
    ].sort_values("review_risk_score", ascending=False)


def build_powerbi_tables(
    summary: dict, mirror: pd.DataFrame, failure_genome: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    kpis = pd.DataFrame(
        [
            {"metric": key, "value": value}
            for key, value in summary.items()
            if isinstance(value, int | float)
        ]
    )
    signal_counts = mirror.groupby("signal_family", as_index=False)["finding_count"].sum()
    risk_rank = failure_genome[["failure_family", "failure_mode", "weighted_risk"]].copy()
    return {
        "powerbi_kpis": kpis,
        "powerbi_signal_counts": signal_counts,
        "powerbi_risk_rank": risk_rank,
    }
