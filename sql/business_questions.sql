-- Latest run only. Values are synthetic and denominated in USD.
-- 1. What changed in collections by region and plan?
with monthly as (
  select m.*,
    lag(collected_revenue) over (partition by region, plan order by month) as previous_month
  from adryn.monthly_collections m
  where run_id = (select run_id from adryn.latest_pipeline_runs)
)
select *, collected_revenue - previous_month as absolute_change,
  collected_revenue / nullif(previous_month, 0) - 1 as relative_change
from monthly order by month desc, region, plan;

-- 2. Which customers have the largest collected value? No duplicated joins.
select * from adryn.customer_collected_value
where run_id = (select run_id from adryn.latest_pipeline_runs)
order by collected_value desc;

-- 3. Where does the acquisition funnel lose members?
select event_type, count(distinct customer_id) as members
from adryn.funnel_events
where run_id = (select run_id from adryn.latest_pipeline_runs)
group by event_type;

-- 4. Is the onboarding experiment balanced and what are the observed rates?
select treatment, count(*) as assigned,
  avg(retained_60d::numeric) as retention_rate,
  avg(support_60d::numeric) as support_tickets_per_member
from adryn.onboarding_assignments
where eligible_for_analysis and run_id = (select run_id from adryn.latest_pipeline_runs)
group by treatment;

-- 5. Which support themes are affecting the most members each month?
select date_trunc('month', created_at)::date as month, predicted_theme,
  count(*) as tickets, count(distinct customer_id) as affected_members,
  avg(resolution_hours) as mean_resolution_hours
from adryn.support_tickets
where run_id = (select run_id from adryn.latest_pipeline_runs)
group by month, predicted_theme order by month desc, tickets desc;
