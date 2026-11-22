-- Preserve manufacturer's exact vehicle peak DC rating. Do not round on write.
begin;
set local search_path=pg_catalog;
set local lock_timeout='5s';
set local statement_timeout='60s';

do $exact_dc$
declare
  catalog oid := 'public.public_ev_variants'::regclass;
  catalog_definition text;
  catalog_owner text;
  catalog_options text[];
  catalog_comment text;
  before_grants jsonb;
  before_columns jsonb;
  before_private jsonb;
  before_public jsonb;
  column_type text;
  target text;
  option_clause text;
  entry record;
  grantee_name text;
begin
  perform pg_advisory_xact_lock(7240016);
  lock table public.canonical_model_variants,public.extracted_variant_drafts in access exclusive mode;
  select pg_get_viewdef(catalog,true), pg_get_userbyid(relowner), reloptions, obj_description(catalog,'pg_class')
    into strict catalog_definition,catalog_owner,catalog_options,catalog_comment
    from pg_class where oid=catalog and relkind='v';
  if catalog_owner<>current_user or not coalesce(catalog_options,array[]::text[]) @> array['security_barrier=true']
    or exists (select 1 from unnest(catalog_options) o where o not in ('security_barrier=true','security_invoker=false')) then
    raise exception 'Unexpected public catalog owner or security options';
  end if;
  if exists(select 1 from pg_attribute where attrelid=catalog and attnum>0 and not attisdropped
    and (attacl is not null or col_description(catalog,attnum) is not null)) then
    raise exception 'Column-level catalog metadata needs separate review';
  end if;
  select coalesce(jsonb_agg(to_jsonb(x) order by x.grantee,x.privilege_type),'[]'::jsonb)
    into before_grants from pg_class c cross join lateral aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x
    where c.oid=catalog;
  if exists (select 1 from jsonb_to_recordset(before_grants) as a(grantor oid)
      where a.grantor <> (select relowner from pg_class where oid=catalog)) then
    raise exception 'Unexpected public catalog grantor';
  end if;
  select jsonb_agg(jsonb_build_array(attname,case when attname='dc_charge_kw' then 'numeric'
    else format_type(atttypid,atttypmod) end) order by attnum) into before_columns
    from pg_attribute where attrelid=catalog and attnum>0 and not attisdropped;
  select jsonb_build_array(
    (select coalesce(jsonb_agg(to_jsonb(v) order by v.id),'[]'::jsonb) from public.canonical_model_variants v),
    (select coalesce(jsonb_agg(to_jsonb(d) order by d.id),'[]'::jsonb) from public.extracted_variant_drafts d)
  ) into before_private;
  select coalesce(jsonb_agg(to_jsonb(v) order by v.id),'[]'::jsonb) into before_public from public.public_ev_variants v;

  foreach target in array array['canonical_model_variants','extracted_variant_drafts'] loop
    select format_type(att.atttypid,att.atttypmod) into strict column_type
      from pg_attribute att where att.attrelid=('public.'||target)::regclass and att.attname='dc_charge_kw' and not att.attisdropped;
    if column_type not in ('integer','numeric')
      or not (select relrowsecurity from pg_class where oid=('public.'||target)::regclass)
      or has_any_column_privilege('anon','public.'||target,'SELECT')
      or has_any_column_privilege('authenticated','public.'||target,'SELECT') then
      raise exception 'Unexpected DC storage or private access boundary for %',target;
    end if;
  end loop;

  -- Refuse unknown dependents rather than cascading away any catalog consumer.
  drop view public.public_ev_variants restrict;
  foreach target in array array['canonical_model_variants','extracted_variant_drafts'] loop
    execute format('alter table public.%I alter column dc_charge_kw type numeric using dc_charge_kw::numeric,
      drop constraint if exists exact_dc_charge_kw', target);
    -- A numeric typmod would round silently before checking the supplied value.
    execute format('alter table public.%I add constraint exact_dc_charge_kw check (
      dc_charge_kw is null or (dc_charge_kw between 20 and 600 and dc_charge_kw=trunc(dc_charge_kw,2)))',target);
  end loop;
  execute 'create view public.public_ev_variants as '||catalog_definition;
  foreach option_clause in array catalog_options loop
    execute 'alter view public.public_ev_variants set ('||option_clause||')';
  end loop;
  execute format('comment on view public.public_ev_variants is %L',catalog_comment);
  for entry in select distinct x.grantee from pg_class c cross join lateral
    aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x where c.oid='public.public_ev_variants'::regclass loop
    grantee_name:=case when entry.grantee=0 then 'PUBLIC' else quote_ident(pg_get_userbyid(entry.grantee)) end;
    execute 'revoke all on public.public_ev_variants from '||grantee_name;
  end loop;
  for entry in select * from jsonb_to_recordset(before_grants) as a(grantee oid,privilege_type text,is_grantable boolean) loop
    grantee_name:=case when entry.grantee=0 then 'PUBLIC' else quote_ident(pg_get_userbyid(entry.grantee)) end;
    execute 'grant '||entry.privilege_type||' on public.public_ev_variants to '||grantee_name
      ||case when entry.is_grantable then ' with grant option' else '' end;
  end loop;
  catalog:='public.public_ev_variants'::regclass;
  if before_private is distinct from jsonb_build_array(
      (select coalesce(jsonb_agg(to_jsonb(v) order by v.id),'[]'::jsonb) from public.canonical_model_variants v),
      (select coalesce(jsonb_agg(to_jsonb(d) order by d.id),'[]'::jsonb) from public.extracted_variant_drafts d))
    or before_public is distinct from (select coalesce(jsonb_agg(to_jsonb(v) order by v.id),'[]'::jsonb) from public.public_ev_variants v) then
    raise exception 'DC migration changed existing facts or publication scope';
  end if;
  if catalog_definition is distinct from pg_get_viewdef(catalog,true)
    or catalog_options is distinct from (select reloptions from pg_class where oid=catalog)
    or catalog_comment is distinct from obj_description(catalog,'pg_class')
    or before_columns is distinct from (select jsonb_agg(jsonb_build_array(attname,format_type(atttypid,atttypmod)) order by attnum)
      from pg_attribute where attrelid=catalog and attnum>0 and not attisdropped)
    or before_grants is distinct from (select coalesce(jsonb_agg(to_jsonb(x) order by x.grantee,x.privilege_type),'[]'::jsonb)
      from pg_class c cross join lateral aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x where c.oid=catalog) then
    raise exception 'DC migration changed public catalog definition or grants';
  end if;
end
$exact_dc$;
notify pgrst,'reload schema';
commit;
