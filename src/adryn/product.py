"""Decision workspace views backed exclusively by computed pipeline artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from adryn.io import read_table
from adryn.reviews import record_review, review_history
from adryn.settings import get_settings

PAGES = [
    "Command center",
    "Customers & retention",
    "Customer 360",
    "Growth & cohorts",
    "Demand planning",
    "Experiments",
    "Customer voice",
    "Model health",
]
COLORS = ["#7db8b0", "#d58f83", "#b9bfc8", "#aaa0c0", "#c2ad79"]


def chart(fig, height=300):
    fig.update_layout(
        height=height,
        margin={"l": 64, "r": 16, "t": 20, "b": 48},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Segoe UI", "size": 12, "color": "#c9ced6"},
        colorway=COLORS,
        legend={"orientation": "h", "y": -0.18},
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor="#30353b", zeroline=False, automargin=True)
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})


def table(frame: pd.DataFrame, name: str):
    frame = frame.drop(columns=["run_id"], errors="ignore")
    st.dataframe(frame, hide_index=True, width="stretch")
    st.download_button(
        "Export " + name,
        frame.to_csv(index=False),
        name.replace(" ", "_") + ".csv",
        "text/csv",
        icon=":material/download:",
        key="download_" + name,
    )


def navigate(page: str):
    st.session_state["business_page"] = page


def render(page: str, directory: Path):
    review_path = get_settings().output_dir / "review_history.sqlite"
    summary_file = directory / "business_summary.json"
    if not summary_file.exists():
        st.title("ADRYN")
        st.info("The decision workspace needs a completed analysis run.")
        return
    try:
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        if not isinstance(summary, dict) or "as_of" not in summary:
            raise ValueError("Incomplete business summary")
    except (ValueError, OSError):
        st.error("The business summary cannot be read. Check the published analysis files.")
        return

    def read(name):
        path = directory / f"{name}.csv"
        if not path.exists():
            st.error(f"Required dataset is unavailable: {name}. Re-run analysis.")
            st.stop()
        try:
            return read_table(path)
        except (OSError, ValueError, pd.errors.ParserError):
            st.error(f"Dataset cannot be read: {name}. Check the published analysis files.")
            st.stop()

    customer = read("customer_360")
    customer.copy()
    scoped = page in [
        "Command center",
        "Customers & retention",
        "Customer 360",
        "Growth & cohorts",
        "Customer voice",
    ]
    if scoped:
        with st.sidebar:
            st.divider()
            region = st.multiselect("Region", sorted(customer.region.unique()), key="region_filter")
            plans = st.multiselect("Plan", sorted(customer.plan.unique()), key="plan_filter")
        if region:
            customer = customer[customer.region.isin(region)]
        if plans:
            customer = customer[customer.plan.isin(plans)]
    ids = set(customer.customer_id)
    st.caption("ADRYN LEARNING / DECISION WORKSPACE")
    st.title("ADRYN" if page == "Command center" else page)
    st.caption(f"{page}  |  Synthetic business  |  As of {summary['as_of']}  |  USD")
    if customer.empty:
        st.info("No customers match the selected region and plan.")
        return
    monthly = read("monthly_kpis")
    if scoped:
        if region:
            monthly = monthly[monthly.region.isin(region)]
        if plans:
            monthly = monthly[monthly.plan.isin(plans)]
    monthly = monthly.groupby("month", as_index=False).sum(numeric_only=True)
    queue = customer[customer.churn_probability.notna()].sort_values(
        "monthly_revenue_exposure", ascending=False
    )

    if page == "Command center":
        brief = directory / "decision_brief.md"
        if brief.exists():
            st.download_button(
                "Decision brief",
                brief.read_text(encoding="utf-8"),
                "ADRYN_decision_brief.md",
                icon=":material/download:",
            )
        active = customer[customer.status == "Active"]
        latest = monthly.iloc[-1]
        previous = monthly.iloc[-2]
        a, b, c, d = st.container(key="command_metrics").columns(4)
        a.metric(
            "Monthly recurring revenue",
            f"${active.monthly_price.sum():,.0f}",
            help="Monthly list price of subscriptions active at the snapshot, regardless of collection.",
        )
        b.metric(
            "September collections",
            f"${latest.collected_revenue:,.0f}",
            f"{latest.collected_revenue - previous.collected_revenue:+,.0f} USD",
            help="Paid September invoices; the change compares collections with August.",
        )
        c.metric("Active members", f"{len(active):,}")
        d.metric(
            "Retention reviews",
            f"{int(queue.review_required.fillna(False).sum()):,}",
            help="Validation-selected model threshold; review candidates, not confirmed cancellations.",
        )
        left, right = st.columns([1.65, 1])
        with left:
            st.subheader("Collections over time")
            chart(
                px.area(
                    monthly,
                    x="month",
                    y="collected_revenue",
                    labels={"collected_revenue": "Collected USD", "month": ""},
                    color_discrete_sequence=COLORS,
                )
            )
        with right:
            st.subheader("Requires attention")
            st.warning(f"{int(latest.failed_payments)} failed subscription payments in September.")
            st.info(
                f"{int(queue.review_required.fillna(False).sum())} active members exceed the retention review threshold."
            )
            st.button(
                "Open retention queue",
                on_click=navigate,
                args=("Customers & retention",),
                icon=":material/arrow_forward:",
            )
            st.button(
                "Investigate customer voice",
                on_click=navigate,
                args=("Customer voice",),
                icon=":material/forum:",
            )
        left, right = st.columns(2)
        with left:
            st.subheader("Member composition")
            groups = customer.groupby(["segment", "status"]).size().reset_index(name="members")
            chart(
                px.bar(
                    groups,
                    x="members",
                    y="segment",
                    color="status",
                    orientation="h",
                    color_discrete_sequence=COLORS,
                    labels={"segment": "", "members": "Members"},
                )
            )
        with right:
            st.subheader("Engagement and service demand")
            chart(
                px.line(
                    monthly,
                    x="month",
                    y="sessions",
                    markers=True,
                    labels={"sessions": "Learning sessions", "month": ""},
                    color_discrete_sequence=COLORS,
                )
            )
        st.caption(
            "Revenue is reconciled to paid invoices. Model scores and intervention costs are synthetic planning evidence."
        )

    elif page == "Customers & retention":
        left, right = st.columns([2, 1])
        status = left.multiselect(
            "Member status", ["Active", "Cancelled", "Trial"], default=["Active"]
        )
        minimum = right.slider("Minimum churn probability", 0.0, 1.0, 0.0, 0.01)
        view = customer[customer.status.isin(status)] if status else customer
        if minimum:
            view = view[view.churn_probability.fillna(0) >= minimum]
        view = view.sort_values("monthly_revenue_exposure", ascending=False)
        st.caption(
            f"{len(view):,} members. Probability is next-month cancellation among members active at the snapshot."
        )
        columns = [
            "customer_id",
            "region",
            "plan",
            "segment",
            "status",
            "sessions",
            "monetary",
            "churn_probability",
            "monthly_revenue_exposure",
            "suggested_action",
        ]
        selection = st.dataframe(
            view[columns],
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "churn_probability": st.column_config.ProgressColumn(
                    "Churn probability", min_value=0, max_value=1, format="percent"
                ),
                "monetary": st.column_config.NumberColumn("Collected value", format="$%.0f"),
                "monthly_revenue_exposure": st.column_config.NumberColumn(
                    "Monthly exposure", format="$%.2f"
                ),
            },
        )
        if selection.selection.rows:
            st.session_state["selected_customer"] = view.iloc[
                selection.selection.rows[0]
            ].customer_id
            st.button(
                "Open selected customer",
                on_click=navigate,
                args=("Customer 360",),
                icon=":material/person_search:",
            )
        st.download_button(
            "Export current queue",
            view[columns].to_csv(index=False),
            "retention_queue.csv",
            icon=":material/download:",
        )
        with st.expander("Segmentation evaluation"):
            table(read("segmentation_evaluation"), "segment evaluation")
        left, right = st.columns(2)
        with left:
            st.subheader("Value and engagement")
            chart(
                px.scatter(
                    view,
                    x="sessions",
                    y="monetary",
                    color="segment",
                    hover_data=["customer_id", "status"],
                    color_discrete_sequence=COLORS,
                    labels={
                        "monetary": "Collected lifetime revenue",
                        "sessions": "Latest observed monthly sessions",
                    },
                )
            )
        with right:
            st.subheader("RFM distribution")
            chart(
                px.histogram(
                    view,
                    x="rfm_score",
                    color_discrete_sequence=COLORS,
                    labels={"rfm_score": "Recency / frequency / monetary score"},
                )
            )

    elif page == "Customer 360":
        options = customer.customer_id.tolist()
        selected = st.session_state.get("selected_customer")
        cid = st.selectbox(
            "Customer", options, index=options.index(selected) if selected in options else 0
        )
        row = customer[customer.customer_id == cid].iloc[0]
        st.subheader(f"{row.full_name} / {row.plan}")
        st.caption(f"{row.region} | {row.status} | {row.segment} | Consent: {row.consent_status}")
        a, b, c, d = st.columns(4)
        a.metric("Collected value", f"${row.monetary:,.0f}")
        b.metric("Paid invoices", f"{row.frequency:.0f}")
        c.metric("Monthly price", f"${row.monthly_price:,.0f}")
        d.metric(
            "Next-month churn",
            f"{row.churn_probability:.1%}" if pd.notna(row.churn_probability) else "Not eligible",
        )
        if pd.notna(row.suggested_action):
            st.info(row.suggested_action)
        a, b, c, d = st.tabs(["Activity", "Billing & support", "Risk & value", "Review history"])
        with a:
            activity = read("subscription_activity")
            activity = activity[activity.customer_id == cid]
            if activity.empty:
                st.info("No paid activity recorded for this member.")
            else:
                chart(
                    px.line(
                        activity,
                        x="month",
                        y="sessions",
                        markers=True,
                        color_discrete_sequence=COLORS,
                    )
                )
                table(activity, "member activity")
        with b:
            orders = read("subscription_orders")
            table(orders[orders.customer_id == cid], "member billing")
            tickets = read("voice_tickets")
            table(
                tickets[tickets.customer_id == cid][
                    ["created_at", "text", "predicted_theme", "resolution_hours"]
                ],
                "member support",
            )
        with c:
            explanations = read("churn_explanations")
            explanations = explanations[explanations.customer_id == cid].sort_values("contribution")
            if not explanations.empty:
                scale = explanations.iloc[0].scale
                st.caption(
                    f"SHAP contributions in {scale}. Positive values increase the model score relative to its background. These explain model behavior, not causes of cancellation."
                )
                chart(
                    px.bar(
                        explanations,
                        x="contribution",
                        y="feature",
                        orientation="h",
                        color_discrete_sequence=COLORS,
                        hover_data=["value", "base_value"],
                    )
                )
            st.caption(
                "Scenario assumes a constant monthly churn probability, 75% gross margin and no discounting. It is not a validated lifetime-value forecast."
            )
            if pd.notna(row.value_12m_scenario):
                st.metric("12-month expected margin scenario", f"${row.value_12m_scenario:,.0f}")
            else:
                st.info("A scenario is available for active, scored subscribers.")
        with d:
            with st.form("customer_review"):
                reviewer = st.text_input("Reviewer")
                decision = st.selectbox(
                    "Decision", ["Investigating", "No action", "Escalated", "Resolved"]
                )
                note = st.text_area("Evidence and next action", max_chars=4000)
                submitted = st.form_submit_button("Save review", icon=":material/save:")
            if submitted:
                try:
                    record_review(
                        review_path,
                        summary["run_id"],
                        cid,
                        reviewer,
                        decision,
                        note,
                    )
                    st.success("Review recorded.")
                except ValueError as exc:
                    st.error(str(exc))
            history = review_history(review_path, cid)
            if history.empty:
                st.info("No review has been recorded for this member.")
            else:
                table(history, "customer reviews")

    elif page == "Growth & cohorts":
        events = read("subscription_events")
        events = events[events.customer_id.isin(ids)]
        counts = (
            events.groupby("event_type")
            .customer_id.nunique()
            .reindex(["signup", "first_lesson", "trial_complete", "paid"], fill_value=0)
        )
        left, right = st.columns([1, 1.8])
        with left:
            st.subheader("Acquisition funnel")
            chart(
                go.Figure(
                    go.Funnel(
                        y=counts.index,
                        x=counts.values,
                        marker_color=COLORS[0],
                        textinfo="value+percent initial",
                    )
                )
            )
            st.caption(
                "Observed events through the snapshot. Recent signups may still be in trial."
            )
        with right:
            st.subheader("Subscriber retention by cohort")
            # Recompute cohort numerators for the selected membership rather than filtering percentages.
            contracts = read("subscription_contracts")
            contracts = contracts[contracts.customer_id.isin(ids)].copy()
            contracts["cohort"] = pd.to_datetime(contracts.start_date).dt.to_period("M").astype(str)
            rows = []
            for cohort, group in contracts.groupby("cohort"):
                for age in range(12):
                    end = pd.Period(cohort, "M").to_timestamp() + pd.offsets.MonthEnd(age + 1)
                    if end > pd.Timestamp(summary["as_of"]):
                        break
                    retained = group.cancelled_at.isna() | (
                        pd.to_datetime(group.cancelled_at) > end
                    )
                    rows.append({"cohort": cohort, "age": age, "retention": retained.mean()})
            if rows:
                matrix = pd.DataFrame(rows).pivot(index="cohort", columns="age", values="retention")
                chart(
                    px.imshow(
                        matrix,
                        zmin=0,
                        zmax=1,
                        color_continuous_scale=["#25292e", "#7db8b0"],
                        labels={"x": "Months since paid start", "y": "Cohort", "color": "Retained"},
                        aspect="auto",
                    ),
                    height=480,
                )

    elif page == "Demand planning":
        history, forecast = read("demand_history"), read("demand_forecast")
        comparison, backtest = read("forecast_comparison"), read("forecast_backtests")
        st.caption(
            "Scope: all regions and plans. Target: monthly learning sessions. Horizon: three months."
        )
        a, b = st.columns([2, 1])
        with a:
            fig = go.Figure()
            fig.add_scatter(
                x=history.month, y=history.sessions, name="Observed", line_color=COLORS[0]
            )
            fig.add_scatter(
                x=forecast.month,
                y=forecast.upper_empirical,
                mode="lines",
                line_width=0,
                showlegend=False,
            )
            fig.add_scatter(
                x=forecast.month,
                y=forecast.lower_empirical,
                mode="lines",
                line_width=0,
                fill="tonexty",
                fillcolor="rgba(226,117,99,.18)",
                name="Empirical residual band",
            )
            fig.add_scatter(
                x=forecast.month,
                y=forecast.forecast,
                name="Forecast",
                line={"color": COLORS[1], "dash": "dash"},
            )
            chart(fig, 360)
        with b:
            st.subheader("Capacity scenario")
            capacity = st.number_input(
                "Monthly session capacity",
                min_value=1,
                value=max(1, int(forecast.forecast.max() * 1.1)),
                step=100,
            )
            st.metric("Peak forecast", f"{forecast.forecast.max():,.0f}")
            st.metric("Headroom at peak", f"{capacity - forecast.forecast.max():,.0f}")
            st.caption(
                "Bands use 10th/90th percentiles of selection residuals from four origins. Coverage is not calibrated."
            )
        st.subheader("Forecast comparison")
        table(comparison, "forecast evaluation")
        with st.expander("Rolling backtest evidence"):
            table(backtest, "backtests")
        st.caption(
            "Model selection uses earlier rolling origins. July-September 2026 is the final held-out window; the production forecast refits through September."
        )

    elif page == "Experiments":
        results = read("experiment_results")
        overall = results[results.segment == "Overall"].iloc[0]
        st.subheader("Guided onboarding / 60-day retention")
        st.caption(
            "Assignment at signup, one assignment per customer. Intention-to-treat analysis includes non-converters. Only fully observed 60-day outcomes are included."
        )
        a, b, c = st.columns(3)
        a.metric(
            "Control retained",
            f"{overall.control_rate:.1%}",
            help=f"{int(overall.control_n)} assigned members",
        )
        b.metric(
            "Treatment retained",
            f"{overall.treatment_rate:.1%}",
            help=f"{int(overall.treatment_n)} assigned members",
        )
        c.metric(
            "Absolute effect",
            f"{overall.absolute_effect * 100:+.2f} pp",
            help="Treatment minus control. See the interval before making a decision.",
        )
        st.info(overall.decision)
        fig = go.Figure(
            go.Scatter(
                x=results.absolute_effect * 100,
                y=results.segment,
                mode="markers",
                error_x={
                    "type": "data",
                    "array": (results.ci95_high - results.absolute_effect) * 100,
                    "arrayminus": (results.absolute_effect - results.ci95_low) * 100,
                },
                marker={"color": COLORS[0], "size": 10},
            )
        )
        fig.add_vline(x=0, line_dash="dot", line_color="#79847f")
        fig.update_xaxes(title="Retention difference (percentage points), approximate 95% CI")
        chart(fig)
        st.caption(
            f"Planning target: {int(overall.required_per_arm_for_5pp):,} per arm for a 5 pp effect, 80% power, two-sided 5% significance, assumed 50% base rate. Practical rollout threshold: lower bound above +3 pp and support guardrail upper bound below +0.2 tickets/member."
        )
        table(results, "experiment evidence")
        st.caption(
            "Regional comparisons are exploratory and unadjusted. Individual uplift is not estimated: this trial has insufficient evidence for reliable treatment-effect targeting."
        )

    elif page == "Customer voice":
        with st.expander("Emerging issues / all regions and plans"):
            table(read("voice_emerging_issues"), "emerging issues")
        tickets = read("voice_tickets")
        tickets = tickets[tickets.customer_id.isin(ids)].copy()
        if tickets.empty:
            st.info("No support interactions match this scope.")
            return
        themes = st.multiselect("Issue theme", sorted(tickets.predicted_theme.unique()))
        if themes:
            tickets = tickets[tickets.predicted_theme.isin(themes)]
        left, right = st.columns([1.5, 1])
        with left:
            st.subheader("Service issues over time")
            trend = tickets.groupby(["month", "predicted_theme"]).size().reset_index(name="tickets")
            chart(
                px.line(
                    trend,
                    x="month",
                    y="tickets",
                    color="predicted_theme",
                    color_discrete_sequence=COLORS,
                )
            )
        with right:
            st.subheader("Affected members")
            affected = (
                tickets.groupby("predicted_theme").customer_id.nunique().reset_index(name="members")
            )
            chart(
                px.bar(
                    affected,
                    x="members",
                    y="predicted_theme",
                    orientation="h",
                    color_discrete_sequence=COLORS,
                )
            )
        table(
            tickets[
                [
                    "ticket_id",
                    "customer_id",
                    "created_at",
                    "text",
                    "predicted_theme",
                    "confidence",
                    "needs_review",
                    "resolution_hours",
                ]
            ],
            "support evidence",
        )
        with st.expander("Classification evaluation"):
            table(read("voice_metrics"), "voice evaluation")

    elif page == "Model health":
        metadata = json.loads((directory / "models" / "metadata.json").read_text(encoding="utf-8"))
        st.subheader(metadata["selected_model"])
        st.caption(
            f"Training: {metadata['train_rows']:,} observations | Validation: {metadata['validation_rows']:,} | Test: {metadata['test_rows']:,} | Threshold: {metadata['threshold']:.2f}"
        )
        st.caption(
            "Customer-month observations recur across temporal splits; this evaluates future scoring of the membership population, not generalization to unseen customers."
        )
        table(read("churn_metrics"), "churn evaluation")
        left, right = st.columns(2)
        with left:
            st.subheader("Observed versus predicted risk")
            cal = read("churn_calibration")
            fig = px.scatter(
                cal, x="predicted", y="observed", size="rows", color_discrete_sequence=COLORS
            )
            fig.add_scatter(
                x=[0, 1],
                y=[0, 1],
                mode="lines",
                name="Perfect calibration",
                line={"color": "#9aa4a1", "dash": "dot"},
            )
            chart(fig)
        with right:
            st.subheader("Held-out feature importance")
            importance = read("churn_importance").sort_values("importance")
            chart(
                px.bar(
                    importance,
                    x="importance",
                    y="feature",
                    orientation="h",
                    error_x="std",
                    color_discrete_sequence=COLORS,
                )
            )
        st.subheader("Input drift")
        table(read("feature_drift"), "drift signals")
        st.caption(
            "KS effect threshold 0.15 with a Bonferroni-adjusted significance check. Monthly review is required; drift does not trigger automatic promotion."
        )
        with st.expander("Run provenance"):
            st.json(metadata)
