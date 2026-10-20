-- Complete the deployed legacy catalog without changing existing facts or ACLs.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.canonical_models
  add column if not exists image_url text,
  add column if not exists image_source_url text,
  add column if not exists image_verified_at timestamptz;
alter table public.manufacturer_sources
  add column if not exists source_name text,
  add column if not exists source_authority text,
  add column if not exists authorization_evidence_url text;
alter table public.canonical_model_variants
  add column if not exists price_type text,
  add column if not exists price_valid_until date,
  add column if not exists wltp_consumption_kwh_100km numeric(4,1);
alter table public.extracted_variant_drafts
  add column if not exists price_type text,
  add column if not exists price_valid_until date,
  add column if not exists wltp_consumption_kwh_100km numeric(4,1);

do $catalog_contract$
declare
  target text;
  relation_name text;
  column_name text;
  existing_columns text[];
  projection text;
  supported text[] := array[
    'id','canonical_model_id','brand','model','body_type','market_seen','available_confirmed',
    'discontinued_candidate','coming_or_low_volume','variant_name','price_sek','wltp_range_km',
    'battery_kwh','dc_charge_kw','ac_charge_kw','boot_liters','tow_kg','seats','drivetrain',
    'source_url','source_hash','source_quote','extraction_confidence','validation_status',
    'review_approved_by','review_reason','review_promoted_at','verified_at',
    'price_type','price_valid_until','wltp_consumption_kwh_100km','source_name','image_url','image_source_url'];
begin
  foreach target in array array['canonical_model_variants','extracted_variant_drafts'] loop
    if not exists (select 1 from pg_constraint where conrelid = ('public.' || target)::regclass
      and conname = target || '_catalog_price_type_check') then
      execute format('alter table public.%I add constraint %I check (price_type is null or price_type in (''list_price'',''campaign_price'',''dealer_offer''))', target, target || '_catalog_price_type_check');
    end if;
    if not exists (select 1 from pg_constraint where conrelid = ('public.' || target)::regclass
      and conname = target || '_catalog_consumption_check') then
      execute format('alter table public.%I add constraint %I check (wltp_consumption_kwh_100km is null or wltp_consumption_kwh_100km between 5 and 50)', target, target || '_catalog_consumption_check');
    end if;
  end loop;
  foreach relation_name in array array['canonical_models','canonical_model_variants','extracted_variant_drafts',
    'manufacturer_sources','market_models','market_model_monthly_stats','model_aliases'] loop
    if not (select relrowsecurity from pg_class where oid = ('public.' || relation_name)::regclass)
      or has_any_column_privilege('anon', 'public.' || relation_name, 'SELECT')
      or has_any_column_privilege('authenticated', 'public.' || relation_name, 'SELECT') then
      raise exception 'Apply the private access boundary before catalog migration: %', relation_name;
    end if;
  end loop;
  if not exists (select 1 from pg_class c join pg_roles r on r.oid = c.relowner
    where c.oid = 'public.public_ev_variants'::regclass and (r.rolsuper or r.rolbypassrls)
    and not coalesce(c.reloptions, array[]::text[]) @> array['security_invoker=true']) then
    raise exception 'Expected an owner-privileged public catalog view';
  end if;

  -- Preserve existing column order, dependent objects and ACLs; append only new fields.
  select array_agg(attname::text order by attnum) into existing_columns from pg_attribute
    where attrelid = 'public.public_ev_variants'::regclass and attnum > 0 and not attisdropped;
  if not existing_columns <@ supported then raise exception 'Unexpected public catalog columns'; end if;
  foreach column_name in array supported loop
    if not column_name = any(existing_columns) then existing_columns := array_append(existing_columns, column_name); end if;
  end loop;
  select string_agg(format('r.%I', name), ', ' order by position) into projection
    from unnest(existing_columns) with ordinality as cols(name, position);
  execute 'create or replace view public.public_ev_variants with (security_barrier=true) as select ' || projection || $view$
    from (
      select cv.id, cv.canonical_model_id, cm.brand, cm.model, cm.body_type,
        cm.market_seen, cm.available_confirmed, cm.discontinued_candidate, cm.coming_or_low_volume,
        cv.variant_name, cv.price_sek, cv.wltp_range_km, cv.battery_kwh, cv.dc_charge_kw,
        cv.ac_charge_kw, cv.boot_liters, cv.tow_kg, cv.seats, cv.drivetrain,
        coalesce(cv.source_url, ms.url) as source_url,
        coalesce(cv.source_hash, ms.content_hash) as source_hash,
        cv.source_quote, cv.extraction_confidence, cv.validation_status,
        cv.review_approved_by, cv.review_reason, cv.review_promoted_at, ms.verified_at,
        cv.price_type, cv.price_valid_until, cv.wltp_consumption_kwh_100km,
        coalesce(ms.source_name, ms.title, cm.brand) as source_name, cm.image_url, cm.image_source_url
      from public.canonical_model_variants cv
      join public.canonical_models cm on cm.id = cv.canonical_model_id
      left join public.manufacturer_sources ms on ms.id = cv.source_id
      where cm.validation_status <> 'rejected'
        and cv.validation_status in ('published','published_reviewed')
    ) r
  $view$;
end
$catalog_contract$;

notify pgrst, 'reload schema';
commit;
