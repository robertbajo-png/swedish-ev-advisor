-- Owner-only read-only checks AFTER migration 017; no activation or writes.
with private_tables as (
  select c.oid,c.relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname in ('news_notice_release_config','news_notice_publications')
), checks as (
  select '01 Notice tables private' as check_name,(count(*)=2 and bool_and(relrowsecurity))::text as result,true as required from private_tables
  union all select '02 Public roles denied notice tables',(not exists(
    select 1 from private_tables t cross join unnest(array['anon','authenticated']) r(role_name)
    where has_table_privilege(r.role_name,t.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
      or has_any_column_privilege(r.role_name,t.oid,'SELECT,INSERT,UPDATE,REFERENCES')))::text,true
  union all select '03 Worker read-only on notice controls',coalesce(bool_and(
    has_table_privilege('service_role',t.oid,'SELECT')
    and not has_table_privilege('service_role',t.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
    and not has_any_column_privilege('service_role',t.oid,'INSERT,UPDATE,REFERENCES')),false)::text,true from private_tables t
  union all select '04 Publication RPC service-only',(
    to_regprocedure('public.publish_news_notice(text,text,jsonb,jsonb)') is not null
    and has_function_privilege('service_role','public.publish_news_notice(text,text,jsonb,jsonb)','EXECUTE')
    and not has_function_privilege('anon','public.publish_news_notice(text,text,jsonb,jsonb)','EXECUTE')
    and not has_function_privilege('authenticated','public.publish_news_notice(text,text,jsonb,jsonb)','EXECUTE'))::text,true
  union all select '05 Internal helpers owner-only',(not exists(
    select 1 from unnest(array['anon','authenticated','service_role']) r(role_name)
    cross join unnest(array['public.news_notice_source_snapshot(text)','public.news_notice_release_error(public.news_articles)']) f(signature)
    where has_function_privilege(r.role_name,f.signature,'EXECUTE')))::text,true
  union all select '06 Notice policy matches',(count(*)=1 and bool_and(policy='news-notice-2026-10-v1' and review_method='deterministic_typed_notice_v1'))::text,true
    from public.news_notice_release_config where id='production'
  union all select '07 Public news read-only',bool_and(
    has_table_privilege(r.role_name,'public.public_news_articles','SELECT')
    and not has_table_privilege(r.role_name,'public.public_news_articles','INSERT,UPDATE,DELETE')
    and not has_any_column_privilege(r.role_name,'public.public_news_articles','INSERT,UPDATE'))::text,true
    from unnest(array['anon','authenticated']) r(role_name)
  union all select '08 Paid AI off',(count(*)=1 and bool_and(not enabled))::text,true from public.news_ai_config where id='production'
  union all select '09 Global publication off',(count(*)=1 and bool_and(not publication_enabled))::text,true from public.news_ai_config where id='production'
  union all select '10 Notice publication off',(count(*)=1 and bool_and(not enabled))::text,true from public.news_notice_release_config where id='production'
  union all select '11 Approved budget and model',(count(*)=1 and bool_and(daily_limit_micro_usd=250000 and monthly_limit_micro_usd=5000000 and model in ('gpt-5.4-mini','gpt-6-sol')))::text,true
    from public.news_ai_config where id='production'
  union all select '12 Published news',count(*)::text,false from public.public_news_articles
  union all select '13 Notice publication receipts',count(*)::text,false from public.news_notice_publications
  union all select '14 Open AI requests',count(*)::text,false from public.news_ai_requests where settled_at is null and budget_closed_at is null
)
select check_name,result,required from checks order by check_name;
