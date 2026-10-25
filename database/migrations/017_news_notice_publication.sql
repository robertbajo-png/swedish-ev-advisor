-- Local release support only. Installation never enables publishing or paid AI.
create table if not exists public.news_notice_release_config (
  id text primary key check(id='production'),
  enabled boolean not null default false,
  daily_limit integer not null default 2 check(daily_limit between 0 and 5),
  policy text not null default 'news-notice-2026-10-v1' check(policy='news-notice-2026-10-v1'),
  review_method text not null default 'deterministic_typed_notice_v1' check(review_method='deterministic_typed_notice_v1')
);
insert into public.news_notice_release_config(id) values('production') on conflict(id) do nothing;
alter table public.news_notice_release_config enable row level security;
revoke all on public.news_notice_release_config from public,anon,authenticated,service_role;
grant select on public.news_notice_release_config to service_role;

create table if not exists public.news_notice_publications (
  article_id text primary key references public.news_articles(id),
  artifact_hash text not null,
  source_hash text not null,
  source_snapshot_hash text not null,
  validated_at timestamptz not null default clock_timestamp(),
  transaction_id bigint not null,
  policy text not null check(policy='news-notice-2026-10-v1'),
  review_method text not null check(review_method='deterministic_typed_notice_v1')
);
alter table public.news_notice_publications enable row level security;
revoke all on public.news_notice_publications from public,anon,authenticated,service_role;
grant select on public.news_notice_publications to service_role;

-- Snapshot comparison uses JSONB equality, not a Python/Postgres serialization guess.
create or replace function public.news_notice_source_snapshot(article_key text)
returns jsonb language sql stable security definer set search_path=pg_catalog,public as $$
select jsonb_build_object(
  'item',jsonb_build_object('id',i.id,'source_id',i.source_id,'url',i.url,'cluster_id',i.cluster_id,'status',i.status,'payload',i.payload),
  'source',jsonb_build_object('id',s.id,'payload',s.payload),
  'cluster',jsonb_build_object('id',c.id,'event_key',c.event_key,'payload',c.payload),
  'checks',coalesce((select jsonb_agg(jsonb_build_object('id',q.id,'kind',q.kind,'artifact_hash',q.artifact_hash,'passed',q.passed,'payload',q.payload) order by q.kind)
    from public.news_quality_checks q where q.article_id=a.id and q.artifact_hash=a.artifact_hash),'[]'::jsonb),
  'links',coalesce((select jsonb_agg(jsonb_build_object('item_id',l.item_id,'payload',l.payload) order by l.item_id)
    from public.news_article_sources l where l.article_id=a.id),'[]'::jsonb),
  'vehicles',coalesce((select jsonb_agg(jsonb_build_object('canonical_model_id',v.canonical_model_id,'payload',v.payload) order by v.payload->>'key')
    from public.news_vehicle_links v where v.article_id=a.id),'[]'::jsonb))
from public.news_articles a join public.news_items i on i.id=a.payload->'sources'->0->>'item_id'
join public.news_sources s on s.id=i.source_id join public.news_story_clusters c on c.id=a.cluster_id
where a.id=article_key
$$;

-- Necessary commit-time checks. Template re-extraction/re-render belongs to the
-- trusted deterministic worker; neither this RPC nor AI confidence replaces it.
create or replace function public.news_notice_release_error(candidate public.news_articles)
returns text language plpgsql security definer set search_path=pg_catalog,public as $$
declare p jsonb:=candidate.payload; f jsonb:=p->'notice_facts'; i public.news_items;
  s public.news_sources; c public.news_story_clusters; cfg public.news_notice_release_config;
  host text; path text; n integer;
begin
  select * into cfg from public.news_notice_release_config where id='production';
  if not found or not cfg.enabled then return 'notice_publication_disabled'; end if;
  if p->>'editorial_recipe' is distinct from cfg.policy or coalesce(p->>'notice_kind','') not in ('model','price','statistics')
    or f->>'kind' is distinct from p->>'notice_kind' or p->'image' is distinct from 'null'::jsonb
    or jsonb_typeof(p->'sources') is distinct from 'array' or jsonb_typeof(p->'paragraphs') is distinct from 'array'
    or jsonb_typeof(p->'related_models') is distinct from 'array' then return 'notice_invalid_format'; end if;
  if jsonb_array_length(p->'sources')<>1 or jsonb_array_length(p->'paragraphs') not between 1 and 6
    or exists(select 1 from jsonb_array_elements(p->'paragraphs') b where b->>'kind' is distinct from 'reporting')
    or p->>'category' is distinct from (case p->>'notice_kind' when 'model' then 'modeller' when 'price' then 'priser' else 'marknad' end)
    then return 'notice_invalid_public_fields'; end if;
  select * into i from public.news_items where id=p->'sources'->0->>'item_id';
  if not found or i.status<>'processed' or i.cluster_id is distinct from candidate.cluster_id
    or i.payload->>'access_status' is distinct from 'accessible' then return 'notice_source_not_ready'; end if;
  select * into s from public.news_sources where id=i.source_id;
  if not found or s.payload->>'kind' is distinct from 'primary' or i.payload->>'source_kind' is distinct from 'primary'
    then return 'notice_source_not_official'; end if;
  if s.id='vw-sweden-press' then host:='https://www.vwgroup.se'; path:='^https://www[.]vwgroup[.]se/nyheter--media/pressmeddelanden/[^?#]+/$';
  elsif s.id='acea' then host:='https://www.acea.auto'; path:='^https://www[.]acea[.]auto/pc-registrations/[^/?#]+/$';
  else return 'notice_unsupported_source'; end if;
  if rtrim(coalesce(s.payload->>'website',''),'/')<>host or i.url !~ path
    or i.payload->>'final_url' is distinct from i.url or i.payload->>'publisher' is distinct from s.payload->>'name'
    or p->'sources'->0->>'url' is distinct from i.url or p->'sources'->0->>'kind' is distinct from 'primary'
    or p->'sources'->0->>'publisher' is distinct from i.payload->>'publisher'
    or p->'sources'->0->>'title' is distinct from i.payload->>'title'
    or p->'sources'->0->>'published_at' is distinct from i.payload->>'published_at'
    or f->>'source_id' is distinct from i.source_id or f->>'item_id' is distinct from i.id
    or f->>'source_url' is distinct from i.url or f->>'publisher' is distinct from i.payload->>'publisher'
    or f->>'source_title' is distinct from i.payload->>'title'
    or f->>'source_published_at' is distinct from i.payload->>'published_at'
    then return 'notice_attribution_mismatch'; end if;
  if nullif(i.payload->>'content','') is null or coalesce(i.payload->>'content_hash','') !~ '^[a-f0-9]{64}$'
    or encode(sha256(convert_to(i.payload->>'content','UTF8')),'hex') is distinct from i.payload->>'content_hash'
    or f->>'source_hash' is distinct from i.payload->>'content_hash' then return 'notice_source_hash_changed'; end if;
  if nullif(i.payload->>'published_at','') is null or nullif(i.payload->>'fetched_at','') is null
    or (i.payload->>'published_at')::timestamptz not between clock_timestamp()-interval '7 days' and clock_timestamp()+interval '5 minutes'
    or (i.payload->>'fetched_at')::timestamptz not between clock_timestamp()-interval '1 day' and clock_timestamp()+interval '5 minutes'
    then return 'notice_source_stale'; end if;
  select * into c from public.news_story_clusters where id=candidate.cluster_id;
  if not found or c.payload->>'notice_recipe' is distinct from cfg.policy
    or nullif(f->>'subject','') is null
    or c.event_key is distinct from 'notice:'||lower(f->>'subject')||':'||left(f->>'source_published_at',10)
    then return 'notice_event_identity_mismatch'; end if;
  select count(*) into n from public.news_quality_checks q where q.article_id=candidate.id
    and q.artifact_hash=candidate.artifact_hash and q.passed
    and q.payload->>'policy_version'=cfg.policy and q.payload->>'notice_recipe'=cfg.policy
    and q.payload->>'review_method'=cfg.review_method and q.payload->'audit_performed'='false'::jsonb
    and q.payload->'deterministic_review_performed'='true'::jsonb and q.payload->'errors'='[]'::jsonb
    and q.payload->>'source_hash'=f->>'source_hash' and q.payload->>'reviewed_artifact_hash' ~ '^[a-f0-9]{64}$'
    and (q.payload->>'checked_at')::timestamptz between clock_timestamp()-interval '1 day' and clock_timestamp()+interval '5 minutes';
  if n<>3 then return 'notice_missing_or_stale_checks'; end if;
  if (select count(*) from public.news_article_sources where article_id=candidate.id)<>1
    or not exists(select 1 from public.news_article_sources where article_id=candidate.id and item_id=i.id and payload=p->'sources'->0)
    then return 'notice_attribution_rows_mismatch'; end if;
  if (select count(*) from public.news_vehicle_links where article_id=candidate.id)<>jsonb_array_length(p->'related_models')
    or exists(select 1 from jsonb_array_elements(p->'related_models') r where not exists(
      select 1 from public.news_vehicle_links v join public.canonical_models m on m.id=v.canonical_model_id
      where v.article_id=candidate.id and v.payload=r and v.canonical_model_id::text=r->>'canonical_model_id'
      and m.brand=r->>'brand' and m.model=r->>'model')) then return 'notice_vehicle_rows_mismatch'; end if;
  if exists(select 1 from public.news_articles a where a.id<>candidate.id and a.status='published' and (
    exists(select 1 from jsonb_array_elements(a.payload->'sources') r where r->>'url'=i.url or r->>'item_id'=i.id)
    or (lower(a.payload->'notice_facts'->>'subject')=lower(f->>'subject')
      and left(a.payload->'notice_facts'->>'source_published_at',10)=left(f->>'source_published_at',10))))
    then return 'notice_event_already_published'; end if;
  return null;
end $$;

create or replace function public.news_guard_publication() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
declare cfg public.news_ai_config; notice_cfg public.news_notice_release_config; reason text;
begin
  new.artifact_hash := encode(sha256(convert_to(new.payload::text,'UTF8')),'hex');
  if tg_op='UPDATE' and old.status='published' then
    if new.payload is distinct from old.payload or new.status<>old.status or new.published_at is distinct from old.published_at
      or new.slug<>old.slug or new.cluster_id<>old.cluster_id then raise exception 'Published news is immutable'; end if;
    return new;
  end if;
  if new.status='published' then
    perform pg_advisory_xact_lock(72716491);
    select * into cfg from public.news_ai_config where id='production';
    if not found or not cfg.publication_enabled then raise exception 'News publication disabled'; end if;
    if (select count(*) from public.news_articles where status='published'
      and published_at>=date_trunc('day',now() at time zone 'UTC') at time zone 'UTC')>=cfg.daily_article_limit
      then raise exception 'News daily publication limit reached'; end if;
    if new.payload ? 'notice_facts' or new.payload ? 'notice_kind' or new.payload->>'editorial_recipe' like 'news-notice-%' then
      reason:=public.news_notice_release_error(new);
      if reason is not null then raise exception '%',reason; end if;
      select * into notice_cfg from public.news_notice_release_config where id='production';
      if (select count(*) from public.news_articles where status='published'
        and published_at>=date_trunc('day',now() at time zone 'UTC') at time zone 'UTC')>=notice_cfg.daily_limit
        then raise exception 'notice_daily_publication_limit'; end if;
      if not exists(select 1 from public.news_notice_publications r where r.article_id=new.id
        and r.artifact_hash=new.artifact_hash and r.source_hash=new.payload->'notice_facts'->>'source_hash'
        and r.policy=notice_cfg.policy and r.review_method=notice_cfg.review_method and r.transaction_id=txid_current()
        and r.source_snapshot_hash=encode(sha256(convert_to(public.news_notice_source_snapshot(new.id)::text,'UTF8')),'hex'))
        then raise exception 'notice_requires_transactional_publication'; end if;
    else
      -- Preserve the separate legacy article publication contract.
      if (select count(distinct kind) from public.news_quality_checks where article_id=new.id and passed
        and artifact_hash=new.artifact_hash and payload->>'policy_version'='news-editorial-2026-10-v2')<>3
        then raise exception 'Missing or stale news quality gates'; end if;
      if jsonb_typeof(new.payload->'sources') is distinct from 'array' or jsonb_array_length(new.payload->'sources')=0
        then raise exception 'News must have attributed evidence'; end if;
      if exists(select 1 from jsonb_array_elements(new.payload->'sources') ref where not exists(
        select 1 from public.news_article_sources s join public.news_items i on i.id=s.item_id
        where s.article_id=new.id and i.id=ref->>'item_id' and i.url=ref->>'url' and i.status='processed'
        and i.payload->>'access_status'='accessible' and nullif(i.payload->>'content_hash','') is not null))
        then raise exception 'News source evidence missing or inaccessible'; end if;
    end if;
    new.published_at:=clock_timestamp();
  end if;
  new.updated_at:=clock_timestamp();
  return new;
end $$;

create or replace function public.publish_news_notice(article_key text,expected_artifact_hash text,expected_payload jsonb,expected_source jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare a public.news_articles; i public.news_items; snapshot jsonb; reason text;
begin
  perform pg_advisory_xact_lock(72716491);
  select * into a from public.news_articles where id=article_key for update;
  if not found or a.artifact_hash is distinct from expected_artifact_hash or a.payload is distinct from expected_payload
    then raise exception 'notice_article_snapshot_changed'; end if;
  if a.status='published' and exists(select 1 from public.news_notice_publications where article_id=a.id and artifact_hash=a.artifact_hash)
    then return jsonb_build_object('published',true,'already_published',true); end if;
  if a.status<>'draft' then raise exception 'notice_release_requires_current_draft'; end if;
  perform 1 from public.news_ai_config where id='production' for share;
  perform 1 from public.news_notice_release_config where id='production' for share;
  select * into i from public.news_items where id=a.payload->'sources'->0->>'item_id' for share;
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
    txid_current(),'news-notice-2026-10-v1','deterministic_typed_notice_v1');
  update public.news_articles set status='published' where id=a.id;
  return jsonb_build_object('published',true,'already_published',false);
end $$;
revoke all on function public.news_notice_source_snapshot(text),public.news_notice_release_error(public.news_articles),
  public.news_guard_publication(),public.publish_news_notice(text,text,jsonb,jsonb) from public,anon,authenticated;
revoke all on function public.news_notice_source_snapshot(text),public.news_notice_release_error(public.news_articles) from service_role;
grant execute on function public.publish_news_notice(text,text,jsonb,jsonb) to service_role;
