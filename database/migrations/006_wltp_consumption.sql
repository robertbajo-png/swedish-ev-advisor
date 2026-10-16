alter table extracted_variant_drafts
  add column if not exists wltp_consumption_kwh_100km numeric(4,1);

alter table canonical_model_variants
  add column if not exists wltp_consumption_kwh_100km numeric(4,1);

do $$ begin
  alter table extracted_variant_drafts
    add constraint extracted_variant_consumption_valid
    check (wltp_consumption_kwh_100km is null or wltp_consumption_kwh_100km between 5 and 50);
exception
  when duplicate_object then null;
end $$;

do $$ begin
  alter table canonical_model_variants
    add constraint canonical_variant_consumption_valid
    check (wltp_consumption_kwh_100km is null or wltp_consumption_kwh_100km between 5 and 50);
exception
  when duplicate_object then null;
end $$;

drop view if exists public_ev_variants;

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

grant select on public_ev_variants to anon, authenticated;
