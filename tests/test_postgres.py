"""Runs only against an explicitly supplied integration-test database."""

import os
from uuid import uuid4

import pandas as pd
import psycopg
import pytest

from adryn.db.postgres import init_database, store_pipeline_run
from adryn.settings import Settings


@pytest.mark.skipif(
    not os.getenv("ADRYN_TEST_DATABASE_URL"), reason="No explicit PostgreSQL test URL"
)
def test_normalized_load_is_idempotent_and_foreign_keys_rollback():
    settings = Settings(database_url=os.environ["ADRYN_TEST_DATABASE_URL"])
    init_database(settings)
    run_id = str(uuid4())
    summary = {
        "run_id": run_id,
        "seed": 1,
        "quality_findings": 0,
        "pii_findings": 0,
        "contract_records_requiring_review": 0,
        "ai_reviews_scored": 0,
    }
    frames = {
        "quality_findings": pd.DataFrame(columns=["rule_id", "entity_id", "severity", "finding"]),
        "evidence_graph_edges": pd.DataFrame(
            columns=["source_node", "relationship", "target_node", "evidence_type", "weight"]
        ),
        "subscription_customers": pd.DataFrame(
            [
                {
                    "customer_id": "TEST-C1",
                    "region": "NA",
                    "plan": "Essential",
                    "signup_date": "2026-01-01",
                    "acquisition_channel": "organic",
                    "consent_status": "granted",
                }
            ]
        ),
        "subscription_orders": pd.DataFrame(
            [
                {
                    "order_id": "TEST-I1",
                    "customer_id": "TEST-C1",
                    "order_date": "2026-02-01",
                    "amount": 19,
                    "payment_status": "paid",
                },
                {
                    "order_id": "TEST-I2",
                    "customer_id": "TEST-C1",
                    "order_date": "2026-03-01",
                    "amount": 19,
                    "payment_status": "failed",
                },
            ]
        ),
    }
    store_pipeline_run(settings, summary, frames)
    store_pipeline_run(settings, summary, frames)
    with psycopg.connect(settings.database_url) as conn:
        assert (
            conn.execute(
                "select count(*) from adryn.invoices where run_id = %s", (run_id,)
            ).fetchone()[0]
            == 2
        )
        assert (
            float(
                conn.execute(
                    "select collected_value from adryn.customer_collected_value where run_id = %s",
                    (run_id,),
                ).fetchone()[0]
            )
            == 19
        )
        assert conn.execute(
            "select collected_revenue from adryn.monthly_collections "
            "where run_id = %s and month = '2026-03-01'", (run_id,),
        ).fetchone()[0] == 0
    bad_id = str(uuid4())
    bad_summary = summary | {"run_id": bad_id}
    bad_frames = {key: value.copy() for key, value in frames.items()}
    bad_frames["subscription_orders"].loc[0, "customer_id"] = "MISSING"
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        store_pipeline_run(settings, bad_summary, bad_frames)
    with psycopg.connect(settings.database_url) as conn:
        assert (
            conn.execute(
                "select count(*) from adryn.pipeline_runs where run_id = %s", (bad_id,)
            ).fetchone()[0]
            == 0
        )
