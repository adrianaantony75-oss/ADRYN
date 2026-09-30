create schema if not exists adryn;

create table if not exists adryn.pipeline_runs (
    run_id uuid primary key,
    started_at timestamptz not null default now(),
    source_seed integer not null,
    quality_findings integer not null,
    pii_findings integer not null,
    reconciliation_reviews integer not null,
    ai_reviews integer not null
);

create table if not exists adryn.quality_findings (
    finding_id bigint generated always as identity primary key,
    run_id uuid not null references adryn.pipeline_runs(run_id),
    rule_id text not null,
    entity_id text not null,
    severity text not null,
    finding text not null,
    evidence jsonb not null default '{}'::jsonb
);

alter table adryn.quality_findings
    add column if not exists evidence jsonb not null default '{}'::jsonb;

create table if not exists adryn.evidence_edges (
    edge_id bigint generated always as identity primary key,
    run_id uuid not null references adryn.pipeline_runs(run_id),
    source_node text not null,
    relationship text not null,
    target_node text not null,
    evidence_type text not null,
    weight integer not null
);

create table if not exists adryn.result_rows (
    run_id uuid not null references adryn.pipeline_runs(run_id),
    dataset_name text not null,
    row_number integer not null,
    payload jsonb not null,
    primary key (run_id, dataset_name, row_number)
);

create index if not exists result_rows_dataset_idx
    on adryn.result_rows (dataset_name, run_id);
create index if not exists evidence_edges_type_idx
    on adryn.evidence_edges (run_id, evidence_type);

create or replace view adryn.latest_pipeline_runs as
select * from adryn.pipeline_runs
order by started_at desc, run_id desc
limit 1;

create or replace view adryn.latest_quality_findings as
select f.* from adryn.quality_findings f
where f.run_id = (select run_id from adryn.pipeline_runs order by started_at desc, run_id desc limit 1);

create table if not exists adryn.customers (
    run_id uuid not null references adryn.pipeline_runs(run_id),
    customer_id text not null,
    region text not null,
    plan text not null,
    signup_date date not null,
    acquisition_channel text not null,
    consent_status text not null,
    primary key (run_id, customer_id)
);
create table if not exists adryn.subscriptions (
    run_id uuid not null,
    subscription_id text not null,
    customer_id text not null,
    plan text not null,
    monthly_price numeric(12,2) not null check (monthly_price > 0),
    start_date date not null,
    cancelled_at date,
    primary key (run_id, subscription_id),
    unique (run_id, customer_id),
    foreign key (run_id, customer_id) references adryn.customers(run_id, customer_id),
    check (cancelled_at is null or cancelled_at >= start_date)
);
create table if not exists adryn.invoices (
    run_id uuid not null,
    order_id text not null,
    customer_id text not null,
    order_date date not null,
    amount numeric(12,2) not null check (amount > 0),
    payment_status text not null check (payment_status in ('paid', 'failed', 'pending')),
    primary key (run_id, order_id),
    foreign key (run_id, customer_id) references adryn.customers(run_id, customer_id)
);
create table if not exists adryn.monthly_activity (
    run_id uuid not null,
    customer_id text not null,
    month date not null,
    sessions integer not null check (sessions >= 0),
    learning_minutes integer not null check (learning_minutes >= 0),
    days_since_activity integer not null check (days_since_activity >= 0),
    support_tickets integer not null check (support_tickets >= 0),
    payment_failed integer not null check (payment_failed in (0, 1)),
    monthly_price numeric(12,2) not null,
    tenure_months integer not null,
    primary key (run_id, customer_id, month),
    foreign key (run_id, customer_id) references adryn.customers(run_id, customer_id)
);
create table if not exists adryn.support_tickets (
    run_id uuid not null,
    ticket_id text not null,
    customer_id text not null,
    created_at date not null,
    text text not null,
    predicted_theme text not null,
    confidence double precision not null check (confidence between 0 and 1),
    resolution_hours double precision not null check (resolution_hours >= 0),
    primary key (run_id, ticket_id),
    foreign key (run_id, customer_id) references adryn.customers(run_id, customer_id)
);
create table if not exists adryn.onboarding_assignments (
    run_id uuid not null,
    customer_id text not null,
    assigned_at date not null,
    treatment integer not null check (treatment in (0, 1)),
    eligible_for_analysis boolean not null,
    retained_60d integer not null check (retained_60d in (0, 1)),
    support_60d integer not null check (support_60d >= 0),
    primary key (run_id, customer_id),
    foreign key (run_id, customer_id) references adryn.customers(run_id, customer_id)
);
create table if not exists adryn.funnel_events (
    run_id uuid not null,
    event_id text not null,
    customer_id text not null,
    event_date date not null,
    event_type text not null,
    primary key (run_id, event_id),
    foreign key (run_id, customer_id) references adryn.customers(run_id, customer_id)
);
create index if not exists invoice_customer_date on adryn.invoices (run_id, customer_id, order_date);
create index if not exists activity_month on adryn.monthly_activity (run_id, month);

create or replace view adryn.monthly_collections as
select i.run_id, date_trunc('month', i.order_date)::date as month, c.region, c.plan,
       coalesce(sum(i.amount) filter (where i.payment_status = 'paid'), 0) as collected_revenue,
       count(*) filter (where i.payment_status = 'failed') as failed_payments,
       count(distinct i.customer_id) as billed_subscribers
from adryn.invoices i join adryn.customers c using (run_id, customer_id)
group by i.run_id, date_trunc('month', i.order_date)::date, c.region, c.plan;

create or replace view adryn.customer_collected_value as
select c.run_id, c.customer_id, c.region, c.plan,
       coalesce(sum(i.amount) filter (where i.payment_status = 'paid'), 0) as collected_value,
       count(i.order_id) filter (where i.payment_status = 'paid') as paid_invoices
from adryn.customers c left join adryn.invoices i using (run_id, customer_id)
group by c.run_id, c.customer_id, c.region, c.plan;

