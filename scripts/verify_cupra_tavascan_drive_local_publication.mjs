import assert from 'node:assert/strict';
import { mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { PGlite } from '@electric-sql/pglite';
import { readDriveCapture, readDriveImage, MODEL, policy } from './cupra_tavascan_drive_publication.mjs';
import { readTavascanDriveScope } from './prepare_cupra_tavascan_drive_readback.mjs';
import { applyNewModelPlan, buildNewModelPlan, publicationHash, publicationSnapshot,
  validateNewModelIntake } from './new_model_publication.mjs';
import { anonymousCatalogRows, catalogWithComparableTimes, readCommittedPublicBaseline, readPublishedFixture,
  seedCatalogFixture } from './isolated_catalog_review.mjs';
import { catalogHash, compareCatalogs } from './sync_public_catalog.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';

async function rehearse(db,fixture,plan,baseline,now) {
  await seedCatalogFixture(db,fixture,[plan]);
  const initial = await anonymousCatalogRows(db);
  assert(compareCatalogs(catalogWithComparableTimes(baseline),catalogWithComparableTimes(initial)).ok,
    'Committed export, live export and copied anonymous view differ');
  const before = await publicationSnapshot(db);
  const {intake,image} = plan;
  assert.deepEqual(buildNewModelPlan(before,intake,image,now),plan);
  const digest = publicationHash(plan);
  for(const change of [
    d=>{d.drafts[0].facts.wltp_range_km=552;},
    d=>{d.drafts[0].facts.wltp_consumption_kwh_100km=15.3;},
    d=>{d.drafts[0].identity_evidence.measurements[1].model_year=2027;},
    d=>{d.drafts[0].field_evidence.wltp_range_km.corroboration.source_hash='0'.repeat(64);},
    d=>{d.drafts[0].price_evidence.price_type='dealer_offer';},
    d=>{d.drafts[0].price_evidence.dealer_offer.price_type='list_price';},
    d=>{d.sources.find(s=>s.source_authority==='authorized_dealer').authorization_evidence_url=policy.primaryUrl;},
    d=>{d.market.row.model_raw='BORN';},
  ]) {
    const invalid = structuredClone(intake);change(invalid);
    assert.throws(()=>buildNewModelPlan(before,invalid,image,now));
  }
  assert.throws(()=>buildNewModelPlan(before,intake,{...image,model_key:'cupra|born'},now));
  assert.throws(()=>buildNewModelPlan(before,intake,image,new Date(+now+900001)),/Fresh source capture/);
  await assert.rejects(applyNewModelPlan({query(){assert.fail('Remote write requested');}},plan,digest,now),/local PGlite/);
  await assert.rejects(applyNewModelPlan(db,plan,'0'.repeat(64),now),/packet changed/);
  await db.exec(`CREATE FUNCTION local_tavascan_failure() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Local Tavascan late rollback'; END $$;
    CREATE TRIGGER local_tavascan_failure BEFORE UPDATE ON public.market_models
    FOR EACH ROW EXECUTE FUNCTION local_tavascan_failure();`);
  await assert.rejects(applyNewModelPlan(db,plan,digest,now),/Local Tavascan late rollback/);
  assert.deepEqual(await publicationSnapshot(db),before);
  assert.deepEqual(await anonymousCatalogRows(db),initial);
  await db.exec('DROP TRIGGER local_tavascan_failure ON public.market_models');
  const applied = await applyNewModelPlan(db,plan,digest,now);
  assert.equal(applied.variants_inserted,1);
  assert.equal(applied.anonymous_before_commit,true);
  const after = await publicationSnapshot(db);
  const visible = await anonymousCatalogRows(db);
  assert.equal(visible.length,initial.length+1);
  const added = visible.filter(r=>r.id===plan.targets[0].id);
  policy.verifyPublic(added,plan);
  assert.deepEqual(visible.filter(r=>r.id!==plan.targets[0].id),initial);
  assert.deepEqual(after.market_model_monthly_stats.filter(s=>s.month!==intake.market.row.last_seen_month),
    before.market_model_monthly_stats.filter(s=>s.month!==intake.market.row.last_seen_month));
  assert.equal((await applyNewModelPlan(db,plan,digest,now)).already_applied,true);
  assert.deepEqual(await publicationSnapshot(db),after);
  return {added:added[0],rows:catalogWithComparableTimes(visible),plan_hash:digest};
}

async function main() {
  const {values}=parseArgs({options:{review:{type:'string'},connector:{type:'string'}}});
  assert(values.review,'Supply a fresh private MY26 Drive receipt');
  const {intake,capture_sha256}=await readDriveCapture(values.review);
  const photo=readDriveImage();
  const now=new Date();
  assert.equal(validateNewModelIntake(intake,now).localOnly,true);
  const releaseRoot=await realpath(new URL('../data/local/release-data',import.meta.url));
  const connector=values.connector?resolve(values.connector):
    join(await realpath(new URL('../data/local/db-tools',import.meta.url)),'source-client.mjs');
  assert.equal(basename(connector),'source-client.mjs');
  assert.equal(await realpath(connector),connector);
  const sourceRoot=resolve(dirname(connector),'../../..');
  assert.equal(join(sourceRoot,'data','local','db-tools',basename(connector)),connector);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(releaseRoot));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(connector));
  const {openSourceSnapshot,closeSourceSnapshot}=await import(pathToFileURL(connector).href);
  const candidateRoot=process.cwd();
  let client;
  try {
    process.chdir(sourceRoot);
    client=await openSourceSnapshot();
  } finally { process.chdir(candidateRoot); }
  let plan,fixture;
  try {
    assert.equal((await client.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
    assert.equal((await client.query('SHOW transaction_isolation')).rows[0].transaction_isolation,'repeatable read');
    useCalendarDateText(client);
    plan=await readTavascanDriveScope(client,intake,photo,now);
    fixture=await readPublishedFixture(client);
  } finally {await closeSourceSnapshot(client);}
  const output=await mkdtemp(join(releaseRoot,'cupra-tavascan-readback-'));
  const {base,proof}=await readCommittedPublicBaseline(releaseRoot,output,{imageTools:true});
  assert(!base.some(r=>String(r.model).toLowerCase()===MODEL.normalized_model));
  const db=new PGlite();
  let result;
  try {result=await rehearse(db,fixture,plan,base,now);} finally {await db.close();}
  const report={status:'tavascan_drive_local_only_passed',...proof,candidate_count:result.rows.length,
    candidate_sha256:catalogHash(result.rows),plan_hash:result.plan_hash,existing_rows_preserved:true,
    anonymous_before_commit:true,rollback_replay_and_write_guard:true,photo_sha256:photo.content_sha256,
    production_writes:0,publication_approved:false};
  const save=(name,data)=>writeFile(join(output,name),JSON.stringify(data,null,2)+'\n',{flag:'wx'});
  await save('candidate-catalog.json',{generated_at:now.toISOString(),source:'isolated_catalog_rehearsal',schema_version:1,
    missing_view_columns:[],catalog_sha256:report.candidate_sha256,records:result.rows});
  await save('report.json',{...report,added_variant:result.added,image:photo});
  await save('reviewed-plan.json',{...report,capture_sha256,plan,public_projection_sha256:catalogHash(catalogWithComparableTimes(base))});
  console.log(JSON.stringify({...report,output}));
}

if(process.argv[1]&&pathToFileURL(process.argv[1]).href===import.meta.url) await main().catch(error=>{
  const location=error.stack?.split('\n').find(line=>/^\s+at .*\.mjs:\d+:\d+/.test(line))?.trim();
  console.error(JSON.stringify({status:'held',error:error.name,code:error.code??null,reason:error.message.split('\n')[0],location,production_writes:0}));
  process.exitCode=1;
});
