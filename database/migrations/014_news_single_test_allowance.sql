-- Owner-issued exceptions for individual private tests; ordinary caps are unchanged.
create table if not exists public.news_test_allowances (
  id text primary key,
  issued_at timestamptz not null default clock_timestamp(),
  expires_at timestamptz not null,
  closed_at timestamptz,
  maximum_micro_usd bigint not null check (maximum_micro_usd between 1 and 100000),
  maximum_requests integer not null check (maximum_requests between 1 and 3),
  approval_note text not null check (length(approval_note) >= 30),
  check (expires_at > issued_at and expires_at <= issued_at + interval '2 hours')
);
alter table public.news_test_allowances enable row level security;
revoke all on public.news_test_allowances from public,anon,authenticated,service_role;
grant select on public.news_test_allowances to service_role;
alter table public.news_ai_requests add column if not exists test_allowance_id text
  references public.news_test_allowances(id);
create index if not exists news_ai_requests_test_allowance on public.news_ai_requests(test_allowance_id);

create or replace function public.reserve_news_test_ai(
  allowance_key text, request_key uuid, stage_key text, model_key text,
  input_bound bigint, output_bound bigint, request_digest text
) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare cfg public.news_ai_config; permit public.news_test_allowances; amount bigint;
  used_test bigint; requests_test bigint; used_day bigint; used_month bigint;
  utc_day timestamptz; utc_month timestamptz;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into cfg from public.news_ai_config where id='production' for update;
  if not found or cfg.enabled or cfg.publication_enabled then
    return jsonb_build_object('allowed',false,'reason','private_test_requires_production_paused');
  end if;
  select * into permit from public.news_test_allowances where id=allowance_key for update;
  if not found or permit.closed_at is not null or clock_timestamp() >= permit.expires_at
    or (permit.issued_at at time zone 'UTC')::date <> (now() at time zone 'UTC')::date then
    return jsonb_build_object('allowed',false,'reason','private_test_allowance_inactive');
  end if;
  if (now() at time zone 'UTC')::date >= cfg.pricing_valid_until then
    return jsonb_build_object('allowed',false,'reason','news_pricing_expired');
  end if;
  if cfg.daily_limit_micro_usd <> 250000 or cfg.monthly_limit_micro_usd <> 5000000
    or model_key is distinct from cfg.model or request_key is null
    or input_bound is null or input_bound not between 1 and 131072
    or output_bound is null or output_bound not between 128 and 3000
    or request_digest is null or request_digest !~ '^[a-f0-9]{64}$'
    or stage_key is null or stage_key not in ('swedish_ev_article','ev_news_independent_audit','ev_news_block_repair') then
    return jsonb_build_object('allowed',false,'reason','private_test_request_outside_contract');
  end if;
  if exists(select 1 from public.news_ai_requests where id=request_key) then
    return jsonb_build_object('allowed',false,'reason','news_request_already_reserved');
  end if;
  if exists(select 1 from public.news_ai_requests where
    (settled_at is null and budget_closed_at is null) or provider_status='accounting_anomaly') then
    return jsonb_build_object('allowed',false,'reason','private_test_unresolved_accounting');
  end if;
  amount := (input_bound*3 + output_bound*18 + 3)/4;
  select coalesce(sum(charged_micro_usd),0),count(*) into used_test,requests_test
    from public.news_ai_requests where test_allowance_id=allowance_key;
  if used_test+amount > permit.maximum_micro_usd or requests_test >= permit.maximum_requests then
    return jsonb_build_object('allowed',false,'reason','private_test_allowance_exhausted');
  end if;
  utc_day := date_trunc('day',now() at time zone 'UTC') at time zone 'UTC';
  utc_month := date_trunc('month',now() at time zone 'UTC') at time zone 'UTC';
  select coalesce(sum(charged_micro_usd) filter(where created_at >= utc_day),0),coalesce(sum(charged_micro_usd),0)
    into used_day,used_month from public.news_ai_requests where created_at >= utc_month;
  if used_day+amount > cfg.daily_limit_micro_usd+permit.maximum_micro_usd
    or used_month+amount > cfg.monthly_limit_micro_usd+permit.maximum_micro_usd then
    return jsonb_build_object('allowed',false,'reason','private_test_period_allowance_exhausted');
  end if;
  insert into public.news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,
    reserved_micro_usd,charged_micro_usd,test_allowance_id)
  values(request_key,stage_key,model_key,request_digest,input_bound,output_bound,amount,amount,allowance_key);
  return jsonb_build_object('allowed',true,'request_id',request_key,'reserved_micro_usd',amount);
end $$;

create or replace function public.close_news_test_allowance(allowance_key text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
begin
  perform pg_advisory_xact_lock(72716492);
  update public.news_test_allowances set closed_at=coalesce(closed_at,clock_timestamp()) where id=allowance_key;
  return jsonb_build_object('closed',found);
end $$;
revoke all on function public.reserve_news_test_ai(text,uuid,text,text,bigint,bigint,text),
  public.close_news_test_allowance(text) from public,anon,authenticated;
grant execute on function public.reserve_news_test_ai(text,uuid,text,text,bigint,bigint,text),
  public.close_news_test_allowance(text) to service_role;
