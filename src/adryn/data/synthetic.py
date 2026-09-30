from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from adryn.data.platform import generate_platform, validate_platform, write_platform


@dataclass(frozen=True)
class SyntheticDataPaths:
    customers: Path
    orders: Path
    contracts: Path
    ai_reviews: Path


def generate_enterprise_data(
    raw_dir: Path, seed: int, customers_count: int = 1800
) -> SyntheticDataPaths:
    """Create the subscription ecosystem and dirty CRM projection for trust review."""
    rng = np.random.default_rng(seed)
    tables = generate_platform(seed, customers_count)
    validate_platform(tables)
    write_platform(tables, raw_dir / "platform")
    customers = tables["customers"].copy()
    paid = tables["orders"].query("payment_status == 'paid'").groupby("customer_id").amount.sum()
    customers["lifetime_value"] = customers.customer_id.map(paid).fillna(0)
    customers.loc[customers.index % 47 == 0, "email"] = "invalid-email"
    customers.loc[customers.index % 61 == 0, "phone"] = ""
    customers = pd.concat(
        [customers, customers.sample(min(12, len(customers)), random_state=seed)], ignore_index=True
    )
    contracts = tables["subscriptions"][
        ["subscription_id", "customer_id", "monthly_price", "cancelled_at"]
    ].copy()
    contracts = contracts.rename(columns={"subscription_id": "contract_id"})
    contracts["crm_contract_value"] = contracts.monthly_price
    contracts["erp_contract_value"] = contracts.monthly_price
    discrepancy = contracts.index % 9 == 0
    contracts.loc[discrepancy, "erp_contract_value"] += 150
    contracts["crm_status"] = np.where(contracts.cancelled_at.isna(), "active", "cancelled")
    contracts["erp_status"] = contracts.crm_status
    contracts.loc[contracts.index % 13 == 0, "erp_status"] = "pending_sync"
    contracts = contracts.drop(columns=["monthly_price", "cancelled_at"])
    reviews = []
    for i, ticket in tables["tickets"].head(500).iterrows():
        severity = str(
            rng.choice(["low", "medium", "high", "critical"], p=[0.43, 0.34, 0.18, 0.05])
        )
        reviews.append(
            {
                "review_id": f"REV-{i + 1:05d}",
                "ticket_id": ticket.ticket_id,
                "customer_id": ticket.customer_id,
                "model_name": str(
                    rng.choice(["support-triage-v1", "support-triage-v2", "support-summary-v1"])
                ),
                "prompt_category": ticket.theme,
                "severity": severity,
                "human_disagreed": bool(
                    rng.random()
                    < {"low": 0.04, "medium": 0.1, "high": 0.24, "critical": 0.38}[severity]
                ),
                "contains_sensitive_context": bool(rng.random() < 0.22),
                "latency_ms": max(1, int(rng.normal(930, 220))),
                "review_notes": ticket.text,
            }
        )
    paths = SyntheticDataPaths(
        *(raw_dir / f"{name}.csv" for name in ["customers", "orders", "contracts", "ai_reviews"])
    )
    customers.to_csv(paths.customers, index=False)
    tables["orders"].to_csv(paths.orders, index=False)
    contracts.to_csv(paths.contracts, index=False)
    pd.DataFrame(reviews).to_csv(paths.ai_reviews, index=False)
    return paths
