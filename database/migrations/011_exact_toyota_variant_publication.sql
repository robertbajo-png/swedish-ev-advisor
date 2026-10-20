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
