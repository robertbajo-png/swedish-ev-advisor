create extension if not exists pgcrypto;

do $$ begin
  create type validation_status as enum ('draft', 'extracted', 'validated', 'published', 'published_reviewed', 'rejected', 'needs_review', 'verified', 'blocked', 'queued');
exception
  when duplicate_object then null;
end $$;

do $$ begin
  alter type validation_status add value if not exists 'published_reviewed';
  alter type validation_status add value if not exists 'needs_review';
  alter type validation_status add value if not exists 'verified';
  alter type validation_status add value if not exists 'blocked';
  alter type validation_status add value if not exists 'queued';
exception
  when duplicate_object then null;
end $$;

do $$ begin
  create type source_type as enum ('manufacturer_page', 'importer_page', 'price_list_pdf', 'technical_pdf', 'configurator', 'mobility_sweden_export', 'model_page', 'specs_page', 'price_list', 'fleet_page', 'manufacturer_specs_page', 'manufacturer_model_page', 'manufacturer_configurator', 'manufacturer_price_list', 'manufacturer_rendered_model_page', 'manufacturer_indexed_model_page', 'manufacturer_official_override_source', 'authorized_dealer_model_page', 'authorized_dealer_stock_page');
exception
  when duplicate_object then null;
end $$;

do $$ begin
  alter type source_type add value if not exists 'model_page';
  alter type source_type add value if not exists 'specs_page';
  alter type source_type add value if not exists 'price_list';
  alter type source_type add value if not exists 'fleet_page';
  alter type source_type add value if not exists 'manufacturer_specs_page';
  alter type source_type add value if not exists 'manufacturer_model_page';
  alter type source_type add value if not exists 'manufacturer_configurator';
  alter type source_type add value if not exists 'manufacturer_price_list';
  alter type source_type add value if not exists 'manufacturer_rendered_model_page';
  alter type source_type add value if not exists 'manufacturer_indexed_model_page';
  alter type source_type add value if not exists 'manufacturer_official_override_source';
  alter type source_type add value if not exists 'authorized_dealer_model_page';
  alter type source_type add value if not exists 'authorized_dealer_stock_page';
exception
  when duplicate_object then null;
end $$;

create table if not exists canonical_models (
  id uuid primary key default gen_random_uuid(),
  brand text not null,
  model text not null,
  normalized_brand text not null,
  normalized_model text not null,
  body_type text,
  market_seen boolean not null default false,
  available_confirmed boolean not null default false,
  discontinued_candidate boolean not null default false,
  coming_or_low_volume boolean not null default false,
  image_url text,
  image_source_url text,
  image_verified_at timestamptz,
  validation_status validation_status not null default 'draft',
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (normalized_brand, normalized_model)
);

create table if not exists market_models (
  id uuid primary key default gen_random_uuid(),
  brand_raw text not null,
  model_raw text not null,
  fuel_type_raw text not null,
  normalized_brand text not null,
  normalized_model text not null,
  model_group text,
  needs_mapping boolean not null default false,
  canonical_model_id uuid references canonical_models(id),
  first_seen_month date,
  last_seen_month date,
  registrations_last_month integer not null default 0,
  registrations_ytd integer not null default 0,
  registrations_12m integer,
  source_name text not null default 'Mobility Sweden',
  source_url text not null default 'https://mobilitysweden.se/statistik/databas-nyregistreringar',
  imported_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint market_models_registrations_nonnegative check (
    registrations_last_month >= 0 and registrations_ytd >= 0 and
    (registrations_12m is null or registrations_12m >= 0)
  ),
  unique (normalized_brand, normalized_model, fuel_type_raw)
);

create index if not exists market_models_canonical_idx on market_models(canonical_model_id);
create index if not exists market_models_needs_mapping_idx on market_models(needs_mapping) where needs_mapping = true;

create table if not exists market_model_monthly_stats (
  id uuid primary key default gen_random_uuid(),
  market_model_id uuid not null references market_models(id) on delete cascade,
  month date not null,
  brand_raw text not null,
  model_raw text not null,
  fuel_type_raw text not null,
  registrations integer not null default 0,
  private_registrations integer,
  company_registrations integer,
  county text,
  municipality text,
  imported_at timestamptz not null default now(),
  constraint monthly_registrations_nonnegative check (registrations >= 0),
  unique nulls not distinct (market_model_id, month, county, municipality)
);

create index if not exists market_model_monthly_stats_month_idx on market_model_monthly_stats(month);

create table if not exists model_aliases (
  id uuid primary key default gen_random_uuid(),
  canonical_model_id uuid references canonical_models(id) on delete cascade,
  brand_raw text not null,
  model_raw text not null,
  normalized_brand text not null,
  normalized_model text not null,
  alias_rule text,
  model_group text,
  needs_mapping boolean not null default false,
  confidence numeric(4,3) not null default 1.0,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint alias_confidence_range check (confidence >= 0 and confidence <= 1),
  constraint alias_requires_mapping_or_canonical check (
    needs_mapping = true or canonical_model_id is not null
  ),
  unique (normalized_brand, normalized_model)
);

create index if not exists model_aliases_needs_mapping_idx on model_aliases(needs_mapping) where needs_mapping = true;

create table if not exists manufacturer_sources (
  id uuid primary key default gen_random_uuid(),
  canonical_model_id uuid references canonical_models(id) on delete cascade,
  brand text not null,
  model text not null,
  source_type source_type not null,
  url text not null,
  title text,
  country text not null default 'SE',
  language text not null default 'sv',
  fetched_at timestamptz,
  content_hash text,
  extraction_status validation_status not null default 'draft',
  extraction_confidence numeric(4,3),
  http_status integer,
  final_url text,
  source_validation text not null default 'needs_discovery',
  source_authority text not null default 'manufacturer',
  authorization_evidence_url text,
  source_name text,
  is_primary boolean not null default false,
  extracted_payload jsonb,
  validation_errors jsonb,
  verified_by text,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint source_confidence_range check (
    extraction_confidence is null or (extraction_confidence >= 0 and extraction_confidence <= 1)
  ),
  constraint manufacturer_sources_authority_check check (
    source_authority in ('manufacturer', 'importer', 'authorized_dealer', 'public_authority')
  ),
  unique (url)
);

create index if not exists manufacturer_sources_model_idx on manufacturer_sources(canonical_model_id);
create index if not exists manufacturer_sources_status_idx on manufacturer_sources(extraction_status);
create index if not exists manufacturer_sources_validation_idx on manufacturer_sources(source_validation);

create table if not exists extracted_variant_drafts (
  id uuid primary key default gen_random_uuid(),
  canonical_model_id uuid references canonical_models(id) on delete cascade,
  source_id uuid references manufacturer_sources(id) on delete set null,
  brand text not null,
  model text not null,
  variant_name text not null,
  price_sek integer,
  price_type text,
  price_valid_until date,
  wltp_range_km integer,
  wltp_consumption_kwh_100km numeric(4,1),
  battery_kwh numeric(5,2),
  dc_charge_kw integer,
  ac_charge_kw integer,
  boot_liters integer,
  tow_kg integer,
  seats integer,
  drivetrain text,
  source_url text not null,
  source_quote text,
  source_hash text,
  extraction_confidence numeric(4,3) not null default 0,
  extraction_payload jsonb,
  validation_status validation_status not null default 'extracted',
  validation_errors jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint draft_confidence_range check (extraction_confidence >= 0 and extraction_confidence <= 1),
  constraint extracted_variant_price_type_check check (
    price_type is null or price_type in ('list_price', 'campaign_price', 'dealer_offer')
  ),
  constraint extracted_variant_values_valid check (
    (price_sek is null or price_sek between 100000 and 3000000) and
    (wltp_range_km is null or wltp_range_km between 50 and 1200) and
    (wltp_consumption_kwh_100km is null or wltp_consumption_kwh_100km between 5 and 50) and
    (dc_charge_kw is null or dc_charge_kw between 20 and 600) and
    (boot_liters is null or boot_liters between 50 and 3500) and
    (tow_kg is null or tow_kg between 0 and 4000) and
    (seats is null or seats between 1 and 9)
  )
);

create index if not exists extracted_variant_drafts_model_idx on extracted_variant_drafts(canonical_model_id);
create index if not exists extracted_variant_drafts_status_idx on extracted_variant_drafts(validation_status);
create unique index if not exists extracted_variant_drafts_source_variant_idx
  on extracted_variant_drafts(source_url, variant_name);

create table if not exists canonical_model_variants (
  id uuid primary key default gen_random_uuid(),
  canonical_model_id uuid not null references canonical_models(id) on delete cascade,
  variant_name text not null,
  price_sek integer,
  price_type text,
  price_valid_until date,
  wltp_range_km integer,
  wltp_consumption_kwh_100km numeric(4,1),
  battery_kwh numeric(5,2),
  dc_charge_kw integer,
  ac_charge_kw integer,
  boot_liters integer,
  tow_kg integer,
  seats integer,
  drivetrain text,
  source_url text,
  source_hash text,
  source_quote text,
  extraction_confidence numeric(4,3),
  review_approved_by text,
  review_reason text,
  review_promoted_at timestamptz,
  source_id uuid references manufacturer_sources(id),
  validation_status validation_status not null default 'draft',
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint canonical_variant_values_valid check (
    (price_sek is null or price_sek between 100000 and 3000000) and
    (wltp_range_km is null or wltp_range_km between 50 and 1200) and
    (wltp_consumption_kwh_100km is null or wltp_consumption_kwh_100km between 5 and 50) and
    (dc_charge_kw is null or dc_charge_kw between 20 and 600) and
    (boot_liters is null or boot_liters between 50 and 3500) and
    (tow_kg is null or tow_kg between 0 and 4000) and
    (seats is null or seats between 1 and 9)
  ),
  constraint canonical_variant_price_type_check check (
    price_type is null or price_type in ('list_price', 'campaign_price', 'dealer_offer')
  ),
  unique (canonical_model_id, variant_name)
);

create index if not exists canonical_model_variants_public_idx
  on canonical_model_variants(canonical_model_id, validation_status)
  where validation_status in ('published', 'published_reviewed');

create or replace view public_ev_models as
select
  cm.id,
  cm.brand,
  cm.model,
  cm.body_type,
  cm.market_seen,
  cm.available_confirmed,
  cm.discontinued_candidate,
  cm.coming_or_low_volume,
  cm.image_url,
  cm.image_source_url,
  cm.image_verified_at,
  cm.published_at
from canonical_models cm
where cm.validation_status <> 'rejected'
  and exists (
    select 1
    from canonical_model_variants cv
    where cv.canonical_model_id = cm.id
      and cv.validation_status in ('published', 'published_reviewed')
  );

create or replace view public_ev_variants as
select
  cv.id,
  cv.canonical_model_id,
  cm.brand,
  cm.model,
  cm.body_type,
  cm.market_seen,
  cm.available_confirmed,
  cm.discontinued_candidate,
  cm.coming_or_low_volume,
  cm.image_url,
  cm.image_source_url,
  cv.variant_name,
  cv.price_sek,
  cv.price_type,
  cv.price_valid_until,
  cv.wltp_range_km,
  cv.wltp_consumption_kwh_100km,
  cv.battery_kwh,
  cv.dc_charge_kw,
  cv.ac_charge_kw,
  cv.boot_liters,
  cv.tow_kg,
  cv.seats,
  cv.drivetrain,
  coalesce(cv.source_url, ms.url) as source_url,
  coalesce(ms.source_name, ms.title, cm.brand) as source_name,
  coalesce(cv.source_hash, ms.content_hash) as source_hash,
  cv.source_quote,
  cv.extraction_confidence,
  cv.validation_status,
  cv.review_approved_by,
  cv.review_reason,
  cv.review_promoted_at,
  ms.verified_at
from canonical_model_variants cv
join canonical_models cm on cm.id = cv.canonical_model_id
left join manufacturer_sources ms on ms.id = cv.source_id
where cm.validation_status <> 'rejected'
  and cv.validation_status in ('published', 'published_reviewed');

grant select on public_ev_models to anon, authenticated;
grant select on public_ev_variants to anon, authenticated;

-- Keep the fresh-install access boundary identical to migration 008.
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

-- Keep fresh installations aligned with migration 010.
-- Publish an existing exact-variant source group atomically, from validated staging.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

create or replace function public.publish_variant_refresh(p_batch jsonb)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $refresh$
declare
  s public.manufacturer_sources%rowtype;
  v public.canonical_model_variants%rowtype;
  d public.extracted_variant_drafts%rowtype;
  target record;
  expected_ids uuid[];
  source_ids uuid[];
  fact text;
  evidence jsonb;
  fact_fields text[] := array['price_sek','price_type','price_valid_until','wltp_range_km',
    'wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','boot_liters','tow_kg','seats','drivetrain'];
  fetched timestamptz;
  already_applied boolean;
  before_rows jsonb;
begin
  if jsonb_typeof(p_batch->'targets') <> 'array'
    or jsonb_array_length(p_batch->'targets') not between 1 and 20
    or coalesce(p_batch->>'batch_id','') !~ '^[a-f0-9]{64}$'
    or coalesce(p_batch->>'source_hash','') !~ '^[a-f0-9]{64}$'
    or p_batch->>'adapter' is distinct from 'polestar_table_v1' then
    raise exception 'Invalid refresh envelope';
  end if;
  fetched := (p_batch->>'fetched_at')::timestamptz;
  if fetched is null or fetched < now() - interval '15 minutes' or fetched > now() + interval '1 minute' then
    raise exception 'Stale refresh evidence';
  end if;
  select * into strict s from public.manufacturer_sources where id = (p_batch->>'source_id')::uuid for update;
  -- This first adapter is intentionally limited to the inspected Swedish source.
  if s.url <> 'https://www.polestar.com/se/polestar-2/specifications/' or s.brand <> 'Polestar' or s.model <> '2'
    or s.country <> 'SE' or s.language <> 'sv' or p_batch->>'final_url' is distinct from s.url then
    raise exception 'Unapproved refresh source';
  end if;
  if not exists (select 1 from public.canonical_models where id=s.canonical_model_id
    and brand=s.brand and model=s.model and validation_status <> 'rejected') then
    raise exception 'Rejected or mismatched canonical model';
  end if;
  select array_agg(id order by id) into expected_ids from jsonb_to_recordset(p_batch->'targets') as t(id uuid);
  if cardinality(expected_ids) <> (select count(distinct id) from unnest(expected_ids) as ids(id)) then
    raise exception 'Duplicate refresh target';
  end if;
  perform 1 from public.canonical_model_variants where id = any(expected_ids) order by id for update;
  select array_agg(id order by id) into source_ids from public.canonical_model_variants
    where source_id = s.id or source_url = s.url;
  if expected_ids is distinct from source_ids then raise exception 'Incomplete source-group refresh'; end if;
  already_applied := coalesce(s.extracted_payload->>'refresh_batch_id' = p_batch->>'batch_id', false);
  if not already_applied and (s.content_hash is distinct from p_batch->>'expected_source_hash'
    or s.updated_at is distinct from (p_batch->>'expected_source_updated_at')::timestamptz) then
    raise exception 'Concurrent source change';
  end if;
  select jsonb_agg(to_jsonb(cv) order by cv.id) into before_rows
    from public.canonical_model_variants cv where cv.id = any(expected_ids);

  for target in select * from jsonb_to_recordset(p_batch->'targets') as t(
    id uuid, draft_id uuid, expected_updated_at timestamptz, expected_hash text) order by id loop
    select * into strict v from public.canonical_model_variants where id = target.id;
    select * into strict d from public.extracted_variant_drafts where id = target.draft_id for update;
    if v.canonical_model_id is distinct from s.canonical_model_id or d.canonical_model_id is distinct from v.canonical_model_id
      or d.source_id is distinct from s.id or d.source_url <> s.url or d.brand <> s.brand or d.model <> s.model
      or d.variant_name <> v.variant_name or v.validation_status <> 'published'
      or d.validation_status <> (case when already_applied then 'published' else 'validated' end)::public.validation_status
      or d.extraction_payload->>'adapter' is distinct from 'polestar_table_v1'
      or coalesce(d.validation_errors,'[]'::jsonb) <> '[]'::jsonb
      or d.source_hash is distinct from p_batch->>'source_hash' or coalesce(length(trim(d.source_quote)),0) = 0
      or d.extraction_confidence is null or d.extraction_confidence < 0.92
      or d.extraction_confidence > 1 or (d.price_sek is null and d.wltp_range_km is null) then
      raise exception 'Draft identity, evidence or validation mismatch';
    end if;
    if not already_applied and (v.updated_at is distinct from target.expected_updated_at
      or v.source_hash is distinct from target.expected_hash) then raise exception 'Concurrent variant change'; end if;
    if (d.price_sek is not null and d.price_sek not between 100000 and 3000000)
      or (d.wltp_range_km is not null and d.wltp_range_km not between 150 and 1200)
      or (d.wltp_consumption_kwh_100km is not null and d.wltp_consumption_kwh_100km not between 5 and 50)
      or (d.battery_kwh is not null and d.battery_kwh not between 5 and 300)
      or (d.dc_charge_kw is not null and d.dc_charge_kw not between 20 and 600)
      or (d.ac_charge_kw is not null and d.ac_charge_kw not between 1 and 50)
      or (d.boot_liters is not null and d.boot_liters not between 50 and 3500)
      or (d.tow_kg is not null and d.tow_kg not between 0 and 4000)
      or (d.seats is not null and d.seats not between 1 and 9)
      or (d.price_type is not null and d.price_type not in ('list_price','campaign_price','dealer_offer'))
      or d.price_valid_until < current_date then raise exception 'Invalid refreshed values'; end if;
    if (v.price_sek > 0 and abs(d.price_sek::numeric / v.price_sek - 1) > 0.15)
      or (v.wltp_range_km > 0 and abs(d.wltp_range_km::numeric / v.wltp_range_km - 1) > 0.15) then
      raise exception 'Large change requires quarantine';
    end if;
    foreach fact in array fact_fields loop
      if to_jsonb(v)->fact <> 'null'::jsonb and to_jsonb(d)->fact = 'null'::jsonb then
        raise exception 'Refresh would discard an existing fact';
      end if;
      if to_jsonb(d)->fact <> 'null'::jsonb then
        evidence := d.extraction_payload->'field_evidence'->fact;
        if evidence is null or evidence->>'source_url' is distinct from s.url
          or evidence->>'source_hash' is distinct from d.source_hash or coalesce(length(evidence->>'quote'),0) = 0
          or coalesce(evidence->>'scope','') not in ('common_model','variant_column')
          or (evidence->>'scope' = 'variant_column' and trim(evidence->>'column_header') is distinct from d.variant_name) then
          raise exception 'Missing field-level source evidence';
        end if;
      end if;
      if already_applied and to_jsonb(v)->fact is distinct from to_jsonb(d)->fact then
        raise exception 'Previously applied batch was subsequently changed';
      end if;
    end loop;
    if already_applied and (v.source_hash is distinct from d.source_hash or v.source_id is distinct from s.id
      or s.content_hash is distinct from d.source_hash) then raise exception 'Applied evidence changed'; end if;
    if not already_applied then
      update public.canonical_model_variants set price_sek=d.price_sek, price_type=d.price_type,
        price_valid_until=d.price_valid_until, wltp_range_km=d.wltp_range_km,
        wltp_consumption_kwh_100km=d.wltp_consumption_kwh_100km, battery_kwh=d.battery_kwh,
        dc_charge_kw=d.dc_charge_kw, ac_charge_kw=d.ac_charge_kw, boot_liters=d.boot_liters,
        tow_kg=d.tow_kg, seats=d.seats, drivetrain=d.drivetrain, source_url=d.source_url,
        source_id=s.id, source_hash=d.source_hash, source_quote=d.source_quote,
        extraction_confidence=d.extraction_confidence, updated_at=now() where id=v.id;
      update public.extracted_variant_drafts set validation_status='published', updated_at=now() where id=d.id;
    end if;
  end loop;
  if not already_applied then
    update public.manufacturer_sources set content_hash=p_batch->>'source_hash', fetched_at=fetched,
      verified_at=fetched, verified_by='deterministic_variant_refresh_v1', http_status=200,
      final_url=p_batch->>'final_url', source_validation='reachable_official_model_source',
      source_authority='manufacturer', source_name='Polestar Sverige', extraction_status='validated',
      extracted_payload=jsonb_build_object('refresh_batch_id',p_batch->>'batch_id',
        'adapter',p_batch->>'adapter','previous_variants',before_rows), updated_at=now() where id=s.id;
  end if;
  return jsonb_build_object('published',cardinality(expected_ids),'already_applied',already_applied,'source_verified',true);
end;
$refresh$;

revoke all on function public.publish_variant_refresh(jsonb) from public, anon, authenticated;
grant execute on function public.publish_variant_refresh(jsonb) to service_role;
notify pgrst, 'reload schema';
commit;

-- Keep fresh installations aligned with migration 011.
-- Initial publication of a new, source-identified Toyota variant group.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.canonical_model_variants
  add column if not exists manufacturer_variant_id uuid,
  add column if not exists manufacturer_model_id uuid,
  add column if not exists manufacturer_config_version text;
create unique index if not exists canonical_variant_manufacturer_identity_idx
  on public.canonical_model_variants(canonical_model_id,manufacturer_variant_id)
  where manufacturer_variant_id is not null;

create or replace function public.publish_new_toyota_variants(p_batch jsonb)
returns jsonb language plpgsql security invoker
set search_path = pg_catalog, public
as $toyota$
declare
  s public.manufacturer_sources%rowtype;
  d public.extracted_variant_drafts%rowtype;
  v public.canonical_model_variants%rowtype;
  target record;
  cfg jsonb;
  motor jsonb;
  proof jsonb;
  raw jsonb;
  spec jsonb;
  identity uuid;
  model_identity uuid;
  version text;
  grade text;
  engine_parts text[];
  prefix text;
  path text[];
  field_name text;
  expected numeric;
  ids uuid[];
  inserted_ids uuid[] := array[]::uuid[];
  replay boolean;
  fetched timestamptz;
  fact_fields text[] := array['price_sek','price_type','price_valid_until','wltp_range_km',
    'wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','boot_liters','tow_kg','seats','drivetrain'];
begin
  if coalesce(p_batch->>'adapter','') <> 'toyota_embedded_config_v1'
    or coalesce(p_batch->>'batch_id','') !~ '^[a-f0-9]{64}$'
    or coalesce(p_batch->>'source_hash','') !~ '^[a-f0-9]{64}$'
    or jsonb_typeof(p_batch->'targets') is distinct from 'array'
    or jsonb_array_length(p_batch->'targets') not between 1 and 12 then
    raise exception 'Invalid new-variant packet';
  end if;
  fetched := (p_batch->>'fetched_at')::timestamptz;
  if fetched is null or fetched < now()-interval '15 minutes' or fetched > now()+interval '1 minute' then
    raise exception 'Stale source evidence';
  end if;
  select * into strict s from public.manufacturer_sources where id=(p_batch->>'source_id')::uuid for update;
  if s.url <> 'https://www.toyota.se/bilar/bz4x/specifications'
    or p_batch->>'final_url' is distinct from s.url or s.brand <> 'Toyota' or s.model <> 'bZ4X'
    or s.country <> 'SE' or s.language <> 'sv' or s.source_authority <> 'manufacturer'
    or s.source_validation <> 'reachable_official_model_source' or s.http_status is distinct from 200 then
    raise exception 'Unapproved Toyota source';
  end if;
  perform 1 from public.canonical_models where id=s.canonical_model_id and brand=s.brand and model=s.model
    and validation_status <> 'rejected' for update;
  if not found then raise exception 'Missing or rejected canonical model'; end if;
  replay := coalesce(s.extracted_payload->>'publication_batch_id'=p_batch->>'batch_id',false);
  if replay and (s.content_hash is distinct from p_batch->>'source_hash' or s.verified_at is distinct from fetched) then
    raise exception 'Applied source evidence changed';
  end if;
  if not replay and (s.updated_at is distinct from (p_batch->>'expected_source_updated_at')::timestamptz
    or s.content_hash is distinct from p_batch->>'expected_source_hash') then
    raise exception 'Concurrent source change';
  end if;
  if not replay and exists(select 1 from public.canonical_model_variants
    where source_id=s.id or source_url=s.url) then
    raise exception 'Existing source requires full-group refresh, not initial publication';
  end if;
  select array_agg(draft_id order by draft_id) into ids from jsonb_to_recordset(p_batch->'targets') as t(draft_id uuid);
  if cardinality(ids) <> (select count(distinct i) from unnest(ids) as i) then
    raise exception 'Duplicate draft targets';
  end if;
  perform 1 from public.extracted_variant_drafts where id=any(ids) order by id for update;
  for target in select * from jsonb_to_recordset(p_batch->'targets') as t(draft_id uuid,expected_updated_at timestamptz) order by draft_id loop
    select * into strict d from public.extracted_variant_drafts where id=target.draft_id;
    if d.canonical_model_id is distinct from s.canonical_model_id or d.source_id is distinct from s.id
      or d.brand <> s.brand or d.model <> s.model or d.source_url <> s.url
      or d.source_hash is distinct from p_batch->>'source_hash'
      or d.validation_status <> (case when replay then 'published' else 'validated' end)::public.validation_status
      or d.extraction_payload->>'adapter' is distinct from 'toyota_embedded_config_v1'
      or coalesce(d.validation_errors,'[]'::jsonb) <> '[]'::jsonb
      or d.extraction_confidence is null or d.extraction_confidence not between 0.92 and 1
      or (not replay and d.updated_at is distinct from target.expected_updated_at) then
      raise exception 'Draft is not current validated evidence';
    end if;
    cfg := d.extraction_payload->'source_configuration';
    identity := (d.extraction_payload->>'manufacturer_variant_id')::uuid;
    model_identity := (d.extraction_payload->>'manufacturer_model_id')::uuid;
    version := d.extraction_payload->>'model_config_version';
    grade := d.extraction_payload->>'grade';
    prefix := d.extraction_payload->>'motorization_pointer';
    if identity is null or model_identity is null or coalesce(version,'') !~ '^[A-Za-z0-9._-]{1,40}$'
      or coalesce(grade,'') !~ '^[A-Za-z0-9 +\-]{1,50}$'
      or coalesce(prefix,'') !~ '^/carConfigMotorization/motorization/[0-9]+$'
      or cfg->'commonSettings' is distinct from '{"brand":"toyota","country":"se","language":"sv"}'::jsonb
      or cfg#>'{car,initialized}' is distinct from 'true'::jsonb
      or cfg#>'{carConfigMotorization,initialized}' is distinct from 'true'::jsonb
      or cfg#>>'{car,model,name}' is distinct from 'Nya Toyota bZ4X'
      or cfg#>>'{car,model,id}' is distinct from model_identity::text
      or cfg#>>'{car,model,configVersion}' is distinct from version
      or cfg#>>'{car,grade,name}' is distinct from grade
      or jsonb_array_length(cfg#>'{carConfigMotorization,motorization}') is distinct from cardinality(ids) then
      raise exception 'Unproven manufacturer identity';
    end if;
    motor := cfg #> string_to_array(substr(prefix,2),'/');
    if motor->>'carId' is distinct from identity::text or motor#>>'{engine,category,code}' is distinct from 'BEV'
      or motor#>>'{engine,internalFuelCode}' is distinct from 'ELECTRIC'
      or motor#>>'{engine,certification}' is distinct from '2' then
      raise exception 'Wrong exact motorization';
    end if;
    engine_parts := regexp_match(motor#>>'{engine,name}', '^Elmotor ([0-9]+) hk, batteri ([0-9]+,[0-9]+) kWh$');
    if engine_parts is null or d.battery_kwh is distinct from replace(engine_parts[2],',','.')::numeric
      or d.variant_name is distinct from (grade||' '||d.drivetrain||' '||trim_scale(d.battery_kwh)::text||' kWh '||engine_parts[1]||' hk')
      or d.drivetrain is distinct from (case motor#>>'{wheeldrive,name}' when 'Framhjulsdrift' then 'FWD' when 'Fyrhjulsdrift' then 'AWD' else '' end)
      or d.price_sek is distinct from (motor#>>'{price,cash}')::numeric
      or (motor#>>'{price,exclVat}')::numeric * 1.25 is distinct from d.price_sek::numeric
      or d.source_quote is distinct from ((motor#>>'{engine,name}')||' | '||grade||' | '||d.price_sek::text) then
      raise exception 'Battery, price, name or drivetrain evidence disagrees';
    end if;
    if d.price_sek is null or d.price_sek not between 100000 and 3000000
      or d.battery_kwh is null or d.battery_kwh not between 5 and 300
      or (d.wltp_range_km is not null and d.wltp_range_km not between 50 and 1200)
      or (d.wltp_consumption_kwh_100km is not null and d.wltp_consumption_kwh_100km not between 5 and 50)
      or (d.tow_kg is not null and d.tow_kg not between 0 and 4000)
      or (d.seats is not null and d.seats not between 1 and 9)
      or d.price_type is not null or d.price_valid_until is not null
      or d.dc_charge_kw is not null or d.ac_charge_kw is not null or d.boot_liters is not null then
      raise exception 'Unsupported or out-of-range facts';
    end if;
    foreach field_name in array fact_fields loop
      if to_jsonb(d)->field_name <> 'null'::jsonb then
        proof := d.extraction_payload->'field_evidence'->field_name;
        path := string_to_array(substr(proof->>'source_pointer',2),'/');
        raw := cfg #> path;
        if proof is null or raw is null or proof->>'source_url' is distinct from s.url
          or proof->>'source_hash' is distinct from d.source_hash
          or proof->>'manufacturer_variant_id' is distinct from identity::text
          or proof->'raw_value' is distinct from raw or proof->>'quote' is distinct from raw::text then
          raise exception 'Missing or tampered source pointer';
        end if;
        if field_name in ('price_sek','battery_kwh','drivetrain') then
          if proof->>'source_pointer' is distinct from (prefix||case field_name when 'price_sek' then '/price/cash'
            when 'battery_kwh' then '/engine/name' else '/wheeldrive/name' end) then
            raise exception 'Fact points outside exact variant';
          end if;
        elsif field_name in ('wltp_range_km','wltp_consumption_kwh_100km') then
          if proof->>'source_pointer' !~ ('^'||prefix||'/specs/[0-9]+/value$') then
            raise exception 'Wrong WLTP pointer';
          end if;
          spec := cfg #> path[1:cardinality(path)-1];
          if spec->>'certification' is distinct from '2' or spec->>'internalCode' is distinct from
            (case field_name when 'wltp_range_km' then 'PERCOMBINED' else 'ECCOMBINEDWLTP' end)
            or spec->>'unit' is distinct from (case field_name when 'wltp_range_km' then 'km' else 'Wh/km' end)
            or coalesce(spec->>'value','') !~ '^[0-9]+$' then raise exception 'Uncertified or interval WLTP'; end if;
          expected := (spec->>'value')::numeric / (case field_name when 'wltp_range_km' then 1 else 10 end);
          if (to_jsonb(d)->>field_name)::numeric is distinct from expected then raise exception 'Wrong WLTP conversion'; end if;
        elsif field_name in ('tow_kg','seats') then
          if proof->>'source_pointer' !~ '^/specs/techSpecs/[0-9]+/data/[0-9]+/value$'
            or cfg#>>'{car,id}' is distinct from identity::text then raise exception 'Other vehicle technical data'; end if;
          spec := cfg #> path[1:cardinality(path)-1];
          if spec->>'internalCode' is distinct from (case field_name when 'tow_kg' then 'TOWCAPBRK' else 'NRSEAT' end)
            or spec->>'unit' is distinct from (case field_name when 'tow_kg' then 'kg' else 'säten' end)
            or (to_jsonb(d)->>field_name)::numeric is distinct from (spec->>'value')::numeric then
            raise exception 'Wrong technical value'; end if;
        else raise exception 'Unimplemented fact mapping';
        end if;
      end if;
    end loop;
    if replay then
      select * into strict v from public.canonical_model_variants where canonical_model_id=s.canonical_model_id
        and manufacturer_variant_id=identity;
      if v.source_id is distinct from s.id or v.source_hash is distinct from d.source_hash
        or v.variant_name <> d.variant_name or v.validation_status <> 'published'
        or v.manufacturer_model_id is distinct from model_identity or v.manufacturer_config_version is distinct from version then
        raise exception 'Applied identity subsequently changed'; end if;
      foreach field_name in array fact_fields loop
        if to_jsonb(v)->field_name is distinct from to_jsonb(d)->field_name then raise exception 'Applied facts changed'; end if;
      end loop;
    else
      if exists(select 1 from public.canonical_model_variants where canonical_model_id=s.canonical_model_id
        and (variant_name=d.variant_name or manufacturer_variant_id=identity)) then raise exception 'Existing identity must not be overwritten'; end if;
      insert into public.canonical_model_variants(canonical_model_id,variant_name,manufacturer_variant_id,
        manufacturer_model_id,manufacturer_config_version,price_sek,wltp_range_km,wltp_consumption_kwh_100km,
        battery_kwh,tow_kg,seats,drivetrain,source_url,source_id,source_hash,source_quote,extraction_confidence,
        validation_status,published_at) values(s.canonical_model_id,d.variant_name,identity,model_identity,version,
        d.price_sek,d.wltp_range_km,d.wltp_consumption_kwh_100km,d.battery_kwh,d.tow_kg,d.seats,d.drivetrain,
        s.url,s.id,d.source_hash,d.source_quote,d.extraction_confidence,'published',now()) returning * into v;
      update public.extracted_variant_drafts set validation_status='published',updated_at=now() where id=d.id;
    end if;
    inserted_ids := array_append(inserted_ids,v.id);
  end loop;
  if not replay then
    update public.manufacturer_sources set content_hash=p_batch->>'source_hash',fetched_at=fetched,verified_at=fetched,
      verified_by='deterministic_toyota_identity_v1',source_name='Toyota Sverige',extraction_status='validated',
      validation_errors='[]',extracted_payload=jsonb_build_object('publication_batch_id',p_batch->>'batch_id',
        'canonical_variant_ids',to_jsonb(inserted_ids),'previous_source',to_jsonb(s)),updated_at=now() where id=s.id;
  end if;
  return jsonb_build_object('inserted',case when replay then 0 else cardinality(inserted_ids) end,
    'already_applied',replay,'canonical_variant_ids',to_jsonb(inserted_ids));
end;
$toyota$;
revoke all on function public.publish_new_toyota_variants(jsonb) from public,anon,authenticated;
grant execute on function public.publish_new_toyota_variants(jsonb) to service_role;
notify pgrst, 'reload schema';
commit;

-- Price-only refresh: keep technical evidence and source verification unchanged.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.canonical_model_variants
  add column if not exists price_source_url text,
  add column if not exists price_source_hash text,
  add column if not exists price_source_quote text,
  add column if not exists price_source_name text,
  add column if not exists price_verified_at timestamptz,
  add column if not exists price_refresh_batch_id text;

do $price_contract$
declare
  name text;
  columns_present integer;
  existing_definition text;
begin
  foreach name in array array['canonical_model_variants','extracted_variant_drafts','manufacturer_sources'] loop
    if not (select relrowsecurity from pg_class where oid=('public.'||name)::regclass)
      or has_any_column_privilege('anon','public.'||name,'SELECT')
      or has_any_column_privilege('authenticated','public.'||name,'SELECT') then
      raise exception 'Private access boundary required';
    end if;
  end loop;
  if not exists(select 1 from pg_class c join pg_roles r on r.oid=c.relowner
    where c.oid='public.public_ev_variants'::regclass and (r.rolsuper or r.rolbypassrls)
      and not coalesce(c.reloptions,array[]::text[]) @> array['security_invoker=true']) then
    raise exception 'Owner-privileged public view required';
  end if;
  if not exists(select 1 from pg_constraint where conrelid='public.canonical_model_variants'::regclass
    and conname='canonical_price_evidence_complete') then
    alter table public.canonical_model_variants add constraint canonical_price_evidence_complete check(
      num_nonnulls(price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id)=0
      or (num_nonnulls(price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id)=6
        and price_sek is not null and price_type is not null
        and price_source_url ~ '^https://[^[:space:]@]+$'
        and price_source_hash ~ '^[a-f0-9]{64}$' and price_refresh_batch_id ~ '^[a-f0-9]{64}$'
        and length(trim(price_source_quote))>0 and length(trim(price_source_name))>0
        and (price_type <> 'campaign_price' or price_valid_until is not null)));
  end if;
  select count(*) into columns_present from pg_attribute
    where attrelid='public.public_ev_variants'::regclass and not attisdropped
      and attname in ('price_source_url','price_source_hash','price_source_quote','price_source_name','price_verified_at');
  if columns_present not in (0,5) then raise exception 'Partial public price contract'; end if;
  if columns_present=0 then
    existing_definition:=regexp_replace(pg_get_viewdef('public.public_ev_variants'::regclass,true),';[[:space:]]*$','');
    execute 'create or replace view public.public_ev_variants with (security_barrier=true) as
      select base.*, cv.price_source_url,cv.price_source_hash,cv.price_source_quote,cv.price_source_name,cv.price_verified_at
      from ('||existing_definition||') base join public.canonical_model_variants cv on cv.id=base.id';
  end if;
end;
$price_contract$;

-- Another ingestion path must not retain evidence for a price it replaced.
create or replace function public.invalidate_replaced_price_evidence()
returns trigger language plpgsql set search_path=pg_catalog,public as $price_invalidation$
begin
  if row(new.price_sek,new.price_type,new.price_valid_until) is distinct from
      row(old.price_sek,old.price_type,old.price_valid_until)
    and new.price_refresh_batch_id is not distinct from old.price_refresh_batch_id then
    new.price_source_url:=null; new.price_source_hash:=null; new.price_source_quote:=null;
    new.price_source_name:=null; new.price_verified_at:=null; new.price_refresh_batch_id:=null;
  end if;
  return new;
end;
$price_invalidation$;
revoke all on function public.invalidate_replaced_price_evidence() from public,anon,authenticated;
drop trigger if exists invalidate_replaced_price_evidence on public.canonical_model_variants;
create trigger invalidate_replaced_price_evidence before update of price_sek,price_type,price_valid_until
  on public.canonical_model_variants for each row execute function public.invalidate_replaced_price_evidence();

create or replace function public.publish_skoda_price_refresh(p_batch jsonb)
returns jsonb language plpgsql security invoker set search_path=pg_catalog,public as $price_refresh$
declare
  s public.manufacturer_sources%rowtype;
  v public.canonical_model_variants%rowtype;
  d public.extracted_variant_drafts%rowtype;
  target record;
  expected_ids uuid[];
  actual_ids uuid[];
  fetched timestamptz;
  replay boolean;
  field_name text;
  proof jsonb;
  motor text;
  row_pattern text;
  row_quote text;
  original_row jsonb;
  url_constant constant text:='https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660';
  adapter constant text:='skoda_enyaq_price_private_v1';
begin
  if jsonb_typeof(p_batch->'targets') is distinct from 'array'
    or jsonb_array_length(p_batch->'targets')<>4
    or coalesce(p_batch->>'batch_id','') !~ '^[a-f0-9]{64}$'
    or coalesce(p_batch->>'source_hash','') !~ '^[a-f0-9]{64}$'
    or p_batch->>'adapter' is distinct from adapter
    or p_batch->>'final_url' is distinct from url_constant then raise exception 'Invalid price envelope'; end if;
  fetched:=(p_batch->>'fetched_at')::timestamptz;
  if fetched is null or fetched<now()-interval '15 minutes' or fetched>now()+interval '1 minute' then
    raise exception 'Stale price fetch';
  end if;
  select * into strict s from public.manufacturer_sources where id=(p_batch->>'source_id')::uuid for update;
  if s.url<>url_constant or s.brand<>'Skoda' or s.model<>'Enyaq' or s.country<>'SE' or s.language<>'sv'
    or coalesce(s.source_authority,'') not in ('manufacturer','importer')
    or not exists(select 1 from public.canonical_models where id=s.canonical_model_id and brand=s.brand
      and model=s.model and validation_status<>'rejected') then raise exception 'Unapproved price source'; end if;
  select array_agg(id order by id) into expected_ids from jsonb_to_recordset(p_batch->'targets') as t(id uuid);
  if cardinality(expected_ids)<>4 or (select count(distinct id) from unnest(expected_ids) ids(id))<>4 then
    raise exception 'Duplicate price targets';
  end if;
  perform 1 from public.canonical_model_variants where id=any(expected_ids) order by id for update;
  select array_agg(id order by id) into actual_ids from public.canonical_model_variants
    where canonical_model_id=s.canonical_model_id and (source_id=s.id or source_url=s.url);
  if expected_ids is distinct from actual_ids then raise exception 'Incomplete price source group'; end if;
  select bool_and(price_refresh_batch_id is not distinct from p_batch->>'batch_id') into replay
    from public.canonical_model_variants where id=any(expected_ids);
  if not replay and (s.content_hash is distinct from p_batch->>'expected_source_hash'
    or s.updated_at is distinct from (p_batch->>'expected_source_updated_at')::timestamptz) then
    raise exception 'Concurrent source change';
  end if;
  for target in select * from jsonb_to_recordset(p_batch->'targets') as t(
    id uuid,draft_id uuid,expected_updated_at timestamptz,expected_hash text) order by id loop
    select * into strict v from public.canonical_model_variants where id=target.id;
    select * into strict d from public.extracted_variant_drafts where id=target.draft_id for update;
    if v.canonical_model_id is distinct from s.canonical_model_id or d.canonical_model_id is distinct from v.canonical_model_id
      or d.source_id is distinct from s.id or d.source_url is distinct from s.url or d.brand is distinct from s.brand
      or d.model is distinct from s.model or d.variant_name is distinct from v.variant_name
      or v.validation_status not in ('published','published_reviewed')
      or d.validation_status is distinct from (case when replay then 'published' else 'validated' end)::public.validation_status
      or d.extraction_payload->>'adapter' is distinct from adapter
      or coalesce(d.validation_errors,'[]'::jsonb)<>'[]'::jsonb
      or d.source_hash is distinct from p_batch->>'source_hash' or coalesce(length(trim(d.source_quote)),0)=0
      or d.extraction_confidence is null or d.extraction_confidence<0.92 or d.extraction_confidence>1 then
      raise exception 'Price draft validation mismatch';
    end if;
    motor:=case v.variant_name when 'Solid Edition 85' then '85' when 'Solid Edition 85x' then '85x'
      when 'Solid Edition 85x Sportline' then '85x Sportline' when 'Solid Edition RS' then 'RS' end;
    if motor is null then raise exception 'Unsupported exact price variant'; end if;
    if not replay and (v.updated_at is distinct from target.expected_updated_at or v.source_hash is distinct from target.expected_hash) then
      raise exception 'Concurrent variant change';
    end if;
    if d.price_sek is null or d.price_sek not between 100000 and 999999 or d.price_type is distinct from 'campaign_price'
      or d.price_valid_until is null or d.price_valid_until<current_date
      or (v.price_sek>0 and abs(d.price_sek::numeric/v.price_sek-1)>0.15) then raise exception 'Invalid campaign price'; end if;
    foreach field_name in array array['wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw',
      'ac_charge_kw','boot_liters','tow_kg','seats','drivetrain'] loop
      if to_jsonb(d)->field_name is distinct from 'null'::jsonb then raise exception 'Technical fact in price-only draft'; end if;
    end loop;
    foreach field_name in array array['price_sek','price_type','price_valid_until'] loop
      proof:=d.extraction_payload->'field_evidence'->field_name;
      if proof is null or proof->>'source_url' is distinct from s.url or proof->>'source_hash' is distinct from d.source_hash
        or proof->>'scope' is distinct from 'exact_variant_row' or proof->>'row_label' is distinct from motor
        or proof->>'edition' is distinct from U&'\0160koda Enyaq Solid Edition'
        or coalesce(length(proof->>'quote'),0)=0
        or strpos(d.source_quote,proof->>'quote')=0 then raise exception 'Unbound price evidence'; end if;
    end loop;
    row_quote:=d.extraction_payload#>>'{field_evidence,price_sek,quote}';
    row_quote:=replace(replace(row_quote,U&'\2013','-'),U&'\2212','-');
    row_pattern:='^'||motor||' [0-9]{3} [0-9]{3} [0-9]{3} 0 '||
      case motor when '85' then '' when '85x' then '' when '85x Sportline' then '- ' else '- - ' end||
      substring(d.price_sek::text,1,3)||' '||substring(d.price_sek::text,4,3)||' kr'||
      case motor when '85' then ' - -' when '85x' then ' - -' else '' end||'$';
    if row_quote!~row_pattern then raise exception 'Price row value or trim column mismatch'; end if;
    if lower(d.extraction_payload#>>'{field_evidence,price_type,quote}') is distinct from U&'erbjudandet \00e4r begr\00e4nsat'
      or (d.extraction_payload#>>'{field_evidence,price_valid_until,quote}') !~*
        (U&'^g[[:space:]]*\00e4ller[[:space:]]+tom[[:space:]]+'||d.price_valid_until::text||'$') then
      raise exception 'Campaign classification or expiry evidence mismatch';
    end if;
    if replay then
      if v.price_sek is distinct from d.price_sek or v.price_type is distinct from d.price_type
        or v.price_valid_until is distinct from d.price_valid_until or v.price_source_hash is distinct from d.source_hash
        or v.price_source_url is distinct from d.source_url or v.price_source_quote is distinct from d.source_quote
        or v.price_verified_at is distinct from fetched then raise exception 'Previously applied price evidence changed'; end if;
    else
      original_row:=to_jsonb(v);
      update public.canonical_model_variants set price_sek=d.price_sek,price_type=d.price_type,price_valid_until=d.price_valid_until,
        price_source_url=d.source_url,price_source_hash=d.source_hash,price_source_quote=d.source_quote,
        price_source_name='Skoda Sverige',price_verified_at=fetched,price_refresh_batch_id=p_batch->>'batch_id',updated_at=now()
        where id=v.id;
      update public.extracted_variant_drafts set validation_status='published',
        extraction_payload=extraction_payload||jsonb_build_object('price_refresh_previous',original_row,'price_refresh_batch_id',p_batch->>'batch_id'),
        updated_at=now() where id=d.id;
    end if;
  end loop;
  return jsonb_build_object('published',4,'already_applied',replay,'price_verified',true,'specifications_reverified',false);
end;
$price_refresh$;
revoke all on function public.publish_skoda_price_refresh(jsonb) from public,anon,authenticated;
grant execute on function public.publish_skoda_price_refresh(jsonb) to service_role;
notify pgrst,'reload schema';
commit;
