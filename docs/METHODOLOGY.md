# Methodology and limitations

## Business simulation
A seeded NumPy generator models ADRYN Learning from April 2024 through September 2026. The cutoff is fixed, so a date change on the computer does not change the scenario. Plans cost USD 19, 39 and 79 monthly. Signup cohorts grow over time; customers pass through a funnel and may begin a subscription. Monthly engagement, payment failure and support interactions influence a programmed cancellation hazard. An onboarding treatment is randomized at signup and changes the early hazard.

These relationships are assumptions built into a simulation. Discovering them demonstrates analysis and validation mechanics, not new evidence about real learners.

## Data quality and value
Quality rules detect duplicate CRM IDs, invalid email, missing phone and high order amounts. Deduplication keeps the first identical projected record and quarantines repetitions. Invalid email becomes null pending source correction. The pipeline measures the revenue overcount that a naive join with duplicate CRM keys would create. Canonical table checks fail on duplicate/null primary keys, orphan customer references, invalid dates and non-positive prices.

Collected value is the sum of paid invoice amounts. MRR is the sum of monthly prices for subscriptions active at the cutoff, regardless of collections. They answer different questions and should not reconcile to one another.

## Segmentation and retention
RFM describes payment recency, paid invoice frequency and collected revenue using documented fixed buckets. K-means operates on standardized log-transformed RFM inputs and latest observed sessions. Four operational segments are retained for review capacity; silhouette and inertia for two through six clusters are diagnostics. Segment names rank monetary centroids; they do not establish causes or predict marketing response. Cancelled customers' latest activity can be historical.

Cohorts begin at the paid subscription start month. A member is retained at month end if the cancellation date is later or absent. Immature cohort cells are omitted. Funnel counts are distinct customers with recorded, nested events; recent trials are still immature.

## Churn model
Eligible observations are customer-months whose subscription remains active at the feature cutoff. The target is cancellation in the following calendar month. The September feature rows have no mature outcomes and are scoring-only.

Training labels end before February 2026. Validation cutoffs start in February and labels end before June. Test cutoffs start in June; only labels ending by September 30 are scored. The temporal gaps prevent labels from overlapping the next split's feature cutoff. Customers can recur across periods: this measures future behavior of a membership population, not transfer to unseen customers.

Candidates are a prevalence baseline, standardized logistic regression and random forest. Validation average precision selects the model. Validation-only threshold tuning minimizes illustrative costs of USD 3 per false-positive review and USD 39 per missed churn. All candidate test metrics share the selected operating threshold for comparison. Test results do not select the winner. The saved model remains the evaluated training fit; there is no silent refit on test data.

Reported metrics include average precision, ROC AUC, Brier score, precision/recall and error counts. Calibration bins and held-out permutation importance accompany them. SHAP values explain the selected model against sampled training background: logistic attributions use log odds and tree attributions use probability. Attributions are not causal explanations.

The 12-month value scenario assumes constant churn probability, 75% gross margin and no discounting. It is an assumption-driven planning scenario, not a validated lifetime-value forecast.

## Demand forecasting
The target is monthly learning sessions aggregated from customer activity. Candidates are last-month persistence, seasonal naive and ridge trend with annual sine/cosine terms. Four earlier rolling origins select by MAE across three-month horizons. July-September 2026 is a separate final holdout. MAE, WAPE and bias show error in operational terms. The final forecast refits the selected method through September.

Only 30 monthly observations exist. Residual bands use the 10th/90th percentiles of selection errors and are descriptive, not calibrated prediction intervals. Capacity changes are user-entered scenarios. No revenue saving is inferred from the forecast.

## Experimentation
Assignment is once per customer at signup. The primary outcome is paid retention at 60 days; the analysis includes non-converters and only mature outcomes. The support guardrail is tickets per assigned member in 60 days. Reported evidence includes assignment counts, sample-ratio mismatch, absolute/relative effect, approximate 95% Wald intervals and two-sided tests. The support comparison uses Welch's test and an approximate normal upper bound.

Planning uses a 50% baseline, a 5 percentage-point effect, 80% power and 5% two-sided significance. Rollout consideration requires adequate sample size, a retention lower bound above +3 points, no assignment-imbalance signal and a support upper bound below +0.2 tickets/member. Segment results are exploratory and unadjusted. Individual uplift modeling is deliberately deferred until the randomized sample can support it.

## Customer voice
TF-IDF unigrams/bigrams with logistic regression classify four support themes. Customers, rather than tickets, are split between train and test. The template vocabulary still overlaps, so high synthetic accuracy does not demonstrate real-language performance. Low-confidence cases require review. Theme counts, unique affected members and resolution hours connect text to service workflows.

Emerging-issue flags compare latest and previous monthly shares with a five-point effect threshold and a four-theme adjustment. Repeat tickets violate independence; these are descriptive investigation signals, not confirmed incident or causal findings. Real deployment requires human-labeled, temporally held-out text, a broader taxonomy and evaluation of routing usefulness.

## Preserved trust modules
PII detection currently scans column names. Consent screening maps granted/revoked/unknown to operational review states. Contract mismatches reflect injected projection errors. Isolation Forest on invoice amount can correctly flag zero anomalies when all amounts follow a small price catalogue. Order drift uses an exploratory median-date split.

The separate AI-review disagreement model evaluates generated support-review labels with a stratified split. Full-queue scores include training rows; only the held-out metrics estimate benchmark performance. Mirror, Shadow Reviewer, Failure Genome and Evidence Graph are rule summaries and explicit CSV relationships, not autonomous policy enforcement.

## Monitoring and claims
KS statistics compare churn-training inputs with the current scoring population. A 0.15 effect threshold and Bonferroni-adjusted test nominate review signals. Repeated customer observations limit formal inference. Drift is not an automatic retraining or deployment decision. All impact estimates, prices and intervention costs must remain labeled synthetic or assumed.
