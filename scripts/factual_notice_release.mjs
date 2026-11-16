import assert from 'node:assert/strict';

export const POLICY='news-single-official-fact-2026-11-v1';
export const METHOD='deterministic_single_official_fact_v1';
const json=value=>JSON.stringify(value);
const one=rows=>{assert.equal(rows.length,1);return rows[0];};

export async function captureReleaseState(db) {
 const config=one((await db.query("select to_jsonb(c) value from public.news_ai_config c where id='production'")).rows).value;
 const notice=one((await db.query("select to_jsonb(c) value from public.news_notice_release_config c where id='production'")).rows).value;
 const publicRows=(await db.query('select to_jsonb(a) value from public.public_news_articles a order by id')).rows.map(r=>r.value);
 const vehicles=(await db.query("select to_jsonb(c) value from public.canonical_models c order by id")).rows.map(r=>r.value);
 const variants=(await db.query("select to_jsonb(c) value from public.canonical_model_variants c order by id")).rows.map(r=>r.value);
 const ledger=(await db.query('select id,charged_micro_usd,reserved_micro_usd,settled_at,budget_closed_at,provider_status from public.news_ai_requests order by id')).rows;
 return JSON.parse(json({config,notice,publicRows,vehicles,variants,ledger}));
}

export async function stageOneNotice(db,manifest) {
 assert.equal(manifest.recipe,POLICY);assert.equal(manifest.review_method,METHOD);assert.equal(manifest.review.passed,true);
 const t=manifest.tables;
 assert.deepEqual(Object.keys(t).sort(),['news_sources','news_story_clusters','news_items','news_articles','news_article_sources','news_quality_checks'].sort());
 for(const k of Object.keys(t))assert.equal(t[k].length,k==='news_quality_checks'?3:1);
 const s=one(t.news_sources),c=one(t.news_story_clusters),i=one(t.news_items),a=one(t.news_articles),l=one(t.news_article_sources);
 assert.equal(s.id,'kia-sweden-prices');assert.equal(i.source_id,s.id);assert.equal(i.url,'https://www.kia.com/se/kopa/prislista/');
 assert.equal(a.id,manifest.article_id);assert.equal(a.status,'draft');assert.equal(a.published_at,null);
 assert.equal(a.payload.editorial_recipe,POLICY);assert.equal(a.payload.notice_kind,'price');
 assert.equal(c.id,a.cluster_id);assert.equal(l.article_id,a.id);assert.equal(l.item_id,i.id);
 assert.equal(i.payload.content_hash,a.payload.notice_facts.source_hash);
 const existing=(await db.query('select payload=$2::jsonb same from public.news_sources where id=$1',[s.id,json(s.payload)])).rows;
 if(existing.length)assert.equal(existing[0].same,true,'Existing source must not be overwritten');
 else await db.query('insert into public.news_sources(id,payload) values($1,$2)',[s.id,json(s.payload)]);
 await db.query('insert into public.news_story_clusters(id,event_key,payload) values($1,$2,$3)',[c.id,c.event_key,json(c.payload)]);
 await db.query('insert into public.news_items(id,source_id,url,cluster_id,status,payload) values($1,$2,$3,$4,$5,$6)',
  [i.id,i.source_id,i.url,i.cluster_id,i.status,json(i.payload)]);
 const row=one((await db.query('insert into public.news_articles(id,cluster_id,slug,status,payload) values($1,$2,$3,$4,$5) returning *',
  [a.id,a.cluster_id,a.slug,'draft',json(a.payload)])).rows);
 await db.query('insert into public.news_article_sources(id,article_id,item_id,payload) values($1,$2,$3,$4)',[l.id,l.article_id,l.item_id,json(l.payload)]);
 for(const q of t.news_quality_checks){
  assert.equal(q.article_id,a.id);assert.equal(q.passed,true);assert.equal(q.payload.review_method,METHOD);
  await db.query('insert into public.news_quality_checks(id,article_id,kind,artifact_hash,passed,payload) values($1,$2,$3,$4,$5,$6)',
   [q.id,a.id,q.kind,row.artifact_hash,true,json(q.payload)]);
 }
 const snapshot=one((await db.query('select public.news_notice_source_snapshot($1) value',[a.id])).rows).value;
 assert.deepEqual(snapshot.item.payload,i.payload);assert.deepEqual(snapshot.source.payload,s.payload);
 assert.deepEqual(row.payload,a.payload);
 return {article:row,snapshot};
}

export async function releaseExactlyOne(db,manifest,{migration,expected,approvedDay,commit=false,allowFixture=false}={}) {
 assert.equal(manifest.fixture,allowFixture,'Synthetic notices are forbidden in production');
 assert(/^\d{4}-\d{2}-\d{2}$/.test(approvedDay));
 await db.query('begin isolation level serializable read write');
 try{
  await db.query("set local lock_timeout='10s'");await db.query("set local statement_timeout='90s'");
  await db.query('select pg_advisory_xact_lock(72716491)');
  await db.query("select id from public.news_ai_config where id='production' for update");
  await db.query("select id from public.news_notice_release_config where id='production' for update");
  const day=one((await db.query("select to_char(clock_timestamp() at time zone 'UTC','YYYY-MM-DD') as utc_day")).rows).utc_day;
  assert.equal(day,approvedDay,'Owner release day changed');
  const before=await captureReleaseState(db);
  assert.deepEqual(before,expected,'Release baseline changed');
  assert.equal(before.config.publication_enabled,true,'Existing master publication switch must already be on');
  assert.equal(before.notice.enabled,false,'This is a single owner release, not ongoing notice activation');
  assert.equal(before.notice.policy,'news-notice-2026-10-v1');
  assert.equal(before.config.daily_article_limit,1);
  if(typeof db.exec==='function')await db.exec(migration);else await db.query(migration);
  const installed=await captureReleaseState(db);assert.deepEqual(installed,before,'Migration changed data or settings');
  const staged=await stageOneNotice(db,manifest);
  await db.query("update public.news_notice_release_config set enabled=true,policy=$1,review_method=$2 where id='production'",[POLICY,METHOD]);
  const result=one((await db.query('select public.publish_news_notice($1,$2,$3,$4) value',
   [staged.article.id,staged.article.artifact_hash,json(staged.article.payload),json(staged.snapshot)])).rows).value;
  assert.deepEqual(result,{published:true,already_published:false});
  await db.query("update public.news_notice_release_config set enabled=$1,policy=$2,review_method=$3 where id='production'",
   [before.notice.enabled,before.notice.policy,before.notice.review_method]);
  const after=await captureReleaseState(db);
  for(const key of ['config','notice','vehicles','variants','ledger'])assert.deepEqual(after[key],before[key],key+' changed');
  assert.equal(after.publicRows.length,before.publicRows.length+1);
  assert.deepEqual(after.publicRows.filter(r=>r.id!==staged.article.id),before.publicRows);
  const pub=one(after.publicRows.filter(r=>r.id===staged.article.id));
  for(const privateKey of ['notice_facts','fact_ids','item_id','source_hash','source_capture'])
   assert(!json(pub.payload).includes('"'+privateKey+'"'),'Private evidence leaked');
  const today=one((await db.query("select count(*)::int count from public.news_articles where status='published' and published_at>=date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'")).rows).count;
  assert.equal(today,1,'Exactly one article may be published today');
  const receipt=one((await db.query('select article_id,artifact_hash,source_hash,policy,review_method from public.news_notice_publications where article_id=$1',[pub.id])).rows);
  assert.equal(receipt.policy,POLICY);assert.equal(receipt.review_method,METHOD);
  await db.query(commit?'commit':'rollback');
  return {committed:commit,article:pub,receipt,public_count:after.publicRows.length,daily_count:today,config_restored:true,vehicle_data_unchanged:true,paid_calls:0};
 }catch(error){await db.query('rollback').catch(()=>{});throw error;}
}
