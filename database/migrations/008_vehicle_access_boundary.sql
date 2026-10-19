-- Keep private vehicle data server-only; expose only the existing filtered views.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

do $vehicle_access$
declare
  table_name text;
  view_name text;
  columns_sql text;
  view_owner oid;
begin
  if not exists (select 1 from pg_roles where rolname = 'service_role' and rolbypassrls) then
    raise exception 'service_role must exist and bypass RLS for server ingestion';
  end if;

  foreach view_name in array array['public_ev_models', 'public_ev_variants'] loop
    select relowner into view_owner from pg_class
      where oid = to_regclass(format('public.%I', view_name)) and relkind = 'v'
      and not coalesce(reloptions, array[]::text[]) @> array['security_invoker=true'];
    if view_owner is null or not exists (
      select 1 from pg_roles where oid = view_owner and (rolsuper or rolbypassrls)
    ) then
      raise exception 'Expected an existing owner-privileged public view: %', view_name;
    end if;
  end loop;

  foreach table_name in array array[
    'canonical_models', 'canonical_model_variants', 'extracted_variant_drafts',
    'manufacturer_sources', 'market_models', 'market_model_monthly_stats', 'model_aliases'
  ] loop
    if to_regclass(format('public.%I', table_name)) is null then
      raise exception 'Required vehicle table missing: %', table_name;
    end if;
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all privileges on table public.%I from public, anon, authenticated', table_name);
    select string_agg(quote_ident(attname), ', ' order by attnum) into columns_sql
      from pg_attribute where attrelid = to_regclass(format('public.%I', table_name))
      and attnum > 0 and not attisdropped;
    execute format('revoke all privileges (%s) on table public.%I from public, anon, authenticated', columns_sql, table_name);
    execute format('grant select, insert, update, delete on table public.%I to service_role', table_name);
  end loop;

  foreach view_name in array array['public_ev_models', 'public_ev_variants'] loop
    execute format('alter view public.%I set (security_barrier = true)', view_name);
    execute format('revoke all privileges on table public.%I from public, anon, authenticated', view_name);
    select string_agg(quote_ident(attname), ', ' order by attnum) into columns_sql
      from pg_attribute where attrelid = to_regclass(format('public.%I', view_name))
      and attnum > 0 and not attisdropped;
    execute format('revoke all privileges (%s) on table public.%I from public, anon, authenticated', columns_sql, view_name);
    execute format('grant select on table public.%I to anon, authenticated, service_role', view_name);
  end loop;
end
$vehicle_access$;

-- New tables/views stay private until a migration explicitly grants public access.
alter default privileges for role postgres in schema public
  revoke all privileges on tables from public, anon, authenticated;

do $verify_access$
declare
  table_name text;
  view_name text;
  role_name text;
  privilege_name text;
begin
  foreach table_name in array array[
    'canonical_models', 'canonical_model_variants', 'extracted_variant_drafts',
    'manufacturer_sources', 'market_models', 'market_model_monthly_stats', 'model_aliases'
  ] loop
    foreach role_name in array array['anon', 'authenticated'] loop
      foreach privilege_name in array array['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] loop
        if has_table_privilege(role_name, format('public.%I', table_name), privilege_name) then
          raise exception 'Unexpected % access for % on %', privilege_name, role_name, table_name;
        end if;
      end loop;
      foreach privilege_name in array array['SELECT', 'INSERT', 'UPDATE', 'REFERENCES'] loop
        if has_any_column_privilege(role_name, format('public.%I', table_name), privilege_name) then
          raise exception 'Unexpected column % access for % on %', privilege_name, role_name, table_name;
        end if;
      end loop;
    end loop;
    foreach privilege_name in array array['SELECT', 'INSERT', 'UPDATE', 'DELETE'] loop
      if not has_table_privilege('service_role', format('public.%I', table_name), privilege_name) then
        raise exception 'Server ingestion lost % on %', privilege_name, table_name;
      end if;
    end loop;
  end loop;
  foreach view_name in array array['public_ev_models', 'public_ev_variants'] loop
    foreach role_name in array array['anon', 'authenticated'] loop
      if not has_table_privilege(role_name, format('public.%I', view_name), 'SELECT') then
        raise exception 'Public SELECT missing for % on %', role_name, view_name;
      end if;
      foreach privilege_name in array array['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] loop
        if has_table_privilege(role_name, format('public.%I', view_name), privilege_name) then
          raise exception 'Public view is not read-only: % % %', role_name, view_name, privilege_name;
        end if;
      end loop;
      foreach privilege_name in array array['INSERT', 'UPDATE', 'REFERENCES'] loop
        if has_any_column_privilege(role_name, format('public.%I', view_name), privilege_name) then
          raise exception 'Public view has writable columns: % %', role_name, view_name;
        end if;
      end loop;
    end loop;
  end loop;
end
$verify_access$;

notify pgrst, 'reload schema';
commit;
