-- Adds a separately reviewed price-notice format. Does not activate any switch.
-- The legacy checker, common publication trigger, AI settings and grants stay intact.
do $$
declare source text;
begin
  if to_regprocedure('public.news_legacy_notice_release_error(public.news_articles)') is null then
    select prosrc into source from pg_proc where oid='public.news_notice_release_error(public.news_articles)'::regprocedure;
    if encode(sha256(convert_to(replace(source,chr(13)||chr(10),chr(10)),'UTF8')),'hex')
      <> '1236b024d0b80c7791726ed7fe6bc331f0e941fd463e88e270827948888b0810' then
      raise exception 'single_fact_legacy_checker_changed';
    end if;
    execute format('create function public.news_legacy_notice_release_error(candidate public.news_articles)
      returns text language plpgsql security definer set search_path=pg_catalog,public as %L',source);
  else
    select prosrc into source from pg_proc where oid='public.news_legacy_notice_release_error(public.news_articles)'::regprocedure;
    if encode(sha256(convert_to(replace(source,chr(13)||chr(10),chr(10)),'UTF8')),'hex')
      <> '1236b024d0b80c7791726ed7fe6bc331f0e941fd463e88e270827948888b0810' then
      raise exception 'single_fact_saved_legacy_checker_changed';
    end if;
  end if;
end $$;
revoke all on function public.news_legacy_notice_release_error(public.news_articles) from public,anon,authenticated,service_role;

alter table public.news_notice_release_config drop constraint if exists news_notice_release_config_policy_check;
alter table public.news_notice_release_config add constraint news_notice_release_config_policy_check
  check(policy in ('news-notice-2026-10-v1','news-single-official-fact-2026-11-v1'));
alter table public.news_notice_release_config drop constraint if exists news_notice_release_config_review_method_check;
alter table public.news_notice_release_config add constraint news_notice_release_config_review_method_check
  check(review_method in ('deterministic_typed_notice_v1','deterministic_single_official_fact_v1'));
alter table public.news_notice_release_config drop constraint if exists news_notice_release_config_policy_pair_check;
alter table public.news_notice_release_config add constraint news_notice_release_config_policy_pair_check check(
  (policy='news-notice-2026-10-v1' and review_method='deterministic_typed_notice_v1') or
  (policy='news-single-official-fact-2026-11-v1' and review_method='deterministic_single_official_fact_v1'));
alter table public.news_notice_publications drop constraint if exists news_notice_publications_policy_check;
alter table public.news_notice_publications add constraint news_notice_publications_policy_check
  check(policy in ('news-notice-2026-10-v1','news-single-official-fact-2026-11-v1'));
alter table public.news_notice_publications drop constraint if exists news_notice_publications_review_method_check;
alter table public.news_notice_publications add constraint news_notice_publications_review_method_check
  check(review_method in ('deterministic_typed_notice_v1','deterministic_single_official_fact_v1'));

create or replace function public.news_notice_release_error(candidate public.news_articles)
returns text language plpgsql security definer set search_path=pg_catalog,public as $$
declare p jsonb:=candidate.payload; f jsonb:=p->'notice_facts'; fact jsonb:=f->'fact';
  i public.news_items; s public.news_sources; c public.news_story_clusters; cfg public.news_notice_release_config; n integer;
begin
  select * into cfg from public.news_notice_release_config where id='production';
  if cfg.policy='news-notice-2026-10-v1' then
    return public.news_legacy_notice_release_error(candidate);
  end if;
  if not found or not cfg.enabled then return 'notice_publication_disabled'; end if;
  if cfg.policy<>'news-single-official-fact-2026-11-v1' or cfg.review_method<>'deterministic_single_official_fact_v1'
    or p->>'editorial_recipe' is distinct from cfg.policy or p->>'notice_kind' is distinct from 'price'
    or f->>'kind' is distinct from 'price' or fact->>'type' is distinct from 'swedish_list_price'
    or p->>'category' is distinct from 'priser' or p->'image' is distinct from 'null'::jsonb
    or jsonb_typeof(p->'sources') is distinct from 'array' or jsonb_array_length(p->'sources')<>1
    or jsonb_typeof(p->'paragraphs') is distinct from 'array' or jsonb_array_length(p->'paragraphs') not between 1 and 6
    or jsonb_typeof(p->'related_models') is distinct from 'array' or jsonb_array_length(p->'related_models')<>0
    or exists(select 1 from jsonb_array_elements(p->'paragraphs') b where b->>'kind' is distinct from 'reporting')
    then return 'single_fact_invalid_format'; end if;
  if f->>'brand' is distinct from 'Kia' or nullif(f->>'model','') is null or f->>'model' !~ '^EV[0-9]+$'
    or f->>'subject' is distinct from 'Kia '||(f->>'model')
    or nullif(fact->>'variant','') is null or fact->>'variant' not like 'Kia '||(f->>'model')||' %'
    or jsonb_typeof(fact->'price_sek') is distinct from 'number'
    or (fact->>'price_sek')::numeric not between 100000 and 3000000
    or fact->>'price_type' is distinct from 'list_price' or fact->>'currency' is distinct from 'SEK'
    or fact->>'market' is distinct from 'SE' or fact->'vat_included' is distinct from 'true'::jsonb
    or nullif(fact->>'row_key','') is null or nullif(fact->>'evidence','') is null
    then return 'single_fact_invalid_price_identity'; end if;
  select * into i from public.news_items where id=p->'sources'->0->>'item_id';
  if not found or i.status<>'processed' or i.payload->>'access_status' is distinct from 'accessible'
    or i.source_id<>'kia-sweden-prices' or i.url<>'https://www.kia.com/se/kopa/prislista/'
    or i.payload->>'final_url' is distinct from i.url or i.payload->>'source_kind' is distinct from 'primary'
    then return 'single_fact_source_not_ready'; end if;
  select * into s from public.news_sources where id=i.source_id;
  if not found or s.payload->>'kind' is distinct from 'primary' or s.payload->>'name' is distinct from 'Kia Sverige'
    or s.payload->>'website' is distinct from 'https://www.kia.com/se/'
    or i.payload->>'publisher' is distinct from s.payload->>'name'
    then return 'single_fact_source_not_official'; end if;
  if f->>'item_id' is distinct from i.id or f->>'source_id' is distinct from i.source_id
    or f->>'source_url' is distinct from i.url or f->>'publisher' is distinct from s.payload->>'name'
    or f->>'source_title' is distinct from i.payload->>'title'
    or f->'source_published_at' is distinct from i.payload->'published_at'
    or p->'sources'->0 is distinct from jsonb_build_object('item_id',i.id,'url',i.url,'publisher',s.payload->>'name',
      'title',i.payload->>'title','published_at',i.payload->'published_at','kind','primary')
    then return 'single_fact_attribution_mismatch'; end if;
  if f->>'source_hash' is distinct from i.payload->>'content_hash'
    or fact->>'source_hash' is distinct from f->>'source_hash'
    or encode(sha256(convert_to(i.payload->>'content','UTF8')),'hex') is distinct from f->>'source_hash'
    or fact->>'raw_source_hash' is distinct from i.payload->'source_capture'->'source'->>'content_hash'
    or encode(sha256(convert_to(i.payload->'source_capture'->>'html','UTF8')),'hex') is distinct from fact->>'raw_source_hash'
    or i.payload->'source_capture'->'source'->>'status' is distinct from 'reachable'
    or i.payload->'source_capture'->'source'->>'http_status' is distinct from '200'
    or i.payload->'source_capture'->'source'->>'final_url' is distinct from i.url
    then return 'single_fact_source_hash_changed'; end if;
  if i.payload->>'source_date_kind' is distinct from 'evergreen_price_snapshot'
    or i.payload->'published_at' is distinct from 'null'::jsonb
    or nullif(i.payload->>'fetched_at','') is null
    or i.payload->'source_capture'->'source'->>'fetched_at' is distinct from i.payload->>'fetched_at'
    or (i.payload->>'fetched_at')::timestamptz not between clock_timestamp()-interval '1 day' and clock_timestamp()+interval '5 minutes'
    then return 'single_fact_source_stale'; end if;
  select * into c from public.news_story_clusters where id=candidate.cluster_id;
  if not found or c.payload->>'notice_recipe' is distinct from cfg.policy
    or c.event_key !~ '^news-single-official-fact-2026-11-v1:[a-f0-9]{64}$'
    then return 'single_fact_event_identity_mismatch'; end if;
  select count(distinct q.kind) into n from public.news_quality_checks q
    where q.article_id=candidate.id and q.artifact_hash=candidate.artifact_hash and q.passed
    and q.kind in ('evidence','editorial','originality') and q.payload->>'policy_version'=cfg.policy
    and q.payload->>'notice_recipe'=cfg.policy and q.payload->>'review_method'=cfg.review_method
    and q.payload->'audit_performed'='false'::jsonb and q.payload->'deterministic_review_performed'='true'::jsonb
    and q.payload->'errors'='[]'::jsonb and q.payload->>'source_hash'=f->>'source_hash'
    and q.payload->>'reviewed_artifact_hash' ~ '^[a-f0-9]{64}$'
    and (q.payload->>'checked_at')::timestamptz between clock_timestamp()-interval '1 day' and clock_timestamp()+interval '5 minutes';
  if n<>3 then return 'single_fact_missing_or_stale_checks'; end if;
  if (select count(*) from public.news_article_sources where article_id=candidate.id)<>1 or not exists(
    select 1 from public.news_article_sources where article_id=candidate.id and item_id=i.id and payload=p->'sources'->0)
    or exists(select 1 from public.news_vehicle_links where article_id=candidate.id)
    then return 'single_fact_link_mismatch'; end if;
  if exists(select 1 from public.news_articles a where a.id<>candidate.id and a.status='published'
    and a.payload->'notice_facts'->'fact'->>'type'='swedish_list_price'
    and a.payload->'notice_facts'->'fact'->>'row_key'=fact->>'row_key'
    and a.payload->'notice_facts'->'fact'->'price_sek'=fact->'price_sek'
    and a.payload->'notice_facts'->'fact'->>'currency'='SEK'
    and a.payload->'notice_facts'->'fact'->>'market'='SE') then return 'single_fact_already_published'; end if;
  return null;
end $$;
revoke all on function public.news_notice_release_error(public.news_articles) from public,anon,authenticated,service_role;

-- Existing RPC and permissions, with policy-specific receipts rather than a v1 literal.
create or replace function public.publish_news_notice(article_key text,expected_artifact_hash text,expected_payload jsonb,expected_source jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare a public.news_articles; i public.news_items; snapshot jsonb; reason text; cfg public.news_notice_release_config;
begin
  perform pg_advisory_xact_lock(72716491);
  select * into a from public.news_articles where id=article_key for update;
  if not found or a.artifact_hash is distinct from expected_artifact_hash or a.payload is distinct from expected_payload
    then raise exception 'notice_article_snapshot_changed'; end if;
  if a.status='published' and exists(select 1 from public.news_notice_publications where article_id=a.id and artifact_hash=a.artifact_hash)
    then return jsonb_build_object('published',true,'already_published',true); end if;
  if a.status<>'draft' then raise exception 'notice_release_requires_current_draft'; end if;
  perform 1 from public.news_ai_config where id='production' for share;
  select * into cfg from public.news_notice_release_config where id='production' for share;
  perform 1 from public.news_items where id=a.payload->'sources'->0->>'item_id' for share;
  select * into i from public.news_items where id=a.payload->'sources'->0->>'item_id';
  perform 1 from public.news_sources where id=i.source_id for share;
  perform 1 from public.news_story_clusters where id=a.cluster_id for share;
  perform 1 from public.news_quality_checks where article_id=a.id for share;
  perform 1 from public.news_article_sources where article_id=a.id for share;
  perform 1 from public.news_vehicle_links where article_id=a.id for share;
  perform 1 from public.canonical_models where id in (select canonical_model_id from public.news_vehicle_links where article_id=a.id) for share;
  snapshot:=public.news_notice_source_snapshot(a.id);
  if snapshot is null or snapshot is distinct from expected_source then raise exception 'notice_source_snapshot_changed'; end if;
  reason:=public.news_notice_release_error(a);
  if reason is not null then raise exception '%',reason; end if;
  insert into public.news_notice_publications(article_id,artifact_hash,source_hash,source_snapshot_hash,transaction_id,policy,review_method)
  values(a.id,a.artifact_hash,a.payload->'notice_facts'->>'source_hash',encode(sha256(convert_to(snapshot::text,'UTF8')),'hex'),
    txid_current(),cfg.policy,cfg.review_method);
  update public.news_articles set status='published' where id=a.id;
  return jsonb_build_object('published',true,'already_published',false);
end $$;
revoke all on function public.publish_news_notice(text,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.publish_news_notice(text,text,jsonb,jsonb) to service_role;
