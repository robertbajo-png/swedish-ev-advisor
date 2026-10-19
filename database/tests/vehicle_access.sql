-- Read-only verification for Supabase SQL Editor after migration 008.
begin read only;
set local statement_timeout = '30s';
do $role_checks$
declare
  role_name text;
  table_name text;
  expected_models bigint;
  expected_variants bigint;
  actual_count bigint;
begin
  select count(*) into expected_models from public.public_ev_models;
  select count(*) into expected_variants from public.public_ev_variants;
  foreach role_name in array array['anon', 'authenticated'] loop
    execute format('set local role %I', role_name);
    select count(*) into actual_count from public.public_ev_models;
    if actual_count <> expected_models then raise exception 'Public models changed for %', role_name; end if;
    select count(*) into actual_count from public.public_ev_variants;
    if actual_count <> expected_variants then raise exception 'Public variants changed for %', role_name; end if;
    foreach table_name in array array[
      'canonical_models', 'canonical_model_variants', 'extracted_variant_drafts',
      'manufacturer_sources', 'market_models', 'market_model_monthly_stats', 'model_aliases'
    ] loop
      begin
        execute format('select 1 from public.%I limit 1', table_name);
        raise exception 'Private table readable by %: %', role_name, table_name;
      exception when insufficient_privilege then null;
      end;
    end loop;
    reset role;
  end loop;
end
$role_checks$;
select
  'PASS: anon + authenticated restricted' as access_checks,
  (select count(*) from pg_class where relnamespace = 'public'::regnamespace
    and relname = any(array['canonical_models','canonical_model_variants','extracted_variant_drafts',
      'manufacturer_sources','market_models','market_model_monthly_stats','model_aliases'])
    and relrowsecurity) as rls_protected_tables,
  (select count(*) from public.public_ev_models) as public_models,
  (select count(*) from public.public_ev_variants) as public_variants;
rollback;
