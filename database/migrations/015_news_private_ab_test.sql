-- Owner-issued A/B experiments WITHIN ordinary caps, never an extra allowance.
create table if not exists public.news_ab_test_permits (
  id text primary key,
  issued_at timestamptz not null default clock_timestamp(),
  expires_at timestamptz not null,
  closed_at timestamptz,
  maximum_micro_usd bigint not null check (maximum_micro_usd between 1 and 200000),
  manifest_hash text not null check (manifest_hash ~ '^[a-f0-9]{64}$'),
  approval_note text not null check (length(approval_note) between 30 and 1000),
  check (expires_at > issued_at and expires_at <= issued_at + interval '2 hours')
);
alter table public.news_ab_test_permits enable row level security;
revoke all on public.news_ab_test_permits from public,anon,authenticated,service_role;
grant select on public.news_ab_test_permits to service_role;
alter table public.news_ai_requests add column if not exists ab_test_id text references public.news_ab_test_permits(id);
alter table public.news_ai_requests add column if not exists ab_cell_key text;
create unique index if not exists news_ab_one_attempt_per_stage
  on public.news_ai_requests(ab_test_id,ab_cell_key,stage) where ab_test_id is not null;

create or replace function public.reserve_news_ab_ai(
  permit_key text, manifest_digest text, cell_key text, request_key uuid, stage_key text,
  model_key text, input_bound bigint, output_bound bigint, request_digest text
) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare cfg public.news_ai_config; permit public.news_ab_test_permits; amount bigint;
  used_test bigint; used_day bigint; used_month bigint; required_model text;
  utc_day timestamptz; utc_month timestamptz;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into cfg from public.news_ai_config where id='production' for update;
  if not found or cfg.enabled or cfg.publication_enabled or cfg.model <> 'gpt-5.4-mini'
    or cfg.daily_limit_micro_usd <> 250000 or cfg.monthly_limit_micro_usd <> 5000000 then
    return jsonb_build_object('allowed',false,'reason','ab_requires_paused_unchanged_production');
  end if;
  select * into permit from public.news_ab_test_permits where id=permit_key for update;
  if not found or permit.closed_at is not null or clock_timestamp() >= permit.expires_at
    or (permit.issued_at at time zone 'UTC')::date <> (now() at time zone 'UTC')::date
    or permit.manifest_hash is distinct from manifest_digest then
    return jsonb_build_object('allowed',false,'reason','ab_permit_inactive_or_manifest_changed');
  end if;
  if (now() at time zone 'UTC')::date >= least(cfg.pricing_valid_until,date '2026-11-21') then
    return jsonb_build_object('allowed',false,'reason','ab_pricing_expired');
  end if;
  if cell_key is null or cell_key !~ '^(model|price|statistics)-(mini|full)$'
    or stage_key is null or stage_key not in ('ev_news_facts','swedish_ev_article','ev_news_independent_audit')
    or request_key is null or input_bound is null or input_bound not between 1 and 131072
    or output_bound is null or output_bound not between 128 and 3000
    or request_digest is null or request_digest !~ '^[a-f0-9]{64}$' then
    return jsonb_build_object('allowed',false,'reason','ab_request_outside_contract');
  end if;
  -- A common mini reviewer sees neither the candidate model nor cell label.
  required_model := case when stage_key='ev_news_independent_audit' or cell_key like '%-mini'
    then 'gpt-5.4-mini' else 'gpt-5.4' end;
  if model_key is distinct from required_model then
    return jsonb_build_object('allowed',false,'reason','ab_wrong_model_for_cell_stage');
  end if;
  if exists(select 1 from public.news_ai_requests where id=request_key
    or (ab_test_id=permit_key and ab_cell_key=cell_key and stage=stage_key)) then
    return jsonb_build_object('allowed',false,'reason','ab_attempt_already_consumed');
  end if;
  if exists(select 1 from public.news_ai_requests where
    (settled_at is null and budget_closed_at is null) or provider_status='accounting_anomaly') then
    return jsonb_build_object('allowed',false,'reason','ab_unresolved_accounting');
  end if;
  -- Standard-tier micro-USD: mini 0.75/4.50, full 2.50/15.00 per M tokens.
  amount := case when model_key='gpt-5.4-mini' then (input_bound*3+output_bound*18+3)/4
                 else (input_bound*5+output_bound*30+1)/2 end;
  select coalesce(sum(charged_micro_usd),0) into used_test from public.news_ai_requests where ab_test_id=permit_key;
  utc_day := date_trunc('day',now() at time zone 'UTC') at time zone 'UTC';
  utc_month := date_trunc('month',now() at time zone 'UTC') at time zone 'UTC';
  select coalesce(sum(charged_micro_usd) filter(where created_at >= utc_day),0),coalesce(sum(charged_micro_usd),0)
    into used_day,used_month from public.news_ai_requests where created_at >= utc_month;
  if used_test+amount > permit.maximum_micro_usd or used_day+amount > cfg.daily_limit_micro_usd
    or used_month+amount > cfg.monthly_limit_micro_usd then
    return jsonb_build_object('allowed',false,'reason','ab_ordinary_budget_exhausted');
  end if;
  insert into public.news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,
    reserved_micro_usd,charged_micro_usd,ab_test_id,ab_cell_key)
  values(request_key,stage_key,model_key,request_digest,input_bound,output_bound,amount,amount,permit_key,cell_key);
  return jsonb_build_object('allowed',true,'request_id',request_key,'reserved_micro_usd',amount);
end $$;

create or replace function public.settle_news_ab_ai(
  request_key uuid, used_input bigint, used_output bigint, response_body jsonb
) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare req public.news_ai_requests; amount bigint; model_pattern text;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into req from public.news_ai_requests where id=request_key for update;
  if not found or req.ab_test_id is null then
    return jsonb_build_object('settled',false,'reason','ab_reservation_missing');
  end if;
  model_pattern := case when req.model='gpt-5.4-mini' then '^gpt-5\.4-mini(-[0-9]{4}-[0-9]{2}-[0-9]{2})?$'
    when req.model='gpt-5.4' then '^gpt-5\.4(-[0-9]{4}-[0-9]{2}-[0-9]{2})?$' else '$^' end;
  if response_body->>'service_tier' is distinct from 'default'
    or coalesce(response_body->>'model','') !~ model_pattern then
    update public.news_ab_test_permits set closed_at=coalesce(closed_at,clock_timestamp()) where id=req.ab_test_id;
    return jsonb_build_object('settled',false,'reason','ab_unexpected_provider_pricing_halted');
  end if;
  if used_input is null or used_output is null or used_input < 0 or used_output < 0
    or used_input > 1000000 or used_output > 1000000 or response_body is null or pg_column_size(response_body)>250000
    or (response_body->'usage'->>'input_tokens') is distinct from used_input::text
    or (response_body->'usage'->>'output_tokens') is distinct from used_output::text then
    return jsonb_build_object('settled',false,'reason','ab_unknown_usage_reservation_retained');
  end if;
  if req.settled_at is not null then
    return jsonb_build_object('settled',req.provider_status <> 'accounting_anomaly'
      and req.input_tokens=used_input and req.output_tokens=used_output,'reason','ab_already_settled');
  end if;
  amount := case when req.model='gpt-5.4-mini' then (used_input*3+used_output*18+3)/4
    else (used_input*5+used_output*30+1)/2 end;
  if used_input>req.input_bound or used_output>req.output_bound or amount>req.reserved_micro_usd then
    update public.news_ai_requests set charged_micro_usd=greatest(amount,reserved_micro_usd),input_tokens=used_input,
      output_tokens=used_output,settled_at=clock_timestamp(),provider_status='accounting_anomaly',response_payload=response_body where id=request_key;
    update public.news_ab_test_permits set closed_at=coalesce(closed_at,clock_timestamp()) where id=req.ab_test_id;
    return jsonb_build_object('settled',false,'reason','ab_accounting_halted');
  end if;
  update public.news_ai_requests set charged_micro_usd=amount,input_tokens=used_input,output_tokens=used_output,
    settled_at=clock_timestamp(),provider_status=coalesce(response_body->>'status','unknown'),response_payload=response_body where id=request_key;
  return jsonb_build_object('settled',true,'charged_micro_usd',amount);
end $$;

create or replace function public.close_news_ab_test(permit_key text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
begin
  perform pg_advisory_xact_lock(72716492);
  update public.news_ab_test_permits set closed_at=coalesce(closed_at,clock_timestamp()) where id=permit_key;
  return jsonb_build_object('closed',found);
end $$;
revoke all on function public.reserve_news_ab_ai(text,text,text,uuid,text,text,bigint,bigint,text),
  public.settle_news_ab_ai(uuid,bigint,bigint,jsonb), public.close_news_ab_test(text) from public,anon,authenticated;
grant execute on function public.reserve_news_ab_ai(text,text,text,uuid,text,text,bigint,bigint,text),
  public.settle_news_ab_ai(uuid,bigint,bigint,jsonb), public.close_news_ab_test(text) to service_role;
