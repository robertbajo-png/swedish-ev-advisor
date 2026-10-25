-- Read-only checks after 007 + 012 + 013. Never activates AI or publication.
with private_tables as (
  select c.oid,c.relrowsecurity
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname in (
    'news_sources','news_ingestion_runs','news_items','news_story_clusters',
    'news_articles','news_article_sources','news_vehicle_links','news_quality_checks',
    'news_verification_requests','news_ai_config','news_ai_requests')
), checks as (
  select '01 Private tables' as check_name,
    (count(*)=11 and bool_and(relrowsecurity))::text as result from private_tables
  union all
  select '02 Public roles denied raw tables',(not exists(
    select 1 from private_tables t cross join unnest(array['anon','authenticated']) r(role_name)
    cross join unnest(array['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p(privilege)
    where has_table_privilege(r.role_name,t.oid,p.privilege)
       or has_any_column_privilege(r.role_name,t.oid,'SELECT,INSERT,UPDATE,REFERENCES')
  ))::text
  union all
  select '03 Worker cannot change budget',(not exists(
    select 1 from unnest(array['news_ai_config','news_ai_requests']) t(table_name)
    cross join unnest(array['INSERT','UPDATE','DELETE','TRUNCATE']) p(privilege)
    where has_table_privilege('service_role','public.'||t.table_name,p.privilege)
       or has_any_column_privilege('service_role','public.'||t.table_name,'INSERT,UPDATE')
  ))::text
  union all
  select '04 Budget RPCs private',(not exists(
    select 1 from unnest(array['anon','authenticated']) r(role_name)
    cross join unnest(array['public.reserve_news_ai(uuid,text,text,bigint,bigint,text)',
      'public.settle_news_ai(uuid,bigint,bigint,jsonb)','public.publish_news_article(text,integer)']) f(signature)
    where has_function_privilege(r.role_name,f.signature,'EXECUTE')
  ))::text
  union all
  select '05 Public news view read-only',bool_and(
    has_table_privilege(r.role_name,'public.public_news_articles','SELECT')
    and not has_table_privilege(r.role_name,'public.public_news_articles','INSERT,UPDATE,DELETE')
  )::text from unnest(array['anon','authenticated']) r(role_name)
  union all
  select '06 AI disabled',(not enabled)::text from public.news_ai_config where id='production'
  union all
  select '07 Publication disabled',(not publication_enabled)::text from public.news_ai_config where id='production'
  union all
  select '08 Daily budget USD',(daily_limit_micro_usd::numeric/1000000)::text from public.news_ai_config where id='production'
  union all
  select '09 Monthly budget USD',(monthly_limit_micro_usd::numeric/1000000)::text from public.news_ai_config where id='production'
  union all
  select '10 Published news',count(*)::text from public.public_news_articles
  union all
  select '11 Public vehicle variants',count(*)::text from public.public_ev_variants
  union all
  select '12 Unknown usage closure owner-only',(not exists(
    select 1 from unnest(array['anon','authenticated','service_role']) r(role_name)
    where has_function_privilege(r.role_name,'public.close_news_unknown_usage_budget(uuid,bigint,text,text)','EXECUTE')
  ))::text
  union all
  select '13 Unknown usage fully counted',(not exists(
    select 1 from public.news_ai_requests where budget_closed_at is not null
    and (charged_micro_usd <> reserved_micro_usd or settled_at is not null
      or input_tokens is not null or output_tokens is not null or response_payload is not null)
  ))::text
  union all
  select '14 Unresolved AI requests',count(*)::text from public.news_ai_requests
    where settled_at is null and budget_closed_at is null
  union all
  select '15 Conservatively closed requests',count(*)::text from public.news_ai_requests
    where budget_closed_at is not null
)
select check_name,result from checks order by check_name;
