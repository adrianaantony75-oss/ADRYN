# Data contracts

Canonical sources are CSVs under `data/raw/platform/`. Blanks represent missing values; the region code `NA` represents North America and must remain a string. IDs are strings, amounts are USD, and dates are ISO calendar dates. Every computed snapshot table carries `run_id`.

| Dataset | Primary key | Important fields | Relationship |
|---|---|---|---|
| customers | customer_id | full_name, email, phone, region, signup_date, consent_status, acquisition_channel, plan | Master membership record |
| subscriptions | subscription_id | customer_id, plan, monthly_price, start_date, cancelled_at | Zero/one subscription per customer |
| orders | order_id | customer_id, order_date, amount, payment_status, channel | Many invoices per subscriber |
| activity | customer_id + month | sessions, learning_minutes, days_since_activity, support_tickets, payment_failed, monthly_price, tenure_months | One observation per billed member/month |
| tickets | ticket_id | customer_id, created_at, text, theme, resolution_hours | Support interactions; theme is synthetic ground truth |
| experiment | customer_id | assigned_at, treatment, eligible_for_analysis, retained_60d, support_60d | One onboarding assignment at signup |
| events | event_id | customer_id, event_date, event_type | Nested acquisition funnel events |

Names use explicit Demo Member labels; emails use `example.test`. Text uses a small declared template vocabulary. There are no real customer records. AI review projections reference generated support tickets and customer IDs.

## Key analytical outputs
`customer_360` is one row/customer; `retention_queue` is one row/current active subscriber; `churn_features` is one row/eligible customer-month; `churn_predictions` contains held-out outcomes; `churn_explanations` is one row/customer/feature. Do not sum scores or probabilities.

`monthly_kpis` is one row/month/region/plan. `cohort_retention` is one row/paid-start cohort/age. `forecast_backtests` is one row/origin/model/horizon. `experiment_results` contains the overall result and exploratory region rows: do not sum those rows together. `voice_tickets` is one row/ticket. `quality_remediation` records rule actions and measured duplicate-join consequences.

## Validation boundaries
Primary keys, required references, positive amounts and chronological relationships fail the canonical run when violated. CRM projection defects are intentionally non-blocking findings. Cleaning records what changed and quarantines duplicate rows. Schema checks are specific to this scenario; this is not an arbitrary CSV ingestion product.
