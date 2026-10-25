import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {PGlite} from '@electric-sql/pglite';

const db=new PGlite();
const sql=name=>readFile(new URL(`../database/migrations/${name}`,import.meta.url),'utf8');
const permit=randomUUID(), digest='a'.repeat(64), writerDigest='b'.repeat(64);
const reserve=(stage='ev_news_hybrid_launch_write',args={})=>{
  const id=randomUUID();
  return db.query('select reserve_news_sol_test_ai($1,$2,$3,$4,$5,$6,$7) r',
    [permit,args.manifest??digest,id,stage,args.input??1000,args.output??2500,args.hash??writerDigest])
    .then(r=>({id,...r.rows[0].r}));
};
const response={model:'gpt-6-sol',service_tier:'default',status:'completed',usage:{input_tokens:1000,output_tokens:100,
  total_tokens:1100,input_tokens_details:{cached_tokens:0,cache_write_tokens:0}},output:[]};
const settle=id=>db.query('select settle_news_ai($1,1000,100,$2) r',[id,JSON.stringify(response)]).then(r=>r.rows[0].r);
const denied=p=>assert.rejects(p,e=>e.code==='42501');
const reset=async(cap=370000)=>{
  await db.exec('reset role; truncate news_ai_requests,news_sol_test_permits');
  await db.query(`insert into news_sol_test_permits(id,expires_at,maximum_micro_usd,manifest_hash,writer_hash,
    writer_input_bound,review_input_bound,approval_note) values($1,now()+interval '1 hour',$2,$3,$4,1000,5000,
    'Owner approved one bounded private Sol trial; no publication')`,[permit,cap,digest,writerDigest]);
  await db.exec(`update news_ai_config set enabled=false,publication_enabled=false,model='gpt-6-sol',
    daily_limit_micro_usd=250000,monthly_limit_micro_usd=5000000,pricing_valid_until=current_date+30;
    set role service_role`);
};

try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    grant usage on schema public to anon,authenticated,service_role;
    create table canonical_models(id uuid primary key,brand text,model text);
    insert into canonical_models values('00000000-0000-4000-8000-000000000001','Untouched','Vehicle');
    create view public_ev_variants as select * from canonical_models;`);
  for(const f of ['007_news_engine.sql','012_news_release_guardrails.sql','013_news_unknown_usage_accounting.sql',
    '017_news_notice_publication.sql','018_news_gpt6_sol.sql','019_news_private_sol_test.sql','019_news_private_sol_test.sql']) await db.exec(await sql(f));
  const before=(await db.query('select * from canonical_models')).rows;
  for(const role of ['anon','authenticated']){
    await db.exec(`set role ${role}`);
    await denied(reserve()); await denied(db.query('select * from news_sol_test_permits'));
    await denied(db.query('select close_news_sol_test($1)',[permit]));
    await db.exec('reset role');
  }
  await db.exec('set role service_role');
  await denied(db.query("insert into news_sol_test_permits(id) values('forged')"));
  await denied(db.query("update news_ai_config set enabled=true"));
  assert.equal((await reserve()).reason,'sol_test_permit_inactive_or_wrong_manifest');
  await reset();
  assert.equal((await reserve('ev_news_hybrid_launch_review')).allowed,false);
  assert.equal((await reserve(undefined,{manifest:'c'.repeat(64)})).allowed,false);
  assert.equal((await reserve(undefined,{hash:'c'.repeat(64)})).allowed,false);
  assert.equal((await reserve(undefined,{input:1001})).allowed,false);
  assert.equal((await reserve(undefined,{output:3000})).allowed,false);
  const write=await reserve(); assert.equal(write.reserved_micro_usd,30000);
  assert.equal((await reserve()).reason,'sol_test_attempt_consumed');
  assert.equal((await reserve('ev_news_hybrid_launch_review')).allowed,false);
  assert.equal((await settle(write.id)).charged_micro_usd,3000);
  const review=await reserve('ev_news_hybrid_launch_review'); assert.equal(review.allowed,true);
  await settle(review.id);
  assert.equal((await reserve('ev_news_hybrid_launch_review')).reason,'sol_test_attempt_consumed');
  assert.equal((await db.query('select close_news_sol_test($1) r',[permit])).rows[0].r.closed,true);
  assert.equal((await reserve()).reason,'sol_test_permit_inactive_or_wrong_manifest');
  await reset(40000);
  const limited=await reserve(); await settle(limited.id);
  assert.equal((await reserve('ev_news_hybrid_launch_review')).reason,'sol_test_total_reservations_exhausted');
  await reset();
  await db.exec('reset role');
  await db.query("update news_sol_test_permits set expires_at=issued_at where id=$1",[permit]).then(
    ()=>assert.fail('Invalid lifetime accepted'),e=>assert.equal(e.code,'23514'));
  await db.query("update news_sol_test_permits set issued_at=now()-interval '2 hours',expires_at=now()-interval '1 hour' where id=$1",[permit]);
  await db.exec('set role service_role');
  assert.equal((await reserve()).allowed,false);
  await reset();
  await db.exec("reset role; update news_ai_config set enabled=true; set role service_role");
  assert.equal((await reserve()).reason,'sol_test_requires_paused_unchanged_production');
  await reset();
  await db.exec('reset role');
  await db.query(`insert into news_ai_requests(id,stage,model,request_hash,input_bound,output_bound,
    reserved_micro_usd,charged_micro_usd,settled_at,provider_status) values($1,'swedish_ev_article','gpt-5.4-mini',$2,1000,500,240000,240000,now(),'completed')`,[randomUUID(),digest]);
  await db.exec('set role service_role');
  const extra=await reserve(); assert.equal(extra.allowed,true,'Only this permit can exceed the daily cap');
  await settle(extra.id);
  await db.exec('reset role; update news_ai_requests set charged_micro_usd=4999999 where sol_test_id is null; set role service_role');
  assert.equal((await reserve('ev_news_hybrid_launch_review')).reason,'sol_test_period_allowance_exhausted');
  await db.exec('reset role');
  assert.deepEqual((await db.query('select * from canonical_models')).rows,before);
  const cfg=(await db.query('select * from news_ai_config')).rows[0];
  assert.equal(cfg.enabled,false); assert.equal(cfg.publication_enabled,false);
  assert.equal(Number(cfg.daily_limit_micro_usd),250000); assert.equal(Number(cfg.monthly_limit_micro_usd),5000000);
  console.log(JSON.stringify({sol_single_trial_sql_ok:true,owner_only_permits:true,two_stages_once:true,
    exact_writer_hash:true,permit_expiry:true,total_reservations_capped:true,monthly_cap_unchanged:true,
    production_off:true,vehicle_data_unchanged:true,paid_calls:0}));
} finally {await db.close();}
