"""A fixed-date, seeded subscription business simulation; never real customer data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

AS_OF = pd.Timestamp("2026-09-30")
START = pd.Timestamp("2024-04-01")
PRICES = {"Essential": 19.0, "Professional": 39.0, "Teams": 79.0}
THEMES = {
    "billing": [
        "My invoice has an unexpected charge",
        "Please explain the renewal payment",
        "I need help changing my payment method",
        "The subscription charge seems incorrect",
    ],
    "playback": [
        "The lesson video freezes halfway through",
        "Audio stops while watching a course",
        "Video playback is buffering again",
        "The player will not load my lesson",
    ],
    "content": [
        "Please add more advanced analytics courses",
        "This course needs updated examples",
        "I cannot find the topic I need",
        "The lesson material is too basic",
    ],
    "access": [
        "I cannot sign in to my account",
        "The password reset link has expired",
        "My team invitation does not work",
        "I lost access to the course library",
    ],
}


def generate_platform(seed: int, customer_count: int = 1800) -> dict[str, pd.DataFrame]:
    """Simulate monthly subscriptions, observable behavior and randomized onboarding.

    Cancellation is drawn AFTER the month's activity. Outcome labels are built from
    next-month status downstream, so no future cancellation fields enter features.
    Experiments assign onboarding at signup and affect the same retention process.
    """
    if customer_count < 100:
        raise ValueError("At least 100 customers are required for the simulation.")
    rng = np.random.default_rng(seed)
    months = pd.date_range(START, AS_OF, freq="MS")
    customers, subscriptions, activity, invoices, tickets, assignments, events = (
        [] for _ in range(7)
    )
    for i in range(customer_count):
        cid = f"CUST-{i + 1:05d}"
        start_index = int(
            rng.choice(
                len(months),
                p=np.linspace(1, 2.2, len(months)) / np.linspace(1, 2.2, len(months)).sum(),
            )
        )
        signup = months[start_index] + pd.Timedelta(days=int(rng.integers(0, 20)))
        plan = str(rng.choice(list(PRICES), p=[0.49, 0.38, 0.13]))
        region = str(rng.choice(["NA", "EU", "APAC", "LATAM"], p=[0.4, 0.27, 0.23, 0.1]))
        consent = str(rng.choice(["granted", "revoked", "unknown"], p=[0.85, 0.08, 0.07]))
        motivation = float(rng.beta(3, 2))
        converted = bool(rng.random() < 0.76)
        treatment = int(rng.integers(0, 2))
        eligible = signup < AS_OF - pd.Timedelta(days=60)
        assignments.append(
            {
                "customer_id": cid,
                "assigned_at": signup.date().isoformat(),
                "treatment": treatment,
                "eligible_for_analysis": eligible,
            }
        )
        customers.append(
            {
                "customer_id": cid,
                "full_name": f"Demo Member {i + 1:04d}",
                "email": f"member{i + 1}@example.test",
                "phone": f"+1-202-555-{i % 10000:04d}",
                "region": region,
                "signup_date": signup.date().isoformat(),
                "consent_status": consent,
                "acquisition_channel": str(
                    rng.choice(["organic", "referral", "paid_search", "partner"])
                ),
                "plan": plan,
            }
        )
        for stage, offset in [
            ("signup", 0),
            ("first_lesson", 1),
            ("trial_complete", 7),
            ("paid", 14),
        ]:
            if signup + pd.Timedelta(days=offset) > AS_OF:
                break
            if stage == "first_lesson" and rng.random() < 0.12:
                break
            if stage == "trial_complete" and rng.random() < 0.08:
                break
            if stage == "paid" and not converted:
                break
            events.append(
                {
                    "event_id": f"EV-{len(events) + 1:06d}",
                    "customer_id": cid,
                    "event_date": (signup + pd.Timedelta(days=offset)).date().isoformat(),
                    "event_type": stage,
                }
            )
        # A paid subscription must follow the actual funnel path.
        converted = any(e["event_type"] == "paid" for e in events[-4:] if e["customer_id"] == cid)
        cancelled = None
        subscription_start = signup + pd.Timedelta(days=14)
        if converted:
            for j, month in enumerate(months):
                if month.to_period("M") < subscription_start.to_period("M"):
                    continue
                month_end = month + pd.offsets.MonthEnd(0)
                sessions = int(
                    rng.poisson(max(0.5, 22 * motivation * (1 + 0.15 * np.sin(j * np.pi / 6))))
                )
                failed = int(rng.random() < (0.035 if plan != "Essential" else 0.07))
                support_count = int(rng.poisson(0.18 + failed * 1.4))
                recency = int(min(30, rng.geometric(min(0.8, (sessions + 1) / 35))))
                activity.append(
                    {
                        "customer_id": cid,
                        "month": month.date().isoformat(),
                        "sessions": sessions,
                        "learning_minutes": int(sessions * rng.uniform(12, 40)),
                        "days_since_activity": recency,
                        "support_tickets": support_count,
                        "payment_failed": failed,
                        "monthly_price": PRICES[plan],
                        "tenure_months": j - start_index + 1,
                    }
                )
                bill_date = max(
                    month + pd.Timedelta(days=min(subscription_start.day, 28) - 1),
                    subscription_start,
                )
                invoices.append(
                    {
                        "order_id": f"INV-{len(invoices) + 1:06d}",
                        "customer_id": cid,
                        "order_date": bill_date.date().isoformat(),
                        "amount": PRICES[plan],
                        "payment_status": "failed" if failed else "paid",
                        "channel": "subscription",
                    }
                )
                for _ in range(support_count):
                    theme = str(
                        rng.choice(
                            list(THEMES),
                            p=[0.25, 0.4 if j >= 25 else 0.25, 0.15 if j >= 25 else 0.3, 0.2],
                        )
                    )
                    tickets.append(
                        {
                            "ticket_id": f"TKT-{len(tickets) + 1:06d}",
                            "customer_id": cid,
                            "created_at": bill_date.date().isoformat(),
                            "text": str(rng.choice(THEMES[theme]))
                            + str(
                                rng.choice(
                                    [
                                        ". Please help.",
                                        ". This happened today.",
                                        ". It is affecting my learning.",
                                        ". Can someone investigate?",
                                    ]
                                )
                            ),
                            "theme": theme,
                            "resolution_hours": round(
                                float(rng.gamma(2, 7 if theme == "playback" else 4)), 2
                            ),
                        }
                    )
                early = j - start_index < 3
                hazard = np.clip(
                    0.018
                    + 0.13 * (1 - motivation)
                    + 0.06 * failed
                    + 0.025 * (sessions < 5)
                    - 0.025 * treatment * early,
                    0.008,
                    0.4,
                )
                if rng.random() < hazard:
                    cancelled = month_end
                    break
                motivation = float(np.clip(motivation + rng.normal(-0.005, 0.06), 0.03, 0.97))
            subscriptions.append(
                {
                    "subscription_id": f"SUB-{i + 1:05d}",
                    "customer_id": cid,
                    "plan": plan,
                    "monthly_price": PRICES[plan],
                    "start_date": subscription_start.date().isoformat(),
                    "cancelled_at": cancelled.date().isoformat() if cancelled is not None else None,
                }
            )
    tables = {
        "customers": pd.DataFrame(customers),
        "subscriptions": pd.DataFrame(subscriptions),
        "activity": pd.DataFrame(activity),
        "orders": pd.DataFrame(invoices),
        "tickets": pd.DataFrame(tickets),
        "experiment": pd.DataFrame(assignments),
        "events": pd.DataFrame(events),
    }
    exp = tables["experiment"].merge(
        tables["subscriptions"][["customer_id", "start_date", "cancelled_at"]],
        how="left",
        on="customer_id",
    )
    cutoff = pd.to_datetime(exp.assigned_at) + pd.Timedelta(days=60)
    exp["retained_60d"] = (
        exp.start_date.notna()
        & (exp.cancelled_at.isna() | (pd.to_datetime(exp.cancelled_at) >= cutoff))
    ).astype(int)
    exp["support_60d"] = [
        int(
            (
                (tables["tickets"].customer_id == row.customer_id)
                & (
                    pd.to_datetime(tables["tickets"].created_at)
                    < pd.Timestamp(row.assigned_at) + pd.Timedelta(days=60)
                )
            ).sum()
        )
        for row in exp.itertuples()
    ]
    tables["experiment"] = exp.drop(columns=["start_date", "cancelled_at"])
    return tables


def validate_platform(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Fail closed on invalid primary keys, relationships, dates or ledger amounts."""
    customers = tables["customers"]
    checks = []
    keys = {
        "customers": ["customer_id"],
        "subscriptions": ["subscription_id"],
        "activity": ["customer_id", "month"],
        "orders": ["order_id"],
        "tickets": ["ticket_id"],
        "experiment": ["customer_id"],
        "events": ["event_id"],
    }
    for name, key in keys.items():
        frame = tables[name]
        checks.append(
            {
                "table": name,
                "check": "unique_nonnull_key",
                "failed_rows": int((frame.duplicated(key) | frame[key].isna().any(axis=1)).sum()),
            }
        )
        if name != "customers":
            checks.append(
                {
                    "table": name,
                    "check": "customer_foreign_key",
                    "failed_rows": int((~frame.customer_id.isin(customers.customer_id)).sum()),
                }
            )
    checks.append(
        {
            "table": "orders",
            "check": "positive_amount",
            "failed_rows": int(
                (~np.isfinite(tables["orders"].amount) | (tables["orders"].amount <= 0)).sum()
            ),
        }
    )
    for name, date_column in [
        ("customers", "signup_date"),
        ("orders", "order_date"),
        ("tickets", "created_at"),
        ("events", "event_date"),
    ]:
        dated = tables[name].merge(
            customers[["customer_id", "signup_date"]].rename(
                columns={"signup_date": "customer_signup"}
            ),
            on="customer_id",
            how="left",
            validate="many_to_one",
        )
        dates = pd.to_datetime(dated[date_column], errors="coerce")
        invalid = dates.isna() | (dates > AS_OF) | (dates < pd.to_datetime(dated.customer_signup))
        checks.append(
            {
                "table": name,
                "check": "date_within_customer_history",
                "failed_rows": int(invalid.sum()),
            }
        )
    subscriptions = tables["subscriptions"]
    checks.append({
        "table": "subscriptions",
        "check": "unique_customer_subscription",
        "failed_rows": int(subscriptions.customer_id.duplicated().sum()),
    })
    checks.append(
        {
            "table": "subscriptions",
            "check": "cancel_after_start",
            "failed_rows": int(
                (
                    pd.to_datetime(subscriptions.cancelled_at)
                    < pd.to_datetime(subscriptions.start_date)
                ).sum()
            ),
        }
    )
    result = pd.DataFrame(checks)
    if result.failed_rows.sum():
        raise ValueError(
            "Platform validation failed: "
            + result[result.failed_rows > 0].to_json(orient="records")
        )
    return result


def write_platform(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(directory / f"{name}.csv", index=False)
