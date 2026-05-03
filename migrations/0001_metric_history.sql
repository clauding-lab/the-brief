-- migrations/0001_metric_history.sql
-- Last-known metric values + provenance.

create table if not exists public.metric_history (
  metric_id    text        not null,
  as_of        date        not null,
  value        jsonb       not null,
  source       text        not null,
  ingested_at  timestamptz not null default now(),
  primary key (metric_id, as_of)
);

create index if not exists metric_history_lookup
  on public.metric_history (metric_id, as_of desc);

-- RLS: service key only. No anon / authenticated access.
alter table public.metric_history enable row level security;
