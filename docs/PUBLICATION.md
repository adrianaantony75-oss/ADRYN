# Publication evidence — 2026-10-01

Repository: `adrianaantony75-oss/ADRYN`. GitHub's repository API reports it already public. Origin matches that repository; remote HEAD is the initial `.gitignore` commit `93318b8289b1024dcb079049c73d8008b7ffafaf` at inspection. No repository rename is needed.

## Verification executed for publication

- Existing Python environment: `python -m pytest -q` returned **38 passed, 1 skipped, 1 warning in 40.64s**.
- `ruff check src app tests`: **All checks passed**.
- Source inventory: eight entries in `adryn.product.PAGES`, six trust views in `app/streamlit_app.py`, two prediction POST routes and one GET health route in `src/adryn/api.py`.
- Current snapshot `0c6ed7db-5c0d-4834-aefd-f931149d1ce7`: 51 top-level CSV files. Its summary explicitly marks the data synthetic. These are inventory checks; no new live-service or browser validation was performed in this publication pass.
- PostgreSQL integration was skipped because no explicit test database URL was supplied. Docker, fresh installation, Power BI Desktop and GitHub Actions execution are not verified by these checks.

## Publication exclusions and security scope

Only `.gitignore` was previously tracked, so repository history contains no application data or credentials. The proposed file set consists of source, tests, documentation, SQL/Power BI text assets and configuration. Generated inputs/outputs, virtual environments, local reviews, logs, caches and private configuration are excluded. A common credential-pattern scan of publishable source found no matches; generic password fields and CI-only disposable PostgreSQL credentials require contextual review, not treatment as user secrets. Pattern scanning cannot guarantee that every possible secret is detected.

The application generates synthetic data; local datasets and model binaries will not be uploaded. API authentication is absent and endpoints are intended for localhost demonstration. Screenshot capture is pending. Historical validation records describe previous checks and must not be treated as newly executed evidence.

The final file manifest and exclusion checks are reviewed before commit/push. Publishing the implementation requires the user's approval of that final state.
