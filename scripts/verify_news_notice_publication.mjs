import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {PGlite} from '@electric-sql/pglite';

const generated=spawnSync(process.execPath,['scripts/run_python.mjs','-c',
  "import sys,json;sys.path.insert(0,'tests');from test_news_notice_publication import sql_fixtures;print(json.dumps(sql_fixtures()))"],
  {encoding:'utf8',maxBuffer:2*1024*1024});
assert.equal(generated.status,0,generated.stderr);
const fixtures=JSON.parse(generated.stdout);
const db=new PGlite();
const migration=await readFile(new URL('../database/migrations/017_news_notice_publication.sql',import.meta.url),'utf8');
const deny=p=>assert.rejects(p,e=>e.code==='42501');
const snapshot=id=>db.query('select news_notice_source_snapshot($1) s',[id]).then(r=>r.rows[0].s);
const publish=(f,s=f.snapshot,hash=f.article.artifact_hash,payload=f.article.payload)=>db.query(
  'select publish_news_notice($1,$2,$3,$4) r',[f.article.id,hash,JSON.stringify(payload),JSON.stringify(s)]).then(r=>r.rows[0].r);
const count=async table=>Number((await db.query('select count(*) n from '+table)).rows[0].n);
function ownerSql(f, publicCount=0) {
  const result=spawnSync(process.execPath,['scripts/run_python.mjs','-c',
    "import sys,json;sys.path.insert(0,'scripts');from news_notice_release import single_release_sql;from news_notices import NOTICE_REVIEW;f,n=json.load(sys.stdin);a=f['article'];print(single_release_sql(a,{'passed':True,'errors':[],'artifact_hash':a['artifact_hash'],'method':NOTICE_REVIEW,'snapshot':f['snapshot']},n))"],
    {input:JSON.stringify([f,publicCount]),encoding:'utf8',maxBuffer:2*1024*1024});
  assert.equal(result.status,0,result.stderr);
  return result.stdout;
}
const reset=()=>db.exec(`reset role; truncate news_notice_publications,news_quality_checks,news_vehicle_links,
  news_article_sources,news_verification_requests,news_articles,news_items,news_story_clusters,news_sources cascade;
  update news_notice_release_config set enabled=false,daily_limit=2;
  update news_ai_config set enabled=false,publication_enabled=false,daily_article_limit=2;`);
const enable=()=>db.exec('reset role; update news_notice_release_config set enabled=true; update news_ai_config set publication_enabled=true');
async function seed(original=fixtures[0]) {
  const f=structuredClone(original),s=f.snapshot;
  await db.query('insert into news_sources(id,payload) values($1,$2)',[s.source.id,JSON.stringify(s.source.payload)]);
  await db.query('insert into news_story_clusters(id,event_key,payload) values($1,$2,$3)',[s.cluster.id,s.cluster.event_key,JSON.stringify(s.cluster.payload)]);
  await db.query('insert into news_items(id,source_id,url,cluster_id,status,payload) values($1,$2,$3,$4,$5,$6)',
    [s.item.id,s.item.source_id,s.item.url,s.item.cluster_id,s.item.status,JSON.stringify(s.item.payload)]);
  f.article.artifact_hash=(await db.query('insert into news_articles(id,cluster_id,slug,status,payload) values($1,$2,$3,$4,$5) returning artifact_hash',
    [f.article.id,f.article.cluster_id,f.article.slug,f.article.status,JSON.stringify(f.article.payload)])).rows[0].artifact_hash;
  for(const q of s.checks) {
    q.artifact_hash=f.article.artifact_hash;
    await db.query('insert into news_quality_checks(id,article_id,kind,artifact_hash,passed,payload) values($1,$2,$3,$4,$5,$6)',
      [q.id,f.article.id,q.kind,q.artifact_hash,q.passed,JSON.stringify(q.payload)]);
  }
  for(const l of s.links) await db.query('insert into news_article_sources(id,article_id,item_id,payload) values($1,$2,$3,$4)',
    ['link-'+f.article.id,f.article.id,l.item_id,JSON.stringify(l.payload)]);
  assert.deepEqual(await snapshot(f.article.id),s,'Python worker/SQL JSONB snapshot contract');
  return f;
}
try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls; create role outsider;
    grant usage on schema public to anon,authenticated,service_role,outsider;
    create table canonical_models(id uuid primary key,brand text,model text);
    insert into canonical_models values('00000000-0000-4000-8000-000000000001','Untouched','Vehicle');`);
  for(const file of ['007_news_engine.sql','012_news_release_guardrails.sql','013_news_unknown_usage_accounting.sql'])
    await db.exec(await readFile(new URL('../database/migrations/'+file,import.meta.url),'utf8'));
  const before=(await db.query('select to_jsonb(c) c from news_ai_config c')).rows;
  const cars=(await db.query('select * from canonical_models')).rows;
  await db.exec(migration);await db.exec(migration);
  assert.deepEqual((await db.query('select to_jsonb(c) c from news_ai_config c')).rows,before);
  assert.equal((await db.query('select enabled from news_notice_release_config')).rows[0].enabled,false);
  const readiness=await readFile(new URL('../database/checks/news_notice_release_readiness.sql',import.meta.url),'utf8');
  for(const row of (await db.query(readiness)).rows.filter(r=>r.required)) assert.equal(row.result,'true',row.check_name);
  for(const role of ['anon','authenticated','outsider']) {
    await db.exec('set role '+role);
    await deny(db.query("select publish_news_notice('x','x','{}','{}')"));
    await deny(db.query('select * from news_notice_release_config'));
    await deny(db.query('select * from news_notice_publications'));
    await deny(db.query("select news_notice_source_snapshot('x')"));
    await db.exec('reset role');
  }
  await db.exec('set role service_role');
  await deny(db.exec('update news_notice_release_config set enabled=true'));
  await deny(db.exec("insert into news_notice_publications(article_id) values('x')"));
  await deny(db.exec("select news_notice_source_snapshot('x')"));
  await db.exec('reset role');

  for(const fixture of fixtures) {
    await reset(); const first=await seed(fixture);
    await db.exec(ownerSql(first));
    assert.equal(await count('public_news_articles'),1,'single owner transaction publishes exactly once');
    assert.equal(await count('news_notice_publications'),1);
    assert.deepEqual((await db.query('select enabled,publication_enabled from news_ai_config')).rows[0],
      {enabled:false,publication_enabled:false});
    assert.equal((await db.query('select enabled from news_notice_release_config')).rows[0].enabled,false);
    await assert.rejects(db.exec(ownerSql(first)),/single_notice_public_count_changed/);
    await db.exec('rollback');
    assert.equal(await count('public_news_articles'),1,'replay cannot publish another notice');
  }
  await reset(); const failingFirst=await seed();
  await db.exec("update news_quality_checks set passed=false");
  await assert.rejects(db.exec(ownerSql(failingFirst)),/notice_source_snapshot_changed/);
  await db.exec('rollback');
  assert.equal(await count('public_news_articles'),0);
  assert.equal(await count('news_notice_publications'),0);
  assert.equal((await db.query('select publication_enabled from news_ai_config')).rows[0].publication_enabled,false);
  assert.equal((await db.query('select enabled from news_notice_release_config')).rows[0].enabled,false,
    'failure rolls the temporary flags back without leaving a release window');
  const quoted=structuredClone(failingFirst);
  quoted.snapshot.item.payload.content="Source's $single_notice_release$; SELECT 'untrusted source';";
  await assert.rejects(db.exec(ownerSql(quoted)),/notice_source_snapshot_changed/);
  await db.exec('rollback');
  assert.equal(await count('public_news_articles'),0,'source prose cannot escape the owner SQL body');
  await reset();

  let f=await seed();
  await assert.rejects(publish(f),/notice_publication_disabled/);
  await db.exec('update news_notice_release_config set enabled=true');
  await assert.rejects(publish(f),/News publication disabled/);
  assert.equal(await count('news_notice_publications'),0,'failed commit rolls receipt back');
  await db.exec('update news_notice_release_config set enabled=false; update news_ai_config set publication_enabled=true');
  await assert.rejects(publish(f),/notice_publication_disabled/);

  for(const fixture of fixtures) {
    await reset(); f=await seed(fixture);await enable();
    await assert.rejects(db.query('select publish_news_article($1)',[f.article.id]),/notice_requires_transactional_publication/);
    await assert.rejects(db.query("update news_articles set status='published' where id=$1",[f.article.id]),/notice_requires_transactional_publication/);
    await db.exec('set role service_role');
    assert.deepEqual(await publish(f),{published:true,already_published:false});
    assert.deepEqual(await publish(f),{published:true,already_published:true});
    await assert.rejects(db.query("update news_articles set slug='renamed' where id=$1",[f.article.id]),/immutable/);
    await deny(db.query('delete from news_notice_publications'));
    await db.exec('set role anon');
    const visible=(await db.query('select * from public_news_articles')).rows;
    assert.equal(visible.length,1);
    const p=visible[0].payload;
    for(const key of ['notice_facts','source_hash','fact_ids','item_id','checked_at','transaction_id'])
      assert.equal(JSON.stringify(p).includes('"'+key+'"'),false,key);
    assert.equal(p.editorial_method,'Automatisk faktanotis med källkontroll');
    assert.equal(p.title,f.article.payload.title);assert.equal(p.image,null);
    await deny(db.query("update public_news_articles set slug='bad'"));
  }
  await reset();f=await seed();await enable();
  await db.query("update news_items set payload=jsonb_set(payload,'{fetched_at}',to_jsonb(clock_timestamp()::text)) where id=$1",[f.snapshot.item.id]);
  await assert.rejects(publish(f),/notice_source_snapshot_changed/);
  assert.equal(await count('news_notice_publications'),0);

  const failures=[
    ["update news_items set payload=jsonb_set(payload,'{fetched_at}',to_jsonb((now()-interval '2 days')::text))",/notice_source_stale/],
    ["update news_items set payload=jsonb_set(payload,'{content}',to_jsonb('changed evidence'::text))",/notice_source_hash_changed/],
    ["update news_items set payload=jsonb_set(payload,'{access_status}',to_jsonb('blocked'::text))",/notice_source_not_ready/],
    ["update news_sources set payload=jsonb_set(payload,'{kind}',to_jsonb('publisher'::text))",/notice_source_not_official/],
    ["update news_quality_checks set passed=false",/notice_missing_or_stale_checks/],
    ["update news_quality_checks set payload=jsonb_set(payload,'{policy_version}',to_jsonb('news-editorial-2026-10-v2'::text))",/notice_missing_or_stale_checks/],
    ["update news_quality_checks set payload=jsonb_set(payload,'{audit_performed}','true'::jsonb)",/notice_missing_or_stale_checks/],
    ["update news_quality_checks set payload=jsonb_set(payload,'{checked_at}',to_jsonb((now()-interval '2 days')::text))",/notice_missing_or_stale_checks/],
    ["delete from news_article_sources",/notice_attribution_rows_mismatch/],
  ];
  for(const [sql,error] of failures) {
    await reset();f=await seed();await enable();await db.exec(sql);
    await assert.rejects(publish(f,await snapshot(f.article.id)),error);
    assert.equal(await count('news_notice_publications'),0);assert.equal(await count('public_news_articles'),0);
  }
  await reset();f=await seed();await enable();
  await db.query("update news_articles set payload=jsonb_set(payload,'{intro}',to_jsonb('Invented text'::text)) where id=$1",[f.article.id]);
  await assert.rejects(publish(f),/notice_article_snapshot_changed/);

  // Separate legacy checks still work, but cannot authorize the notice path.
  await reset();f=await seed();await enable();
  await db.exec("insert into news_story_clusters(id,event_key,payload) values('legacy','legacy','{}')");
  const oldPayload={title:'Legacy article',intro:'Independent checked article',paragraphs:[{text:'Body',kind:'reporting'}],sources:f.article.payload.sources};
  const old=(await db.query("insert into news_articles(id,cluster_id,slug,payload) values('legacy','legacy','legacy',$1) returning artifact_hash",[JSON.stringify(oldPayload)])).rows[0];
  await db.query("insert into news_article_sources(id,article_id,item_id,payload) values('legacy','legacy',$1,'{}')",[f.snapshot.item.id]);
  await assert.rejects(db.exec("select publish_news_article('legacy')"),/quality gates/);
  for(const kind of ['evidence','editorial','originality']) await db.query(
    "insert into news_quality_checks(id,article_id,kind,artifact_hash,passed,payload) values($1,'legacy',$2,$3,true,$4)",
    ['legacy-'+kind,kind,old.artifact_hash,JSON.stringify({policy_version:'news-editorial-2026-10-v2'})]);
  await db.exec("select publish_news_article('legacy')");
  await assert.rejects(publish(f),/notice_event_already_published/);

  await reset();f=await seed();await enable();await db.exec('update news_notice_release_config set daily_limit=1');
  await publish(f);
  const other=await seed(fixtures[2]);
  await assert.rejects(publish(other),/notice_daily_publication_limit/);
  assert.equal(await count('news_notice_publications'),1);assert.equal(await count('public_news_articles'),1);
  await db.exec(migration);
  assert.equal((await db.query('select enabled from news_notice_release_config')).rows[0].enabled,true,'idempotent install never resets owner flags');
  assert.deepEqual((await db.query('select * from canonical_models')).rows,cars);
  assert.equal(await count('news_ai_requests'),0);
  console.log(JSON.stringify({notice_publication_sql_ok:true,three_templates:true,default_off:true,owner_only:true,
    master_switch:true,snapshot_races:true,transactional_receipts:true,idempotent:true,source_and_check_guards:true,
    duplicates_and_daily_limit:true,legacy_separation:true,public_sanitization:true,vehicle_data_unchanged:true,
    single_owner_atomic_release:true,paid_calls:0}));
} catch(error) {
  console.error(JSON.stringify({message:error.message,code:error.code,position:error.position,where:error.where,
    detail:error.detail,assertion:error.code==='ERR_ASSERTION'?{actual:error.actual,expected:error.expected,stack:error.stack}:undefined}));
  process.exitCode=1;
} finally {await db.close();}
