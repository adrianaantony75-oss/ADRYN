# ADRYN Learning: business charter

ADRYN Learning is a fictional subscription platform for professional courses. Individual members and small teams buy monthly access. The internal ADRYN workspace helps employees review the same customer journey from signup through paid use, service issues and retention.

| Stakeholder | Daily question | Evidence | Decision supported |
|---|---|---|---|
| General manager | What changed in collections and engagement? | Invoice totals, activity trends and plan/region filters | Choose an investigation owner |
| Retention analyst | Which active members warrant review? | Validated churn scores, value exposure and customer history | Investigate payment, support or engagement issues |
| Product analyst | Where are people dropping out? | Nested funnel events and paid-start cohorts | Specify an onboarding hypothesis |
| Operations lead | How much learning demand should we plan for? | Baseline comparisons, rolling errors and capacity scenario | Review session capacity assumptions |
| Support lead | Which issues affect members? | Theme trends, affected customers and underlying tickets | Review service issues and routing |
| Experiment owner | Does guided onboarding improve retention? | Intention-to-treat effect, interval, power and guardrail | Continue, investigate, reject or consider rollout |
| Data/model owner | Can we trust these results? | Data contracts, remediation, temporal evaluation and provenance | Approve corrections or model review |

## Operating assumptions
The scenario covers April 2024 through September 2026. Currency is USD. Essential, Professional and Teams list prices are 19, 39 and 79 per month. The simplified scenario has no taxes, refunds, annual prepayments, upgrades or reactivations. Subscription cancellation occurs at a month end. Billing collection and recurring-revenue exposure are different measures.

The primary product outcome is retained paid membership at 60 days after signup. Engagement, support burden and payment health explain operational context. Scores nominate human investigations; they do not send messages, change access or offer discounts automatically.

## Decision discipline
An investigation should state the affected population, the evidence and its cutoff, the proposed next action and the uncertainty. Human decisions are recorded with a run ID. A model score is not a measured treatment effect. Revenue exposure is not an estimate of recoverable revenue. Real impact requires a valid intervention evaluation.
