-- Owner-requested news model change only. No activation, grants, cap or ledger reset.
-- Verified 2026-10-23: https://developers.openai.com/api/docs/models/gpt-6-sol
-- https://developers.openai.com/api/docs/guides/prompt-caching
begin;
set local lock_timeout='10s';
set local statement_timeout='30s';
select pg_advisory_xact_lock(72716492);
do $$ begin
  if not exists(select 1 from public.news_ai_config where id='production'
    and not enabled and not publication_enabled and model in ('gpt-5.4-mini','gpt-6-sol')
    and daily_limit_micro_usd=250000 and monthly_limit_micro_usd=5000000)
    or exists(select 1 from public.news_notice_release_config where enabled)
    or exists(select 1 from public.news_ai_requests where (settled_at is null and budget_closed_at is null)
      or provider_status='accounting_anomaly') then
    raise exception 'Sol migration requires paused production, unchanged caps and reconciled usage';
  end if;
end $$;
alter table public.news_ai_config drop constraint if exists news_ai_config_model_check;
alter table public.news_ai_config add constraint news_ai_config_model_check check(model in ('gpt-5.4-mini','gpt-6-sol'));

create or replace function public.reserve_news_ai(
  request_key uuid, stage_key text, model_key text, input_bound bigint, output_bound bigint, request_digest text
) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare cfg public.news_ai_config; amount bigint; used_day bigint; used_month bigint;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into cfg from public.news_ai_config where id='production' for update;
  if not found or not cfg.enabled then return jsonb_build_object('allowed',false,'reason','news_budget_disabled'); end if;
  if (now() at time zone 'UTC')::date >= cfg.pricing_valid_until then
    return jsonb_build_object('allowed',false,'reason','news_pricing_expired'); end if;
  if model_key is null or model_key not in ('gpt-5.4-mini','gpt-6-sol') or model_key is distinct from cfg.model
    or request_key is null or input_bound is null or input_bound not between 1 and 131072
    or output_bound is null or output_bound not between 128 and 3000
    or request_digest is null or request_digest !~ '^[a-f0-9]{64}$'
    or stage_key is null or stage_key not in ('ev_news_facts','news_event_identity','swedish_ev_article',
      'ev_news_independent_audit','ev_news_block_repair','ev_news_hybrid_launch_write','ev_news_hybrid_launch_review') then
    return jsonb_build_object('allowed',false,'reason','news_request_outside_contract'); end if;
  if exists(select 1 from public.news_ai_requests where id=request_key) then
    return jsonb_build_object('allowed',false,'reason','news_request_already_reserved'); end if;
  if exists(select 1 from public.news_ai_requests where (settled_at is null and budget_closed_at is null)
    or provider_status='accounting_anomaly') then
    return jsonb_build_object('allowed',false,'reason','news_unresolved_accounting'); end if;
  -- Sol standard <=272K: input/cached/30m-write/12h-write/output USD2/.2/2.5/5/10 per M.
  -- Bound is below the long-context threshold. Reserve worst input tariff, not a cache discount.
  amount := case when model_key='gpt-6-sol' then input_bound*5+output_bound*10
    else (input_bound*3+output_bound*18+3)/4 end;
  select coalesce(sum(charged_micro_usd) filter(where created_at >= date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'),0),
    coalesce(sum(charged_micro_usd),0) into used_day,used_month from public.news_ai_requests
    where created_at >= date_trunc('month',now() at time zone 'UTC') at time zone 'UTC';
  if used_day+amount > cfg.daily_limit_micro_usd or used_month+amount > cfg.monthly_limit_micro_usd then
    return jsonb_build_object('allowed',false,'reason','news_budget_exhausted'); end if;
  insert into public.news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,charged_micro_usd)
  values(request_key,stage_key,model_key,request_digest,input_bound,output_bound,amount,amount);
  return jsonb_build_object('allowed',true,'request_id',request_key,'reserved_micro_usd',amount);
end $$;

create or replace function public.settle_news_ai(request_key uuid, used_input bigint, used_output bigint, response_body jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare req public.news_ai_requests; amount bigint; pattern text; u jsonb; details jsonb; wd jsonb;
  cached bigint; written bigint; w30 bigint; w12 bigint; ordinary bigint;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into req from public.news_ai_requests where id=request_key for update;
  if not found or req.model not in ('gpt-5.4-mini','gpt-6-sol') then
    return jsonb_build_object('settled',false,'reason','news_reservation_missing'); end if;
  pattern := case when req.model='gpt-6-sol' then '^gpt-6-sol(-[0-9]{4}-[0-9]{2}-[0-9]{2})?$'
    else '^gpt-5\.4-mini(-[0-9]{4}-[0-9]{2}-[0-9]{2})?$' end;
  if response_body is null or pg_column_size(response_body)>250000
    or response_body->>'service_tier' is distinct from 'default' or coalesce(response_body->>'model','') !~ pattern then
    update public.news_ai_config set enabled=false where id='production';
    return jsonb_build_object('settled',false,'reason','news_unexpected_provider_pricing_halted'); end if;
  if used_input is null or used_output is null or used_input not between 0 and 1000000 or used_output not between 0 and 1000000 then
    return jsonb_build_object('settled',false,'reason','news_usage_unknown_reservation_retained'); end if;
  if req.settled_at is not null then
    return jsonb_build_object('settled',req.provider_status<>'accounting_anomaly' and req.input_tokens=used_input
      and req.output_tokens=used_output and req.response_payload=response_body,'reason','news_already_settled'); end if;
  if req.budget_closed_at is not null then
    return jsonb_build_object('settled',false,'reason','news_budget_closed_hold_preserved'); end if;
  if req.model='gpt-6-sol' then
    u := response_body->'usage'; details := u->'input_tokens_details'; wd := details->'cache_write_tokens_details';
    if coalesce(u->>'input_tokens','') !~ '^[0-9]{1,7}$' or coalesce(u->>'output_tokens','') !~ '^[0-9]{1,7}$'
      or coalesce(u->>'total_tokens','') !~ '^[0-9]{1,7}$'
      or coalesce(details->>'cached_tokens','') !~ '^[0-9]{1,7}$'
      or coalesce(details->>'cache_write_tokens','') !~ '^[0-9]{1,7}$' then
      return jsonb_build_object('settled',false,'reason','news_sol_cache_usage_unknown_hold_retained'); end if;
    if (u->>'input_tokens')::bigint <> used_input or (u->>'output_tokens')::bigint <> used_output
      or (u->>'total_tokens')::bigint <> used_input+used_output then
      return jsonb_build_object('settled',false,'reason','news_sol_inconsistent_usage_hold_retained'); end if;
    cached := (details->>'cached_tokens')::bigint; written := (details->>'cache_write_tokens')::bigint;
    w30 := 0; w12 := 0;
    if written>0 or wd is not null and wd<>'null'::jsonb then
      if coalesce(wd->>'ttl_30m_tokens','') !~ '^[0-9]{1,7}$' or coalesce(wd->>'ttl_12h_tokens','') !~ '^[0-9]{1,7}$' then
        return jsonb_build_object('settled',false,'reason','news_sol_cache_lifetime_unknown_hold_retained'); end if;
      w30 := (wd->>'ttl_30m_tokens')::bigint; w12 := (wd->>'ttl_12h_tokens')::bigint;
    end if;
    ordinary := used_input-cached-written;
    if ordinary<0 or w30+w12<>written then
      return jsonb_build_object('settled',false,'reason','news_sol_inconsistent_cache_usage_hold_retained'); end if;
    amount := (ordinary*2000+cached*200+w30*2500+w12*5000+used_output*10000+999)/1000;
  else
    amount := (used_input*3+used_output*18+3)/4;
  end if;
  if used_input>req.input_bound or used_output>req.output_bound or amount>req.reserved_micro_usd then
    update public.news_ai_requests set charged_micro_usd=greatest(amount,reserved_micro_usd),input_tokens=used_input,
      output_tokens=used_output,settled_at=clock_timestamp(),provider_status='accounting_anomaly',response_payload=response_body where id=request_key;
    update public.news_ai_config set enabled=false where id='production';
    return jsonb_build_object('settled',false,'reason','news_accounting_halted'); end if;
  update public.news_ai_requests set charged_micro_usd=amount,input_tokens=used_input,output_tokens=used_output,
    settled_at=clock_timestamp(),provider_status=coalesce(response_body->>'status','unknown'),response_payload=response_body where id=request_key;
  return jsonb_build_object('settled',true,'charged_micro_usd',amount);
end $$;

-- Keep all pre-existing privileges and ledger/vehicle/article rows unchanged.
update public.news_ai_config set model='gpt-6-sol' where id='production';
notify pgrst,'reload schema';
commit;
