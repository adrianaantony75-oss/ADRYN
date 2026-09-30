from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from adryn.io import current_output, read_table
from adryn.product import PAGES, render
from adryn.reports.pipeline import run_pipeline
from adryn.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]
APP_SETTINGS = get_settings()
st.set_page_config(page_title="ADRYN | Decision Workspace", page_icon="◈", layout="wide")
try:
    OUTPUT_DIR = current_output(APP_SETTINGS.output_dir)
except (ValueError, KeyError, TypeError, OSError):
    st.title("ADRYN")
    st.error("The published analysis is unavailable. Check outputs/current_run.json and its snapshot.")
    st.stop()
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = ROOT / OUTPUT_DIR

st.markdown(
    """
    <style>
    :root { --ink:#edf0f3; --muted:#a1a8b1; --green:#bbc5d1; --line:#30353b; --paper:#111315; }
    html, body, [class*="css"] { font-family:'Segoe UI', sans-serif; color:var(--ink); }
    .stApp { background:var(--paper); }
    [data-testid="stHeader"] { background:rgba(17,19,21,.96); }
    [data-testid="stSidebar"] { background:#171a1e; border-right:1px solid var(--line); }
    [data-testid="stSidebar"] > div:first-child { padding-top:1.2rem; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stRadio"] label,
    [data-testid="stSidebar"] [data-testid="stRadio"] label *,
    [data-testid="stSidebar"] label, [data-testid="stSidebar"] p { color:var(--ink) !important; }
    .brand { font:700 26px 'Segoe UI',sans-serif; letter-spacing:0; color:var(--ink); }
    .brand-mark { color:var(--green); padding-right:8px; }
    .brand-sub { color:var(--muted); font-size:11px; letter-spacing:0; margin:2px 0 22px 34px; }
    .eyebrow { color:var(--green); font-size:11px; font-weight:700; letter-spacing:0; text-transform:uppercase; }
    h1,h2,h3 { font-family:'Segoe UI',sans-serif !important; letter-spacing:0 !important; color:var(--ink) !important; }
    h1 { font-size:30px !important; margin:0 0 3px !important; }
    h2 { font-size:21px !important; font-weight:600 !important; }
    h3 { font-size:18px !important; font-weight:600 !important; }
    .subhead { color:var(--muted); font-size:14px; margin-bottom:22px; }
    .metric { background:#1b1e22; border:1px solid var(--line); border-radius:6px; padding:17px 18px 15px; min-height:104px; animation:rise .42s ease both; }
    .metric-label { color:var(--muted); font-size:11px; font-weight:700; text-transform:uppercase; }
    .metric-value { font:650 28px 'Segoe UI',sans-serif; color:var(--ink); margin-top:9px; }
    .metric-note { color:var(--muted); font-size:11px; margin-top:1px; }
    .section-label { font:600 16px 'Segoe UI',sans-serif; margin:18px 0 8px; }
    .status { display:inline-flex; align-items:center; gap:7px; color:var(--muted); font-size:12px; }
    .status-dot { width:7px; height:7px; border-radius:50%; background:#91b9ab; box-shadow:0 0 0 3px #25332e; }
    div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:6px; overflow:hidden; }
    div.stButton > button, div.stDownloadButton > button { border-radius:5px; font-weight:600; }
    div.stButton > button[kind="primary"] { background:var(--green); border-color:var(--green); color:#111315 !important; }
    [data-testid="stSidebar"] div.stButton > button[kind="primary"] p { color:#111315 !important; }
    div.stButton > button:hover, div.stDownloadButton > button:hover { border-color:var(--green); color:var(--green); transition:all .16s ease; }
    [data-testid="stMetric"] { background:#1b1e22; border:1px solid var(--line); border-radius:6px; padding:16px 18px; min-height:128px; animation:rise .35s ease both; }
    [data-testid="stMetricValue"] { font-size:23px !important; line-height:1.2; }
    [data-testid="stTabs"] button { font-weight:600; }
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color:var(--muted) !important; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { padding:6px 0; min-height:36px; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:#272c32; border-radius:5px; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background:#22262b; border-radius:5px; }
    [data-testid="stMainBlockContainer"] { padding-top:2.8rem; padding-bottom:3rem; }
    [data-testid="stMetricLabel"] { min-height:34px; }
    [data-testid="stMetricLabel"] p { color:var(--muted); font-size:12px; white-space:normal !important; overflow:visible !important; text-overflow:clip !important; }
    [data-testid="stMetricValue"] { color:var(--ink); overflow-wrap:anywhere; }
    [data-testid="stAlert"] { border-radius:5px; }
    @media (max-width:640px) {
        [data-testid="stMainBlockContainer"] { padding:4.5rem 1rem 2rem; }
        h1 { font-size:26px !important; }
        .st-key-command_metrics [data-testid="stHorizontalBlock"] { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
        .st-key-command_metrics [data-testid="stColumn"] { width:100% !important; min-width:0 !important; flex:unset !important; }
        .st-key-command_metrics [data-testid="stMetric"] { padding:12px; }
    }
    @keyframes rise { from { opacity:0; transform:translateY(7px); } to { opacity:1; transform:translateY(0); } }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration:.01ms !important; transition-duration:.01ms !important; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def read_csv(name: str) -> pd.DataFrame:
    path = OUTPUT_DIR / f"{name}.csv"
    return read_table(path) if path.exists() else pd.DataFrame()


def metric(label: str, value: int | str, note: str = "") -> None:
    st.markdown(
        f'<div class="metric"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div><div class="metric-note">{note}</div></div>',
        unsafe_allow_html=True,
    )


def display_frame(frame: pd.DataFrame, **kwargs) -> None:
    st.dataframe(frame.drop(columns=["run_id"], errors="ignore"), **kwargs)


with st.sidebar:
    st.markdown(
        '<div class="brand"><span class="brand-mark">◈</span>ADRYN</div>', unsafe_allow_html=True
    )
    st.markdown('<div class="brand-sub">DECISION INTELLIGENCE</div>', unsafe_allow_html=True)
    workspace = st.selectbox("Workspace", ["Business intelligence", "Trust operations"])
    page = st.radio(
        "View",
        PAGES
        if workspace == "Business intelligence"
        else [
            "Overview",
            "Data quality",
            "Privacy",
            "Contracts",
            "AI reviews",
            "Evidence & signals",
        ],
        label_visibility="collapsed",
        key="business_page" if workspace == "Business intelligence" else "trust_page",
    )
    st.divider()
    st.markdown(
        '<span class="status"><span class="status-dot"></span>Local workspace</span>',
        unsafe_allow_html=True,
    )
    if st.button("Run analysis", type="primary", icon="▶", width="stretch"):
        with st.spinner("Generating the reproducible trust assessment…"):
            try:
                st.session_state["last_run"] = run_pipeline(APP_SETTINGS)
                st.success("Analysis complete")
                st.rerun()
            except (ValueError, OSError, RuntimeError, KeyError) as exc:
                st.error(f"Analysis could not finish: {exc}")

summary_path = OUTPUT_DIR / "pipeline_summary.json"
if not summary_path.exists():
    st.title("ADRYN Trust Operations")
    st.markdown(
        '<div class="subhead">A clear view of data quality, privacy, contracts, and AI review risk.</div>',
        unsafe_allow_html=True,
    )
    st.info(
        "No assessment is available yet. Start a run to build the reviewer queues and evidence outputs."
    )
    st.stop()

try:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or "run_id" not in summary:
        raise ValueError("Incomplete analysis summary")
except (ValueError, OSError):
    st.error("The analysis summary cannot be read. Check the published snapshot before rerunning analysis.")
    st.stop()
if workspace == "Business intelligence":
    render(page, OUTPUT_DIR)
    st.stop()
page_copy = {
    "Overview": (
        "Trust operations, at a glance",
        "Signals from the latest reproducible assessment.",
    ),
    "Data quality": (
        "Data quality",
        "Findings are grouped by rule and severity for focused remediation.",
    ),
    "Privacy": (
        "Privacy review",
        "Consent state and detected personal data, surfaced for human review.",
    ),
    "Contracts": (
        "Contract reconciliation",
        "Differences between CRM and ERP records, with evidence fields.",
    ),
    "AI reviews": (
        "AI review queue",
        "Risk scores prioritize human attention; decisions remain with reviewers.",
    ),
    "Evidence & signals": (
        "Evidence and signals",
        "Traceable relationships, anomalies, drift checks, and run outputs.",
    ),
}
title, subtitle = page_copy[page]
st.markdown('<div class="eyebrow">ADRYN  /  TRUST INTELLIGENCE</div>', unsafe_allow_html=True)
st.title(title)
st.markdown(f'<div class="subhead">{subtitle}</div>', unsafe_allow_html=True)

if page == "Overview":
    cols = st.columns(4)
    values = [
        ("Quality findings", summary["quality_findings"], "Across customer and order data"),
        (
            "Consent reviews",
            summary["privacy_records_requiring_review"],
            "Restricted or unknown consent",
        ),
        (
            "Contract reviews",
            summary["contract_records_requiring_review"],
            "CRM and ERP mismatches",
        ),
        ("AI reviews", summary["ai_reviews_scored"], "Risk scored for triage"),
    ]
    for col, valueset in zip(cols, values):
        with col:
            metric(*valueset)
    signal_cols = st.columns(3)
    for col, valueset in zip(
        signal_cols,
        [
            ("Privacy signals", summary["pii_findings"], "Sensitive columns identified"),
            ("Order anomalies", summary["anomalous_orders"], "Flagged by Isolation Forest"),
            ("Evidence links", summary["evidence_edges"], "Traceable relationships"),
        ],
    ):
        with col:
            metric(*valueset)
    left, right = st.columns([1.25, 1])
    with left:
        st.markdown('<div class="section-label">Signals by family</div>', unsafe_allow_html=True)
        signal = read_csv("powerbi_signal_counts")
        if not signal.empty:
            st.bar_chart(
                signal.set_index("signal_family")["finding_count"], color="#167451", height=260
            )
        st.markdown(
            '<div class="section-label">Priority failure modes</div>', unsafe_allow_html=True
        )
        risk = read_csv("powerbi_risk_rank")
        if not risk.empty:
            display_frame(
                risk[["failure_family", "failure_mode", "weighted_risk"]].head(6),
                hide_index=True,
                width="stretch",
            )
    with right:
        st.markdown(
            '<div class="section-label">AI evaluation snapshot</div>', unsafe_allow_html=True
        )
        a, b = st.columns(2)
        a.metric("Accuracy", f"{summary['ai_eval_accuracy']:.1%}")
        b.metric("ROC AUC", f"{summary['ai_eval_roc_auc']:.3f}")
        c, d = st.columns(2)
        c.metric("Recall", f"{summary['ai_eval_recall']:.1%}")
        d.metric("Risk cutoff", f"{summary['ai_eval_review_threshold']:.2f}")
        st.caption(
            f"Precision {summary['ai_eval_precision']:.1%} · "
            f"F1 {summary['ai_eval_f1']:.1%} · "
            f"Held-out sample: {summary['ai_eval_test_rows']} reviews. "
            "Synthetic benchmark, not a production performance claim."
        )
        st.markdown('<div class="section-label">Latest assessment</div>', unsafe_allow_html=True)
        st.caption(f"Run ID: {summary['run_id']}  ·  Seed: {summary['seed']}")
        deck_path = OUTPUT_DIR / "ADRYN_Executive_Brief.pptx"
        if deck_path.exists():
            st.download_button(
                "Download executive brief",
                deck_path.read_bytes(),
                file_name=deck_path.name,
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                icon="⬇",
            )

elif page == "Data quality":
    remediation = read_csv("quality_remediation")
    if not remediation.empty:
        st.subheader("Remediation and measured impact")
        display_frame(remediation, hide_index=True, width="stretch")
    findings = read_csv("quality_findings")
    profile = read_csv("data_profile")
    if findings.empty:
        st.success("No findings in this run.")
    else:
        c1, c2 = st.columns(2)
        severities = ["All"] + sorted(findings["severity"].dropna().unique().tolist())
        rules = ["All"] + sorted(findings["rule_id"].dropna().unique().tolist())
        severity = c1.selectbox("Severity", severities)
        rule = c2.selectbox("Rule", rules)
        filtered = findings.copy()
        if severity != "All":
            filtered = filtered[filtered["severity"] == severity]
        if rule != "All":
            filtered = filtered[filtered["rule_id"] == rule]
        st.caption(f"{len(filtered):,} findings in the current view")
        display_frame(filtered, hide_index=True, width="stretch")
        st.download_button(
            "Export current findings",
            filtered.to_csv(index=False),
            "quality_findings.csv",
            "text/csv",
            icon="⬇",
        )
    with st.expander("Dataset profile"):
        display_frame(profile, hide_index=True, width="stretch")

elif page == "Privacy":
    twin = read_csv("privacy_twin")
    pii = read_csv("pii_findings")
    if not pii.empty:
        st.markdown(
            '<div class="section-label">Detected sensitive columns</div>', unsafe_allow_html=True
        )
        display_frame(pii, hide_index=True, width="stretch")
    if not twin.empty:
        only_review = st.toggle("Only records requiring human review", value=True)
        view = twin[twin["requires_human_review"]] if only_review else twin
        st.caption(f"{len(view):,} customer records shown")
        display_frame(view, hide_index=True, width="stretch")
        st.download_button(
            "Export privacy queue",
            view.to_csv(index=False),
            "privacy_review_queue.csv",
            "text/csv",
            icon="⬇",
        )

elif page == "Contracts":
    contracts = read_csv("contract_reconciliation")
    if not contracts.empty:
        only_review = st.toggle("Only mismatches requiring review", value=True)
        view = contracts[contracts["requires_review"]] if only_review else contracts
        c1, c2 = st.columns(2)
        st.metric("Records shown", f"{len(view):,}")
        st.metric("Value mismatches", f"{int(view['value_mismatch'].sum()):,}")
        display_frame(view, hide_index=True, width="stretch")
        st.download_button(
            "Export contract queue",
            view.to_csv(index=False),
            "contract_review_queue.csv",
            "text/csv",
            icon="⬇",
        )

elif page == "AI reviews":
    reviews = read_csv("ai_review_priorities")
    if not reviews.empty:
        c1, c2, c3 = st.columns(3)
        priorities = ["All"] + [
            p for p in ["critical", "high", "medium", "low"] if p in set(reviews["review_priority"])
        ]
        priority = c1.selectbox("Priority", priorities)
        models = ["All"] + sorted(reviews["model_name"].dropna().unique().tolist())
        model_name = c2.selectbox("Model", models)
        human_only = c3.toggle("Human disagreement only", value=False)
        view = reviews.copy()
        if priority != "All":
            view = view[view["review_priority"] == priority]
        if model_name != "All":
            view = view[view["model_name"] == model_name]
        if human_only:
            view = view[view["human_disagreed"]]
        st.caption(f"{len(view):,} reviews in this queue, sorted by risk score")
        display_frame(view, hide_index=True, width="stretch")
        st.download_button(
            "Export current queue",
            view.to_csv(index=False),
            "ai_review_queue.csv",
            "text/csv",
            icon="⬇",
        )
        ambiguity = read_csv("ambiguity_lab")
        with st.expander(f"Ambiguity Lab · {len(ambiguity):,} near-boundary cases"):
            display_frame(ambiguity, hide_index=True, width="stretch")
        with st.expander("Model signal importance"):
            importance = read_csv("ai_feature_importance")
            st.caption(
                "Permutation importance on the held-out sample. Values can be near zero or negative."
            )
            display_frame(importance, hide_index=True, width="stretch")
        with st.expander("Sensitive-context subgroup check"):
            groups = read_csv("ai_group_evaluation")
            st.caption(
                "Held-out metrics by synthetic sensitive-context flag; small sample sizes can be unstable."
            )
            display_frame(groups, hide_index=True, width="stretch")

else:
    evidence, genome = read_csv("evidence_graph_edges"), read_csv("failure_genome")
    anomalies, drift = read_csv("order_anomalies"), read_csv("order_drift")
    st.markdown('<div class="section-label">Failure Genome</div>', unsafe_allow_html=True)
    display_frame(genome, hide_index=True, width="stretch")
    a, b = st.columns(2)
    with a:
        st.markdown('<div class="section-label">Order anomalies</div>', unsafe_allow_html=True)
        display_frame(
            anomalies[anomalies["is_anomaly"]].head(100),
            hide_index=True,
            width="stretch",
        )
    with b:
        st.markdown('<div class="section-label">Temporal drift check</div>', unsafe_allow_html=True)
        display_frame(drift, hide_index=True, width="stretch")
        st.caption("Exploratory distribution comparison; this signal does not establish a cause.")
    with st.expander(f"Evidence graph · {len(evidence):,} edges"):
        display_frame(evidence, hide_index=True, width="stretch")
        st.download_button(
            "Export evidence edges",
            evidence.to_csv(index=False),
            "evidence_graph_edges.csv",
            "text/csv",
            icon="⬇",
        )
    comparison = read_csv("model_comparison")
    with st.expander("Model comparison"):
        display_frame(comparison, hide_index=True, width="stretch")
