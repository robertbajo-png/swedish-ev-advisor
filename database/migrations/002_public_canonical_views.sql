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
exception
  when duplicate_object then null;
end $$;

alter table canonical_model_variants
  add column if not exists source_url text,
  add column if not exists source_hash text,
  add column if not exists review_approved_by text,
  add column if not exists review_reason text,
  add column if not exists review_promoted_at timestamptz;

drop index if exists canonical_model_variants_public_idx;
create index if not exists canonical_model_variants_public_idx
  on canonical_model_variants(canonical_model_id, validation_status)
  where validation_status in ('published', 'published_reviewed');

drop view if exists public_ev_variants;
drop view if exists public_ev_models;

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

grant select on public_ev_models to anon, authenticated;
grant select on public_ev_variants to anon, authenticated;
