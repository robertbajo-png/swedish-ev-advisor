do $$ begin
  alter type source_type add value if not exists 'authorized_dealer_model_page';
  alter type source_type add value if not exists 'authorized_dealer_stock_page';
exception
  when duplicate_object then null;
end $$;

alter table manufacturer_sources
  add column if not exists source_authority text not null default 'manufacturer',
  add column if not exists authorization_evidence_url text,
  add column if not exists source_name text;

alter table manufacturer_sources
  drop constraint if exists manufacturer_sources_authority_check;

alter table manufacturer_sources
  add constraint manufacturer_sources_authority_check
  check (source_authority in ('manufacturer', 'importer', 'authorized_dealer', 'public_authority'));

alter table canonical_models
  add column if not exists image_url text,
  add column if not exists image_source_url text,
  add column if not exists image_verified_at timestamptz;

alter table extracted_variant_drafts
  add column if not exists price_type text,
  add column if not exists price_valid_until date;

alter table canonical_model_variants
  add column if not exists price_type text,
  add column if not exists price_valid_until date;

alter table extracted_variant_drafts
  drop constraint if exists extracted_variant_price_type_check;
alter table extracted_variant_drafts
  add constraint extracted_variant_price_type_check
  check (price_type is null or price_type in ('list_price', 'campaign_price', 'dealer_offer'));

alter table canonical_model_variants
  drop constraint if exists canonical_variant_price_type_check;
alter table canonical_model_variants
  add constraint canonical_variant_price_type_check
  check (price_type is null or price_type in ('list_price', 'campaign_price', 'dealer_offer'));

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
