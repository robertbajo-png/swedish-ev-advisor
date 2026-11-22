-- Allow source-bound manufacturer starting prices without relabeling existing prices.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

do $from_price$
declare
  target text;
  old_name text;
begin
  foreach target in array array['canonical_model_variants','extracted_variant_drafts'] loop
    if not (select relrowsecurity from pg_class where oid=('public.'||target)::regclass)
      or has_any_column_privilege('anon','public.'||target,'SELECT')
      or has_any_column_privilege('authenticated','public.'||target,'SELECT') then
      raise exception 'Private catalog access boundary required for %', target;
    end if;
    old_name := case when target='canonical_model_variants' then 'canonical_variant_price_type_check'
      else 'extracted_variant_price_type_check' end;
    if not exists (select 1 from pg_constraint where conrelid=('public.'||target)::regclass
      and conname in (old_name, target||'_catalog_price_type_check') and contype='c') then
      raise exception 'Existing price type check required for %', target;
    end if;
    execute format('alter table public.%I drop constraint if exists %I, drop constraint if exists %I',
      target, old_name, target||'_catalog_price_type_check');
    execute format('alter table public.%I add constraint %I
      check (price_type is null or price_type in (''list_price'',''campaign_price'',''dealer_offer'',''manufacturer_from''))',
      target, target||'_catalog_price_type_check');
  end loop;
  if not exists(select 1 from pg_constraint where conrelid='public.canonical_model_variants'::regclass
    and conname='canonical_price_evidence_complete' and convalidated) then
    raise exception 'Apply the verified price evidence contract before manufacturer starting prices';
  end if;
end
$from_price$;

alter table public.canonical_model_variants
  drop constraint if exists canonical_manufacturer_from_evidence,
  add constraint canonical_manufacturer_from_evidence check (
    price_type is distinct from 'manufacturer_from' or (
      price_sek is not null and price_sek between 100000 and 3000000
      and price_valid_until is null
      and num_nonnulls(price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id)=6
    )
  );

alter table public.extracted_variant_drafts
  drop constraint if exists draft_manufacturer_from_evidence,
  add constraint draft_manufacturer_from_evidence check (
    price_type is distinct from 'manufacturer_from' or (
      price_sek is not null and price_sek between 100000 and 3000000
      and price_valid_until is null
      and extraction_payload#>>'{price_evidence,price_type}' is not distinct from 'manufacturer_from'
      and extraction_payload#>>'{price_evidence,value}' is not distinct from price_sek::text
      and coalesce(extraction_payload#>>'{price_evidence,source_url}','') ~ '^https://[^[:space:]@]+$'
      and coalesce(extraction_payload#>>'{price_evidence,source_hash}','') ~ '^[a-f0-9]{64}$'
      and coalesce(length(trim(extraction_payload#>>'{price_evidence,quote}')),0)>0
    )
  );

commit;
