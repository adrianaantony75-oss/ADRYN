# Explaining ADRYN

## A concise introduction
I built an internal decision workspace for a fictional subscription learning business. The project connects billing, engagement, support, experiments and retention through one reproducible dataset. Analysts can move from a business signal to a customer's evidence, inspect a model explanation and record a review decision. The work demonstrates a full analytical workflow while keeping synthetic results and deployment limitations explicit.

## Questions to prepare
**Why synthetic data?** It allows controlled relationships, deliberate quality defects, randomized assignment and reproducible tests without using personal customer data. It also limits external validity: model scores and apparent improvements cannot be presented as real business results.

**How do you prevent leakage?** Features end at a month-end cutoff, labels occur in the next month, immature outcomes are excluded, and temporal splits leave non-overlapping label windows. Model and threshold selection use validation, not the final test. The same customer can recur across time because the task is future membership scoring.

**Why can a simple forecast win?** The scenario has only 30 monthly observations. Complexity is evaluated against persistence and seasonal naive using rolling origins. A baseline wins when it has lower selection error; the interface reports that outcome directly.

**Why is a churn score not uplift?** Churn estimates risk under observed conditions. Uplift estimates a treatment effect and needs suitable randomized data, sample size and evaluation. ADRYN reports the onboarding experiment and defers individualized treatment targeting.

**What does SHAP prove?** It attributes a model output relative to a background population. It explains the fitted model, not the causal reason a person cancels.

**What did data cleaning change?** Duplicate CRM keys can inflate joined invoice totals. The pipeline measures that overcount, quarantines duplicate projection rows and reconciles customer and monthly totals to the invoice ledger. Invalid email is set to null for source correction.

**Why is support classification accuracy high?** Labels and text come from a small template generator. Customer separation prevents same-customer leakage but does not remove template overlap. A real system would need broader human-labeled text and temporal/usefulness evaluation.

**What makes this a product rather than notebooks?** Shared definitions, coherent navigation, record-level evidence, saved review decisions, prediction parity, immutable published runs, provenance and automated application tests.

**What is not yet production-ready?** PostgreSQL integration and Docker execution need environment verification. Authentication, live ingestion, operational monitoring, backups and human model-promotion controls are still required for shared deployment.

## Resume statements that remain defensible
- Built a reproducible subscription analytics workspace connecting retention, demand forecasting, support NLP and randomized onboarding evaluation.
- Implemented time-based model evaluation, baseline comparisons, SHAP explanations and API-to-dashboard prediction consistency checks.
- Added ledger reconciliation, data-quality remediation, SQL persistence design and immutable analysis snapshots with traceable run metadata.

Only add numerical results from a named executed snapshot. Describe synthetic workload counts as demonstration scale, not customer impact or revenue saved.
