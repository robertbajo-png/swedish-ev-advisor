import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {PGlite} from '@electric-sql/pglite';
const db=new PGlite();
const hash='b'.repeat(64);
const reserve=(id,caseKey='model',permit='luna',input=1000,output=1200,digest=hash)=>db.query(
  'select reserve_news_luna_ai($1,$2,$3,$4,$5,$6,$7) r',[permit,digest,caseKey,id,input,output,'a'.repeat(64)]).then(r=>r.rows[0].r);
const response=(more={})=>({model:'gpt-6-luna',service_tier:'default',status:'completed',usage:{input_tokens:1000,
  output_tokens:200,total_tokens:1200,input_tokens_details:{cached_tokens:100,cache_write_tokens:400,
    cache_write_tokens_details:{ttl_30m_tokens:300,ttl_12h_tokens:100}}},...more});
const settle=(id,body=response())=>db.query('select settle_news_luna_ai($1,$2) r',[id,JSON.stringify(body)]).then(r=>r.rows[0].r);
const denied=p=>assert.rejects(p,e=>e.code==='42501');
try {
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls; grant usage on schema public to anon,authenticated,service_role; create table canonical_models(id uuid primary key)');
  for(const file of ['007_news_engine.sql','012_news_release_guardrails.sql','013_news_unknown_usage_accounting.sql',
    '016_news_private_luna_test.sql','016_news_private_luna_test.sql'])
    await db.exec(await readFile(new URL('../database/migrations/'+file,import.meta.url),'utf8'));
  await db.exec(`insert into news_luna_test_permits(id,expires_at,maximum_micro_usd,manifest_hash,approval_note)
    values('luna',clock_timestamp()+interval '1 hour',20000,repeat('b',64),'Owner approved one private GPT-6 Luna probe; ordinary caps remain unchanged.')`);
  for(const role of ['anon','authenticated']) {
    await db.exec('set role '+role);
    await denied(reserve(randomUUID())); await denied(settle(randomUUID()));
    await denied(db.exec('select * from news_luna_test_permits'));
    await denied(db.exec("select close_news_luna_test('luna')"));
    await db.exec('reset role');
  }
  await db.exec('set role service_role');
  await denied(db.exec('update news_luna_test_permits set maximum_micro_usd=20000'));
  await denied(db.exec("insert into news_luna_test_permits(id) values('unapproved')"));
  for(const args of [[randomUUID(),'other'],[randomUUID(),'model','missing'],[randomUUID(),'model','luna',0],
    [randomUUID(),'model','luna',1000,2500],[randomUUID(),'model','luna',1000,1200,'c'.repeat(64)]])
    assert.equal((await reserve(...args)).allowed,false);
  const id=randomUUID(); const first=await reserve(id);
  assert.equal(first.allowed,true); assert.equal(Number(first.reserved_micro_usd),850);
  assert.equal((await reserve(randomUUID(),'price')).reason,'luna_unresolved_accounting');
  const inconsistent=response(); inconsistent.usage.input_tokens_details.cache_write_tokens=0;
  assert.equal((await settle(id,inconsistent)).reason,'luna_inconsistent_usage_hold_retained');
  // (500 ordinary*0.10 +100 cached*0.01 +300 writes*0.125 +100 writes*0.25 +200 output*0.5)=213.5 micro-USD.
  assert.equal((await settle(id)).charged_micro_usd,214);
  assert.equal((await settle(id)).settled,true);
  assert.equal((await reserve(randomUUID())).reason,'luna_attempt_already_consumed');
  const unknown=randomUUID(); await reserve(unknown,'price');
  assert.equal((await settle(unknown,response({usage:{input_tokens:1000,output_tokens:200,total_tokens:1200}}))).settled,false);
  assert.equal(Number((await db.query('select charged_micro_usd from news_ai_requests where id=$1',[unknown])).rows[0].charged_micro_usd),850);
  assert.equal((await settle(unknown,response({model:'gpt-5.6-luna'}))).reason,'luna_unexpected_provider_contract');
  assert.equal((await reserve(randomUUID(),'statistics')).allowed,false);
  assert.equal((await settle(unknown)).settled,true); // accounting remains possible after closure
  await db.exec(`reset role; insert into news_luna_test_permits(id,expires_at,maximum_micro_usd,manifest_hash,approval_note)
    values('caps',clock_timestamp()+interval '1 hour',20000,repeat('b',64),'Independent ordinary budget and switch tests, not an exception.');
    insert into news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,charged_micro_usd,provider_status,settled_at)
    values('${randomUUID()}','old','gpt-5.4-mini',repeat('d',64),1,1,249000,249000,'completed',now()); set role service_role;`);
  assert.equal((await reserve(randomUUID(),'model','caps',10000)).reason,'luna_ordinary_budget_exhausted');
  await db.exec("reset role; delete from news_ai_requests where stage='old'; update news_ai_config set publication_enabled=true; set role service_role;");
  assert.equal((await reserve(randomUUID(),'model','caps')).allowed,false);
  await db.exec("reset role; update news_ai_config set publication_enabled=false; update news_luna_test_permits set expires_at=clock_timestamp() where id='caps'; set role service_role;");
  assert.equal((await reserve(randomUUID(),'model','caps')).allowed,false);
  const cfg=(await db.query('select * from news_ai_config')).rows[0];
  assert.equal(cfg.model,'gpt-5.4-mini'); assert.equal(cfg.enabled,false); assert.equal(cfg.publication_enabled,false);
  assert.equal(Number(cfg.daily_limit_micro_usd),250000); assert.equal(Number(cfg.monthly_limit_micro_usd),5000000);
  console.log(JSON.stringify({news_luna_budget_ok:true,idempotent:true,public_denials:true,owner_only:true,
    three_one_use_cases:true,ordinary_caps_only:true,cache_accounting:true,unknown_usage_retained:true,closed_and_expired_denied:true,production_off:true}));
} finally {await db.close();}
