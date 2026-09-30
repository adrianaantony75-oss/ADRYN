import json
from pathlib import Path

import click
import psycopg
from dotenv import dotenv_values

from adryn.db.postgres import init_database, store_pipeline_run, validate_run_tables
from adryn.io import current_output, read_table
from adryn.reports.pipeline import run_pipeline
from adryn.settings import PROJECT_ROOT, get_settings


@click.group()
def cli() -> None:
    """ADRYN command line tools."""


def _database_url() -> str:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        raise click.ClickException("Project .env is absent; PostgreSQL connectivity is unverified.")
    url = dotenv_values(env_path, interpolate=False).get("ADRYN_DATABASE_URL")
    if not url:
        raise click.ClickException("ADRYN_DATABASE_URL is not configured in the project .env.")
    return url


@cli.command("run-pipeline")
def run_pipeline_command() -> None:
    """Generate data, run trust checks, and export reports."""
    summary = run_pipeline(get_settings())
    click.echo(json.dumps(summary, indent=2))


@cli.command("init-db")
def init_db_command() -> None:
    """Create ADRYN PostgreSQL schema objects."""
    url = _database_url()
    settings = get_settings().model_copy(update={"database_url": url})
    try:
        init_database(settings)
    except psycopg.Error:
        raise click.ClickException(
            "Database initialization failed. Check the local connection and schema permissions."
        ) from None
    click.echo("ADRYN database schema initialized.")


@cli.command("load-db")
def load_db_command() -> None:
    """Load the latest computed output set into PostgreSQL."""
    url = _database_url()
    settings = get_settings().model_copy(update={"database_url": url})
    output = current_output(settings.output_dir)
    summary_path = output / "pipeline_summary.json"
    if not summary_path.exists():
        raise click.ClickException("Run 'adryn run-pipeline' before loading a run into PostgreSQL.")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    frames = {path.stem: read_table(path) for path in Path(output).glob("*.csv")}
    try:
        validate_run_tables(summary, frames)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None
    try:
        init_database(settings)
        store_pipeline_run(settings, summary, frames)
    except psycopg.Error:
        raise click.ClickException(
            "Database load failed. Check the local connection, schema and input constraints."
        ) from None
    click.echo(f"Loaded run {summary['run_id']} with {len(frames)} output tables.")


@cli.command("verify-db")
def verify_db_command() -> None:
    """Check PostgreSQL without writing data; read credentials only from the project .env."""
    url = _database_url()
    try:
        with psycopg.connect(
            url, connect_timeout=5, options="-c default_transaction_read_only=on"
        ) as conn:
            conn.execute("select 1").fetchone()
            objects = [
                "pipeline_runs", "quality_findings", "evidence_edges", "result_rows",
                "customers", "subscriptions", "invoices", "monthly_activity",
                "support_tickets", "onboarding_assignments", "funnel_events",
                "monthly_collections", "customer_collected_value",
            ]
            missing = [
                name for name in objects
                if not conn.execute(
                    "select to_regclass(%s) is not null", (f"adryn.{name}",)
                ).fetchone()[0]
            ]
            report = {"connected": True, "schema_ready": not missing, "missing_objects": missing}
            if "pipeline_runs" not in missing:
                output = current_output(get_settings().output_dir)
                summary_path = output / "pipeline_summary.json"
                if summary_path.is_file():
                    run_id = json.loads(summary_path.read_text(encoding="utf-8"))["run_id"]
                    report["run_id"] = run_id
                    report["published_run_loaded"] = conn.execute(
                        "select exists(select 1 from adryn.pipeline_runs where run_id = %s)",
                        (run_id,),
                    ).fetchone()[0]
    except (psycopg.Error, ValueError, OSError, KeyError, TypeError):
        raise click.ClickException(
            "Database verification failed. Check the local .env, database access and published run. "
            "Connection details are withheld."
        ) from None
    click.echo(json.dumps(report, indent=2))


if __name__ == "__main__":
    cli()
