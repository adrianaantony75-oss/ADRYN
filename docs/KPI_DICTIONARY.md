# KPI and metric dictionary

All monetary measures use USD and all dates use the fixed synthetic snapshot. The dashboard exposes region and plan filters only where the computation respects them. Forecast, experiment and model-health views explicitly use the full population.

| Metric | Definition / denominator | Grain and source | Interpretation |
|---|---|---|---|
| Customers | Distinct customer IDs | Customer master | Includes trials and former members |
| Active subscribers | Subscription exists and has no cancellation by cutoff | Subscription | Current membership, excludes ended contracts |
| MRR | Sum of monthly price for active subscriptions | Subscription snapshot | Recurring price exposure, not cash collection |
| Collections | Sum amount where payment status is paid | Invoice / calendar month | Cash proxy; no accrual or refund modeling |
| Collected value | Sum paid invoices for one customer | Customer history | Observed cumulative value, not predicted CLV |
| Billed subscribers | Customer-month activity rows | Month, region, plan | Includes members cancelling at that month end |
| Failed payments | Sum payment-failed indicator | Customer-month | One billing attempt per month in this model |
| Sessions | Sum learning sessions | Customer-month | Synthetic session counts |
| RFM recency | Snapshot minus last paid invoice date | Customer | For never-paid customers, signup age is the fallback |
| RFM frequency | Count paid invoices | Customer | Full observed history |
| RFM monetary | Sum paid invoice amount | Customer | Full observed history |
| Cohort retention | Members not cancelled at month end / initial paid-start cohort | Cohort and age | Empty immature cells are not zero |
| Funnel count | Distinct customers with each recorded stage | Event | Signup, first lesson, trial complete, paid; events are nested |
| Churn probability | Predicted cancellation in the next calendar month | Active customer at cutoff | Conditional model score, synthetic benchmark |
| Monthly revenue exposure | Churn probability times monthly price | Active customer | Prioritization amount; not causal loss or recoverable revenue |
| 12-month value scenario | 0.75 * price * sum((1-p)^m, m=1..12) | Active customer | Constant risk, 75% margin, no discounting; assumptions only |
| Retention review count | Active scored members above validation-selected threshold | Snapshot | Review workload at assumed error costs |
| 60-day retention | Paid start occurred and cancellation is absent or >= signup + 60 days | Mature randomized assignment | Includes non-converters; fixed intention-to-treat denominator |
| Absolute experiment effect | Treatment retention minus control retention | Experiment | Percentage-point difference |
| Support guardrail | Tickets before signup + 60 days / assigned members | Arm | Includes members with zero tickets |
| Forecast MAE | Mean absolute forecast error | Backtest origin/horizon | Sessions per month |
| Forecast WAPE | Sum absolute error / sum actual sessions | Backtest split | Undefined when actual sum is zero |

R scores use <=30, <=60, <=120, <=365, >365 days with descending scores 5..1. F scores use 0, 1-2, 3-5, 6-11, >=12 invoices with ascending scores 1..5. M scores use 0, (0,100], (100,300], (300,800], >800 USD with ascending scores 1..5. Combined RFM is 100R + 10F + M, an ordinal label rather than a continuous utility score.
