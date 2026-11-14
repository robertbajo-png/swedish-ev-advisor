-- Preserve manufacturer AC ratings such as 10.5 kW without rounding.
begin;
set local search_path=pg_catalog;
set local lock_timeout='5s';
set local statement_timeout='60s';

do $decimal_ac$
declare
  view_oid oid := 'public.public_ev_variants'::regclass;
  view_sql text;
  view_owner text;
  view_options text[];
  view_comment text;
  view_acl jsonb;
  before_variants jsonb;
  before_drafts jsonb;
  before_public jsonb;
  before_policies jsonb;
  before_rls jsonb;
  relation_name text;
  column_type text;
  entry record;
  grantee_name text;
begin
  perform pg_advisory_xact_lock(7240016);
  lock table public.canonical_model_variants,public.extracted_variant_drafts in access exclusive mode;
  select pg_get_viewdef(c.oid,true),r.rolname,c.reloptions,obj_description(c.oid,'pg_class')
    into strict view_sql,view_owner,view_options,view_comment
    from pg_class c join pg_roles r on r.oid=c.relowner
    where c.oid=view_oid and c.relkind='v';
  if view_owner<>current_user or exists (
    select 1 from unnest(coalesce(view_options,array[]::text[])) o
    where o not in ('security_barrier=true','security_invoker=false')) then
    raise exception 'Unexpected public view owner or security options';
  end if;
  if exists (select 1 from pg_attribute where attrelid=view_oid and attnum>0 and not attisdropped
    and (attacl is not null or col_description(view_oid,attnum) is not null)) then
    raise exception 'Column-level view metadata needs a separate migration';
  end if;
  select coalesce(jsonb_agg(jsonb_build_object('grantee',x.grantee,'privilege',x.privilege_type,
    'grantable',x.is_grantable) order by x.grantee,x.privilege_type),'[]'::jsonb)
    into view_acl from pg_class c cross join lateral aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x
    where c.oid=view_oid;
  if exists (select 1 from pg_class c cross join lateral aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x
    where c.oid=view_oid and x.grantor<>c.relowner) then
    raise exception 'Unexpected public view grantor';
  end if;
  select coalesce(jsonb_agg(to_jsonb(v) order by v.id),'[]'::jsonb) into before_variants from public.canonical_model_variants v;
  select coalesce(jsonb_agg(to_jsonb(d) order by d.id),'[]'::jsonb) into before_drafts from public.extracted_variant_drafts d;
  execute 'select coalesce(jsonb_agg(to_jsonb(v) order by v.id),''[]''::jsonb) from public.public_ev_variants v' into before_public;
  select coalesce(jsonb_agg(to_jsonb(p) order by schemaname,tablename,policyname),'[]'::jsonb)
    into before_policies from pg_policies p where schemaname='public';
  select jsonb_agg(jsonb_build_array(c.oid,c.relrowsecurity,c.relforcerowsecurity) order by c.oid)
    into before_rls from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in ('r','p');
  foreach relation_name in array array['canonical_model_variants','extracted_variant_drafts'] loop
    select format_type(a.atttypid,a.atttypmod) into strict column_type from pg_attribute a
      where a.attrelid=('public.'||relation_name)::regclass and a.attname='ac_charge_kw' and not a.attisdropped;
    if column_type not in ('integer','numeric(5,2)') then raise exception 'Unexpected AC column type: %',column_type; end if;
  end loop;
  -- RESTRICT deliberately refuses any unreviewed dependent view/function.
  -- Everything is transactional, including recreation and original grants.
  drop view public.public_ev_variants restrict;
  alter table public.canonical_model_variants alter column ac_charge_kw type numeric(5,2) using ac_charge_kw::numeric(5,2);
  alter table public.extracted_variant_drafts alter column ac_charge_kw type numeric(5,2) using ac_charge_kw::numeric(5,2);
  execute 'create view public.public_ev_variants as '||view_sql;
  foreach relation_name in array coalesce(view_options,array[]::text[]) loop
    execute 'alter view public.public_ev_variants set ('||relation_name||')';
  end loop;
  execute format('comment on view public.public_ev_variants is %L',view_comment);
  for entry in select distinct x.grantee from pg_class c cross join lateral
    aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x where c.oid='public.public_ev_variants'::regclass loop
    grantee_name:=case when entry.grantee=0 then 'PUBLIC' else quote_ident(pg_get_userbyid(entry.grantee)) end;
    execute 'revoke all on public.public_ev_variants from '||grantee_name;
  end loop;
  for entry in select * from jsonb_to_recordset(view_acl) as a(grantee oid,privilege text,grantable boolean) loop
    grantee_name:=case when entry.grantee=0 then 'PUBLIC' else quote_ident(pg_get_userbyid(entry.grantee)) end;
    execute 'grant '||entry.privilege||' on public.public_ev_variants to '||grantee_name||case when entry.grantable then ' with grant option' else '' end;
  end loop;
  if before_variants is distinct from (select coalesce(jsonb_agg(to_jsonb(v) order by v.id),'[]'::jsonb) from public.canonical_model_variants v)
    or before_drafts is distinct from (select coalesce(jsonb_agg(to_jsonb(d) order by d.id),'[]'::jsonb) from public.extracted_variant_drafts d)
    or before_public is distinct from (select coalesce(jsonb_agg(to_jsonb(v) order by v.id),'[]'::jsonb) from public.public_ev_variants v) then
    raise exception 'AC migration changed existing facts or publication scope';
  end if;
  if before_policies is distinct from (select coalesce(jsonb_agg(to_jsonb(p) order by schemaname,tablename,policyname),'[]'::jsonb) from pg_policies p where schemaname='public')
    or before_rls is distinct from (select jsonb_agg(jsonb_build_array(c.oid,c.relrowsecurity,c.relforcerowsecurity) order by c.oid) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in ('r','p')) then
    raise exception 'AC migration changed private access boundaries';
  end if;
  if view_sql is distinct from pg_get_viewdef('public.public_ev_variants'::regclass,true)
    or view_options is distinct from (select reloptions from pg_class where oid='public.public_ev_variants'::regclass)
    or view_acl is distinct from (select coalesce(jsonb_agg(jsonb_build_object('grantee',x.grantee,'privilege',x.privilege_type,
      'grantable',x.is_grantable) order by x.grantee,x.privilege_type),'[]'::jsonb)
      from pg_class c cross join lateral aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x where c.oid='public.public_ev_variants'::regclass) then
    raise exception 'AC migration changed public definition or permissions';
  end if;
end
$decimal_ac$;
notify pgrst,'reload schema';
commit;
