# Local validation record

## Senior review follow-up

On 2026-10-01, the review added 15 regression cases. Final result: **38 passed, one PostgreSQL integration test skipped, one upstream test-client warning in 42.43 seconds**. Ruff and dependency consistency checks passed. See `SENIOR_REVIEW.md` for findings, changes and the conditional demonstration-readiness decision.

The restarted live API matched both saved prediction models and returned HTTP 422 for non-finite numeric JSON inputs without echoing submitted data. The preserved snapshot passed database-loader preflight across 51 CSVs and all 20 source-validation checks. The dashboard health endpoint returned `ok`; the full suite exercised all 14 views. No fresh visual redesign or Power BI engine execution was performed. The SQL zero-collections regression was added to the skipped integration test and remains unexecuted against PostgreSQL.

The prior verification record below is retained as historical evidence.

Date: 2026-10-01 (Asia/Calcutta). Platform: Windows, existing Python 3.13.15 virtual environment.

- Full suite: 23 tests passed, one PostgreSQL integration test skipped because no explicit test database URL was supplied (final run: 36.25 seconds).
- Application tests: all eight business views, all six preserved trust views, region filtering and saving a Customer 360 review passed in isolated test data.
- Existing-output check: all 14 views also loaded against the user's current published snapshot, without application exceptions or missing-artifact errors. The existing snapshot pointer was unchanged.
- All 51 top-level snapshot CSV tables were readable. Run IDs agreed across tables, summaries and model metadata. All seven canonical source SHA-256 hashes matched the saved metadata. Customer/invoice keys and references passed; paid invoice collections reconciled to Customer 360 monetary value and the business summary.
- Four snapshot JSON artifacts parsed successfully. Both Markdown reports were readable; the existing PowerPoint had a valid archive and four slides. Its slide design was not re-reviewed in this validation pass.
- Running FastAPI service: health readiness and published run ID matched, churn predictions matched saved queue scores, and support-theme class/probability matched the persisted model. Negative churn input, unknown fields and blank support text returned HTTP 422. OpenAPI routes were present.
- Running Streamlit health endpoint returned `ok`. Browser command-center metrics matched the existing snapshot.
- Existing dependency check: `pip check` reported no broken requirements. No software was downloaded or installed, no caches were cleared, and the existing virtual environment was retained.
- Ruff checks passed. Git whitespace check passed for tracked changes.
- Browser inspection: charcoal desktop layout at 1101 x 884 and mobile layout at 390 x 844. The mobile metric grid has two columns; no document horizontal overflow or visible application exception was detected. Charts and sidebar collapse were inspected. The temporary mobile viewport was reset.
- Error-path checks: broken publication manifests and damaged model files produce controlled unavailable responses. Readiness does not treat metadata alone as a usable model. Database verification refuses ambient credentials when the project `.env` is absent and sanitizes connection exceptions.
- The test client emits an upstream Starlette/httpx deprecation warning. It does not currently prevent test execution.

Published business run: `0c6ed7db-5c0d-4834-aefd-f931149d1ce7`. Synthetic cutoff: 2026-09-30. The run contains 1,800 canonical customers, 8,894 invoices and 488 active subscriptions. Paid invoice collections total USD 298,804. These are synthetic scenario totals, not real company impact.

## Not verified
PostgreSQL connectivity and transactional behavior on the user's server, GitHub Actions execution, Docker container execution, an actual Power BI Desktop report, authenticated shared deployment and browser accessibility across additional assistive technologies.

The PostgreSQL 18 Windows service was running, but `D:\ADRYN\.env` did not exist. The read-only verification command stopped with an explicit unverified result. No alternative credential sources were tried and no database password was requested or displayed. End-to-end PostgreSQL/API/dashboard persistence therefore remains unverified.

The source and API versions are 0.2.0. The existing editable installation still reports distribution metadata 0.1.0 from its earlier installation. Local setuptools build tooling is absent, so installation metadata was not refreshed under the no-download requirement. Source execution and runtime dependency checks passed; a fresh package/container installation was not tested.

No Git commit or push was made during this upgrade. Existing history and local project work were retained.
