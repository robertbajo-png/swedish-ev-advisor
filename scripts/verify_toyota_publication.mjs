import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';

const read = (path) => readFile(new URL('../' + path, import.meta.url), 'utf8');
const db = new PGlite();
const url = 'https://www.toyota.se/bilar/bz4x/specifications';
const oldHash = 'a'.repeat(64), hash = 'b'.repeat(64);
const modelId = '99999999-9999-4999-8999-999999999999';
const cars = ['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222'];
const cfg = {commonSettings:{brand:'toyota',country:'se',language:'sv'},
  car:{id:cars[0],initialized:true,grade:{name:'Active'},model:{id:modelId,name:'Nya Toyota bZ4X',configVersion:'test.1'}},
  carConfigMotorization:{initialized:true,motorization:cars.map((carId,i)=>({carId,
    engine:{name:`Elmotor ${i?230:170} hk, batteri ${i?'74,1':'58,7'} kWh`,certification:2,category:{code:'BEV'},internalFuelCode:'ELECTRIC'},
    wheeldrive:{name:i?'Fyrhjulsdrift':'Framhjulsdrift'},price:{cash:i?600000:500000,exclVat:i?480000:400000},
    specs:[{internalCode:'PERCOMBINED',value:i?'500':'450',unit:'km',certification:2},
      {internalCode:'ECCOMBINEDWLTP',value:'148',unit:'Wh/km',certification:2}]}))},
  specs:{techSpecs:[{data:[{internalCode:'TOWCAPBRK',value:'750',unit:'kg'},{internalCode:'NRSEAT',value:'5',unit:'säten'}]}]}};

try {
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls; grant usage on schema public to anon,authenticated,service_role');
  await db.exec((await read('database/schema.sql')).replace('create extension if not exists pgcrypto;',''));
  const acl = () => db.query("select relname,relacl::text,relrowsecurity from pg_class where oid in ('canonical_models'::regclass,'canonical_model_variants'::regclass,'extracted_variant_drafts'::regclass,'manufacturer_sources'::regclass) order by relname");
  const beforeAcl = (await acl()).rows;
  const migration = await read('database/migrations/011_exact_toyota_variant_publication.sql');
  assert((await read('database/schema.sql')).includes(migration.trim()));
  await db.exec(migration); await db.exec(migration);
  assert.deepEqual((await acl()).rows,beforeAcl);
  for(const role of ['anon','authenticated']) {
    await db.exec(`set role ${role}`);
    await assert.rejects(db.query('select public.publish_new_toyota_variants($1)',[{}]),e=>e.code==='42501');
    await assert.rejects(db.query('select manufacturer_variant_id from canonical_model_variants'),e=>e.code==='42501');
    await db.exec('reset role');
  }
  const model = (await db.query("insert into canonical_models(brand,model,normalized_brand,normalized_model,market_seen) values ('Toyota','bZ4X','toyota','bz4x',true) returning *")).rows[0];
  for(const name of ['Active FWD','Active AWD']) await db.query("insert into canonical_model_variants(canonical_model_id,variant_name,price_sek,wltp_range_km,source_url,source_hash,validation_status) values ($1,$2,470000,500,'https://www.toyota.se/legacy-2024.pdf',$3,'published')",[model.id,name,oldHash]);
  const legacy = (await db.query('select * from canonical_model_variants order by id')).rows;
  const flags = (await db.query('select * from canonical_models')).rows;
  const source = (await db.query("insert into manufacturer_sources(canonical_model_id,brand,model,source_type,url,content_hash,source_validation,http_status) values ($1,'Toyota','bZ4X','manufacturer_specs_page',$2,$3,'reachable_official_model_source',200) returning *",[model.id,url,oldHash])).rows[0];
  const targets = [];
  for(let index=0;index<cars.length;index++) {
    const motor=cfg.carConfigMotorization.motorization[index], prefix=`/carConfigMotorization/motorization/${index}`;
    const row={price_sek:motor.price.cash,battery_kwh:index?74.1:58.7,drivetrain:index?'AWD':'FWD',wltp_range_km:index?500:450,wltp_consumption_kwh_100km:14.8};
    const proof={};
    const add=(field,path,raw)=>{proof[field]={source_url:url,source_hash:hash,source_pointer:path,raw_value:raw,quote:JSON.stringify(raw),manufacturer_variant_id:cars[index]};};
    add('price_sek',prefix+'/price/cash',motor.price.cash); add('battery_kwh',prefix+'/engine/name',motor.engine.name);
    add('drivetrain',prefix+'/wheeldrive/name',motor.wheeldrive.name);
    add('wltp_range_km',prefix+'/specs/0/value',motor.specs[0].value); add('wltp_consumption_kwh_100km',prefix+'/specs/1/value','148');
    if(index===0){row.tow_kg=750;row.seats=5;add('tow_kg','/specs/techSpecs/0/data/0/value','750');add('seats','/specs/techSpecs/0/data/1/value','5');}
    const name=`Active ${row.drivetrain} ${row.battery_kwh} kWh ${index?230:170} hk`;
    const payload={adapter:'toyota_embedded_config_v1',source_configuration:cfg,field_evidence:proof,motorization_pointer:prefix,
      manufacturer_variant_id:cars[index],manufacturer_model_id:modelId,model_config_version:'test.1',grade:'Active'};
    const draft=(await db.query(`insert into extracted_variant_drafts(canonical_model_id,source_id,brand,model,variant_name,price_sek,battery_kwh,drivetrain,wltp_range_km,wltp_consumption_kwh_100km,tow_kg,seats,source_url,source_hash,source_quote,extraction_confidence,extraction_payload,validation_status,validation_errors)
      values ($1,$2,'Toyota','bZ4X',$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,0.99,$14,'validated','[]') returning *`,
      [model.id,source.id,name,row.price_sek,row.battery_kwh,row.drivetrain,row.wltp_range_km,row.wltp_consumption_kwh_100km,row.tow_kg??null,row.seats??null,url,hash,motor.engine.name+' | Active | '+motor.price.cash,JSON.stringify(payload)])).rows[0];
    targets.push({draft_id:draft.id,expected_updated_at:draft.updated_at});
  }
  targets.sort((a,b)=>a.draft_id.localeCompare(b.draft_id));
  const packet={adapter:'toyota_embedded_config_v1',batch_id:'c'.repeat(64),source_id:source.id,
    expected_source_hash:oldHash,expected_source_updated_at:source.updated_at,source_hash:hash,final_url:url,fetched_at:new Date().toISOString(),targets};
  const snapshot=async()=>(await db.query(`select jsonb_build_object('variants',(select jsonb_agg(to_jsonb(v) order by v.id) from canonical_model_variants v),
    'drafts',(select jsonb_agg(to_jsonb(d) order by d.id) from extracted_variant_drafts d),'sources',(select jsonb_agg(to_jsonb(s)) from manufacturer_sources s)) as data`)).rows[0].data;
  const call=async(p)=>(await db.query('select public.publish_new_toyota_variants($1) as result',[p])).rows[0].result;
  await db.exec('set role service_role');
  for(const bad of [{...packet,targets:targets.slice(0,1)},{...packet,targets:[targets[0],targets[0]]},
    {...packet,fetched_at:'2020-01-01T00:00:00Z'},{...packet,source_hash:'bad'},
    {...packet,expected_source_hash:hash},{...packet,final_url:'https://example.org/'},
    {...packet,targets:targets.map((t,i)=>i?{...t,expected_updated_at:'2020-01-01T00:00:00Z'}:t)}]) {
    const before=await snapshot(); await assert.rejects(call(bad)); assert.deepEqual(await snapshot(),before);
  }
  const last=targets[1].draft_id;
  for(const [field,value] of [['validation_status','needs_review'],['extraction_confidence',0.5],['price_type','campaign_price'],
    ['source_quote','invented'],['battery_kwh',80],['variant_name','Active AWD'],['dc_charge_kw',150],['price_sek',1000000],
    ['validation_errors',['uncertain']],['extraction_payload',{}]]) {
    const original=(await db.query(`select ${field} as value from extracted_variant_drafts where id=$1`,[last])).rows[0].value;
    const isJson=['extraction_payload','validation_errors'].includes(field);
    await db.query(`update extracted_variant_drafts set ${field}=$1 where id=$2`,[isJson?JSON.stringify(value):value,last]);
    const before=await snapshot(); await assert.rejects(call(packet)); assert.deepEqual(await snapshot(),before,'Late rejection rolls back earlier insert');
    await db.query(`update extracted_variant_drafts set ${field}=$1 where id=$2`,[isJson?JSON.stringify(original):original,last]);
  }
  const original=(await db.query('select extraction_payload from extracted_variant_drafts where id=$1',[last])).rows[0].extraction_payload;
  for(const mutate of [p=>p.field_evidence.price_sek.raw_value=1,p=>p.field_evidence.battery_kwh.source_pointer='/car/id',
    p=>p.source_configuration.commonSettings.country='us',p=>p.source_configuration.car.model.name='Nya Toyota bZ4X Touring',
    p=>p.source_configuration.carConfigMotorization.motorization[Number(p.motorization_pointer.split('/').at(-1))].specs[0].certification=1]) {
    const bad=structuredClone(original); mutate(bad);
    await db.query('update extracted_variant_drafts set extraction_payload=$1 where id=$2',[JSON.stringify(bad),last]);
    const before=await snapshot(); await assert.rejects(call(packet)); assert.deepEqual(await snapshot(),before);
  }
  await db.query('update extracted_variant_drafts set extraction_payload=$1 where id=$2',[JSON.stringify(original),last]);
  const applied=await call(packet); assert.equal(applied.inserted,2); assert.equal(applied.already_applied,false);
  const after=await snapshot(); const replay=await call(packet); assert.equal(replay.inserted,0); assert.equal(replay.already_applied,true);
  assert.deepEqual(await snapshot(),after,'Replay changes no facts or timestamps');
  assert.deepEqual((await db.query('select * from canonical_model_variants where manufacturer_variant_id is null order by id')).rows,legacy);
  assert.deepEqual((await db.query('select * from canonical_models')).rows,flags);
  const publicRows=(await db.query('select * from public_ev_variants')).rows;
  assert.equal(publicRows.length,4);assert.equal(publicRows.filter(r=>r.source_hash===hash&&r.verified_at).length,2);
  await assert.rejects(db.query('insert into canonical_model_variants(canonical_model_id,variant_name,manufacturer_variant_id) values ($1,$2,$3)',[model.id,'Duplicate identity',cars[0]]),e=>e.code==='23505');
  await db.query('update manufacturer_sources set content_hash=$1 where id=$2',[oldHash,source.id]);
  await assert.rejects(call(packet),'Changed applied source rejects replay');
  await db.exec('reset role');
  console.log(JSON.stringify({toyota_publication_ok:true,transactional_rollback:true,source_pointers:true,unique_identity:true,
    stale_and_concurrent_rejected:true,legacy_and_flags_unchanged:true,replay_idempotent:true,public_roles_denied:true,remote_requests:0}));
} finally {await db.close();}
