# Model and application operations

## Local runbook
Run `python -m adryn.cli run-pipeline` inside the project environment. A successful run publishes `outputs/current_run.json`. The referenced snapshot contains source SHA-256 hashes, seed, interpreter/library versions, feature order, split boundaries, chosen model, threshold, metrics and serialized models. The original feature data and model settings allow the result to be inspected without a tracking server.

The dashboard and API resolve the published snapshot. Inference validates numeric ranges, rejects unknown fields and rejects blank support text. Model loading uses trusted local artifacts only; pickle/joblib files from untrusted sources must not be loaded. `/health` loads both prediction artifacts, validates metadata and reports readiness plus the run ID. Missing or damaged publications produce controlled errors. API input and output parity is tested against current scored members.

## Failed run
An exception leaves the previously published snapshot selected. A `.building-<uuid>` directory may remain for diagnosis. It can be removed after reviewing the failure; do not remove a directory referenced by `current_run.json`. Raw and cleaned working data may reflect the attempted run, so downstream consumers must use the published snapshot.

Run only one analysis at a time, including CLI runs and dashboard sessions. Publication is atomic, but generation and cleaning still share working directories. Concurrent runs can mix inputs before publication. This requires a single-writer coordinator or isolated per-run inputs before concurrent use; it is recorded for architecture review, not redesigned in this pass. Keep the published run fixed while refreshing Power BI tables.

## PostgreSQL
Configure `ADRYN_DATABASE_URL` privately in `D:\ADRYN\.env`. `python -m adryn.cli verify-db` reads credentials only from this file, makes a read-only connection, checks schema object availability and checks whether the published run is loaded. The five-second connection timeout prevents an indefinite connection wait. Failure messages withhold connection details. `init-db` adds schema objects without dropping existing data. `load-db` writes a complete run in one transaction. Duplicate run IDs are a no-op. Run the SQL questions and reconcile invoice collections with `business_summary.json` after the first real connection succeeds. On 2026-10-01 the project `.env` was absent, so the user's database connection remains unverified; a running PostgreSQL service alone does not establish connectivity.

The dashboard reads published CSV files and the API loads published model files. PostgreSQL is an optional persistence destination, rather than a live dashboard data source. Changing that relationship would be an architecture decision for separate review.

All three database CLI commands now obtain the database URL from the same project `.env` with interpolation disabled; ambient database URLs cannot redirect initialization or loading. Write connections also have a five-second connection timeout. A business load requires all seven normalized source exports and rejects mixed run IDs and customer/invoice row-count mismatches before connecting. The SQL view definition returns zero collections for a group containing only failed invoices. The SQL change has not been applied or executed on the user's database because its connection is unconfigured.

## Retraining policy
The scenario is fixed; rerunning does not acquire new real observations. For a future live source, review input validity and freshness daily, input drift weekly and mature outcome performance monthly. Retrain only after enough new mature outcomes are available. Compare candidates with the same time-based holdouts, error-cost assumptions, calibration and subgroup coverage. Require a human promotion decision and record the candidate/champion run IDs. Keep the prior snapshot for rollback. No scheduler or automatic promotion has been enabled.

## Monitoring interpretation
Input drift is a review signal. Missing outcomes, changed product definitions, seasonal mix and a data defect can all resemble model deterioration. Confirm source lineage before changing a model. Track actual false positives/negatives after the label window matures. Do not infer retained revenue from review volume.

## Shared deployment
Local servers bind to loopback. Before exposing the product to other users, add authentication, authorization, TLS termination, a managed secrets store and a shared transactional review database. Define backups, retention, restore tests and incident ownership. Compose is a development packaging option; it is not evidence of production deployment. Docker is unavailable in the current machine environment, so container execution remains untested.
