import json
from pathlib import Path
from uuid import UUID

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from adryn.settings import Settings


def validate_run_tables(summary: dict, tables: dict[str, pd.DataFrame]) -> None:
    """Reject incomplete or mixed-run input before any database side effects."""
    required = {"quality_findings", "evidence_graph_edges"}
    if "business" in summary:
        required |= {
            "subscription_customers", "subscription_contracts", "subscription_orders",
            "subscription_activity", "voice_tickets", "onboarding_assignments",
            "subscription_events",
        }
    if missing := required - tables.keys():
        raise ValueError(f"Missing required generated outputs: {', '.join(sorted(missing))}")
    try:
        run_id = str(UUID(summary["run_id"]))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Invalid published run identifier.") from None
    for name, frame in tables.items():
        if "business" in summary and "run_id" not in frame:
            raise ValueError(f"Missing run identifiers in dataset: {name}")
        if "run_id" in frame and not frame.run_id.eq(run_id).all():
            raise ValueError(f"Mixed or missing run identifiers in dataset: {name}")
    if "business" in summary:
        expected = {
            "subscription_customers": summary["business"].get("customers"),
            "subscription_orders": summary.get("orders_rows"),
        }
        for name, count in expected.items():
            if count is not None and len(tables[name]) != count:
                raise ValueError(f"Published row count does not match dataset: {name}")


def init_database(settings: Settings) -> None:
    if not settings.database_url:
        raise ValueError("Set ADRYN_DATABASE_URL in your local .env before using PostgreSQL.")
    schema_path = Path(__file__).with_name("schema.sql")
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(schema_path.read_text(encoding="utf-8"))
        conn.commit()


def store_pipeline_run(settings: Settings, summary: dict, tables: dict[str, pd.DataFrame]) -> None:
    if not settings.database_url:
        raise ValueError("Set ADRYN_DATABASE_URL in your local .env before using PostgreSQL.")
    validate_run_tables(summary, tables)
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(
            """insert into adryn.pipeline_runs
                   (run_id, source_seed, quality_findings, pii_findings,
                    reconciliation_reviews, ai_reviews)
                   values (%s, %s, %s, %s, %s, %s)
                   on conflict (run_id) do nothing returning run_id""",
            (
                summary["run_id"],
                summary["seed"],
                summary["quality_findings"],
                summary["pii_findings"],
                summary["contract_records_requiring_review"],
                summary["ai_reviews_scored"],
            ),
        )
        if cur.fetchone() is None:
            return
        for dataset_name, frame in tables.items():
            records = json.loads(frame.to_json(orient="records", date_format="iso"))
            for row_number, row in enumerate(records):
                cur.execute(
                    """insert into adryn.result_rows
                           (run_id, dataset_name, row_number, payload)
                           values (%s, %s, %s, %s)""",
                    (summary["run_id"], dataset_name, row_number, Jsonb(row)),
                )
        findings = tables["quality_findings"]
        finding_records = json.loads(findings.to_json(orient="records", date_format="iso"))
        for row in finding_records:
            cur.execute(
                """insert into adryn.quality_findings
                       (run_id, rule_id, entity_id, severity, finding, evidence)
                       values (%s, %s, %s, %s, %s, %s)""",
                (
                    summary["run_id"],
                    row["rule_id"],
                    str(row["entity_id"]),
                    row["severity"],
                    row["finding"],
                    Jsonb(row),
                ),
            )
        _store_business_tables(cur, summary["run_id"], tables)


def _store_business_tables(cur, run_id: str, tables: dict[str, pd.DataFrame]) -> None:
    from psycopg import sql

    mapping = {
        "subscription_customers": (
            "customers",
            [
                "customer_id",
                "region",
                "plan",
                "signup_date",
                "acquisition_channel",
                "consent_status",
            ],
        ),
        "subscription_contracts": (
            "subscriptions",
            [
                "subscription_id",
                "customer_id",
                "plan",
                "monthly_price",
                "start_date",
                "cancelled_at",
            ],
        ),
        "subscription_orders": (
            "invoices",
            ["order_id", "customer_id", "order_date", "amount", "payment_status"],
        ),
        "subscription_activity": (
            "monthly_activity",
            [
                "customer_id",
                "month",
                "sessions",
                "learning_minutes",
                "days_since_activity",
                "support_tickets",
                "payment_failed",
                "monthly_price",
                "tenure_months",
            ],
        ),
        "voice_tickets": (
            "support_tickets",
            [
                "ticket_id",
                "customer_id",
                "created_at",
                "text",
                "predicted_theme",
                "confidence",
                "resolution_hours",
            ],
        ),
        "onboarding_assignments": (
            "onboarding_assignments",
            [
                "customer_id",
                "assigned_at",
                "treatment",
                "eligible_for_analysis",
                "retained_60d",
                "support_60d",
            ],
        ),
        "subscription_events": (
            "funnel_events",
            ["event_id", "customer_id", "event_date", "event_type"],
        ),
    }
    for name, (target, columns) in mapping.items():
        if name not in tables:
            continue
        records = json.loads(tables[name][columns].to_json(orient="records"))
        statement = sql.SQL("insert into adryn.{} ({}) values ({})").format(
            sql.Identifier(target),
            sql.SQL(", ").join(map(sql.Identifier, ["run_id", *columns])),
            sql.SQL(", ").join(sql.Placeholder() for _ in range(len(columns) + 1)),
        )
        cur.executemany(statement, [(run_id, *[row[c] for c in columns]) for row in records])
    edge_records = json.loads(
        tables["evidence_graph_edges"].to_json(orient="records", date_format="iso")
    )
    for edge in edge_records:
        cur.execute(
            """insert into adryn.evidence_edges
                   (run_id, source_node, relationship, target_node, evidence_type, weight)
                   values (%s, %s, %s, %s, %s, %s)""",
            (
                run_id,
                edge["source_node"],
                edge["relationship"],
                edge["target_node"],
                edge["evidence_type"],
                int(edge["weight"]),
            ),
        )
