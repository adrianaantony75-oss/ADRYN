# Screenshots and demo checklist

Capture the running application using only the synthetic scenario. Save readable PNG files here:

1. `01-command-center.png`: main metrics and navigation.
2. `02-customer-360.png`: billing, churn explanation and review workflow.
3. `03-demand-planning.png`: forecast and baseline comparison.
4. `04-api-docs.png`: `/docs` with the prediction routes and one successful synthetic request.
5. `05-tests.png`: latest pytest result, including the skipped test and warning.

Crop terminal prompts, personal paths, browser profiles and unrelated tabs. Never show credentials, `.env`, private customer records or tokens. Label all scenario data synthetic. After capture, add real relative image links to the README; do not add broken placeholders.

For a five-minute demo: explain the fictional subscription business; open Command center; investigate a synthetic customer in Customer 360; compare the demand forecast to its baseline; demonstrate a prediction through FastAPI `/docs`; finish with the test evidence and production limitations. Generate outputs first, then start Streamlit and FastAPI in separate terminals using the README. Do not present a forecast, model score or synthetic revenue as measured business impact.
