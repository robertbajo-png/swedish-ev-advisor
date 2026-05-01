create extension if not exists pgcrypto;

do $$ begin
  create type validation_status as enum ('draft', 'extracted', 'validated', 'published', 'rejected');
exception
  when duplicate_object then null;
end $$;

do $$ begin
  create type source_type as enum ('manufacturer_page', 'importer_page', 'price_list_pdf', 'technical_pdf', 'configurator', 'mobility_sweden_export');
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
  unique (market_model_id, month, county, municipality)
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
  wltp_range_km integer,
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
  constraint extracted_variant_values_valid check (
    (price_sek is null or price_sek between 100000 and 3000000) and
    (wltp_range_km is null or wltp_range_km between 50 and 1200) and
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
  wltp_range_km integer,
  battery_kwh numeric(5,2),
  dc_charge_kw integer,
  ac_charge_kw integer,
  boot_liters integer,
  tow_kg integer,
  seats integer,
  drivetrain text,
  source_quote text,
  extraction_confidence numeric(4,3),
  source_id uuid references manufacturer_sources(id),
  validation_status validation_status not null default 'draft',
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint canonical_variant_values_valid check (
    (price_sek is null or price_sek between 100000 and 3000000) and
    (wltp_range_km is null or wltp_range_km between 50 and 1200) and
    (dc_charge_kw is null or dc_charge_kw between 20 and 600) and
    (boot_liters is null or boot_liters between 50 and 3500) and
    (tow_kg is null or tow_kg between 0 and 4000) and
    (seats is null or seats between 1 and 9)
  ),
  unique (canonical_model_id, variant_name)
);

create index if not exists canonical_model_variants_public_idx
  on canonical_model_variants(canonical_model_id, validation_status)
  where validation_status = 'published';

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
  cm.published_at
from canonical_models cm
where cm.validation_status = 'published'
  and cm.available_confirmed = true;

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
  cv.variant_name,
  cv.price_sek,
  cv.wltp_range_km,
  cv.battery_kwh,
  cv.dc_charge_kw,
  cv.ac_charge_kw,
  cv.boot_liters,
  cv.tow_kg,
  cv.seats,
  cv.drivetrain,
  cv.source_quote,
  cv.extraction_confidence,
  ms.url as source_url,
  ms.verified_at
from canonical_model_variants cv
join canonical_models cm on cm.id = cv.canonical_model_id
left join manufacturer_sources ms on ms.id = cv.source_id
where cm.validation_status = 'published'
  and cv.validation_status = 'published'
  and cm.available_confirmed = true;

grant select on public_ev_models to anon, authenticated;
grant select on public_ev_variants to anon, authenticated;
