# Senior technical review

Date: 2026-10-01. Scope: the existing `D:\ADRYN` build following Sol's verification. Existing Python, virtual environment, generated snapshot and services were retained. No downloads, cache clearing, output deletion, environment recreation, database changes, Git commits or architectural rewrite occurred.

## Overall status

**Ready for a guided, local synthetic-data demonstration with one analysis writer at a time. Not ready for production or a claim of verified PostgreSQL/Power BI integration.** The preserved published run is `0c6ed7db-5c0d-4834-aefd-f931149d1ce7`. The API and dashboard are running on loopback ports 8000 and 8501. Predictions match the current saved artifacts.

No critical failure was found in the exercised single-user demonstration. The high-priority concurrency risk below remains an architecture review item. PostgreSQL connectivity remains blocked by the absent project `.env`, so SQL transaction/constraint behavior cannot be certified from this machine's current configuration.

## High-priority findings

### P1: simultaneous runs share mutable inputs (open; Astra review)

Evidence: `D:\ADRYN\src\adryn\reports\pipeline.py:26` creates a private output directory but copies settings with only `output_dir` changed. Generation at line 43 writes the shared raw directory; `D:\ADRYN\src\adryn\reports\business.py:20` reads that directory and writes shared processed files. Two dashboard sessions or a dashboard run overlapping a CLI run can interleave working data. An atomic output pointer does not protect those inputs, so a completed snapshot can contain mixed provenance.

This is a code-inspection finding, not a destructive race experiment against existing outputs. Safe operating constraint: one analysis process at a time. Before concurrency, Astra should choose a single-writer coordinator or immutable per-run inputs with coordinated publication. No concurrency architecture was introduced.

### P1: verification and writes could target different databases (fixed)

Sol's `verify-db` read the project `.env`, while `init-db` and `load-db` used general settings where an ambient database URL takes precedence. A regression with a fake ambient URL and no project `.env` proved that initialization reached its write callback. All three CLI commands now use the same project-file-only reader with interpolation disabled: `D:\ADRYN\src\adryn\cli.py:19`. Tests prove ambient credentials cannot redirect writes and literal file values are preserved. Database URL fields are omitted from settings representations, and validation errors hide raw settings inputs: `D:\ADRYN\src\adryn\settings.py:18`.

### P1: unrecognized consent bypassed review (fixed)

Null, blank and unexpected consent values mapped to a missing privacy state, then `requires_human_review=False`. Three regressions reproduced this. `D:\ADRYN\src\adryn\core\privacy.py:34` now maps unrecognized consent to `review`. This strengthens the screening flag; it does not turn column-name heuristics into a compliance enforcement system.

## Medium-priority findings

| Finding | Evidence and disposition |
| --- | --- |
| Incomplete business exports could be marked loaded | `D:\ADRYN\src\adryn\db\postgres.py:12`. The loader previously skipped absent business tables and recorded a run that later loads would treat as complete. Added preflight for all seven normalized business exports, run IDs and available customer/invoice counts before any connection. Tests cover incomplete and mixed-run inputs. Existing database rows were not modified or repaired. |
| Ingestion admitted invalid financial inputs and duplicate customer subscriptions | `D:\ADRYN\src\adryn\data\platform.py:279` and line 311. NaN/infinity passed a positive-amount comparison; distinct subscription IDs could still duplicate the customer relation, conflicting with SQL uniqueness and one-customer analytics. Regressions reproduced both. Validation now rejects them. The existing sources pass all 20 checks. |
| Non-finite API JSON returned HTTP 500 | `D:\ADRYN\src\adryn\api.py:24`. Validation rejected NaN/infinity internally but error serialization failed while echoing those values. A dedicated validation handler returns HTTP 422 and omits submitted input/context. Both TestClient and the restarted HTTP service passed the regressions. |
| API accepted metadata from another run | `D:\ADRYN\src\adryn\api.py:67`. A regression produced a successful prediction with metadata carrying another run ID. Metadata must now match the published summary and declared feature order; mismatches return HTTP 503. Trusted-local joblib loading remains an explicit assumption. |
| Valid clean data crashed downstream summaries | `D:\ADRYN\src\adryn\core\quality.py:91` and `D:\ADRYN\src\adryn\core\privacy.py:29`. Empty findings had no columns, so Mirror grouping raised a KeyError. Empty results now retain their schema; the clean/no-PII regression passes. |
| SQL collections could be NULL where CSV collections are zero | `D:\ADRYN\src\adryn\db\schema.sql:142`. A group with only failed invoices produces NULL from a filtered SUM. Added COALESCE and a PostgreSQL integration assertion. This SQL change is **not database-verified** because that integration test is skipped. The current generated run has zero such groups, so no current published metric was changed. |
| Power BI refresh can mix run IDs (open) | `D:\ADRYN\powerbi\LoadCurrentSnapshot.pq:5` resolves the manifest independently per imported table. A publication during refresh can combine dimensions/facts from different runs. The guide now requires a stable published run during refresh and checking imported run IDs. A refresh-wide pinned snapshot is integration work for Astra; no M-engine success is claimed. |
| PostgreSQL execution is unverified (open) | `verify-db` reports the absent `D:\ADRYN\.env` and does not connect. Parameterized SQL, transaction scopes, identifiers and relational constraints were inspected, but syntax/DDL migration behavior, idempotence, rollback, counts and query plans were not executed against the user's database. |

## Low-priority findings and limits

- Existing editable distribution metadata still reports version 0.1.0 while source/API/declaration report 0.2.0. It does not block the executed source build. Refreshing package metadata needs local build tooling; no software was downloaded or installed.
- The installed Starlette/httpx TestClient emits a deprecation warning. Tests pass. Dependency upgrades were deferred to preserve the existing environment.
- Power BI CSV column compatibility and the import/measure definitions were inspected. Types, relationships, measures, refresh and visuals have not been executed in Power BI Desktop. An actual PBIX remains outside the verified deliverable.
- Numeric/date/source-domain validation is stronger but is not a general ingestion contract for arbitrary external enterprise files. Real ingestion requires an explicit schema and quarantine policy. Duplicate CRM remediation currently keeps the first row; conflicting duplicates need a source-resolution policy.
- PII detection uses column-name patterns. It can miss sensitive free text or flag non-person name columns. Privacy flags are review signals; real access control and consent enforcement are not implemented.
- Model evaluation uses declared synthetic limitations: recurring members across temporal churn splits, small template families for voice, few forecast origins, assumed review costs, and approximate experiment intervals. AI-review queue scores include training rows; only held-out metrics represent benchmark evaluation. No real-world saved revenue, generalization or causal model impact was established.
- APIs and reviewer identity are unauthenticated local workflows. Shared deployment needs roles, authentication, TLS, request/resource limits, a shared review store and backup/restore tests. Joblib artifacts must remain trusted; metadata identity checks are not cryptographic verification of model binaries.
- No snapshot-wide cross-process write coordinator or schema migration framework exists. The database's latest-run view means latest loaded run, which need not equal the filesystem publication. Reconcile by explicit run ID when using both.

## Tests and verification actually executed

1. New regression cases were run before fixes. They reproduced ambient-credential writes, incomplete-load preflight absence, non-finite amounts, duplicate customer subscriptions, metadata identity mismatch, fail-open consent, empty-finding crashes and HTTP 500 responses for non-finite JSON.
2. Focused final suite: **21 passed**, covering senior-review regressions, configuration and API tests.
3. Full suite: **38 passed, 1 skipped, 1 warning in 42.43 seconds**. The skipped test is the explicitly configured PostgreSQL integration test, now including the zero-collection case. Full tests include temporary pipeline publication, business analysis, all 14 dashboard views, review persistence and model/API parity.
4. Ruff passed. `pip check` reported no broken requirements. `git diff --check` passed for tracked changes. Secret/model-output ignore rules were checked.
5. After restarting the existing local services, live churn and support-theme responses matched saved model outputs. Non-finite churn JSON and blank support text returned HTTP 422; validation errors did not echo submitted inputs. Streamlit health returned `ok`.
6. The existing 51 CSV exports passed loader preflight. The current canonical sources passed all 20 validation checks. The published run pointer was unchanged. No new production snapshot was generated.
7. Sol's recent browser visual checks were retained; UI styling was not changed, so no redundant visual redesign test was performed. Docker, GitHub Actions and Power BI Desktop execution were not claimed.

Evidence is also saved as `ADRYN_Senior_Review_Evidence.json` in the chat output folder. No database password was requested, displayed or read from an alternative source.

## Files changed in this review

| File | Change |
| --- | --- |
| `D:\ADRYN\src\adryn\settings.py` | Reduce accidental credential exposure in representations/errors |
| `D:\ADRYN\src\adryn\cli.py` | Same project `.env` reader for verification and writes; preflight before initialization |
| `D:\ADRYN\src\adryn\db\postgres.py` | Business export/run preflight and bounded connection attempts |
| `D:\ADRYN\src\adryn\db\schema.sql` | Zero collections for failed-only invoice groups; not applied to database |
| `D:\ADRYN\src\adryn\data\platform.py` | Reject non-finite amounts and multiple subscriptions per customer |
| `D:\ADRYN\src\adryn\api.py` | Safe validation response and model metadata contract |
| `D:\ADRYN\src\adryn\core\privacy.py` | Unknown consent requires review; stable empty finding schema |
| `D:\ADRYN\src\adryn\core\quality.py` | Stable empty finding schema |
| `D:\ADRYN\tests\test_senior_review.py` | 15 new regression cases |
| `D:\ADRYN\tests\test_api.py` | Valid metadata fixture for damaged-model tests |
| `D:\ADRYN\tests\test_postgres.py` | Failed-only month collection assertion; currently skipped |
| `D:\ADRYN\docs\OPERATIONS.md` | Single-writer constraint and updated database behavior |
| `D:\ADRYN\docs\POWER_BI.md` | Refresh consistency caveat |
| `D:\ADRYN\docs\VALIDATION.md` | Current review validation addendum |
| `D:\ADRYN\docs\SENIOR_REVIEW.md` | This review |

New ignored service logs were added in `D:\ADRYN\outputs`. Handoff reports/evidence were saved in the chat's output folder. Existing application code not listed above, generated analysis snapshots, Git history, caches and the virtual environment were preserved. Much of the prior build remains untracked in Git; this review did not stage, commit or publish it.

## Commands used

Run from `D:\ADRYN`, unless a full path is supplied:

```powershell
git status --short --branch
git diff --check
git check-ignore .env outputs/current_run.json outputs/snapshots/0c6ed7db-5c0d-4834-aefd-f931149d1ce7/models/churn.joblib
.\.venv\Scripts\python.exe -m adryn.cli verify-db
.\.venv\Scripts\python.exe -m pytest tests/test_senior_review.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_senior_review.py tests/test_configuration.py tests/test_api.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src app tests
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe 'C:\Users\adria\Documents\Codex\2026-09-30\referenced-chatgpt-conversation-this-is-an\work\verify_senior_review.py'
```

Read-only inspection used `Get-Content`, `rg`, and process/service inventory. Only processes positively identified as this repository's Streamlit/Uvicorn servers were restarted, using hidden `Start-Process` launches with the arguments below. No package installation or database initialization/load command was executed.

## Final run instructions

The services were left running. Dashboard: `http://127.0.0.1:8501/`. API documentation: `http://127.0.0.1:8000/docs`. To restart when stopped, use separate PowerShell windows:

```powershell
Set-Location D:\ADRYN
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py --server.port 8501
```

```powershell
Set-Location D:\ADRYN
.\.venv\Scripts\python.exe -m uvicorn adryn.api:app --host 127.0.0.1 --port 8000
```

After configuring the connection privately in `D:\ADRYN\.env`, verify without writing:

```powershell
Set-Location D:\ADRYN
.\.venv\Scripts\python.exe -m adryn.cli verify-db
```

Only after connectivity succeeds, intentionally initialize/load if required:

```powershell
.\.venv\Scripts\python.exe -m adryn.cli init-db
.\.venv\Scripts\python.exe -m adryn.cli load-db
.\.venv\Scripts\python.exe -m adryn.cli verify-db
```

No regeneration is needed for the current demonstration. To deliberately create another run, ensure no other analysis or Power BI refresh is active, then use `.\.venv\Scripts\python.exe -m adryn.cli run-pipeline`. Keep the synthetic-data and unverified-integration boundaries visible during the demonstration.
