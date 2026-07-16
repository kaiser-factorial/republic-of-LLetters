-- Republic of LLetters: hit counter with sampling
-- Every 3rd visit increments the count in Supabase.
-- localStorage tracks the throttle client-side.

begin;

create table if not exists public.page_visits (
  page text primary key,
  visit_count integer not null default 0,
  last_visit timestamptz not null default now(),
  constraint page_visits_page_length check (char_length(page) between 1 and 500),
  constraint page_visits_count_positive check (visit_count >= 0)
);

alter table public.page_visits enable row level security;

-- Insert the initial row if it does not exist
insert into public.page_visits (page, visit_count, last_visit)
values ('total', 0, now())
on conflict (page) do nothing;

-- Remove any prior hit-counter policies
do $$
declare
  policy_record record;
begin
  for policy_record in
    select schemaname, tablename, policyname
    from pg_policies
    where schemaname = 'public' and tablename = 'page_visits'
  loop
    execute format(
      'drop policy if exists %I on %I.%I',
      policy_record.policyname,
      policy_record.schemaname,
      policy_record.tablename
    );
  end loop;
end
$$;

revoke all on table public.page_visits from public, anon, authenticated;
grant select on table public.page_visits to anon, authenticated;
grant update (visit_count, last_visit) on table public.page_visits to anon, authenticated;

-- Anyone can read the visit counts
create policy "Visitors can read visit counts"
on public.page_visits
for select
to anon, authenticated
using (true);

-- Anyone can increment the visit count (one row via upsert)
create policy "Visitors can increment visit counts"
on public.page_visits
for update
to anon, authenticated
using (page = 'total')
with check (page = 'total' and visit_count >= 0);

commit;
