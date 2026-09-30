# ADRYN
## Customer decision intelligence for a subscription learning platform

ADRYN is an internal analytics workspace for **ADRYN Learning**, a fictional digital subscription business. It connects customer retention, learning demand, support intelligence, onboarding experiments, and data/model health through one customer and billing model.

**All business data is synthetic.** Financial totals come from generated invoices. Model metrics come from executed evaluations. This project demonstrates decision workflows and engineering; it does not claim measured impact on a real company.

### The working product
- Command center: current recurring revenue, collections, engagement and investigation queues.
- Customers and Customer 360: RFM, behavioral segments, billing history, support evidence, churn scores, SHAP explanations and a persistent review log.
- Growth: acquisition funnel and subscriber cohort retention.
- Demand planning: three-month session forecasts, rolling backtests, baseline comparison and a capacity scenario.
- Experiments: randomized onboarding, mature intention-to-treat outcomes, confidence intervals, power planning, guardrails and a decision.
- Customer voice: TF-IDF classification, issue trends, emerging issue signals and ticket evidence.
- Model health: temporal evaluation, calibration, importance, input drift and run provenance.
- Trust operations: quality remediation, privacy screening, CRM/ERP reconciliation and AI review evaluation.

### Run locally
Python 3.13 is the tested interpreter. PostgreSQL is optional for local analysis.

For a fresh checkout, run these commands in PowerShell with Python 3.13 installed:

```powershell
git clone https://github.com/adrianaantony75-oss/ADRYN.git
Set-Location ADRYN
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m adryn.cli run-pipeline
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py --server.port 8501
```

Generated data and model files are excluded from Git: the pipeline must run before opening the dashboard or calling prediction endpoints. No database or `.env` is needed for this synthetic local workflow. Fresh installation remains unverified; the current environment is tested. On macOS/Linux use `python3.13 -m venv .venv` and `.venv/bin/python` in place of the Windows commands.

Use the existing environment and generated outputs in this checkout:

```powershell
Set-Location D:\ADRYN
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py --server.port 8501
```

No environment recreation, dependency download or output deletion is needed to run the existing build. If the server is already running, open its URL instead of starting a second copy. To generate another reproducible snapshot intentionally, run `.\.venv\Scripts\python.exe -m adryn.cli run-pipeline`.

The existing Windows checkout already has its environment. Open http://127.0.0.1:8501/ when the server is running. The fixed analysis cutoff is **2026-09-30**; clicking Run analysis rebuilds the same synthetic scenario for the configured seed, not live business data.

Each successful run publishes a complete snapshot beneath `outputs/snapshots/<run-id>/`. `outputs/current_run.json` selects the published run. Old root-level exports from earlier versions are retained but are not the current analysis. Review decisions live separately in `outputs/review_history.sqlite`.

### Prediction service
```powershell
Set-Location D:\ADRYN
.\.venv\Scripts\python.exe -m uvicorn adryn.api:app --host 127.0.0.1 --port 8000
```
Run the API in a separate terminal. Interactive API documentation: http://127.0.0.1:8000/docs. Endpoints: `/health`, `/predict/churn`, `/predict/support-theme`. Predictions use the same persisted model as the dashboard. Health readiness checks both model artifacts and reports the published run ID. Missing or damaged artifacts return an unavailable response. The service is a local prototype; authentication and network controls are required before shared deployment.

### Database and containers
Create a local `.env` from `.env.example` only when no `.env` exists. Set `ADRYN_DATABASE_URL` privately on this machine; never commit it or paste credentials into chat. The read-only verification command uses credentials only from the project `.env`, has a five-second connection timeout and withholds connection details on failure.
```powershell
.\.venv\Scripts\python.exe -m adryn.cli verify-db
```
On 2026-10-01, `D:\ADRYN\.env` was absent. PostgreSQL connectivity and loading remain unverified. Once verification succeeds, the following commands create schema objects and load the selected snapshot:
```powershell
.\.venv\Scripts\python.exe -m adryn.cli init-db
.\.venv\Scripts\python.exe -m adryn.cli load-db
```
The loader appends normalized business tables and evidence in one transaction. Loading an existing run ID is a no-op. SQL questions are in `sql/business_questions.sql`.

Dockerfiles and Compose configuration are provided. With Docker installed, `docker compose up --build` exposes the workspace at port 8502 and API at port 8000, bound to localhost. Generate a local run first. Docker execution and the user's PostgreSQL connection are not yet verified.

### Verify
```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src app tests
```
Tests cover ledger reconciliation, customer relationships, temporal eligibility, churn boundaries, forecasting, experiments, review persistence, the business views and API prediction parity. CI configuration is supplied but has not been run on GitHub.

The publication verification on 2026-10-01 returned **38 passed, one PostgreSQL integration test skipped, one upstream test-client warning in 40.64 seconds**. Ruff passed. See [publication evidence](docs/PUBLICATION.md) for the exact scope and [earlier validation](docs/VALIDATION.md) for historical service checks. The integration test requires an explicitly designated test database; it is separate from the read-only `verify-db` command.

### Demonstration scope and limitations

The source defines eight business views and six trust views (14 total), two prediction endpoints and a health endpoint. The current local snapshot contains 51 CSV tables; that count is a snapshot inventory, not a promise for every version. All customers and business results are synthetic. This is a guided single-user local demonstration, not a production-ready SaaS or evidence of real business impact. Shared authentication, authorization, real-source ingestion, independent model validation and operational monitoring remain future work. PostgreSQL integration, Docker execution, GitHub CI and a Power BI Desktop report have not been verified here.

### Demo and portfolio

See the [screenshot and demo checklist](docs/screenshots/README.md), [CV and LinkedIn wording](docs/PORTFOLIO.md), [architecture](docs/ARCHITECTURE.md) and [SaaS roadmap](docs/ROADMAP.md). Screenshots are pending capture; no product images are fabricated. Project owner: [Adrian's GitHub profile](https://github.com/adrianaantony75-oss).

### Reading order
1. [Business context](docs/BUSINESS_CONTEXT.md) and [metric definitions](docs/KPI_DICTIONARY.md)
2. [Architecture and ER diagram](docs/ARCHITECTURE.md) and [data dictionary](docs/DATA_DICTIONARY.md)
3. [Methodology](docs/METHODOLOGY.md) and [model operations](docs/OPERATIONS.md)
4. [Power BI guide](docs/POWER_BI.md), [interview guide](docs/INTERVIEW_GUIDE.md), [delivery status](docs/ROADMAP.md)

Generated datasets, model artifacts, local reviews and credentials are ignored by Git. The preserved trust deck is narrower than the upgraded business workspace; the generated decision brief describes current business analysis.
