import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';
import {normalizeCatalog,compareCatalogs,catalogHash,prepareScopedPriceExportReceipt,planScopedPriceExport} from './sync_public_catalog.mjs';
const read=n=>readFile(new URL('../'+n,import.meta.url),'utf8');
const migration=(await read('database/migrations/029_scoped_price_reverification_20261127.sql')).trim();
const rollback=await read('database/rollback/029_scoped_price_reverification_20261127.sql');
const schema=await read('database/schema.sql');
assert(schema.includes(migration));
const priorSchema=schema.slice(0,schema.indexOf(migration));
const db=new PGlite();
const url='https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb';
const scope=[
  ...[['60 Selection',449500],['60 Sportline',469900],['85 Selection',494900],['85 Sportline',510300],
  ['85x Selection',544900],['85x Sportline',559900],['RS',591900]].map(([name,price])=>
    ['Skoda','Elroq',name+' Explore Edition',price,'campaign_price','2026-12-15',url,'Skoda Sverige','manufacturer','skoda_elroq_explore_grid_v1',200]),
  ['Volkswagen','Id.3','ID.3 Neo Trend',409900,'list_price',null,'https://www.volkswagen.se/sv/bygg-din-bil.html/__app/30355.app','Volkswagen Sverige','manufacturer','vw_id3_neo_trend_config_v1',200],
  ['Volkswagen','Id.4','ID.4 Pro 4MOTION 77 kWh MY2027 (lagerbil BSJ09L)',628550,'dealer_offer',null,'https://lagerbilar.vwgroup.se/volkswagen/BSJ09L','Volkswagen Group Sverige','importer','vwg_exact_new_stock_v1',200],
  ['Volvo','Es90','ES90 Single Motor Extended Range Ultra MY2026 (lagerbil JWR04C)',819000,'dealer_offer',null,'https://www.volvocarretail.se/bilar-i-lager/nya/volvo/es90/single-motor-extended-range-jwr04c','Volvo Car Retail','authorized_dealer','exact_new_stock_cash_v1',200],
  ['Volvo','Ex30','EX30 P5 Long Range Core MY2027 (lagerbil)',484000,'dealer_offer',null,'https://www.volvocarretail.se/bilar-i-lager/nya/volvo/ex30/p5-long-range-01a0f17196c07c0eac58aa44aeea8ae4','Volvo Car Retail','authorized_dealer','exact_new_stock_cash_v1',200],
  ['Audi','A6 E-Tron','A6 Sportback e-tron performance S-line 270 kW MY2027 (lagerbil RRR07B)',769950,'dealer_offer',null,'https://lagerbilar.vwgroup.se/audi/RRR07B','Volkswagen Group Sverige','importer','exact_stock_offer_unavailable_v1',500],
  ['Audi','Q6 E-Tron','Q6 e-tron quattro SUV 315 kW MY2027 (lagerbil JCE98Y)',799800,'dealer_offer',null,'https://www.bilia.se/bilar/sok-bil/audi/q6-e-tron/jce98y/','Bilia Haninge Audi','authorized_dealer','exact_stock_offer_unavailable_v1',410],
];
const baselineSql="select jsonb_build_object('variants',(select jsonb_agg(to_jsonb(v) order by id) from canonical_model_variants v),'models',(select jsonb_agg(to_jsonb(m) order by id) from canonical_models m),'sources',(select jsonb_agg(to_jsonb(s) order by id) from manufacturer_sources s)) value";
const readBaseline=async()=>(await db.query(baselineSql)).rows[0].value;
const call=async p=>(await db.query('select publish_scoped_price_reverification_20261127($1) value',[p])).rows[0].value;
const auditCount=async()=>(await db.query('select count(*)::int n from catalog_price_reverification_20261127')).rows[0].n;
const publicRows=async()=>(await db.query('select to_jsonb(v) value from public_ev_variants v order by id')).rows.map(r=>r.value);
const models=new Map(), sources=new Map(), entries=[];
let rejected=0;
try {
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls; grant usage on schema public to anon,authenticated,service_role');
  await db.exec(priorSchema.replace('create extension if not exists pgcrypto;',''));
  const serverNow=String((await db.query('select now()::text at')).rows[0].at);
  const now=new Date(serverNow), observed_at=now.toISOString(), old=new Date(now.getTime()-40*86400000).toISOString();
  for(const [brand,model,name,price,type,expiry,source_url,source_name,authority,adapter,status] of scope){
    const k=brand+'|'+model;
    if(!models.has(k)) {
      const m=(await db.query("insert into canonical_models(brand,model,normalized_brand,normalized_model,market_seen) values($1,$2,$3,$4,true) returning id",[brand,model,brand.toLowerCase(),model.toLowerCase()])).rows[0];
      models.set(k,m.id);
    }
    const mid=models.get(k);
    if(!sources.has(source_url)) {
      const s=(await db.query("insert into manufacturer_sources(canonical_model_id,brand,model,source_type,url,country,language,source_authority,source_name,content_hash,verified_at) values($1,$2,$3,'model_page',$4,'SE','sv',$5,$6,$7,$8) returning id",[mid,brand,model,source_url,authority,source_name,'a'.repeat(64),old])).rows[0];
      sources.set(source_url,s.id);
    }
    let tech=sources.get(source_url),techUrl=source_url;
    if(model==='Elroq') {
      techUrl='https://www.skoda.se/modeller/elroq/elroq';
      if(!sources.has(techUrl)) sources.set(techUrl,(await db.query("insert into manufacturer_sources(canonical_model_id,brand,model,source_type,url,country,language,source_authority,source_name,content_hash,verified_at) values($1,$2,$3,'model_page',$4,'SE','sv',$5,$6,$7,$8) returning id",[mid,brand,model,techUrl,authority,source_name,'c'.repeat(64),old])).rows[0].id);
      tech=sources.get(techUrl);
    }
    const v=(await db.query(`insert into canonical_model_variants(canonical_model_id,variant_name,price_sek,price_type,price_valid_until,wltp_range_km,source_id,source_url,source_hash,source_quote,extraction_confidence,validation_status,price_source_url,price_source_hash,price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id)
      values($1,$2,$3,$4,$5,$6,$7,$8,$9,'Synthetic historical quote',0.99,'published',$10,$11,'Synthetic old price',$12,$13,$14) returning id`,
      [mid,name,price,type,expiry,status===200?450:null,tech,techUrl,'c'.repeat(64),source_url,'a'.repeat(64),source_name,old,'d'.repeat(64)])).rows[0];
    let quote='';
    if(model==='Elroq') {const motor=name.split(' ')[0],trim=motor==='RS'?'RS':name.split(' ')[1];
      quote='\u0160koda Elroq Explore Edition | '+motor+' | '+trim+' | '+price+' kr | G\u00e4ller tom 2026-12-15';
    } else if(model==='Id.3') quote='ID.3 Neo | Trend | Pris inkl. moms 409900 kr';
    else if(model==='Id.4') quote=name+' | Pris 627600 kr | Reg avg p\u00e5 950kr tillkommer.';
    else quote=name+' | Kontantpris '+price+' kr';
    const proof={source_url,source_name,adapter,http_status:status,observed_at,...(status===200?{
      price_sek:price,price_type:type,price_valid_until:expiry,source_hash:'b'.repeat(64),source_quote:quote,
      ...(model==='Elroq'?{page_bound:{source_page:1,source_page_count:3,page_text_sha256:'1'.repeat(64),full_text_sha256:'2'.repeat(64),optional_equipment_footer_expiry:'2026-06-16'}}:{}),
      ...(model==='Id.4'?{advertised_cash:627600,mandatory_fee:950}:{})}:{reason:status===500?'source_unavailable':'source_gone'})};
    entries.push({id:v.id,brand,model,variant_name:name,operation:status===200?'refresh':'withhold',proof});
  }
  // Disposable-only emulation of the observed older deployed nullable registry;
  // this is not part of the candidate production migration.
  await db.exec('alter table manufacturer_sources alter column source_authority drop not null; alter table manufacturer_sources alter column source_name drop not null');
  // Actual operator baseline has a legacy missing authority/name for the Elroq
  // price-list only. There are no technical references to it.
  await db.query("update manufacturer_sources set source_authority=null,source_name=null,source_type='manufacturer_official_override_source' where id=$1",[sources.get(url)]);
  // Four actual historical identity shapes, never linked to the price registry.
  for(const oldName of ['60 Selection','85 Selection','85x Selection','RS']) {
    await db.query("insert into canonical_model_variants(canonical_model_id,variant_name,price_sek,price_type,source_id,source_url,source_hash,source_quote,extraction_confidence,validation_status) values($1,$2,500000,'list_price',$3,$4,$5,'Synthetic historic quote',0.99,'needs_review')",
      [models.get('Skoda|Elroq'),oldName,sources.get('https://www.skoda.se/modeller/elroq/elroq'),url,'a'.repeat(64)]);
  }
  // Unrelated, actual published row must remain byte-identical.
  const unrelated=(await db.query("insert into canonical_model_variants(canonical_model_id,variant_name,price_sek,price_type,wltp_range_km,source_id,source_url,source_hash,source_quote,extraction_confidence,validation_status) values($1,'Synthetic unrelated row',500000,'list_price',400,$2,$3,$4,'Synthetic only',0.99,'published') returning id",[models.get('Skoda|Elroq'),sources.get('https://www.skoda.se/modeller/elroq/elroq'),'https://www.skoda.se/modeller/elroq/elroq','f'.repeat(64)])).rows[0].id;
  const before=await readBaseline();
  const pubBefore=await publicRows();
  await db.exec(migration);
  assert.deepEqual(await readBaseline(),before);
  assert.equal(await auditCount(),0);
  const rowsAfterInstall=await publicRows();
  assert.deepEqual(normalizeCatalog(rowsAfterInstall),normalizeCatalog(pubBefore),'Installation changes existing exported rows');
  const baseline=(await db.query('select scoped_price_reverification_20261127_baseline() value')).rows[0].value;
  assert.deepEqual(baseline,before);
  const packet={adapter:'scoped_price_reverification_20261127_v1',batch_id:'e'.repeat(64),baseline,source_alignment:{expected:baseline.sources.find(s=>s.url===url)},targets:entries.map(e=>({...e,expected:baseline.variants.find(r=>r.id===e.id)}))};
  const reject=async p=>{await assert.rejects(call(p));assert.deepEqual(await readBaseline(),before);assert.equal(await auditCount(),0);rejected++};
  for(const change of [
    p=>delete p.source_alignment,p=>p.source_alignment.expected.source_name='Fake',p=>p.targets[0].proof.source_quote='made up',p=>p.targets[0].proof.page_bound.source_page=2,p=>p.targets.pop(),p=>p.targets[12]=p.targets[0],p=>p.targets[0].proof.price_sek++,
    p=>p.targets[8].proof.mandatory_fee=0,p=>p.targets[0].proof.observed_at=old,
    p=>p.targets[11].proof.reason='sold',p=>p.targets[12].proof.http_status=200,
    p=>p.targets[0].expected.source_hash='0'.repeat(64),p=>p.baseline.variants.pop(),
    p=>p.targets[0].proof.source_hash='not-a-hash',p=>p.targets[11].proof.price_sek=1,
  ]) {const p=structuredClone(packet);change(p);await reject(p)}
  // A late failure after twelve archive/UPDATE operations must revert everything.
  await db.exec("create function reject_late() returns trigger language plpgsql as $$ begin if new.evidence->>'reason'='source_gone' then raise exception 'Synthetic late failure'; end if; return new; end $$; create trigger reject_late before insert on catalog_price_reverification_20261127 for each row execute function reject_late()");
  if(now.toISOString().slice(0,10)>'2026-12-15') {
    await reject(packet);
    console.log(JSON.stringify({expired_contract_refuses_publication:true,rejected,real_database_writes:0}));
    process.exitCode=0;
  } else {
    await assert.rejects(call(packet),/Synthetic late failure/);assert.deepEqual(await readBaseline(),before);assert.equal(await auditCount(),0);rejected++;
    await db.exec('drop trigger reject_late on catalog_price_reverification_20261127;drop function reject_late()');
    const acl=(await db.query("select has_table_privilege('anon','catalog_price_reverification_20261127','select') a,has_table_privilege('authenticated','catalog_price_reverification_20261127','select') b,has_table_privilege('service_role','catalog_price_reverification_20261127','update') u,has_function_privilege('anon','publish_scoped_price_reverification_20261127(jsonb)','execute') x,has_function_privilege('service_role','publish_scoped_price_reverification_20261127(jsonb)','execute') s")).rows[0];
    assert.deepEqual(acl,{a:false,b:false,u:false,x:false,s:true});
    await db.exec('set role service_role');
    const result=await call(packet);
    await db.exec('reset role');
    assert.deepEqual(result,{refreshed:11,withheld:2,already_applied:false,batch_id:packet.batch_id,technical_facts_changed:0,source_registry_aligned:true});
    const after=await readBaseline();
    assert.deepEqual(after.variants.filter(v=>v.validation_status==='needs_review'),before.variants.filter(v=>v.validation_status==='needs_review'));
    assert.deepEqual(after.models,before.models);assert.deepEqual(after.sources,before.sources.map(s=>s.url===url?{...s,source_authority:'manufacturer',source_name:'Skoda Sverige'}:s));
    assert.deepEqual(after.variants.find(r=>r.id===unrelated),before.variants.find(r=>r.id===unrelated));
    const hist=(await db.query('select * from catalog_price_reverification_20261127 order by variant_id')).rows;
    assert.equal(hist.length,13);for(const h of hist){assert.deepEqual(h.source_alignment.before,packet.source_alignment.expected);assert.deepEqual(h.source_alignment.after,{...packet.source_alignment.expected,source_authority:'manufacturer',source_name:'Skoda Sverige'});assert.deepEqual(h.before_row,before.variants.find(r=>r.id===h.variant_id));assert.deepEqual(h.after_row,after.variants.find(r=>r.id===h.variant_id))}
    await db.exec('set role anon');const published=await publicRows();await db.exec('reset role');
    assert.equal(published.length,pubBefore.length);
    const normalized=normalizeCatalog(published);
    const withheld=normalized.filter(r=>r.price_withheld_reason);
    assert.equal(withheld.length,2);
    assert(withheld.every(r=>r.price_sek===null&&r.price_type===null&&r.wltp_range_km===null&&r.price_source_url===undefined));
    assert.equal(compareCatalogs(pubBefore,published).changed.length,13);
    // Actual local SQL readback -> anonymous catalog -> scoped export. Exercise
    // the exact prior-representation alias on a genuinely unchanged row.
    const canonicalBefore=normalizeCatalog(pubBefore),canonicalAfter=normalizeCatalog(published);
    const liveRows=structuredClone(canonicalBefore);
    const liveUnrelated=liveRows.find(r=>r.variant_name==='Synthetic unrelated row');
    liveUnrelated.verified_at=new Date(liveUnrelated.verified_at).toISOString();
    const liveSnapshot={records:liveRows,catalog_sha256:catalogHash(liveRows)};
    const rawHistory=(await db.query('select to_jsonb(h) value from catalog_price_reverification_20261127 h order by variant_id')).rows.map(r=>r.value);
    const publication={publication_requested:true,packet,operation_result:result,history:rawHistory};
    const receipt=prepareScopedPriceExportReceipt(Buffer.from(JSON.stringify(liveSnapshot)),
      {records:canonicalBefore,canonicalHash:catalogHash(canonicalBefore)},publication);
    const scoped=planScopedPriceExport(liveSnapshot,canonicalBefore,canonicalAfter,receipt);
    assert.equal(scoped.rows.length,liveRows.length);assert.equal(scoped.difference.changed.length,13);
    assert.deepEqual(scoped.rows.find(r=>r.variant_name==='Synthetic unrelated row'),liveUnrelated);
    for(const change of [
      rows=>rows.find(r=>r.variant_name==='Synthetic unrelated row').price_sek++,
      rows=>rows.find(r=>r.variant_name==='Synthetic unrelated row').verified_at=new Date(Date.parse(liveUnrelated.verified_at)+1).toISOString(),
      rows=>rows.find(r=>r.price_withheld_reason).price_withheld_at=new Date(now.getTime()+1000).toISOString(),
      rows=>rows.find(r=>r.variant_name==='60 Selection Explore Edition').wltp_range_km++,
      rows=>rows.pop()
    ]) {const bad=structuredClone(canonicalAfter);change(bad);assert.throws(()=>planScopedPriceExport(liveSnapshot,canonicalBefore,bad,receipt));rejected++}
    const dry=structuredClone(publication);dry.publication_requested=false;
    assert.throws(()=>prepareScopedPriceExportReceipt(Buffer.from(JSON.stringify(liveSnapshot)), {records:canonicalBefore,canonicalHash:catalogHash(canonicalBefore)},dry));rejected++;

    for(const mutation of [
      r=>delete r.price_withheld_reason,r=>r.price_withheld_reason='sold',r=>r.variant_name+=' extra',r=>r.price_sek=1,
      r=>r.available_confirmed=true,r=>r.price_withheld_at=r.verified_at
    ]) {const bad=structuredClone(normalized);mutation(bad.find(r=>r.price_withheld_reason));assert.throws(()=>normalizeCatalog(bad));rejected++}
    await db.exec('set role service_role');const replay=await call(packet);await db.exec('reset role');
    assert.equal(replay.already_applied,true);
    assert.deepEqual(await readBaseline(),after);assert.equal(await auditCount(),13);
    const wrong=structuredClone(packet);wrong.targets[0].proof.source_quote='different';await assert.rejects(call(wrong));
    await db.exec(rollback);
    assert.equal((await db.query("select has_function_privilege('service_role','publish_scoped_price_reverification_20261127(jsonb)','execute') allowed")).rows[0].allowed,false);
    assert.deepEqual(await readBaseline(),after);assert.equal(await auditCount(),13);
    console.log(JSON.stringify({passed:true,refreshed:11,withheld:2,rows_preserved:normalized.length,rejected,atomic_late_rollback:true,acl_preserved:true,exact_replay:true,scoped_export:true,real_database_writes:0,paid_calls:0}));
  }
} catch(e) {console.error(JSON.stringify({error:e.message,code:e.code,where:e.where,stack:e.stack?.split("\n").slice(-4)}));process.exitCode=1} finally {await db.close()}
