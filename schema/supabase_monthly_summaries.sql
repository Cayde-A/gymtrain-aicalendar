create table if not exists public.trainingos_monthly_summaries (
  user_id uuid not null references auth.users(id) on delete cascade,
  sync_month text not null check (sync_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  schema_version text not null,
  summary jsonb not null,
  uploaded_at timestamptz not null default now(),
  primary key (user_id, sync_month)
);

alter table public.trainingos_monthly_summaries enable row level security;

revoke all on table public.trainingos_monthly_summaries from anon, authenticated;
grant select, insert, update on table public.trainingos_monthly_summaries to authenticated;

create policy "trainingos users read own monthly summaries"
on public.trainingos_monthly_summaries
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "trainingos users insert own monthly summaries"
on public.trainingos_monthly_summaries
for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "trainingos users update own monthly summaries"
on public.trainingos_monthly_summaries
for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);
