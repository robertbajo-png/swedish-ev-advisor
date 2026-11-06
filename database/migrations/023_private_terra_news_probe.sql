-- Private owner-issued Terra test only. No production model, caps or switches change.
begin;
set local lock_timeout='10s';
set local statement_timeout='30s';
create table if not exists public.news_terra_test_permits (
  id text primary key,
  issued_at timestamptz not null default clock_timestamp(),
  expires_at timestamptz not null,
  closed_at timestamptz,
  maximum_micro_usd bigint not null check(maximum_micro_usd between 1 and 100000),
  manifest_hash text not null check(manifest_hash ~ '^[a-f0-9]{64}$'),
  writer_hash text not null check(writer_hash ~ '^[a-f0-9]{64}$'),
  writer_input_bound bigint not null check(writer_input_bound between 1 and 131072),
  review_input_bound bigint not null check(review_input_bound between 1 and 131072),
  approval_note text not null check(length(approval_note) between 30 and 1000),
  check(expires_at>issued_at and expires_at<=issued_at+interval '2 hours')
);
alter table public.news_terra_test_permits enable row level security;
revoke all on public.news_terra_test_permits from public,anon,authenticated,service_role;
grant select on public.news_terra_test_permits to service_role;
alter table public.news_ai_requests add column if not exists terra_test_id text references public.news_terra_test_permits(id);
create unique index if not exists news_terra_test_one_stage on public.news_ai_requests(terra_test_id,stage) where terra_test_id is not null;

create or replace function public.reserve_news_terra_test(
  permit_key text,manifest_digest text,request_key uuid,stage_key text,
  input_bound bigint,output_bound bigint,request_digest text
) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare cfg public.news_ai_config; permit public.news_terra_test_permits;
  amount bigint; reserved_test bigint; used_day bigint; used_month bigint;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into cfg from public.news_ai_config where id='production' for update;
  if not found or cfg.model<>'gpt-6-sol' or cfg.daily_limit_micro_usd<>250000
    or cfg.monthly_limit_micro_usd<>5000000 or cfg.daily_article_limit<>1
    or (now() at time zone 'UTC')::date>=cfg.pricing_valid_until then
    return jsonb_build_object('allowed',false,'reason','terra_production_configuration_changed'); end if;
  select * into permit from public.news_terra_test_permits where id=permit_key for update;
  if not found or permit.closed_at is not null or clock_timestamp()>=permit.expires_at
    or permit.issued_at>clock_timestamp()
    or (permit.issued_at at time zone 'UTC')::date<>(now() at time zone 'UTC')::date
    or permit.manifest_hash is distinct from manifest_digest then
    return jsonb_build_object('allowed',false,'reason','terra_permit_inactive_or_wrong_manifest'); end if;
  if request_key is null or stage_key is null or stage_key not in ('swedish_ev_article','ev_news_independent_audit')
    or input_bound is null or input_bound not between 1 and 131072
    or output_bound is distinct from (case when stage_key='swedish_ev_article' then 2000::bigint else 1300::bigint end)
    or request_digest is null or request_digest !~ '^[a-f0-9]{64}$' then
    return jsonb_build_object('allowed',false,'reason','terra_request_outside_contract'); end if;
  if exists(select 1 from public.news_ai_requests where id=request_key or (terra_test_id=permit_key and stage=stage_key)) then
    return jsonb_build_object('allowed',false,'reason','terra_stage_consumed'); end if;
  if stage_key='swedish_ev_article' then
    if request_digest is distinct from permit.writer_hash or input_bound<>permit.writer_input_bound then
      return jsonb_build_object('allowed',false,'reason','terra_writer_changed'); end if;
  elsif input_bound>permit.review_input_bound or not exists(select 1 from public.news_ai_requests
      where terra_test_id=permit_key and stage='swedish_ev_article' and settled_at is not null
      and provider_status='completed') then
    return jsonb_build_object('allowed',false,'reason','terra_review_requires_settled_writer');
  end if;
  if exists(select 1 from public.news_ai_requests where (settled_at is null and budget_closed_at is null)
    or provider_status='accounting_anomaly') then
    return jsonb_build_object('allowed',false,'reason','terra_unresolved_accounting'); end if;
  -- Verified standard short-context rates: worst 12h input-cache write $2.50/M, output $5/M.
  amount:=(input_bound*5+output_bound*10+1)/2;
  select coalesce(sum(reserved_micro_usd),0) into reserved_test from public.news_ai_requests where terra_test_id=permit_key;
  if reserved_test+amount>permit.maximum_micro_usd then
    return jsonb_build_object('allowed',false,'reason','terra_test_cap_exhausted'); end if;
  select coalesce(sum(charged_micro_usd) filter(where created_at>=date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'),0),
    coalesce(sum(charged_micro_usd),0) into used_day,used_month from public.news_ai_requests
    where created_at>=date_trunc('month',now() at time zone 'UTC') at time zone 'UTC';
  if used_day+(case when stage_key='swedish_ev_article' then permit.maximum_micro_usd else amount end)>cfg.daily_limit_micro_usd
    or used_month+(case when stage_key='swedish_ev_article' then permit.maximum_micro_usd else amount end)>cfg.monthly_limit_micro_usd then
    return jsonb_build_object('allowed',false,'reason','terra_ordinary_budget_exhausted'); end if;
  insert into public.news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,charged_micro_usd,terra_test_id)
  values(request_key,stage_key,'gpt-6.1-terra',request_digest,input_bound,output_bound,amount,amount,permit_key);
  return jsonb_build_object('allowed',true,'reserved_micro_usd',amount);
end $$;

create or replace function public.settle_news_terra_test(request_key uuid, response_body jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare req public.news_ai_requests; used_input bigint; used_output bigint; cached bigint;
  written bigint; w30 bigint:=0; w12 bigint:=0; amount bigint; details jsonb;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into req from public.news_ai_requests where id=request_key for update;
  if not found or req.terra_test_id is null or req.model<>'gpt-6.1-terra' then
    return jsonb_build_object('settled',false,'reason','terra_reservation_missing'); end if;
  if req.budget_closed_at is not null then
    return jsonb_build_object('settled',false,'reason','terra_closed_hold_preserved'); end if;
  if response_body is null or pg_column_size(response_body)>250000
    or response_body->>'service_tier' is distinct from 'default'
    or coalesce(response_body->>'model','') !~ '^gpt-6\.1-terra(-[0-9]{4}-[0-9]{2}-[0-9]{2})?$'
    or coalesce(response_body->>'status','') not in ('completed','incomplete','failed','cancelled') then
    return jsonb_build_object('settled',false,'reason','terra_unverified_response_hold_retained'); end if;
  if req.settled_at is not null then
    return jsonb_build_object('settled',req.provider_status<>'accounting_anomaly' and req.response_payload=response_body,
      'reason','terra_already_settled','charged_micro_usd',req.charged_micro_usd); end if;
  details:=response_body#>'{usage,input_tokens_details}';
  if coalesce(response_body#>>'{usage,input_tokens}','') !~ '^\d{1,9}$'
    or coalesce(response_body#>>'{usage,output_tokens}','') !~ '^\d{1,9}$'
    or coalesce(details->>'cached_tokens','') !~ '^\d{1,9}$'
    or coalesce(details->>'cache_write_tokens','') !~ '^\d{1,9}$' then
    return jsonb_build_object('settled',false,'reason','terra_usage_unknown_hold_retained'); end if;
  used_input:=(response_body#>>'{usage,input_tokens}')::bigint;
  used_output:=(response_body#>>'{usage,output_tokens}')::bigint;
  cached:=(details->>'cached_tokens')::bigint;
  written:=(details->>'cache_write_tokens')::bigint;
  if written>0 then
    if coalesce(details#>>'{cache_write_tokens_details,ttl_30m_tokens}','') !~ '^\d{1,9}$'
      or coalesce(details#>>'{cache_write_tokens_details,ttl_12h_tokens}','') !~ '^\d{1,9}$' then
      return jsonb_build_object('settled',false,'reason','terra_cache_usage_unknown_hold_retained'); end if;
    w30:=(details#>>'{cache_write_tokens_details,ttl_30m_tokens}')::bigint;
    w12:=(details#>>'{cache_write_tokens_details,ttl_12h_tokens}')::bigint;
  end if;
  if cached+written>used_input or w30+w12<>written then
    return jsonb_build_object('settled',false,'reason','terra_usage_inconsistent_hold_retained'); end if;
  amount:=((used_input-cached-written)*20+cached+w30*25+w12*50+used_output*100+19)/20;
  update public.news_ai_requests set charged_micro_usd=case when used_input>req.input_bound or used_output>req.output_bound
      or amount>req.reserved_micro_usd then greatest(amount,req.reserved_micro_usd) else amount end,
    input_tokens=used_input,output_tokens=used_output,settled_at=clock_timestamp(),
    provider_status=case when used_input>req.input_bound or used_output>req.output_bound or amount>req.reserved_micro_usd
      then 'accounting_anomaly' else response_body->>'status' end,response_payload=response_body where id=request_key;
  if used_input>req.input_bound or used_output>req.output_bound or amount>req.reserved_micro_usd then
    return jsonb_build_object('settled',false,'reason','terra_accounting_anomaly_hold_retained'); end if;
  return jsonb_build_object('settled',true,'charged_micro_usd',amount);
end $$;

create or replace function public.close_news_terra_test(permit_key text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
begin
  perform pg_advisory_xact_lock(72716492);
  update public.news_terra_test_permits set closed_at=coalesce(closed_at,clock_timestamp()) where id=permit_key;
  return jsonb_build_object('closed',found);
end $$;
revoke all on function public.reserve_news_terra_test(text,text,uuid,text,bigint,bigint,text),
  public.settle_news_terra_test(uuid,jsonb),public.close_news_terra_test(text) from public,anon,authenticated;
grant execute on function public.reserve_news_terra_test(text,text,uuid,text,bigint,bigint,text),
  public.settle_news_terra_test(uuid,jsonb),public.close_news_terra_test(text) to service_role;
notify pgrst,'reload schema';
commit;
