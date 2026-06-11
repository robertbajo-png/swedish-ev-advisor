pragma foreign_keys = on;

create table if not exists canonical_models (
  id integer primary key autoincrement,
  brand text not null,
  model text not null,
  normalized_brand text not null,
  normalized_model text not null,
  body_type text,
  market_seen integer not null default 0,
  available_confirmed integer not null default 0,
  discontinued_candidate integer not null default 0,
  coming_or_low_volume integer not null default 0,
  validation_status text not null default 'draft',
  published_at text,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique (normalized_brand, normalized_model)
);

create table if not exists market_models (
  id integer primary key autoincrement,
  brand_raw text not null,
  model_raw text not null,
  fuel_type_raw text not null,
  normalized_brand text not null,
  normalized_model text not null,
  model_group text,
  needs_mapping integer not null default 0,
  canonical_model_id integer references canonical_models(id),
  first_seen_month text,
  last_seen_month text,
  registrations_last_month integer not null default 0,
  registrations_ytd integer not null default 0,
  registrations_12m integer,
  source_name text not null default 'Mobility Sweden',
  source_url text not null,
  imported_at text not null default current_timestamp,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique (normalized_brand, normalized_model, fuel_type_raw)
);

create table if not exists market_model_monthly_stats (
  id integer primary key autoincrement,
  market_model_id integer not null references market_models(id) on delete cascade,
  month text not null,
  brand_raw text not null,
  model_raw text not null,
  fuel_type_raw text not null,
  registrations integer not null default 0,
  private_registrations integer,
  company_registrations integer,
  county text not null default '',
  municipality text not null default '',
  imported_at text not null default current_timestamp,
  unique (market_model_id, month, county, municipality)
);

create table if not exists model_aliases (
  id integer primary key autoincrement,
  canonical_model_id integer references canonical_models(id) on delete cascade,
  brand_raw text not null,
  model_raw text not null,
  normalized_brand text not null,
  normalized_model text not null,
  alias_rule text,
  model_group text,
  needs_mapping integer not null default 0,
  confidence real not null default 1.0,
  reviewed_by text,
  reviewed_at text,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique (normalized_brand, normalized_model)
);

create table if not exists manufacturer_sources (
  id integer primary key autoincrement,
  canonical_model_id integer references canonical_models(id) on delete cascade,
  brand text not null,
  model text not null,
  source_type text not null,
  url text not null unique,
  title text,
  country text not null default 'SE',
  language text not null default 'sv',
  fetched_at text,
  content_hash text,
  extraction_status text not null default 'draft',
  extraction_confidence real,
  http_status integer,
  final_url text,
  source_validation text not null default 'needs_discovery',
  is_primary integer not null default 0,
  extracted_payload text,
  validation_errors text,
  verified_by text,
  verified_at text,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists extracted_variant_drafts (
  id integer primary key autoincrement,
  canonical_model_id integer references canonical_models(id) on delete cascade,
  source_id integer references manufacturer_sources(id) on delete set null,
  brand text not null,
  model text not null,
  variant_name text not null,
  price_sek integer,
  wltp_range_km integer,
  battery_kwh real,
  dc_charge_kw integer,
  ac_charge_kw integer,
  boot_liters integer,
  tow_kg integer,
  seats integer,
  drivetrain text,
  source_url text not null,
  source_quote text,
  source_hash text,
  extraction_confidence real not null default 0,
  extraction_payload text,
  validation_status text not null default 'extracted',
  validation_errors text,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique (source_url, variant_name)
);

create table if not exists canonical_model_variants (
  id integer primary key autoincrement,
  canonical_model_id integer not null references canonical_models(id) on delete cascade,
  variant_name text not null,
  price_sek integer,
  wltp_range_km integer,
  battery_kwh real,
  dc_charge_kw integer,
  ac_charge_kw integer,
  boot_liters integer,
  tow_kg integer,
  seats integer,
  drivetrain text,
  source_url text,
  source_hash text,
  source_quote text,
  extraction_confidence real,
  review_approved_by text,
  review_reason text,
  review_promoted_at text,
  source_id integer references manufacturer_sources(id),
  validation_status text not null default 'draft',
  published_at text,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique (canonical_model_id, variant_name)
);

create view if not exists public_ev_models as
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
where cm.validation_status <> 'rejected'
  and exists (
    select 1
    from canonical_model_variants cv
    where cv.canonical_model_id = cm.id
      and cv.validation_status in ('published', 'published_reviewed')
  );

create view if not exists public_ev_variants as
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
  coalesce(cv.source_url, ms.url) as source_url,
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
