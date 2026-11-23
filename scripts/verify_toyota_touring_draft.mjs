import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile,realpath} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {PGlite} from '@electric-sql/pglite';
import {anonymousCatalogRows,catalogWithComparableTimes,readPublishedFixture,seedCatalogFixture} from './isolated_catalog_review.mjs';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {CORE_FIELDS,publicationSnapshot} from './new_model_publication.mjs';
import {compareCatalogs} from './sync_public_catalog.mjs';

const MODEL='https://www.toyota.se/bilar/bz4x-touring', CONFIG=MODEL+'/specifications';
const PDF='https://pdf.toyotasverigebroschyr.com/price-list/bz4x-touring';
const CAR='4dd8d99a-24a0-4de3-b84f-bb4c6fbf1526';
const NAME='bZ4X Touring', ALIAS='BZ4X TOURING', KEY='bz4x touring', TRIM='Active Tech FWD';
const fields={wltp_range_km:591,wltp_consumption_kwh_100km:14,battery_kwh:74.7,dc_charge_kw:150,
  ac_charge_kw:11,boot_liters:669,tow_kg:750,seats:5,drivetrain:'FWD'};
const sha=b=>createHash('sha256').update(b).digest('hex');

async function exactRead(folder,name,limit){
  const path=join(folder,name);
  assert.equal(await realpath(path),path);
  const body=await readFile(path);
  assert(body.length>0&&body.length<=limit);
  return body;
}

async function reviewedPacket(folder,expectedHash){
  const local=resolve('data/local/release-data');
  assert.equal(local,await realpath(local));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(local));
  assert.equal(dirname(folder),local);
  assert.match(basename(folder),/^toyota-touring-capture-[a-z0-9_]+$/);
  assert.equal(await realpath(folder),folder);
  const raw=await exactRead(folder,'review.json',100_000);
  assert.equal(sha(raw),expectedHash,'Reviewed report hash changed');
  const packet=JSON.parse(raw);
  assert.deepEqual([packet.status,packet.brand,packet.model,packet.variant,packet.factory_id,packet.body_type,
    packet.standard_wheel_inches,packet.publication_approved,packet.database_writes,packet.paid_calls],
    ['private_touring_source_review','Toyota',NAME,TRIM,CAR,'Kombi',18,false,0,0]);
  for(const name of ['model.html','specifications.html','brochure.pdf','market.xlsx']){
    assert.equal(sha(await exactRead(folder,name,14_000_000)),packet.source_hashes[name]);
  }
  validateFacts(packet);
  return packet;
}

function validateFacts(packet){
  const {evidence,cash_from:cash,market,source_hashes:hashes}=packet;
  assert.deepEqual(Object.keys(evidence).sort(),[...CORE_FIELDS].sort());
  for(const [field,value] of Object.entries(fields)){
    const proof=evidence[field];
    assert.deepEqual([proof.value,proof.source_url,proof.source_hash],[value,CONFIG,hashes['specifications.html']]);
    assert(proof.quote.trim());
  }
  assert.deepEqual([cash.value,cash.source_url,cash.source_hash,cash.price_type,cash.page],
    [569900,PDF,hashes['brochure.pdf'],'manufacturer_from',3]);
  assert(cash.quote.includes('569 900 kr'));
  const row=market.row;
  assert.deepEqual([row.brand_raw,row.model_raw,row.fuel_type_raw,row.normalized_brand,row.normalized_model,
    row.needs_mapping,row.last_seen_month,row.registrations_last_month,row.registrations_ytd],
    ['TOYOTA',ALIAS,'EL','toyota',KEY,false,'2026-10-01',373,1159]);
  assert.equal(market.source_hash,hashes['market.xlsx']);
  assert.match(market.source_url,/^https:\/\/mobilitysweden\.se\/storage\/[^?#]+\.xlsx$/);
}

async function stage(db,packet){
  assert(db instanceof PGlite,'Touring draft rehearsal is restricted to local PGlite');
  validateFacts(packet);
  await db.exec('BEGIN');
  try{
    const id=(await db.query(`INSERT INTO public.canonical_models(brand,model,normalized_brand,normalized_model,body_type,market_seen)
      VALUES('Toyota',$1,'toyota',$2,'Kombi',true) RETURNING id`,[NAME,KEY])).rows[0].id;
    const market=(await db.query(`INSERT INTO public.market_models(canonical_model_id,brand_raw,model_raw,fuel_type_raw,
      normalized_brand,normalized_model,last_seen_month,registrations_last_month,registrations_ytd,source_url)
      VALUES($1,'TOYOTA',$2,'EL','toyota',$3,'2026-10-01',373,1159,$4) RETURNING id`,
      [id,ALIAS,KEY,packet.market.source_url])).rows[0].id;
    await db.query(`INSERT INTO public.market_model_monthly_stats(market_model_id,month,brand_raw,model_raw,fuel_type_raw,registrations)
      VALUES($1,'2026-10-01','TOYOTA',$2,'EL',373)`,[market,ALIAS]);
    await db.query(`INSERT INTO public.model_aliases(canonical_model_id,brand_raw,model_raw,normalized_brand,normalized_model,alias_rule)
      VALUES($1,'TOYOTA',$2,'toyota',$3,'mobility_sweden_exact_raw_name')`,[id,ALIAS,KEY]);
    let specId;
    for(const [url,type,name] of [[MODEL,'manufacturer_model_page','model.html'],
      [CONFIG,'manufacturer_specs_page','specifications.html'],[PDF,'price_list_pdf','brochure.pdf']]){
      const result=await db.query(`INSERT INTO public.manufacturer_sources(canonical_model_id,brand,model,source_type,url,
        final_url,content_hash,fetched_at,http_status,source_name)
        VALUES($1,'Toyota',$2,$3,$4,$4,$5,$6,200,'Toyota Sverige') RETURNING id`,
        [id,NAME,type,url,packet.source_hashes[name],packet.fetched_at]);
      if(url===CONFIG)specId=result.rows[0].id;
    }
    const slots=['canonical_model_id','source_id','brand','model','variant_name','price_sek','price_type','source_url',
      'source_hash','source_quote','extraction_payload',...CORE_FIELDS];
    const values=[id,specId,'Toyota',NAME,TRIM,packet.cash_from.value,packet.cash_from.price_type,CONFIG,
      packet.source_hashes['specifications.html'],packet.evidence.wltp_range_km.quote,JSON.stringify({
        factory_id:CAR,field_evidence:packet.evidence,price_evidence:packet.cash_from}),...CORE_FIELDS.map(f=>packet.evidence[f].value)];
    await db.query(`INSERT INTO public.extracted_variant_drafts(${slots.join(',')})
      VALUES(${slots.map((_,i)=>'$'+(i+1)).join(',')})`,values);
    await db.exec('COMMIT');
    return id;
  }catch(error){
    await db.exec('ROLLBACK');
    throw error;
  }
}

const {values}=parseArgs({options:{review:{type:'string'},sha256:{type:'string'},'client-module':{type:'string'}},strict:true});
assert(values.review&&/^[a-f0-9]{64}$/.test(values.sha256??''));
const packet=await reviewedPacket(resolve(values.review),values.sha256);
const connection=await catalogConnectorPath(process.cwd(),values['client-module']);
const snapshot=await openCatalogSnapshot(connection);
let fixture,publicRows;
try{
  assert.equal((await snapshot.client.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
  for(const table of ['canonical_models','market_models','model_aliases']){
    const rows=await snapshot.client.query(`SELECT id FROM public.${table} WHERE normalized_brand=$1 AND normalized_model=$2`,['toyota',KEY]);
    assert.equal(rows.rowCount,0,'Existing exact Touring identity needs review: '+table);
  }
  fixture=await readPublishedFixture(snapshot.client);
  publicRows=(await snapshot.client.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')).rows.map(r=>r.row);
}finally{
  await snapshot.close();
}

const db=new PGlite();
try{
  await seedCatalogFixture(db,fixture,[]);
  const publicBefore=await anonymousCatalogRows(db);
  assert(compareCatalogs(catalogWithComparableTimes(publicRows),catalogWithComparableTimes(publicBefore)).ok);
  const before=await publicationSnapshot(db,false,{exactJson:true});
  assert(publicBefore.some(row=>row.brand==='Toyota'&&row.model==='bZ4X'));
  assert(publicBefore.some(row=>row.brand==='Toyota'&&row.model==='C-Hr+'));
  await assert.rejects(stage({query:()=>assert.fail('Attempted remote write')},packet),/local PGlite/);
  const bad=structuredClone(packet);
  bad.evidence.tow_kg.value=1500;
  await assert.rejects(stage(db,bad));
  assert.deepEqual(await publicationSnapshot(db,false,{exactJson:true}),before);
  await db.exec(`ALTER TABLE public.extracted_variant_drafts ADD CONSTRAINT touring_late_failure CHECK (model <> 'bZ4X Touring')`);
  await assert.rejects(stage(db,packet),/touring_late_failure/);
  assert.deepEqual(await publicationSnapshot(db,false,{exactJson:true}),before);
  await db.exec('ALTER TABLE public.extracted_variant_drafts DROP CONSTRAINT touring_late_failure');
  const id=await stage(db,packet);
  const after=await publicationSnapshot(db,false,{exactJson:true});
  const model=after.canonical_models.find(r=>r.id===id);
  assert.deepEqual([model.model,model.validation_status,model.available_confirmed],[NAME,'draft',false]);
  const market=after.market_models.find(r=>r.canonical_model_id===id);
  assert.deepEqual([market.model_raw,market.first_seen_month,market.registrations_12m],[ALIAS,null,null]);
  assert.deepEqual(after.market_model_monthly_stats.filter(r=>r.market_model_id===market.id).map(r=>r.registrations),[373]);
  const assigned=after.model_aliases.find(r=>r.canonical_model_id===id);
  assert.deepEqual([assigned.model_raw,assigned.needs_mapping],[ALIAS,false]);
  const drafts=after.extracted_variant_drafts.filter(r=>r.canonical_model_id===id);
  assert.equal(drafts.length,1);
  assert.equal(drafts[0].validation_status,'extracted');
  assert.deepEqual(drafts[0].extraction_payload.field_evidence,packet.evidence);
  assert.deepEqual(drafts[0].extraction_payload.price_evidence,packet.cash_from);
  for(const [field,value] of Object.entries(fields))assert.equal(drafts[0][field],value);
  assert.deepEqual(after.canonical_model_variants,before.canonical_model_variants);
  assert.deepEqual(await anonymousCatalogRows(db),publicBefore);
  await assert.rejects(stage(db,packet),/duplicate key/);
  assert.deepEqual(await publicationSnapshot(db,false,{exactJson:true}),after);
  console.log(JSON.stringify({touring_private_draft:'passed',technical_fields:9,existing_public_variants:publicRows.length,
    public_variants_added:0,market_alias_verified:true,late_rollback_and_collision:true,production_writes:0}));
}finally{
  await db.close();
}
