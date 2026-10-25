-- Private owner-issued three-call GPT-6 Luna probe, WITHIN ordinary caps.
create table if not exists public.news_luna_test_permits (
  id text primary key,
  issued_at timestamptz not null default clock_timestamp(),
  expires_at timestamptz not null,
  closed_at timestamptz,
  maximum_micro_usd bigint not null check(maximum_micro_usd between 1 and 20000),
  manifest_hash text not null check(manifest_hash ~ '^[a-f0-9]{64}$'),
  approval_note text not null check(length(approval_note) between 30 and 1000),
  check(expires_at > issued_at and expires_at <= issued_at + interval '2 hours')
);
alter table public.news_luna_test_permits enable row level security;
revoke all on public.news_luna_test_permits from public,anon,authenticated,service_role;
grant select on public.news_luna_test_permits to service_role;
alter table public.news_ai_requests add column if not exists luna_test_id text references public.news_luna_test_permits(id);
alter table public.news_ai_requests add column if not exists luna_case text;
create unique index if not exists news_luna_one_attempt on public.news_ai_requests(luna_test_id,luna_case) where luna_test_id is not null;

create or replace function public.reserve_news_luna_ai(
  permit_key text,manifest_digest text,case_key text,request_key uuid,
  input_bound bigint,output_bound bigint,request_digest text
) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare cfg public.news_ai_config; permit public.news_luna_test_permits;
  amount bigint; used_test bigint; used_day bigint; used_month bigint;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into cfg from public.news_ai_config where id='production' for update;
  if not found or cfg.enabled or cfg.publication_enabled or cfg.model <> 'gpt-5.4-mini'
    or cfg.daily_limit_micro_usd <> 250000 or cfg.monthly_limit_micro_usd <> 5000000
    or (now() at time zone 'UTC')::date >= least(cfg.pricing_valid_until,date '2026-11-21') then
    return jsonb_build_object('allowed',false,'reason','luna_requires_unchanged_paused_production'); end if;
  select * into permit from public.news_luna_test_permits where id=permit_key for update;
  if not found or permit.closed_at is not null or clock_timestamp() >= permit.expires_at
    or (permit.issued_at at time zone 'UTC')::date <> (now() at time zone 'UTC')::date
    or permit.manifest_hash is distinct from manifest_digest then
    return jsonb_build_object('allowed',false,'reason','luna_permit_inactive_or_wrong_manifest'); end if;
  if case_key is null or case_key not in ('model','price','statistics') or request_key is null
    or input_bound is null or input_bound not between 1 and 60000
    or output_bound is null or output_bound <> 1200
    or request_digest is null or request_digest !~ '^[a-f0-9]{64}$' then
    return jsonb_build_object('allowed',false,'reason','luna_outside_contract'); end if;
  if exists(select 1 from public.news_ai_requests where id=request_key
    or (luna_test_id=permit_key and luna_case=case_key)) then
    return jsonb_build_object('allowed',false,'reason','luna_attempt_already_consumed'); end if;
  if exists(select 1 from public.news_ai_requests where (settled_at is null and budget_closed_at is null)
    or provider_status='accounting_anomaly') then
    return jsonb_build_object('allowed',false,'reason','luna_unresolved_accounting'); end if;
  -- Reserve WORST verified input tariff (12h writes, USD0.25/M), not a guessed cache discount.
  -- Actual standard input/cached/30m-write/12h-write/output: 0.10/0.01/0.125/0.25/0.50 USD/M.
  amount := (input_bound + 2*output_bound + 3)/4;
  select coalesce(sum(charged_micro_usd),0) into used_test from public.news_ai_requests where luna_test_id=permit_key;
  select coalesce(sum(charged_micro_usd) filter(where created_at >= date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'),0),
    coalesce(sum(charged_micro_usd),0) into used_day,used_month from public.news_ai_requests
    where created_at >= date_trunc('month',now() at time zone 'UTC') at time zone 'UTC';
  if used_test+amount > permit.maximum_micro_usd or used_day+amount > cfg.daily_limit_micro_usd
    or used_month+amount > cfg.monthly_limit_micro_usd then
    return jsonb_build_object('allowed',false,'reason','luna_ordinary_budget_exhausted'); end if;
  insert into public.news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,
    reserved_micro_usd,charged_micro_usd,luna_test_id,luna_case)
  values(request_key,'private_notice_probe','gpt-6-luna',request_digest,input_bound,output_bound,amount,amount,permit_key,case_key);
  return jsonb_build_object('allowed',true,'reserved_micro_usd',amount);
end $$;

create or replace function public.settle_news_luna_ai(request_key uuid,response_body jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare req public.news_ai_requests; u jsonb; details jsonb; write_details jsonb;
  inp bigint; outp bigint; cached bigint; written bigint; w30 bigint; w12 bigint; ordinary bigint; amount bigint;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into req from public.news_ai_requests where id=request_key for update;
  if not found or req.luna_test_id is null then return jsonb_build_object('settled',false,'reason','luna_reservation_missing'); end if;
  if response_body->>'service_tier' is distinct from 'default'
    or coalesce(response_body->>'model','') !~ '^gpt-6-luna(-[0-9]{4}-[0-9]{2}-[0-9]{2})?$'
    or pg_column_size(response_body)>250000 then
    update public.news_luna_test_permits set closed_at=coalesce(closed_at,clock_timestamp()) where id=req.luna_test_id;
    return jsonb_build_object('settled',false,'reason','luna_unexpected_provider_contract'); end if;
  u := response_body->'usage'; details := u->'input_tokens_details'; write_details := details->'cache_write_tokens_details';
  if coalesce(u->>'input_tokens','') !~ '^[0-9]{1,7}$' or coalesce(u->>'output_tokens','') !~ '^[0-9]{1,7}$'
    or coalesce(u->>'total_tokens','') !~ '^[0-9]{1,7}$'
    or coalesce(details->>'cached_tokens','') !~ '^[0-9]{1,7}$'
    or coalesce(details->>'cache_write_tokens','') !~ '^[0-9]{1,7}$' then
    return jsonb_build_object('settled',false,'reason','luna_unknown_usage_hold_retained'); end if;
  inp := (u->>'input_tokens')::bigint; outp := (u->>'output_tokens')::bigint;
  cached := (details->>'cached_tokens')::bigint; written := (details->>'cache_write_tokens')::bigint;
  w30 := 0; w12 := 0;
  if written > 0 or write_details is not null and write_details <> 'null'::jsonb then
    if coalesce(write_details->>'ttl_30m_tokens','') !~ '^[0-9]{1,7}$'
      or coalesce(write_details->>'ttl_12h_tokens','') !~ '^[0-9]{1,7}$' then
      return jsonb_build_object('settled',false,'reason','luna_unknown_cache_write_lifetime'); end if;
    w30 := (write_details->>'ttl_30m_tokens')::bigint; w12 := (write_details->>'ttl_12h_tokens')::bigint;
  end if;
  ordinary := inp-cached-written;
  if ordinary < 0 or w30+w12 <> written or inp+outp <> (u->>'total_tokens')::bigint then
    return jsonb_build_object('settled',false,'reason','luna_inconsistent_usage_hold_retained'); end if;
  amount := (ordinary*100+cached*10+w30*125+w12*250+outp*500+999)/1000;
  if req.settled_at is not null then
    return jsonb_build_object('settled',req.provider_status<>'accounting_anomaly' and req.input_tokens=inp
      and req.output_tokens=outp and req.response_payload=response_body,'reason','luna_already_settled'); end if;
  if inp>req.input_bound or outp>req.output_bound or amount>req.reserved_micro_usd then
    update public.news_ai_requests set charged_micro_usd=greatest(amount,reserved_micro_usd),input_tokens=inp,
      output_tokens=outp,settled_at=clock_timestamp(),provider_status='accounting_anomaly',response_payload=response_body where id=request_key;
    update public.news_luna_test_permits set closed_at=coalesce(closed_at,clock_timestamp()) where id=req.luna_test_id;
    return jsonb_build_object('settled',false,'reason','luna_accounting_halted'); end if;
  update public.news_ai_requests set charged_micro_usd=amount,input_tokens=inp,output_tokens=outp,
    settled_at=clock_timestamp(),provider_status=coalesce(response_body->>'status','unknown'),response_payload=response_body where id=request_key;
  return jsonb_build_object('settled',true,'charged_micro_usd',amount);
end $$;

create or replace function public.close_news_luna_test(permit_key text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
begin
  perform pg_advisory_xact_lock(72716492);
  update public.news_luna_test_permits set closed_at=coalesce(closed_at,clock_timestamp()) where id=permit_key;
  return jsonb_build_object('closed',found);
end $$;
revoke all on function public.reserve_news_luna_ai(text,text,text,uuid,bigint,bigint,text),
  public.settle_news_luna_ai(uuid,jsonb),public.close_news_luna_test(text) from public,anon,authenticated;
grant execute on function public.reserve_news_luna_ai(text,text,text,uuid,bigint,bigint,text),
  public.settle_news_luna_ai(uuid,jsonb),public.close_news_luna_test(text) to service_role;
