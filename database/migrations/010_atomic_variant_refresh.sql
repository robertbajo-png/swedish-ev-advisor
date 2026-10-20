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
