"""Append-only local decision log, independent of regenerated analysis outputs."""

import sqlite3
from pathlib import Path

import pandas as pd


def record_review(
    path: Path, run_id: str, customer_id: str, reviewer: str, decision: str, note: str
) -> None:
    if not reviewer.strip() or not note.strip():
        raise ValueError("Reviewer and decision note are required.")
    if decision not in {"Investigating", "No action", "Escalated", "Resolved"}:
        raise ValueError("Unknown review decision.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "create table if not exists reviews (id integer primary key, created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ','now')), run_id text not null, customer_id text not null, reviewer text not null, decision text not null, note text not null)"
        )
        conn.execute(
            "insert into reviews (run_id, customer_id, reviewer, decision, note) values (?, ?, ?, ?, ?)",
            (run_id, customer_id, reviewer.strip(), decision, note.strip()),
        )


def review_history(path: Path, customer_id: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(
            "select created_at, reviewer, decision, note, run_id from reviews where customer_id = ? order by id desc",
            conn,
            params=(customer_id,),
        )
