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
