-- Scoped additive proof-only RPC. No schema/data/technical provenance updates on installation.
begin;
create or replace function public.publish_skoda_price_refresh_v2(p_batch jsonb)
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
  adapter constant text:='skoda_enyaq_price_separate_proof_v2';
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
  -- Lock the parent so the exact four-member group cannot grow mid-transaction.
  perform 1 from public.canonical_models where id=s.canonical_model_id for update;
  if not found then raise exception 'Missing canonical price parent'; end if;
  select array_agg(id order by id) into expected_ids from jsonb_to_recordset(p_batch->'targets') as t(id uuid);
  if cardinality(expected_ids)<>4 or (select count(distinct id) from unnest(expected_ids) ids(id))<>4 then
    raise exception 'Duplicate price targets';
  end if;
  perform 1 from public.canonical_model_variants where id=any(expected_ids) order by id for update;
  select array_agg(id order by id) into actual_ids from public.canonical_model_variants
    where canonical_model_id=s.canonical_model_id;
  if expected_ids is distinct from actual_ids then raise exception 'Incomplete price source group'; end if;
  select bool_and(price_refresh_batch_id is not distinct from p_batch->>'batch_id') into replay
    from public.canonical_model_variants where id=any(expected_ids);
  if not replay and (s.content_hash is distinct from p_batch->>'expected_source_hash'
    or s.updated_at is distinct from (p_batch->>'expected_source_updated_at')::timestamptz) then
    raise exception 'Concurrent source change';
  end if;
  for target in select * from jsonb_to_recordset(p_batch->'targets') as t(
    id uuid,draft_id uuid,expected_updated_at timestamptz,expected_hash text,
    expected_technical_source_id uuid,expected_technical_source_url text,expected_price jsonb) order by id loop
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
    -- A previously published, complete *price-specific* proof is the binding.
    -- Never substitute the technical source association or accept missing proof.
    if v.price_source_url is distinct from s.url
      or v.price_source_name is distinct from 'Skoda Sverige'
      or coalesce(v.price_source_hash,'') !~ '^[a-f0-9]{64}$'
      or coalesce(length(trim(v.price_source_quote)),0)=0
      or v.price_verified_at is null
      or coalesce(v.price_refresh_batch_id,'') !~ '^[a-f0-9]{64}$'
      or v.price_sek is null or v.price_type is distinct from 'campaign_price'
      or v.price_valid_until is null then raise exception 'Existing exact price proof required'; end if;
    if target.expected_technical_source_id is null
      or v.source_id is distinct from target.expected_technical_source_id
      or v.source_url is distinct from target.expected_technical_source_url
      or coalesce(v.source_hash,'') !~ '^[a-f0-9]{64}$'
      or v.source_hash is distinct from target.expected_hash then
      raise exception 'Concurrent technical provenance change'; end if;
    if not replay and (
      jsonb_typeof(target.expected_price) is distinct from 'object'
      or v.price_source_url is distinct from target.expected_price->>'price_source_url'
      or v.price_source_hash is distinct from target.expected_price->>'price_source_hash'
      or v.price_source_quote is distinct from target.expected_price->>'price_source_quote'
      or v.price_source_name is distinct from target.expected_price->>'price_source_name'
      or v.price_verified_at is distinct from (target.expected_price->>'price_verified_at')::timestamptz
      or v.price_refresh_batch_id is distinct from target.expected_price->>'price_refresh_batch_id'
      or v.price_sek is distinct from (target.expected_price->>'price_sek')::integer
      or v.price_type::text is distinct from target.expected_price->>'price_type'
      or v.price_valid_until is distinct from (target.expected_price->>'price_valid_until')::date
      or fetched<=v.price_verified_at) then raise exception 'Concurrent or stale existing price proof'; end if;
    if not replay and (v.updated_at is distinct from target.expected_updated_at or v.source_hash is distinct from target.expected_hash) then
      raise exception 'Concurrent variant change';
    end if;
    if d.price_sek is null or d.price_sek not between 100000 and 999999 or d.price_type is distinct from 'campaign_price'
      or d.price_valid_until is null or d.price_valid_until<current_date
      or d.price_sek is distinct from v.price_sek
      or d.price_type is distinct from v.price_type
      or d.price_valid_until is distinct from v.price_valid_until then raise exception 'Separate proof refresh cannot change campaign facts'; end if;
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
      update public.canonical_model_variants set price_source_hash=d.source_hash,price_source_quote=d.source_quote,
        price_verified_at=fetched,price_refresh_batch_id=p_batch->>'batch_id',updated_at=now()
        where id=v.id;
      update public.extracted_variant_drafts set validation_status='published',
        extraction_payload=extraction_payload||jsonb_build_object('price_refresh_previous',original_row,'price_refresh_batch_id',p_batch->>'batch_id'),
        updated_at=now() where id=d.id;
    end if;
  end loop;
  return jsonb_build_object('published',4,'already_applied',replay,'price_verified',true,'specifications_reverified',false);
end;
$price_refresh$;
revoke all on function public.publish_skoda_price_refresh_v2(jsonb) from public,anon,authenticated;
grant execute on function public.publish_skoda_price_refresh_v2(jsonb) to service_role;

-- A private, read-only capability probe prevents staging on an old deployment.
create or replace function public.skoda_price_refresh_contract_v2()
returns jsonb language sql stable security invoker set search_path=pg_catalog,public as $contract$
  select jsonb_build_object('contract','skoda_enyaq_price_separate_proof_v2','publisher','publish_skoda_price_refresh_v2')
$contract$;
revoke all on function public.skoda_price_refresh_contract_v2() from public,anon,authenticated;
grant execute on function public.skoda_price_refresh_contract_v2() to service_role;

notify pgrst,'reload schema';
commit;
