-- The one-off 2026-11-27 price adjudication. Additive install, no data mutation.
begin;
set local lock_timeout='5s';
set local statement_timeout='60s';
create table public.catalog_price_reverification_20261127 (
  variant_id uuid primary key references public.canonical_model_variants(id) on delete restrict,
  batch_id text not null check (batch_id ~ '^[a-f0-9]{64}$'),
  operation text not null check (operation in ('refresh','withhold')),
  observed_at timestamptz not null,
  before_row jsonb not null,
  after_row jsonb not null,
  evidence jsonb not null,
  source_alignment jsonb,
  applied_at timestamptz not null default now()
);
alter table public.catalog_price_reverification_20261127 enable row level security;
revoke all on public.catalog_price_reverification_20261127 from public,anon,authenticated,service_role;
grant select,insert on public.catalog_price_reverification_20261127 to service_role;

-- No new public fact: expose only a reason/date for the exact deliberately
-- withheld, still-identical canonical row. The archived evidence is private.
do $status_view$
declare previous text;
begin
  if not exists(select 1 from pg_constraint where conrelid='public.canonical_model_variants'::regclass
      and conname='canonical_price_evidence_complete' and convalidated)
    or not (select relrowsecurity from pg_class where oid='public.canonical_model_variants'::regclass)
    or has_any_column_privilege('anon','public.canonical_model_variants','SELECT')
    or has_any_column_privilege('authenticated','public.canonical_model_variants','SELECT') then
    raise exception 'Existing private catalog and complete price proof required';
  end if;
  if not exists(select 1 from pg_class c join pg_roles r on r.oid=c.relowner
    where c.oid='public.public_ev_variants'::regclass and (r.rolsuper or r.rolbypassrls)
    and not coalesce(c.reloptions,array[]::text[]) @> array['security_invoker=true']) then
    raise exception 'Owner-privileged public view required';
  end if;
  previous:=regexp_replace(pg_get_viewdef('public.public_ev_variants'::regclass,true),';[[:space:]]*$','');
  execute 'create or replace view public.public_ev_variants with (security_barrier=true) as
    select base.*, case when h.variant_id is not null then h.evidence->>''reason'' end as price_withheld_reason,
      h.observed_at as price_withheld_at
    from ('||previous||') base
    join public.canonical_model_variants cv on cv.id=base.id
    left join public.catalog_price_reverification_20261127 h on h.variant_id=base.id
      and h.operation=''withhold'' and base.price_sek is null and base.price_type is null
      and base.price_valid_until is null and h.after_row=to_jsonb(cv)';
end;
$status_view$;

create function public.scoped_price_reverification_20261127_baseline()
returns jsonb language sql stable security invoker set search_path=pg_catalog,public as $baseline$
  select jsonb_build_object(
    'variants',coalesce((select jsonb_agg(to_jsonb(v) order by v.id) from public.canonical_model_variants v),'[]'::jsonb),
    'models',coalesce((select jsonb_agg(to_jsonb(m) order by m.id) from public.canonical_models m),'[]'::jsonb),
    'sources',coalesce((select jsonb_agg(to_jsonb(s) order by s.id) from public.manufacturer_sources s),'[]'::jsonb))
$baseline$;

create function public.publish_scoped_price_reverification_20261127(p_batch jsonb)
returns jsonb language plpgsql security invoker set search_path=pg_catalog,public set lock_timeout='5s' as $reverify$
declare
  sc record;
  t jsonb;
  v public.canonical_model_variants%rowtype;
  m public.canonical_models%rowtype;
  h public.catalog_price_reverification_20261127%rowtype;
  baseline jsonb;
  expected_after jsonb;
  expected_sources jsonb;
  alignment jsonb;
  source_before jsonb;
  source_after jsonb;
  source_id_to_align uuid;
  prior jsonb;
  current_row jsonb;
  proof jsonb;
  quote_expected text;
  motor text;
  trim_name text;
  observed timestamptz;
  bid text:=p_batch->>'batch_id';
  replay boolean;
  ids uuid[]:='{}';
  allowed text[]:=array['price_sek','price_type','price_valid_until','price_source_url','price_source_hash',
    'price_source_quote','price_source_name','price_verified_at','price_refresh_batch_id','updated_at'];
  verified_count int:=0;
  withheld_count int:=0;
begin
  if p_batch->>'adapter' is distinct from 'scoped_price_reverification_20261127_v1'
    or coalesce(bid,'') !~ '^[a-f0-9]{64}$'
    or jsonb_typeof(p_batch->'baseline') is distinct from 'object'
    or jsonb_typeof(p_batch->'targets') is distinct from 'array'
    or jsonb_array_length(p_batch->'targets')<>13 then raise exception 'Invalid exact price batch'; end if;

  perform pg_advisory_xact_lock(7240007);
  lock table public.canonical_model_variants in share row exclusive mode;
  lock table public.canonical_models in share mode;
  lock table public.manufacturer_sources in share row exclusive mode;
  baseline:=public.scoped_price_reverification_20261127_baseline();
  if jsonb_array_length(baseline->'variants')<13
    or baseline->'models' is distinct from p_batch#>'{baseline,models}' then raise exception 'Canonical model drift'; end if;
  select exists(select 1 from public.catalog_price_reverification_20261127) into replay;
  if replay and (select count(*) from public.catalog_price_reverification_20261127 where batch_id=bid)<>13 then
    raise exception 'Prior operation exists; reconcile original batch';
  end if;
  if not replay and baseline is distinct from p_batch->'baseline' then raise exception 'Canonical baseline drift'; end if;
  expected_sources:=p_batch#>'{baseline,sources}';
  -- Optional, separately reviewed registry alignment of a *price-only* source.
  -- Never change verified_at, source hash, technical data or any other source.
  if p_batch->'source_alignment' is not null then
    select value into strict source_before from jsonb_array_elements(expected_sources)
      where value->>'url'='https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb';
    source_id_to_align:=(source_before->>'id')::uuid;
    if p_batch#>'{source_alignment,expected}' is distinct from source_before
      or source_before->>'brand' is distinct from 'Skoda' or source_before->>'model' is distinct from 'Elroq'
      or source_before->>'country' is distinct from 'SE' or source_before->>'language' is distinct from 'sv'
      or source_before->>'source_type' is distinct from 'manufacturer_official_override_source'
      or source_before->>'source_authority' is not null or source_before->>'source_name' is not null
      or exists(select 1 from public.canonical_model_variants where source_id=source_id_to_align
         or (source_url=source_before->>'url' and not (
           validation_status='needs_review' and canonical_model_id=(source_before->>'canonical_model_id')::uuid
           and variant_name in ('60 Selection','85 Selection','85x Selection','RS'))))
      then raise exception 'Ineligible price-source registry alignment'; end if;
    source_after:=source_before||jsonb_build_object('source_authority','manufacturer','source_name','Skoda Sverige');
    if not replay then
      update public.manufacturer_sources set source_authority='manufacturer',source_name='Skoda Sverige'
        where id=source_id_to_align;
    end if;
    if (select to_jsonb(ms) from public.manufacturer_sources ms where id=source_id_to_align) is distinct from source_after then
      raise exception 'Price-source alignment changed other fields';
    end if;
    select jsonb_agg(case when value->>'id'=source_id_to_align::text then source_after else value end order by value->>'id')
      into expected_sources from jsonb_array_elements(expected_sources);
    alignment:=jsonb_build_object('before',source_before,'after',source_after);
  end if;
  if public.scoped_price_reverification_20261127_baseline()->'sources' is distinct from expected_sources then
    raise exception 'Canonical source drift';
  end if;

  for sc in select * from (values
    ('Skoda','Elroq','60 Selection Explore Edition',449500,'campaign_price','2026-12-15','https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb','Skoda Sverige','manufacturer','skoda_elroq_explore_grid_v1',200),
    ('Skoda','Elroq','60 Sportline Explore Edition',469900,'campaign_price','2026-12-15','https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb','Skoda Sverige','manufacturer','skoda_elroq_explore_grid_v1',200),
    ('Skoda','Elroq','85 Selection Explore Edition',494900,'campaign_price','2026-12-15','https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb','Skoda Sverige','manufacturer','skoda_elroq_explore_grid_v1',200),
    ('Skoda','Elroq','85 Sportline Explore Edition',510300,'campaign_price','2026-12-15','https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb','Skoda Sverige','manufacturer','skoda_elroq_explore_grid_v1',200),
    ('Skoda','Elroq','85x Selection Explore Edition',544900,'campaign_price','2026-12-15','https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb','Skoda Sverige','manufacturer','skoda_elroq_explore_grid_v1',200),
    ('Skoda','Elroq','85x Sportline Explore Edition',559900,'campaign_price','2026-12-15','https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb','Skoda Sverige','manufacturer','skoda_elroq_explore_grid_v1',200),
    ('Skoda','Elroq','RS Explore Edition',591900,'campaign_price','2026-12-15','https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb','Skoda Sverige','manufacturer','skoda_elroq_explore_grid_v1',200),
    ('Volkswagen','Id.3','ID.3 Neo Trend',409900,'list_price',null,'https://www.volkswagen.se/sv/bygg-din-bil.html/__app/30355.app','Volkswagen Sverige','manufacturer','vw_id3_neo_trend_config_v1',200),
    ('Volkswagen','Id.4','ID.4 Pro 4MOTION 77 kWh MY2027 (lagerbil BSJ09L)',628550,'dealer_offer',null,'https://lagerbilar.vwgroup.se/volkswagen/BSJ09L','Volkswagen Group Sverige','importer','vwg_exact_new_stock_v1',200),
    ('Volvo','Es90','ES90 Single Motor Extended Range Ultra MY2026 (lagerbil JWR04C)',819000,'dealer_offer',null,'https://www.volvocarretail.se/bilar-i-lager/nya/volvo/es90/single-motor-extended-range-jwr04c','Volvo Car Retail','authorized_dealer','exact_new_stock_cash_v1',200),
    ('Volvo','Ex30','EX30 P5 Long Range Core MY2027 (lagerbil)',484000,'dealer_offer',null,'https://www.volvocarretail.se/bilar-i-lager/nya/volvo/ex30/p5-long-range-01a0f17196c07c0eac58aa44aeea8ae4','Volvo Car Retail','authorized_dealer','exact_new_stock_cash_v1',200),
    ('Audi','A6 E-Tron','A6 Sportback e-tron performance S-line 270 kW MY2027 (lagerbil RRR07B)',769950,'dealer_offer',null,'https://lagerbilar.vwgroup.se/audi/RRR07B','Volkswagen Group Sverige','importer','exact_stock_offer_unavailable_v1',500),
    ('Audi','Q6 E-Tron','Q6 e-tron quattro SUV 315 kW MY2027 (lagerbil JCE98Y)',799800,'dealer_offer',null,'https://www.bilia.se/bilar/sok-bil/audi/q6-e-tron/jce98y/','Bilia Haninge Audi','authorized_dealer','exact_stock_offer_unavailable_v1',410)
  ) as s(brand,model,variant_name,price,price_type,expiry,url,source_name,authority,adapter,http_status) loop
    select value into strict t from jsonb_array_elements(p_batch->'targets')
      where value->>'brand'=sc.brand and value->>'model'=sc.model and value->>'variant_name'=sc.variant_name;
    select cv.* into strict v from public.canonical_model_variants cv
      join public.canonical_models cm on cm.id=cv.canonical_model_id
      where cm.brand=sc.brand and cm.model=sc.model and cv.variant_name=sc.variant_name and cv.id=(t->>'id')::uuid;
    select * into strict m from public.canonical_models where id=v.canonical_model_id;
    if m.validation_status='rejected' or v.validation_status not in ('published','published_reviewed')
      or v.id=any(ids) then raise exception 'Exact published identity required'; end if;
    ids:=array_append(ids,v.id);
    prior:=t->'expected';
    proof:=t->'proof';
    if jsonb_typeof(prior) is distinct from 'object' or jsonb_typeof(proof) is distinct from 'object'
      or prior->>'id' is distinct from v.id::text
      or (prior->>'price_sek')::integer is distinct from sc.price
      or prior->>'price_type' is distinct from sc.price_type
      or prior->>'price_valid_until' is distinct from sc.expiry
      or prior->>'price_source_url' is distinct from sc.url
      or prior->>'price_source_name' is distinct from sc.source_name
      or coalesce(prior->>'price_source_hash','') !~ '^[a-f0-9]{64}$'
      or coalesce(prior->>'price_refresh_batch_id','') !~ '^[a-f0-9]{64}$'
      or coalesce(length(trim(prior->>'price_source_quote')),0)=0 or prior->>'price_verified_at' is null
      or not exists(select 1 from public.manufacturer_sources s
        where s.url=sc.url and s.canonical_model_id=v.canonical_model_id and s.brand=sc.brand and s.model=sc.model
          and s.country='SE' and s.language='sv' and s.source_authority=sc.authority)
      or proof->>'source_url' is distinct from sc.url
      or proof->>'source_name' is distinct from sc.source_name
      or proof->>'adapter' is distinct from sc.adapter
      or (proof->>'http_status')::integer is distinct from sc.http_status then raise exception 'Unbound prior price or source proof'; end if;
    observed:=(proof->>'observed_at')::timestamptz;
    if observed is null or observed<=(prior->>'price_verified_at')::timestamptz
      or (not replay and (observed<now()-interval '15 minutes' or observed>now()+interval '1 minute')) then
      raise exception 'Stale or invalid price observation';
    end if;

    if sc.http_status=200 then
      if t->>'operation' is distinct from 'refresh' or (proof->>'price_sek')::integer is distinct from sc.price
        or proof->>'price_type' is distinct from sc.price_type or proof->>'price_valid_until' is distinct from sc.expiry
        or coalesce(proof->>'source_hash','') !~ '^[a-f0-9]{64}$' or coalesce(length(trim(proof->>'source_quote')),0)=0
        or (sc.expiry is not null and sc.expiry::date<observed::date)
        or proof->>'reason' is not null then raise exception 'Changed or incomplete verified price'; end if;

      -- Bind the exact version, cash amount and classification to its actual
      -- canonical source-quote shape. The operator independently validates raw bytes.
      if sc.model='Elroq' then
        motor:=split_part(sc.variant_name,' ',1);
        trim_name:=case when motor='RS' then 'RS' else split_part(sc.variant_name,' ',2) end;
        quote_expected:=U&'\0160koda Elroq Explore Edition | '||motor||' | '||trim_name||' | '||sc.price::text||U&' kr | G\00e4ller tom '||sc.expiry;
        if (proof#>>'{page_bound,source_page}')::integer is distinct from 1
          or (proof#>>'{page_bound,source_page_count}')::integer is distinct from 3
          or coalesce(proof#>>'{page_bound,page_text_sha256}','') !~ '^[a-f0-9]{64}$'
          or coalesce(proof#>>'{page_bound,full_text_sha256}','') !~ '^[a-f0-9]{64}$'
          or proof#>>'{page_bound,optional_equipment_footer_expiry}' is distinct from '2026-06-16'
          then raise exception 'Exact Elroq page proof required'; end if;
      elsif sc.model='Id.3' then
        quote_expected:='ID.3 Neo | Trend | Pris inkl. moms 409900 kr';
      elsif sc.model='Id.4' then
        quote_expected:=sc.variant_name||U&' | Pris 627600 kr | Reg avg p\00e5 950kr tillkommer.';
      else
        quote_expected:=sc.variant_name||' | Kontantpris '||sc.price::text||' kr';
      end if;
      if regexp_replace(proof->>'source_quote','[[:space:]]','','g') is distinct from regexp_replace(quote_expected,'[[:space:]]','','g') then
        raise exception 'Exact price quote mismatch';
      end if;
      -- Never promote the advertised amount alone when the official listing includes a mandatory fee.
      if sc.model='Id.4' and ((proof->>'advertised_cash')::integer is distinct from 627600
        or (proof->>'mandatory_fee')::integer is distinct from 950) then raise exception 'Exact mandatory fee required'; end if;
      verified_count:=verified_count+1;
    else
      if t->>'operation' is distinct from 'withhold' or proof->>'reason' is distinct from
        (case when sc.http_status=500 then 'source_unavailable' else 'source_gone' end)
        or proof->>'price_sek' is not null or proof->>'price_type' is not null or proof->>'price_valid_until' is not null
        or proof->>'source_hash' is not null or proof->>'source_quote' is not null then raise exception 'Unverified is not a price or sale claim'; end if;
      withheld_count:=withheld_count+1;
    end if;

    if replay then
      select * into strict h from public.catalog_price_reverification_20261127 where variant_id=v.id and batch_id=bid;
      if (select value from jsonb_array_elements(p_batch#>'{baseline,variants}') where value->>'id'=v.id::text) is distinct from prior
        or h.before_row is distinct from prior or h.after_row is distinct from to_jsonb(v) or h.evidence is distinct from proof
        or h.operation is distinct from t->>'operation' or h.observed_at is distinct from observed
        or h.source_alignment is distinct from alignment then
        raise exception 'Original receipt no longer matches';
      end if;
    else
      if to_jsonb(v) is distinct from prior then raise exception 'Concurrent variant change'; end if;
      if sc.http_status=200 then
        update public.canonical_model_variants set price_source_hash=proof->>'source_hash',
          price_source_quote=proof->>'source_quote',price_verified_at=observed,
          price_refresh_batch_id=bid,updated_at=now() where id=v.id;
      else
        update public.canonical_model_variants set price_sek=null,price_type=null,price_valid_until=null,
          price_source_url=null,price_source_hash=null,price_source_quote=null,price_source_name=null,
          price_verified_at=null,price_refresh_batch_id=null,updated_at=now() where id=v.id;
      end if;
      select to_jsonb(cv) into strict current_row from public.canonical_model_variants cv where cv.id=v.id;
      if current_row-allowed is distinct from prior-allowed then raise exception 'Technical or status mutation'; end if;
      if sc.http_status=200 then
        if current_row->>'price_source_hash' is distinct from proof->>'source_hash'
          or current_row->>'price_source_quote' is distinct from proof->>'source_quote'
          or (current_row->>'price_verified_at')::timestamptz is distinct from observed
          or current_row->>'price_refresh_batch_id' is distinct from bid
          or current_row->>'price_sek' is distinct from prior->>'price_sek'
          or current_row->>'price_type' is distinct from prior->>'price_type'
          or current_row->>'price_valid_until' is distinct from prior->>'price_valid_until'
          or current_row->>'price_source_url' is distinct from prior->>'price_source_url'
          or current_row->>'price_source_name' is distinct from prior->>'price_source_name' then
          raise exception 'Price readback mismatch';
        end if;
      elsif exists(select 1 from unnest(allowed) f where f<>'updated_at' and current_row->>f is not null) then
        raise exception 'Withheld offer retains current price';
      end if;
      insert into public.catalog_price_reverification_20261127(variant_id,batch_id,operation,observed_at,before_row,after_row,evidence,source_alignment)
        values(v.id,bid,t->>'operation',observed,prior,current_row,proof,alignment);
    end if;
  end loop;
  if verified_count<>11 or withheld_count<>2 or cardinality(ids)<>13 then raise exception 'Wrong exact scope'; end if;
  -- Compare the whole table, replacing only the 13 archived prior rows by their
  -- verified after-images. No projection, timestamp truncation or other changes.
  select jsonb_agg(coalesce(hist.after_row,old.value) order by old.value->>'id') into expected_after
    from jsonb_array_elements(p_batch#>'{baseline,variants}') old(value)
    left join public.catalog_price_reverification_20261127 hist on hist.variant_id=(old.value->>'id')::uuid and hist.batch_id=bid;
  baseline:=public.scoped_price_reverification_20261127_baseline();
  if baseline->'variants' is distinct from expected_after or baseline->'models' is distinct from p_batch#>'{baseline,models}'
    or baseline->'sources' is distinct from expected_sources then raise exception 'Out-of-scope mutation'; end if;
  return jsonb_build_object('refreshed',verified_count,'withheld',withheld_count,'already_applied',replay,
    'batch_id',bid,'technical_facts_changed',0,'source_registry_aligned',alignment is not null);
end;
$reverify$;

revoke all on function public.scoped_price_reverification_20261127_baseline(),public.publish_scoped_price_reverification_20261127(jsonb) from public,anon,authenticated;
grant execute on function public.scoped_price_reverification_20261127_baseline(),public.publish_scoped_price_reverification_20261127(jsonb) to service_role;
commit;
