import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { PGlite } from '@electric-sql/pglite';
import { anonymousCatalogRows, catalogWithComparableTimes, readCommittedPublicBaseline,
  readPublishedFixture, seedCatalogFixture } from './isolated_catalog_review.mjs';
import { applyNewModelPlan, buildNewModelPlan, publicationHash, publicationSnapshot } from './new_model_publication.mjs';
import { prepareXpG6Readback } from './prepare_xpeng_g6_readback.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { catalogHash, compareCatalogs, normalizeCatalog, variantKey } from './sync_public_catalog.mjs';
import { readReviewedImage, readXpG6Capture } from './xpeng_g6_publication.mjs';
import { MODEL, policy, readG9Capture, readG9Image } from './xpeng_g9_publication.mjs';
import { isG6, requirePublishedG6, validateG9PostG6Delta } from './xpeng_g9_release_review.mjs';

export async function readG9Plan(client,intake,image,now) {
  assert.equal((await client.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
  assert.equal((await client.query('SHOW transaction_isolation')).rows[0].transaction_isolation,'repeatable read');
  const rows = async (sql,args)=>JSON.parse(JSON.stringify((await client.query(sql,args)).rows));
  const key = [MODEL.normalized_brand,MODEL.normalized_model];
  const models = await rows('SELECT * FROM public.canonical_models WHERE normalized_brand=$1 AND normalized_model=$2',key);
  assert.equal(models.length,1);
  const [model] = models;
  assert.equal(model.validation_status,'draft');
  const aliases = await rows('SELECT * FROM public.model_aliases WHERE normalized_brand=$1 AND normalized_model=$2 ORDER BY id',key);
  const market = await rows("SELECT * FROM public.market_models WHERE normalized_brand=$1 AND normalized_model=$2 AND fuel_type_raw='EL'",key);
  assert.equal(market.length,1);
  const monthly = await rows('SELECT * FROM public.market_model_monthly_stats WHERE market_model_id=$1 ORDER BY id',[market[0].id]);
  const matchedMonth = monthly.filter(r=>r.month===intake.market.row.last_seen_month && r.county===null && r.municipality===null);
  assert(matchedMonth.length<=1,'Ambiguous G9 registration month');
  if(matchedMonth.length) assert.equal(matchedMonth[0].registrations,intake.market.row.registrations_last_month);
  const sources = await rows('SELECT * FROM public.manufacturer_sources WHERE url=ANY($1::text[]) ORDER BY id',
    [intake.sources.map(row=>row.final_url)]);
  for(const row of sources) {
    assert.deepEqual([row.brand,row.model],[model.brand,model.model],'Exact G9 source is used by another model');
    assert([null,model.id].includes(row.canonical_model_id));
  }
  const variants = await rows('SELECT * FROM public.canonical_model_variants WHERE canonical_model_id=$1 ORDER BY id',[model.id]);
  const plan = buildNewModelPlan({canonical_models:models,model_aliases:aliases,market_models:market,
    market_model_monthly_stats:monthly,manufacturer_sources:sources,canonical_model_variants:variants},intake,image,now);
  assert.equal((await rows('SELECT id FROM public.canonical_model_variants WHERE id=ANY($1::uuid[]) OR source_id=ANY($2::uuid[])',
    [plan.targets.map(row=>row.id),sources.map(row=>row.id)])).length,0,'Target ID or source is used by an existing variant');
  assert.equal((await rows('SELECT id FROM public.extracted_variant_drafts WHERE source_url=$1 AND variant_name=ANY($2::text[])',
    [policy.primaryUrl,intake.drafts.map(d=>d.variant_name)])).length,0,'Existing G9 drafts require review');
  return plan;
}

async function readOnly(root,g6,g9,now) {
  const connector = join(root,'data','local','db-tools','source-client.mjs');
  assert.equal(await realpath(connector),connector);
  const {openSourceSnapshot,closeSourceSnapshot} = await import(pathToFileURL(connector).href);
  const client = await openSourceSnapshot();
  try {
    assert.equal((await client.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
    assert.equal((await client.query('SHOW transaction_isolation')).rows[0].transaction_isolation,'repeatable read');
    useCalendarDateText(client);
    let first;
    if(g6) ({plan:first}=await prepareXpG6Readback(client,g6.intake,readReviewedImage(),now));
    else {
      const visible = (await client.query("SELECT to_jsonb(v) AS row FROM public.public_ev_variants v WHERE brand=$1 AND model=$2",
        ['Xpeng','G6'])).rows.map(row=>row.row);
      requirePublishedG6(visible);
    }
    const second = await readG9Plan(client,g9.intake,readG9Image(),now);
    if(first) {
      const existingUrls = new Set(first.intake.sources.map(row=>row.final_url));
      assert(!second.intake.sources.some(row=>existingUrls.has(row.final_url)),'G9 reuses a G6-owned exact source URL');
    }
    return {first,second,fixture:await readPublishedFixture(client)};
  } finally {await closeSourceSnapshot(client);}
}

async function rehearse({first,second,fixture},baseline,now) {
  const db = new PGlite();
  const plans = [first,second].filter(Boolean);
  const hashes = plans.map(publicationHash);
  const apply = plan=>applyNewModelPlan(db,plan,hashes[plans.indexOf(plan)],now);
  try {
    await seedCatalogFixture(db,fixture,plans);
    const initial = await anonymousCatalogRows(db);
    assert(compareCatalogs(catalogWithComparableTimes(baseline),catalogWithComparableTimes(initial)).ok,
      'Committed export, live export and isolated public rows differ');
    if(first) assert.equal((await apply(first)).variants_inserted,3);
    const g6Only = await anonymousCatalogRows(db);
    requirePublishedG6(g6Only);
    const before = await publicationSnapshot(db);
    for(const change of [
      intake=>{intake.model.model='G9L';},
      intake=>{intake.drafts[0].manufacturer_identity='E38bV$EEBB';},
      intake=>{intake.drafts[1].facts.battery_kwh=94.6;},
      intake=>{intake.drafts[0].price_evidence.price_type='dealer_offer';},
      intake=>{intake.drafts[0].identity_evidence.german.source_hash='0'.repeat(64);},
    ]) {
      const invalid = structuredClone(second.intake);
      change(invalid);
      assert.throws(()=>buildNewModelPlan(before,invalid,second.image,now));
    }
    assert.deepEqual(buildNewModelPlan(before,second.intake,second.image,now),second);
    assert.throws(()=>buildNewModelPlan(before,second.intake,readReviewedImage(),now));
    assert.throws(()=>buildNewModelPlan(before,second.intake,second.image,new Date(+now+900001)),/Fresh source capture/);
    await assert.rejects(applyNewModelPlan({query(){assert.fail('Remote query attempted');}},second,hashes.at(-1),now),/local PGlite/);
    await db.exec(`CREATE FUNCTION local_g9_failure() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (SELECT COUNT(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id)<>2 THEN
          RAISE EXCEPTION 'Both G9 variants must exist before the rollback probe';
        END IF;
        RAISE EXCEPTION 'Local G9 late rollback probe';
      END $$;
      CREATE TRIGGER local_g9_failure BEFORE UPDATE ON public.market_models FOR EACH ROW EXECUTE FUNCTION local_g9_failure();`);
    await assert.rejects(apply(second),/Local G9 late rollback probe/);
    assert.deepEqual(await publicationSnapshot(db),before,'The G9 rollback changed a saved row');
    assert.deepEqual(await anonymousCatalogRows(db),g6Only,'The G9 rollback changed the anonymous catalog');
    await db.exec('DROP TRIGGER local_g9_failure ON public.market_models');
    const result = await apply(second);
    assert.deepEqual([result.variants_inserted,result.anonymous_before_commit],[2,true]);
    const rows = await anonymousCatalogRows(db);
    const g9 = new Set(second.targets.map(row=>row.id));
    assert.deepEqual(rows.filter(row=>!g9.has(row.id)),g6Only,'The G9 insert changed existing variants or G6');
    validateG9PostG6Delta(g6Only,rows,second);
    const after = await publicationSnapshot(db);
    const oldMonths = list=>list.filter(row=>row.market_model_id!==second.expected_market.id
      || row.month!==second.intake.market.row.last_seen_month);
    assert.deepEqual(oldMonths(after.market_model_monthly_stats),oldMonths(before.market_model_monthly_stats));
    for(const plan of plans) assert.equal((await apply(plan)).already_applied,true);
    assert.deepEqual(await publicationSnapshot(db),after,'Exact G6/G9 replays changed saved data');
    return {rows:catalogWithComparableTimes(rows.filter(row=>(first&&isG6(row))||g9.has(row.id))),
      hashes,counts:[initial.length,g6Only.length,rows.length]};
  } finally {await db.close();}
}

async function main() {
  const {values} = parseArgs({options:{g6:{type:'string'},g9:{type:'string'},'after-live-g6':{type:'boolean'}}});
  assert(values.g9&&(Boolean(values.g6)!==Boolean(values['after-live-g6'])),
    'Supply a fresh G9 review and choose either --g6 <private-review> or --after-live-g6');
  const root = await realpath('.');
  const evidence = await realpath('data/local/release-data');
  assert.equal(evidence,join(root,'data','local','release-data'));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(evidence));
  const g6 = values.g6?readXpG6Capture(values.g6):null, g9 = readG9Capture(values.g9);
  const now = new Date();
  const scope = await readOnly(root,g6,g9,now);
  const output = await mkdtemp(join(evidence,'xpeng-g9-readback-'));
  const {base,proof} = await readCommittedPublicBaseline(evidence,output,{imageTools:true});
  if(!g6) {
    requirePublishedG6(base);
    assert.equal(execFileSync('git',['ls-remote','origin','refs/heads/main'],{encoding:'utf8',timeout:20000}).trim(),
      proof.commit+'\trefs/heads/main','Local origin/main is not the current release revision');
  }
  const result = await rehearse(scope,base,now);
  const candidate = normalizeCatalog([...base,...result.rows]);
  const prior = new Set(base.map(variantKey));
  assert.deepEqual(candidate.filter(row=>prior.has(variantKey(row))),base);
  assert.equal(candidate.length,base.length+(g6?5:2));
  const report = {status:'xpeng_g9_local_after_g6_passed',...proof,variants:2,g6_variants:3,checked_counts:result.counts,
    g6_evidence:g6?'local_fixture':'live_catalog_and_view',
    candidate_sha256:catalogHash(candidate),plan_hashes:result.hashes,review_hashes:[g6?.reviewHash,g9.reviewHash].filter(Boolean),
    exact_replay_noop:true,late_rollback:true,anonymous_before_commit:true,market_history_preserved:true,
    production_writes:0,paid_calls:0,publication_approved:false};
  const save = (name,data)=>writeFile(join(output,name),JSON.stringify(data,null,2)+'\n',{flag:'wx'});
  await save('candidate-catalog.json',{status:'local_only',publication_approved:false,records:candidate});
  await save('g9-plan.json',scope.second);
  await save('report.json',report);
  console.log(JSON.stringify({...report,output}));
}

if(process.argv[1]&&pathToFileURL(process.argv[1]).href===import.meta.url) main().catch(error=>{
  const location = error.stack?.split('\n').find(line=>/^\s+at .*\.mjs:\d+:\d+/.test(line))?.trim();
  console.error(JSON.stringify({status:'held',reason:error.message.split('\n')[0],
    code:error.cause?.code??error.code??null,location,production_writes:0}));
  process.exitCode=1;
});
