import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {PGlite} from '@electric-sql/pglite';
import {captureReleaseState,releaseExactlyOne,POLICY,METHOD} from './factual_notice_release.mjs';

const generated=spawnSync(process.execPath,['scripts/run_python.mjs','-c',
 "import sys,json;sys.path.insert(0,'scripts');sys.path.insert(0,'tests');from datetime import datetime,timezone;from test_news_factual_notices import capture;from news_factual_notices import prepare_price_notices;from prepare_factual_notice_release import make_manifest;c=capture();now=datetime.now(timezone.utc);c['source']['fetched_at']=now.isoformat();p=prepare_price_notices(c,now)[0];print(json.dumps(make_manifest(p,now=now,fixture=True)))"],
 {encoding:'utf8',maxBuffer:3_000_000,windowsHide:true});
assert.equal(generated.status,0,generated.stderr);
const manifest=JSON.parse(generated.stdout),db=new PGlite();
const migration=await readFile(new URL('../database/migrations/024_single_fact_notice_release.sql',import.meta.url),'utf8');
try{
 await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;
  create table canonical_models(id uuid primary key,brand text,model text);
  create table canonical_model_variants(id uuid primary key,canonical_model_id uuid,variant_name text);
  insert into canonical_models values('00000000-0000-4000-8000-000000000001','Kia','Ev2');
  insert into canonical_model_variants values('00000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000001','Untouched');`);
 for(const file of ['007_news_engine.sql','012_news_release_guardrails.sql','013_news_unknown_usage_accounting.sql','017_news_notice_publication.sql','018_news_gpt6_sol.sql'])
  await db.exec(await readFile(new URL('../database/migrations/'+file,import.meta.url),'utf8'));
 await db.exec('update news_ai_config set daily_article_limit=1');
 await db.exec(await readFile(new URL('../database/migrations/022_news_budget_050_10.sql',import.meta.url),'utf8'));
 await db.exec('update news_ai_config set enabled=true,publication_enabled=true,daily_limit_micro_usd=500000,monthly_limit_micro_usd=10000000,daily_article_limit=1');
 const expected=JSON.parse(JSON.stringify(await captureReleaseState(db))),approvedDay=new Date().toISOString().slice(0,10);
 const options={migration,expected,approvedDay,allowFixture:true};
 const dry=await releaseExactlyOne(db,manifest,options);assert.equal(dry.committed,false);
 assert.deepEqual(await captureReleaseState(db),expected);
 assert.equal((await db.query("select to_regprocedure('public.news_legacy_notice_release_error(public.news_articles)') value")).rows[0].value,null,'DDL must roll back too');
 const changed=structuredClone(manifest);changed.tables.news_items[0].payload.content+=' changed';
 await assert.rejects(releaseExactlyOne(db,changed,options),/single_fact_source_hash_changed/);
 assert.deepEqual(await captureReleaseState(db),expected);
 const failed=structuredClone(manifest);failed.tables.news_quality_checks[0].payload.review_method='invented';
 await assert.rejects(releaseExactlyOne(db,failed,options));
 assert.deepEqual(await captureReleaseState(db),expected);
 await assert.rejects(releaseExactlyOne(db,manifest,{...options,allowFixture:false}),/Synthetic notices/);
 const result=await releaseExactlyOne(db,manifest,{...options,commit:true});assert.equal(result.committed,true);
 assert.equal(result.daily_count,1);assert.equal(result.public_count,1);
 assert.equal(result.article.payload.title,manifest.tables.news_articles[0].payload.title);
 const a=manifest.tables.news_articles[0],row=(await db.query('select * from news_articles where id=$1',[a.id])).rows[0];
 const snapshot=(await db.query('select news_notice_source_snapshot($1) value',[a.id])).rows[0].value;
 const replay=(await db.query('select publish_news_notice($1,$2,$3,$4) value',[a.id,row.artifact_hash,JSON.stringify(row.payload),JSON.stringify(snapshot)])).rows[0].value;
 assert.deepEqual(replay,{published:true,already_published:true});
 assert.equal((await db.query('select count(*)::int n from public_news_articles')).rows[0].n,1);
 const duplicate=structuredClone(manifest);duplicate.article_id='different';duplicate.tables.news_articles[0].id='different';
 await assert.rejects(releaseExactlyOne(db,duplicate,{...options,expected:await captureReleaseState(db)}));
 assert.equal((await db.query('select count(*)::int n from public_news_articles')).rows[0].n,1);
 for(const role of ['anon','authenticated']){
  await db.exec('set role '+role);
  await assert.rejects(db.query("select publish_news_notice('x','x','{}','{}')"),e=>e.code==='42501');
  await assert.rejects(db.query('select * from news_notice_release_config'),e=>e.code==='42501');
  await assert.rejects(db.query("select news_legacy_notice_release_error(null::news_articles)"),e=>e.code==='42501');
  await db.exec('reset role');
 }
 await db.exec('set role service_role');
 await assert.rejects(db.query('update news_notice_release_config set enabled=true'),e=>e.code==='42501');
 await db.exec('reset role');
 const config=(await captureReleaseState(db));assert.deepEqual(config.config,expected.config);assert.deepEqual(config.notice,expected.notice);
 assert.equal((await db.query('select policy from news_notice_publications')).rows[0].policy,POLICY);
 assert.equal((await db.query('select review_method from news_notice_publications')).rows[0].review_method,METHOD);
 console.log(JSON.stringify({single_fact_release:'passed',one_committed:true,replay_safe:true,late_rollback:true,
  ddl_rollback:true,source_and_review_guards:true,roles:true,config_restored:true,global_limit:1,canonical_preserved:true,
  fixture_only:true,paid_calls:0,real_publications:0}));
}finally{await db.close();}
