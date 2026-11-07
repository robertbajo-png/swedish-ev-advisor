import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {PGlite} from '@electric-sql/pglite';

const db=new PGlite(),digest='a'.repeat(64);
const sql=name=>readFile(new URL('../database/migrations/'+name,import.meta.url),'utf8');
const migration=await sql('023_private_terra_news_probe.sql');
const response=(input=1000,output=100,cached=0,w30=0,w12=0)=>({model:'gpt-6.1-terra',service_tier:'default',status:'completed',
  usage:{input_tokens:input,output_tokens:output,input_tokens_details:{cached_tokens:cached,cache_write_tokens:w30+w12,
    ...(w30+w12?{cache_write_tokens_details:{ttl_30m_tokens:w30,ttl_12h_tokens:w12}}:{})}},output:[]});
const owner=()=>db.exec('reset role');
const reserve=async(stage='swedish_ev_article',input=1000,output=stage==='swedish_ev_article'?2000:1300,hash=digest,manifest=digest)=>{
  const id=randomUUID();
  return {id,...(await db.query('select reserve_news_terra_test($1,$2,$3,$4,$5,$6,$7) r',['test',manifest,id,stage,input,output,hash])).rows[0].r};
};
const settle=async(id,body=response())=>(await db.query('select settle_news_terra_test($1,$2) r',[id,JSON.stringify(body)])).rows[0].r;
const reset=async()=>{
  await owner();
  await db.exec(`truncate news_ai_requests; delete from news_terra_test_permits;
    update news_ai_config set model='gpt-6-sol',enabled=true,publication_enabled=true,daily_article_limit=1,
      daily_limit_micro_usd=250000,monthly_limit_micro_usd=5000000,pricing_valid_until=current_date+30;
    insert into news_terra_test_permits(id,expires_at,maximum_micro_usd,manifest_hash,writer_hash,writer_input_bound,review_input_bound,approval_note)
    values('test',now()+interval '1 hour',100000,'${digest}','${digest}',1000,10000,'Synthetic isolated owner permit, not a real authorization');
    set role service_role;`);
};
const denied=promise=>assert.rejects(promise,error=>error.code==='42501');
try{
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    grant usage on schema public to anon,authenticated,service_role;
    create table canonical_models(id uuid primary key,brand text,model text);
    insert into canonical_models values('00000000-0000-4000-8000-000000000001','Unchanged','Vehicle');
    create view public_ev_variants as select * from canonical_models;`);
  for(const name of ['007_news_engine.sql','012_news_release_guardrails.sql','013_news_unknown_usage_accounting.sql',
    '017_news_notice_publication.sql','018_news_gpt6_sol.sql'])await db.exec(await sql(name));
  await db.exec(`update news_ai_config set enabled=true,publication_enabled=true,daily_article_limit=1`);
  const before=(await db.query('select * from news_ai_config')).rows;
  const vehicles=(await db.query('select * from public_ev_variants')).rows;
  await db.exec(migration);await db.exec(migration);
  assert.deepEqual((await db.query('select * from news_ai_config')).rows,before);
  assert.deepEqual((await db.query('select * from public_ev_variants')).rows,vehicles);
  for(const role of ['anon','authenticated']){
    await db.exec('set role '+role);
    await denied(db.query('select * from news_terra_test_permits'));
    await denied(reserve());await denied(settle(randomUUID()));
    await denied(db.query("select close_news_terra_test('test')"));
    await owner();
  }
  await reset();
  await denied(db.exec("update news_ai_config set model='gpt-5.4-mini'"));
  await denied(db.exec("insert into news_terra_test_permits values('forged',now(),now()+interval '1 hour',null,1000,'a','a',1,1,'Forged')"));
  assert.equal((await reserve('ev_news_independent_audit')).allowed,false);
  for(const args of [['unapproved_stage'],['swedish_ev_article',1001],['swedish_ev_article',1000,2001],
    ['swedish_ev_article',1000,2000,'b'.repeat(64)],['swedish_ev_article',1000,2000,digest,'b'.repeat(64)]]){
    assert.equal((await reserve(...args)).allowed,false);
  }
  const first=await reserve();assert(first.allowed);assert.equal(first.reserved_micro_usd,12500);
  assert.equal((await reserve()).reason,'terra_stage_consumed');
  assert.equal((await settle(first.id)).charged_micro_usd,1500);
  assert((await settle(first.id)).settled);
  assert.equal((await settle(first.id,response(1000,101))).settled,false);
  const review=await reserve('ev_news_independent_audit');assert(review.allowed);
  assert((await settle(review.id)).settled);
  assert.equal((await reserve('ev_news_independent_audit')).reason,'terra_stage_consumed');
  assert.equal((await db.query('select count(*)::int n from news_ai_requests')).rows[0].n,2);
  for(const [cached,w30,w12,expected]of [[100,300,100,1630],[0,0,1000,3000],[1000,0,0,550],[0,0,0,1500]]){
    await reset();const req=await reserve();
    assert.equal((await settle(req.id,response(1000,100,cached,w30,w12))).charged_micro_usd,expected);
  }
  for(const patch of [{model:'gpt-6-sol'},{service_tier:'fast'},{status:null},{usage:{input_tokens:1000,output_tokens:100}}]){
    await reset();const req=await reserve();
    assert.equal((await settle(req.id,{...response(),...patch})).settled,false);
    assert.equal(Number((await db.query('select charged_micro_usd from news_ai_requests where id=$1',[req.id])).rows[0].charged_micro_usd),12500);
    assert.equal((await reserve('ev_news_independent_audit')).allowed,false);
  }
  await reset();const interrupted=await reserve();
  assert((await settle(interrupted.id,{...response(),status:'incomplete'})).settled);
  assert.equal((await reserve('ev_news_independent_audit')).allowed,false);
  await reset();const unknown=await reserve();
  const malformed=response();delete malformed.usage.input_tokens_details.cache_write_tokens;
  assert.equal((await settle(unknown.id,malformed)).settled,false);
  await owner();await db.exec("update news_ai_requests set budget_closed_at=now(),budget_closed_by='postgres',budget_closure_note='Synthetic retained unknown maximum'");
  await db.exec('set role service_role');
  assert.equal((await settle(unknown.id)).reason,'terra_closed_hold_preserved');
  await reset();const anomaly=await reserve();
  assert.equal((await settle(anomaly.id,response(1001))).settled,false);
  assert.equal((await reserve('ev_news_independent_audit')).allowed,false);
  assert.equal(Number((await db.query('select charged_micro_usd from news_ai_requests')).rows[0].charged_micro_usd),12500);
  await reset();await owner();
  await db.exec("update news_terra_test_permits set closed_at=now(); set role service_role;");
  assert.equal((await reserve()).allowed,false);
  await reset();await owner();
  await db.exec("update news_terra_test_permits set issued_at=now()-interval '2 hours',expires_at=now()-interval '1 minute'; set role service_role;");
  assert.equal((await reserve()).allowed,false);
  await reset();await owner();
  await db.exec("update news_terra_test_permits set maximum_micro_usd=100; set role service_role;");
  assert.equal((await reserve()).reason,'terra_test_cap_exhausted');
  await reset();await owner();
  await db.exec(`insert into news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,charged_micro_usd,
      settled_at,provider_status)values('${randomUUID()}','historical','gpt-6-sol','${digest}',1000,100,200000,200000,now(),'completed');
      set role service_role;`);
  assert.equal((await reserve()).reason,'terra_ordinary_budget_exhausted','ordinary daily cap');
  await reset();await owner();
  const retained=randomUUID();
  await db.query(`insert into news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,reserved_micro_usd,charged_micro_usd,
    settled_at,provider_status,created_at)values($1,'historical','gpt-6-sol',$2,1000,100,4950000,4950000,now(),'completed',date_trunc('month',now() at time zone 'UTC') at time zone 'UTC')`,[retained,digest]);
  await db.exec('set role service_role');
  assert.equal((await reserve()).reason,'terra_ordinary_budget_exhausted','ordinary monthly cap');
  await reset();await owner();
  await db.exec("update news_ai_config set pricing_valid_until=current_date; set role service_role;");
  assert.equal((await reserve()).allowed,false);
  await reset();await owner();
  await db.exec("update news_ai_config set daily_article_limit=2; set role service_role;");
  assert.equal((await reserve()).allowed,false);
  await reset();await owner();
  assert((await db.query("select close_news_terra_test('test') r")).rows[0].r.closed);
  assert((await db.query("select close_news_terra_test('test') r")).rows[0].r.closed);
  assert.deepEqual((await db.query('select * from public_ev_variants')).rows,vehicles);
  console.log(JSON.stringify({private_terra_sql_guards:true,owner_only_permits:true,two_calls_maximum:true,
    ordinary_budgets_preserved:true,production_model_and_switches_unchanged:true,cache_and_unknown_usage:true,
    paid_calls:0,production_writes:0}));
}catch(error){
  console.error(JSON.stringify({terra_test_failed:true,message:error.message,code:error.code,position:error.position,
    actual:error.actual,expected:error.expected}));
  process.exitCode=1;
}finally{await db.close();}
