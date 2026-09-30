# Power BI integration

The Streamlit workspace is the delivered interactive product. A Power BI Desktop PBIX has not yet been built or verified.

## Import
Create a text parameter named OutputRoot containing the absolute project output directory. Import powerbi/LoadCurrentSnapshot.pq as a function named LoadCurrentSnapshot. Call it for each CSV, for example LoadCurrentSnapshot("customer_360"). The function resolves outputs/current_run.json so a refresh uses the published run.

Import customer_360, monthly_kpis, subscription_orders, subscription_activity, voice_tickets, cohort_retention, demand_history, demand_forecast, forecast_comparison, experiment_results and quality_remediation. Explicitly assign numeric, date and boolean types. Preserve region NA as text.

## Relationships
Use customer_360 as a one-row-per-customer dimension for orders, activity and tickets, joined by customer_id. Each import must resolve the same run_id. The monthly_kpis, cohort and experiment aggregates already contain denominators; keep them separate or use appropriate shared dimensions. Do not join customer rows to aggregate tables in a way that multiplies revenue. Use single-direction filters.

The current import function resolves the manifest separately for each table. Do not run analysis or publish a new snapshot during a Power BI refresh. Check that imported run IDs agree before using measures. A refresh-wide pinned snapshot requires separate integration work; the present function does not guarantee atomic refresh across tables.

Measures are provided in powerbi/Measures.dax. They are definitions to add individually after setting types, not a standalone runnable script. Compare Collections and Collected Customer Value to business_summary.json before publishing.

## Suggested report pages
1. Command center: collections trend, MRR, active members and review workload.
2. Customer investigation: retention queue and customer drill-through with billing and support.
3. Growth: nested funnel and cohort retention matrix.
4. Demand: actual sessions, three-month forecast and final holdout errors.
5. Experiment: arm sizes, absolute effect/interval, power and support guardrail.
6. Service and trust: support issues, affected members and quality remediation.

Keep snapshot labels and synthetic-data disclosure visible. Do not sum cohort percentages or experiment rows. MRR and collections measure different things. Existing powerbi_* CSVs retain the original trust reporting model inside each snapshot.

## Verification status
Power Query and DAX import assets are supplied. Desktop refresh, relationships, calculated measures, visual interactions, accessibility and a PBIX file still require verification in Power BI.
