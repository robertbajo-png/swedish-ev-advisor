
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { resolve, relative, sep } from 'node:path';
import { normalizeCatalog, catalogHash, compareCatalogs, variantKey, planEnyaqProofOnlyExport, prepareEnyaqProofExportReceipt, syncPublicCatalog, FIELDS } from './sync_public_catalog.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
// Stable synthetic catalog; CI must not depend on later real proof dates or
// additions to the live product catalog.
const base={brand:'Fixture',model:'BEV',variant_name:'Variant',price_sek:500000,price_type:'campaign_price',price_valid_until:'2026-12-15',
  wltp_range_km:500,tow_kg:1000,source_url:'https://example.invalid/technical',source_quote:'Synthetic technical evidence',source_hash:'a'.repeat(64),
  extraction_confidence:.95,validation_status:'published',market_seen:true,available_confirmed:true,discontinued_candidate:false,coming_or_low_volume:false,
  verified_at:'2026-11-01T09:00:00.000Z',price_source_url:'https://example.invalid/price',price_source_hash:'d'.repeat(64),
  price_source_quote:'Synthetic prior price proof',price_source_name:'Fixture importer',price_verified_at:'2026-10-27T09:30:59.759197+00:00'};
const live={source:'supabase_public_ev_variants',schema_version:1,generated_at:'2026-11-26T09:00:00.000Z',missing_view_columns:[],records:[
  ...['85','85x','85x Sportline','RS'].map((motor,i)=>({...base,brand:'Skoda',model:'Enyaq',variant_name:'Solid Edition '+motor,
    price_sek:[599500,638500,679900,689900][i],source_url:'https://www.skoda.se/modeller/enyaq/enyaq',
    price_source_url:'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660',price_source_name:'Skoda Sverige'})),
  ...Array.from({length:105},(_,i)=>({...base,model:'Fixture '+String(i+1)}))
]};
const targets=live.records.filter(r=>r.brand==='Skoda'&&r.model==='Enyaq');
assert.equal(targets.length,4);
const keys=new Set(targets.map(variantKey));
const other=live.records.filter(r=>!keys.has(variantKey(r))&&r.price_verified_at).slice(0,9);assert.equal(other.length,9);
for(const row of other){row.verified_at='2026-11-22T19:11:27.863Z';row.price_verified_at='2026-11-22T19:11:27.863Z';}
live.records=normalizeCatalog(live.records);live.catalog_sha256=catalogHash(live.records);
const before=structuredClone(live.records);
for(const row of before.filter(r=>other.some(o=>variantKey(o)===variantKey(r)))){
  row.verified_at='2026-11-22T20:11:27.863622+01:00';row.price_verified_at='2026-11-22T20:11:27.863+01:00';
}
const after=structuredClone(before),expected_proofs={};
const freshAt='2026-11-26T10:01:48.367687+00:00',sourceHash='b'.repeat(64);
for(const row of after.filter(r=>keys.has(variantKey(r)))){
  const name=variantKey(row);
  row.price_source_hash=sourceHash;row.price_source_quote+=' synthetic test quote';row.price_verified_at='2026-11-26T11:01:48.367687+01:00';
  expected_proofs[name]=Object.fromEntries(['price_sek','price_type','price_valid_until','price_source_url','price_source_name','price_source_hash','price_source_quote','price_verified_at'].map(f=>[f,row[f]]));
  expected_proofs[name].price_verified_at=freshAt;
}
const liveBytes=Buffer.from(JSON.stringify(live,null,2)+'\n');
const receipt={kind:'approved_enyaq_proof_refresh_v2',live_snapshot_sha256:hash(liveBytes),canonical_before_hash:catalogHash(before),canonical_before_records:before,publication:{adapter:'skoda_enyaq_price_separate_proof_v2',published:4,price_verified:true,specifications_reverified:false,batch_id:'c'.repeat(64),source_hash:sourceHash,fetched_at:freshAt},expected_proofs};
const publicationRecord={
  publication_requested:true,
  operation_result:{staged:4,published:4,price_verified:true,specifications_reverified:false},
  packet:{adapter:receipt.publication.adapter,final_url:'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660',batch_id:receipt.publication.batch_id,
    source_hash:sourceHash,fetched_at:freshAt,targets:before.filter(r=>keys.has(variantKey(r))).map(r=>({variant_name:r.variant_name,expected_price:Object.fromEntries(['price_sek','price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote','price_source_name','price_verified_at'].map(f=>[f,r[f]]))}))},
  source:{url:'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660',final_url:'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660',status:'reachable',brand:'Skoda',model:'Enyaq',http_status:200,content_type:'application/pdf',content_hash:sourceHash,fetched_at:freshAt},
  drafts:after.filter(r=>keys.has(variantKey(r))).map(r=>({brand:r.brand,model:r.model,variant_name:r.variant_name,price_sek:r.price_sek,price_type:r.price_type,price_valid_until:r.price_valid_until,source_url:r.price_source_url,source_hash:r.price_source_hash,source_quote:r.price_source_quote,extraction_payload:{adapter:receipt.publication.adapter}}))
};
const canonicalBefore={records:before,canonicalHash:catalogHash(before)};
assert.deepEqual(prepareEnyaqProofExportReceipt(liveBytes,canonicalBefore,publicationRecord),receipt);
assert.throws(()=>prepareEnyaqProofExportReceipt(liveBytes,canonicalBefore,{...publicationRecord,publication_requested:false}));
assert.throws(()=>prepareEnyaqProofExportReceipt(liveBytes,canonicalBefore,{...publicationRecord,operation_result:{staged:4,published:0}}));
const wrongPrior=structuredClone(publicationRecord);wrongPrior.packet.targets[0].expected_price.price_source_hash='f'.repeat(64);
assert.throws(()=>prepareEnyaqProofExportReceipt(liveBytes,canonicalBefore,wrongPrior));
const plan=planEnyaqProofOnlyExport(live,before,after,receipt);
assert.equal(plan.representation_aliases.length,18);assert.equal(plan.difference.changed.length,4);
assert.equal(compareCatalogs(live.records,before).changed.length,9,'Default strict comparison still detects the raw difference');
assert.deepEqual(plan.rows.filter(r=>!keys.has(variantKey(r))),live.records.filter(r=>!keys.has(variantKey(r))));
let rejected=0;
const reject=(l=live,b=before,a=after,r=receipt)=>{assert.throws(()=>planEnyaqProofOnlyExport(l,b,a,r));rejected++;};
const changeAfter=(key,patch)=>after.map(row=>variantKey(row)===key?{...row,...patch}:row);
const foreign=variantKey(other[0]),target=variantKey(targets[0]);
reject(live,before,changeAfter(foreign,{verified_at:'2026-11-22T20:11:27.863623+01:00'})); // same ms, real raw change must fail
reject(live,before,changeAfter(foreign,{price_sek:before.find(r=>variantKey(r)===foreign).price_sek+1}));
reject(live,before,changeAfter(target,{price_type:'list_price'}));
reject(live,before,changeAfter(target,{price_valid_until:'2099-01-01'}));
reject(live,before,changeAfter(target,{price_verified_at:'2026-11-26T11:01:48.367688+01:00'}));
reject(live,before,changeAfter(target,{price_source_hash:'e'.repeat(64)}));
reject(live,before,after.slice(1));
reject(live,before,[...after,{...after[0],variant_name:'Extra synthetic'}]);
reject(live,before,after,{...receipt,canonical_before_hash:'0'.repeat(64)});
reject(live,before,after,{...receipt,publication:{...receipt.publication,price_verified:false}});
reject(live,before,after,{...receipt,publication:{...receipt.publication,specifications_reverified:true}});
reject(live,before,after,{...receipt,publication:{...receipt.publication,fetched_at:'2026-11-26T10:01:48.367688+00:00'}});
const missing=structuredClone(receipt);delete missing.expected_proofs[target];reject(live,before,after,missing);
const badBefore=before.map(r=>variantKey(r)===foreign?{...r,verified_at:'2026-11-22T21:11:27.863622+01:00'}:r);
const badAfter=after.map(r=>variantKey(r)===foreign?{...r,verified_at:'2026-11-22T21:11:27.863622+01:00'}:r);
reject(live,badBefore,badAfter,{...receipt,canonical_before_hash:catalogHash(badBefore)});
// A real local dry-run and export via the same main entrypoint; dependency
// substituted only at the anonymous HTTP read boundary.
const dir=await mkdtemp(resolve(tmpdir(),'enyaq-proof-export-'));
const cwd=process.cwd(),saved={url:process.env.SUPABASE_URL,key:process.env.SUPABASE_ANON_KEY};
const log=console.log;let reads=0;
try{
  process.chdir(dir);await mkdir('public/data',{recursive:true});await mkdir('data/review',{recursive:true});
  const path='public/data/public_ev_variants.json';await writeFile(path,liveBytes);await writeFile('receipt.json',JSON.stringify(receipt));
  process.env.SUPABASE_URL='https://example.invalid';process.env.SUPABASE_ANON_KEY='sb_publishable_synthetic_fixture';
  function response(rows){
    return new Response(JSON.stringify(rows),{status:200,headers:{'content-range':'0-'+(rows.length-1)+'/'+rows.length,'content-type':'application/json'}});
  }
  const mock=async(url,opts)=>{
    reads++;assert.equal(new URL(url).pathname,'/rest/v1/public_ev_variants');assert.equal(opts.method??'GET','GET');
    assert.equal(opts.headers.apikey,'sb_publishable_synthetic_fixture');return response(after);
  };
  console.log=()=>{};
  await syncPublicCatalog({argv:['--enyaq-proof-receipt','receipt.json'],fetchImpl:mock});
  assert.equal(reads,2);assert((await readFile(path)).equals(liveBytes),'Scoped dry run leaves snapshot byte-identical');
  await assert.rejects(readFile('data/review/catalog_reconciliation.json'),e=>e.code==='ENOENT');
  let n=0;
  await assert.rejects(syncPublicCatalog({argv:['--enyaq-proof-receipt','receipt.json','--write'],fetchImpl:async()=>response(n++?changeAfter(foreign,{verified_at:'2026-11-22T20:11:27.863623+01:00'}):after)}));
  assert((await readFile(path)).equals(liveBytes),'Failed strict double read leaves snapshot unchanged');
  const bad=structuredClone(receipt);bad.live_snapshot_sha256='0'.repeat(64);await writeFile('receipt.json',JSON.stringify(bad));
  await assert.rejects(syncPublicCatalog({argv:['--enyaq-proof-receipt','receipt.json','--write'],fetchImpl:async()=>{throw Error('Must stop before transport');}}));
  assert((await readFile(path)).equals(liveBytes));
  await writeFile('receipt.json',JSON.stringify(receipt));
  await syncPublicCatalog({argv:['--enyaq-proof-receipt','receipt.json','--write'],fetchImpl:mock});
  const result=JSON.parse(await readFile(path,'utf8')),report=JSON.parse(await readFile('data/review/catalog_reconciliation.json','utf8'));
  assert.deepEqual(result.records,plan.rows);assert.equal(result.catalog_sha256,catalogHash(plan.rows));assert.equal(report.scope,'approved_enyaq_proof_refresh_v2');assert.equal(report.representation_aliases.length,18);
  assert.deepEqual(result.records.filter(r=>!keys.has(variantKey(r))),live.records.filter(r=>!keys.has(variantKey(r))));
}finally{
  console.log=log;process.chdir(cwd);
  if(saved.url===undefined)delete process.env.SUPABASE_URL;else process.env.SUPABASE_URL=saved.url;
  if(saved.key===undefined)delete process.env.SUPABASE_ANON_KEY;else process.env.SUPABASE_ANON_KEY=saved.key;
  const rel=relative(resolve(tmpdir()),resolve(dir));assert(rel.startsWith('enyaq-proof-export-')&&!rel.includes(sep));await rm(dir,{recursive:true,force:true});
}
console.log(JSON.stringify({enyaq_scoped_export_ok:true,strict_default_preserved:true,negative_cases:rejected,unrelated_rows_unchanged:live.records.length-4,representation_aliases:18,local_entrypoint_dry_run:true,local_entrypoint_write:true,mock_transport_reads:reads,remote_requests:0,production_writes:0}));

