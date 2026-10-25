-- Owner-approved ONE private Sol trial, <=USD0.37/two calls. Ordinary caps stay.
begin;
set local lock_timeout='10s';
set local statement_timeout='30s';
create table if not exists public.news_sol_test_permits (
  id text primary key,
  issued_at timestamptz not null default clock_timestamp(),
  expires_at timestamptz not null,
  closed_at timestamptz,
  maximum_micro_usd bigint not null check(maximum_micro_usd between 1 and 370000),
  manifest_hash text not null check(manifest_hash ~ '^[a-f0-9]{64}$'),
  writer_hash text not null check(writer_hash ~ '^[a-f0-9]{64}$'),
  writer_input_bound bigint not null check(writer_input_bound between 1 and 131072),
  review_input_bound bigint not null check(review_input_bound between 1 and 131072),
  approval_note text not null check(length(approval_note) between 30 and 1000),
  check(expires_at>issued_at and expires_at<=issued_at+interval '2 hours')
);
alter table public.news_sol_test_permits enable row level security;
revoke all on public.news_sol_test_permits from public,anon,authenticated,service_role;
grant select on public.news_sol_test_permits to service_role;
alter table public.news_ai_requests add column if not exists sol_test_id text references public.news_sol_test_permits(id);
create unique index if not exists news_sol_test_one_attempt on public.news_ai_requests(sol_test_id,stage) where sol_test_id is not null;

create or replace function public.reserve_news_sol_test_ai(
  permit_key text,manifest_digest text,request_key uuid,stage_key text,
  input_bound bigint,output_bound bigint,request_digest text
) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare cfg public.news_ai_config; permit public.news_sol_test_permits;
  amount bigint; reserved_test bigint; used_day bigint; used_month bigint;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into cfg from public.news_ai_config where id='production' for update;
  if not found or cfg.enabled or cfg.publication_enabled or cfg.model<>'gpt-6-sol'
    or cfg.daily_limit_micro_usd<>250000 or cfg.monthly_limit_micro_usd<>5000000
    or (now() at time zone 'UTC')::date>=least(cfg.pricing_valid_until,date '2026-11-21')
    or exists(select 1 from public.news_notice_release_config where enabled) then
    return jsonb_build_object('allowed',false,'reason','sol_test_requires_paused_unchanged_production'); end if;
  select * into permit from public.news_sol_test_permits where id=permit_key for update;
  if not found or permit.closed_at is not null or clock_timestamp()>=permit.expires_at
    or (permit.issued_at at time zone 'UTC')::date<>(now() at time zone 'UTC')::date
    or permit.manifest_hash is distinct from manifest_digest then
    return jsonb_build_object('allowed',false,'reason','sol_test_permit_inactive_or_wrong_manifest'); end if;
  if request_key is null or stage_key is null or stage_key not in ('ev_news_hybrid_launch_write','ev_news_hybrid_launch_review')
    or input_bound is null or input_bound not between 1 and 131072 or output_bound is distinct from 2500
    or request_digest is null or request_digest !~ '^[a-f0-9]{64}$' then
    return jsonb_build_object('allowed',false,'reason','sol_test_outside_contract'); end if;
  if exists(select 1 from public.news_ai_requests where id=request_key or (sol_test_id=permit_key and stage=stage_key)) then
    return jsonb_build_object('allowed',false,'reason','sol_test_attempt_consumed'); end if;
  if stage_key='ev_news_hybrid_launch_write' then
    if request_digest is distinct from permit.writer_hash or input_bound<>permit.writer_input_bound then
      return jsonb_build_object('allowed',false,'reason','sol_test_writer_changed'); end if;
  else
    if input_bound>permit.review_input_bound or not exists(select 1 from public.news_ai_requests
      where sol_test_id=permit_key and stage='ev_news_hybrid_launch_write'
      and settled_at is not null and provider_status='completed') then
      return jsonb_build_object('allowed',false,'reason','sol_test_review_requires_settled_writer'); end if;
  end if;
  if exists(select 1 from public.news_ai_requests where (settled_at is null and budget_closed_at is null)
    or provider_status='accounting_anomaly') then
    return jsonb_build_object('allowed',false,'reason','sol_test_unresolved_accounting'); end if;
  -- Same conservative verified standard short-context cache/output ceiling as 018.
  amount := input_bound*5+output_bound*10;
  select coalesce(sum(reserved_micro_usd),0) into reserved_test from public.news_ai_requests where sol_test_id=permit_key;
  if reserved_test+amount>permit.maximum_micro_usd then
    return jsonb_build_object('allowed',false,'reason','sol_test_total_reservations_exhausted'); end if;
  select coalesce(sum(charged_micro_usd) filter(where created_at>=date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'),0),
    coalesce(sum(charged_micro_usd),0) into used_day,used_month from public.news_ai_requests
    where created_at>=date_trunc('month',now() at time zone 'UTC') at time zone 'UTC';
  if used_day+amount>cfg.daily_limit_micro_usd+permit.maximum_micro_usd
    or used_month+amount>cfg.monthly_limit_micro_usd then
    return jsonb_build_object('allowed',false,'reason','sol_test_period_allowance_exhausted'); end if;
  insert into public.news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,charged_micro_usd,sol_test_id)
  values(request_key,stage_key,'gpt-6-sol',request_digest,input_bound,output_bound,amount,amount,permit_key);
  return jsonb_build_object('allowed',true,'reserved_micro_usd',amount);
end $$;

create or replace function public.close_news_sol_test(permit_key text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
begin
  perform pg_advisory_xact_lock(72716492);
  update public.news_sol_test_permits set closed_at=coalesce(closed_at,clock_timestamp()) where id=permit_key;
  return jsonb_build_object('closed',found);
end $$;
revoke all on function public.reserve_news_sol_test_ai(text,text,uuid,text,bigint,bigint,text),public.close_news_sol_test(text)
  from public,anon,authenticated;
grant execute on function public.reserve_news_sol_test_ai(text,text,uuid,text,bigint,bigint,text),public.close_news_sol_test(text)
  to service_role;
notify pgrst,'reload schema';
commit;
