# Delivery status

This file distinguishes implemented local workflows from integrations and product maturity still requiring work.

## Implemented
- One subscription business ecosystem with fixed-date reproducible generation.
- Shared customer IDs across billing, activity, support, onboarding and trust projections.
- Quality checks, CRM cleanup/quarantine and measured duplicate-join impact.
- SQL schema, normalized loader and analytical queries.
- Ledger metrics, RFM, behavioral segments, funnel, cohorts and Customer 360.
- Churn baselines, temporal evaluation, calibration, threshold costs, SHAP and drift.
- Rolling demand forecast comparison and a capacity scenario.
- Randomized onboarding analysis with power, intervals, guardrails and a decision.
- Support-theme classification, evaluation and emerging-issue evidence.
- Business and trust workspaces with scoped filters, exports and local review persistence.
- Local model API, immutable output publication and per-run experiment records.
- Unit/integration/application tests, CI definition, container definitions and documentation.

## Verification boundaries
The business-view and API parity tests passed during the upgrade. The final test and visual QA results are reported at handoff, rather than hard-coded here.
PostgreSQL persistence remains unverified until a valid local connection setting is supplied.
Docker is not installed on this machine; container execution remains unverified.
CI has not yet run on GitHub. No upgrade commit or push has been made.
Power BI import assets are supplied; an actual Desktop PBIX is not yet delivered.
The original four-slide trust deck remains available; it is not a full business-platform presentation.

## Production maturity remaining
- Authenticated shared deployment, roles and a shared review database.
- Real-source ingestion and operational freshness contracts.
- Human evaluation of support routing and externally valid model validation.
- More forecast history and calibrated intervals.
- Adequately powered experimentation before individual uplift targeting.
- Automated scheduling, alert delivery, backup/restore drills and approved promotion processes.

These are explicit boundaries. The local synthetic product should not be described as a deployed production system.

