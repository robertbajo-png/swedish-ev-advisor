-- Install after 007. Owner-approved ceilings; both activation switches stay OFF.
create table if not exists public.news_ai_config (
  id text primary key check (id='production'),
  enabled boolean not null default false,
  publication_enabled boolean not null default false,
  daily_limit_micro_usd bigint not null check (daily_limit_micro_usd between 0 and 250000),
  monthly_limit_micro_usd bigint not null check (monthly_limit_micro_usd between 0 and 5000000),
  daily_article_limit integer not null default 2 check (daily_article_limit between 0 and 5),
  model text not null check (model='gpt-5.4-mini'),
  pricing_valid_until date not null,
  approval_note text not null
);
insert into public.news_ai_config(id,daily_limit_micro_usd,monthly_limit_micro_usd,model,pricing_valid_until,approval_note)
values('production',250000,5000000,'gpt-5.4-mini','2026-11-21','Owner approved USD 0.25/day and USD 5/month on 2026-10-21; activation pending release checks')
on conflict(id) do nothing;

create table if not exists public.news_ai_requests (
  id uuid primary key,
  created_at timestamptz not null default clock_timestamp(),
  stage text not null,
  model text not null,
  request_hash text not null,
  input_bound bigint not null,
  output_bound bigint not null,
  reserved_micro_usd bigint not null,
  charged_micro_usd bigint not null,
  input_tokens bigint,
  output_tokens bigint,
  settled_at timestamptz,
  provider_status text not null default 'reserved',
  response_payload jsonb
);
create index if not exists news_ai_requests_period on public.news_ai_requests(created_at);
alter table public.news_ai_config enable row level security;
alter table public.news_ai_requests enable row level security;
revoke all on public.news_ai_config, public.news_ai_requests from public,anon,authenticated,service_role;
-- The worker cannot reset the ledger, change rates, raise caps or activate publication.
grant select on public.news_ai_config, public.news_ai_requests to service_role;

create or replace function public.reserve_news_ai(
  request_key uuid, stage_key text, model_key text, input_bound bigint, output_bound bigint, request_digest text
) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare cfg public.news_ai_config; amount bigint; used_day bigint; used_month bigint; utc_day timestamptz; utc_month timestamptz;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into cfg from public.news_ai_config where id='production' for update;
  if not found or not cfg.enabled then return jsonb_build_object('allowed',false,'reason','news_budget_disabled'); end if;
  if (now() at time zone 'UTC')::date >= cfg.pricing_valid_until then
    return jsonb_build_object('allowed',false,'reason','news_pricing_expired');
  end if;
  if model_key is distinct from cfg.model or input_bound is null or output_bound is null
    or input_bound not between 1 and 131072 or output_bound not between 128 and 3000
    or request_digest is null or request_digest !~ '^[a-f0-9]{64}$'
    or stage_key is null or stage_key not in ('ev_news_facts','news_event_identity','swedish_ev_article','ev_news_independent_audit','ev_news_block_repair') then
    return jsonb_build_object('allowed',false,'reason','news_request_outside_contract');
  end if;
  if exists(select 1 from public.news_ai_requests where id=request_key) then
    return jsonb_build_object('allowed',false,'reason','news_request_already_reserved');
  end if;
  -- USD 0.75/M input, USD 4.50/M output. No speculative cache discount.
  amount := (input_bound*3 + output_bound*18 + 3)/4;
  utc_day := date_trunc('day',now() at time zone 'UTC') at time zone 'UTC';
  utc_month := date_trunc('month',now() at time zone 'UTC') at time zone 'UTC';
  select coalesce(sum(charged_micro_usd) filter(where created_at >= utc_day),0),coalesce(sum(charged_micro_usd),0)
    into used_day,used_month from public.news_ai_requests where created_at >= utc_month;
  if used_day+amount > cfg.daily_limit_micro_usd or used_month+amount > cfg.monthly_limit_micro_usd then
    return jsonb_build_object('allowed',false,'reason','news_budget_exhausted');
  end if;
  insert into public.news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,charged_micro_usd)
  values(request_key,stage_key,model_key,request_digest,input_bound,output_bound,amount,amount);
  return jsonb_build_object('allowed',true,'request_id',request_key,'reserved_micro_usd',amount);
end $$;

create or replace function public.settle_news_ai(
  request_key uuid, used_input bigint, used_output bigint, response_body jsonb
) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare req public.news_ai_requests; amount bigint;
begin
  perform pg_advisory_xact_lock(72716492);
  select * into req from public.news_ai_requests where id=request_key for update;
  if not found then return jsonb_build_object('settled',false,'reason','news_reservation_missing'); end if;
  if response_body->>'service_tier' is distinct from 'default'
    or coalesce(response_body->>'model','') !~ '^gpt-5\.4-mini(-[0-9]{4}-[0-9]{2}-[0-9]{2})?$' then
    update public.news_ai_config set enabled=false where id='production';
    return jsonb_build_object('settled',false,'reason','news_unexpected_provider_pricing_halted');
  end if;
  if used_input is null or used_output is null or used_input < 0 or used_output < 0
    or used_input > 1000000 or used_output > 1000000 or response_body is null
    or pg_column_size(response_body) > 250000 then
    return jsonb_build_object('settled',false,'reason','news_usage_unknown_reservation_retained');
  end if;
  if req.settled_at is not null then
    return jsonb_build_object('settled',req.provider_status <> 'accounting_anomaly' and req.input_tokens=used_input and req.output_tokens=used_output,
                             'reason','news_already_settled');
  end if;
  amount := (used_input*3 + used_output*18 + 3)/4;
  if used_input > req.input_bound or used_output > req.output_bound or amount > req.reserved_micro_usd then
    update public.news_ai_requests set charged_micro_usd=greatest(amount,reserved_micro_usd),input_tokens=used_input,
      output_tokens=used_output,settled_at=clock_timestamp(),provider_status='accounting_anomaly',response_payload=response_body where id=request_key;
    update public.news_ai_config set enabled=false where id='production';
    return jsonb_build_object('settled',false,'reason','news_accounting_halted');
  end if;
  update public.news_ai_requests set charged_micro_usd=amount,input_tokens=used_input,output_tokens=used_output,
    settled_at=clock_timestamp(),provider_status=coalesce(response_body->>'status','unknown'),response_payload=response_body where id=request_key;
  return jsonb_build_object('settled',true,'charged_micro_usd',amount);
end $$;
revoke all on function public.reserve_news_ai(uuid,text,text,bigint,bigint,text),
  public.settle_news_ai(uuid,bigint,bigint,jsonb) from public,anon,authenticated;
grant execute on function public.reserve_news_ai(uuid,text,text,bigint,bigint,text),
  public.settle_news_ai(uuid,bigint,bigint,jsonb) to service_role;

do $$ declare t text; begin
  foreach t in array array['news_sources','news_ingestion_runs','news_items','news_story_clusters',
    'news_articles','news_article_sources','news_vehicle_links','news_quality_checks','news_verification_requests'] loop
    execute format('revoke all on public.%I from public, anon, authenticated',t);
    execute format('revoke all on public.%I from service_role',t);
    execute format('grant select,insert,update on public.%I to service_role',t);
    execute format('alter table public.%I enable row level security',t);
  end loop;
end $$;

create or replace function public.news_guard_publication() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
declare cfg public.news_ai_config;
begin
  new.artifact_hash := encode(sha256(convert_to(new.payload::text,'UTF8')),'hex');
  if tg_op='UPDATE' and old.status='published' then
    if new.payload is distinct from old.payload or new.status <> old.status or new.published_at is distinct from old.published_at then
      raise exception 'Published news is immutable';
    end if;
    return new;
  end if;
  if new.status='published' then
    perform pg_advisory_xact_lock(72716491);
    select * into cfg from public.news_ai_config where id='production';
    if not found or not cfg.publication_enabled then raise exception 'News publication disabled'; end if;
    if (select count(*) from public.news_articles where status='published'
      and published_at >= date_trunc('day',now() at time zone 'UTC') at time zone 'UTC') >= cfg.daily_article_limit then
      raise exception 'News daily publication limit reached';
    end if;
    if (select count(distinct kind) from public.news_quality_checks where article_id=new.id and passed
      and artifact_hash=new.artifact_hash and payload->>'policy_version'='news-editorial-2026-10-v2') <> 3 then
      raise exception 'Missing or stale news quality gates';
    end if;
    if jsonb_typeof(new.payload->'sources') is distinct from 'array' or jsonb_array_length(new.payload->'sources')=0 then
      raise exception 'News must have attributed evidence';
    end if;
    if exists(select 1 from jsonb_array_elements(new.payload->'sources') ref where not exists(
      select 1 from public.news_article_sources s join public.news_items i on i.id=s.item_id
      where s.article_id=new.id and i.id=ref->>'item_id' and i.url=ref->>'url'
      and i.status='processed' and i.payload->>'access_status'='accessible'
      and nullif(i.payload->>'content_hash','') is not null)) then
      raise exception 'News source evidence missing or inaccessible';
    end if;
    new.published_at := clock_timestamp();
  end if;
  new.updated_at := clock_timestamp();
  return new;
end $$;
revoke all on function public.news_guard_publication() from public,anon,authenticated;

create or replace view public.public_news_articles as
select id,slug,published_at,jsonb_build_object(
  'title',payload->'title','intro',payload->'intro','category',payload->'category','brands',payload->'brands',
  'editorial_method',payload->'editorial_method','image',payload->'image','related_models',payload->'related_models',
  'paragraphs',coalesce((select jsonb_agg(jsonb_build_object('text',p->'text','kind',p->'kind') order by n)
    from jsonb_array_elements(payload->'paragraphs') with ordinality as parts(p,n)),'[]'::jsonb),
  'sources',coalesce((select jsonb_agg(jsonb_build_object('url',s->'url','publisher',s->'publisher','title',s->'title',
    'published_at',s->'published_at','kind',s->'kind') order by n)
    from jsonb_array_elements(payload->'sources') with ordinality as refs(s,n)),'[]'::jsonb)
) as payload from public.news_articles where status='published';
revoke all on public.public_news_articles from public,anon,authenticated,service_role;
grant select on public.public_news_articles to anon,authenticated,service_role;
