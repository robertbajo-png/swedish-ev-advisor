import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import { PGlite } from '@electric-sql/pglite';
import { readRenault4Scope } from './prepare_renault_4_evolution_readback.mjs';
import { readPairCapture, renault4LocatorRow } from './renault_4_pair_publication.mjs';
import { readEvolutionImage } from './renault_4_evolution_publication.mjs';
import { assertRenault4PairPublishedRows, proveRenault4PairRelease, renault4PairApproval,
  renault4PairReview } from './renault_4_pair_release_scope.mjs';
import { applyNewModelPlan, applyRenault4PairRelease, publicationHash, publicationSnapshot } from './new_model_publication.mjs';
import { anonymousCatalogRows, readPublishedFixture, seedCatalogFixture } from './isolated_catalog_review.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { catalogHash } from './sync_public_catalog.mjs';

const json = async path=>JSON.parse(await readFile(path,'utf8'));
const digest = body=>createHash('sha256').update(body).digest('hex');
const unlinked = async path=>assert.equal(await realpath(path),path,'Require an unlinked review path');

export async function verifyRenault4PairMedia(root, image, report) {
  assert.equal((await json(join(root,'src/model-images.json')))[image.model_key],image.asset_url);
  const rights=(await json(join(root,'src/image-rights.json'))).assets.filter(row=>row.model_key===image.model_key);
  assert.deepEqual(rights,[{...image,changes:'Hela bildutsnittet bevaras. Endast storlek och format har anpassats.'}],
    'Renault 4 model rights record changed');
  const variants=(await json(join(root,'src/image-variants.json')))[image.asset_url];
  assert.equal(variants.source_sha256,image.content_sha256);
  assert.deepEqual(variants.variants.map(row=>row.width),[480,800,1280]);
  const media=[{url:image.asset_url,sha256:image.content_sha256},...variants.variants.map(({url,sha256})=>({url,sha256}))];
  assert.deepEqual(media,report.media,'Registered Renault 4 image bundle differs from browser QA');
  for(const {url,sha256} of media){
    const path=join(root,'public',url.slice(1));
    await unlinked(path);
    assert.equal(digest(await readFile(path)),sha256);
  }
}

export async function verifyTransaction(fixture, reviewed, fresh, ui, approval, now) {
  const db = new PGlite();
  const {plan} = fresh;
  const locator=renault4LocatorRow(plan.intake.sources.find(s=>s.shared));
  try {
    await seedCatalogFixture(db,fixture,[plan]);
    // The deployed model view has no photo columns. The variant view still requires both.
    await db.exec(`DROP VIEW public.public_ev_models;
      CREATE VIEW public.public_ev_models WITH (security_barrier=true) AS
      SELECT id,brand,model,body_type,market_seen,available_confirmed,discontinued_candidate,coming_or_low_volume,published_at
      FROM public.canonical_models cm WHERE validation_status <> 'rejected'
        AND EXISTS (SELECT 1 FROM public.canonical_model_variants cv
          WHERE cv.canonical_model_id=cm.id AND cv.validation_status IN ('published','published_reviewed'));
      GRANT SELECT ON public.public_ev_models TO anon;`);
    const initial=await anonymousCatalogRows(db);
    const before=await publicationSnapshot(db);
    const apply=hash=>applyRenault4PairRelease(db,fresh,reviewed,ui,hash,now);
    await assert.rejects(apply('0'.repeat(64)),/exact approved Renault 4 pair hash/);
    await assert.rejects(applyNewModelPlan(db,plan,fresh.plan_hash,now),/AssertionError|Shared source/);
    assert.deepEqual(await publicationSnapshot(db),before);
    const old=before.canonical_model_variants[0];
    await db.query('UPDATE public.canonical_model_variants SET source_quote=$1 WHERE id=$2',[old.source_quote+' local drift fixture',old.id]);
    const drift=await publicationSnapshot(db);
    await assert.rejects(apply(approval),/Anonymous catalog changed before scoped writes/);
    assert.deepEqual(await publicationSnapshot(db),drift);
    await db.query('UPDATE public.canonical_model_variants SET source_quote=$1 WHERE id=$2',[old.source_quote,old.id]);
    await db.exec(`CREATE FUNCTION fail_r4_scoped_transaction() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (SELECT COUNT(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id) <> 2
          OR NOT EXISTS(SELECT 1 FROM public.manufacturer_sources WHERE url='https://www.renault.se/om-oss/aterforsaljare'
            AND brand='Renault' AND canonical_model_id IS NULL) THEN
          RAISE EXCEPTION 'Both variants and the locator must exist before the rollback probe';
        END IF;
        RAISE EXCEPTION 'Injected scoped Renault 4 late failure';
      END $$;
      CREATE TRIGGER r4_scoped_failure BEFORE UPDATE ON public.market_models
      FOR EACH ROW EXECUTE FUNCTION fail_r4_scoped_transaction();`);
    await assert.rejects(apply(approval),/Injected scoped Renault 4 late failure/);
    assert.deepEqual(await publicationSnapshot(db),before,'Partial write after aborted scoped Renault 4 transaction');
    assert.deepEqual(await anonymousCatalogRows(db),initial);
    await db.exec('DROP TRIGGER r4_scoped_failure ON public.market_models');
    const receipt=await apply(approval);
    assert.equal(receipt.committed,true);
    assert.equal(receipt.anonymous_before_commit,true);
    assert.equal(receipt.variants_inserted,2);
    const targetIds=new Set(plan.targets.map(t=>t.id));
    const rows=await anonymousCatalogRows(db);
    assertRenault4PairPublishedRows(rows.filter(row=>targetIds.has(row.id)),plan);
    assert.deepEqual(rows.filter(row=>!targetIds.has(row.id)),initial);
    const after=await publicationSnapshot(db);
    const matching=after.manufacturer_sources.filter(row=>row.url===locator.url);
    assert.equal(matching.length,1);
    for(const [key,value] of Object.entries(locator)) assert.equal(matching[0][key],value);
    await assert.rejects(apply(approval),/requires an unpublished canonical model/);
    assert.deepEqual(await publicationSnapshot(db),after);
    return {preserved:initial.length,private_rows:rows.length,scoped_late_rollback:true,
      unseen_locator_created:!before.manufacturer_sources.some(row=>row.url===locator.url),
      invalid_approval_and_catalog_drift_rejected:true,prior_release_rejected:true,legacy_model_projection:true};
  } finally { await db.close(); }
}

async function main() {
  const {values}=parseArgs({options:{readback:{type:'string'},capture:{type:'string'},ui:{type:'string'},fresh:{type:'string'}}});
  const root=await realpath('.');
  const evidence=join(root,'data/local/release-data');
  await unlinked(evidence);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(root));
  const location=async (input,pattern,parent)=>{
    const path=resolve(input);
    await unlinked(path);
    assert.equal(dirname(path),parent);
    assert.match(basename(path),pattern);
    return path;
  };
  const readbackFolder=await location(values.readback,/^renault-4-readback-[a-z0-9]+$/i,evidence);
  const readback=await json(join(readbackFolder,'report.json'));
  const uiPath=resolve(values.ui);
  const pairRoot=await location(dirname(dirname(uiPath)),/^renault-4-pair-ui-[a-z0-9]+$/i,evidence);
  await location(dirname(uiPath),/^browser-[a-z0-9]+$/i,pairRoot);
  await location(uiPath,/^ui-report\.json$/,dirname(uiPath));
  const ui=await json(uiPath);
  assert.match(ui.commit,/^[a-f0-9]{40}$/);
  assert.equal(execFileSync('git',['ls-remote','origin','refs/heads/main'],{encoding:'utf8',timeout:20000}).trim(),
    ui.commit+'\trefs/heads/main','Remote main changed');
  const {records:baseline}=JSON.parse(execFileSync('git',['show',ui.commit+':public/data/public_ev_variants.json'],
    {encoding:'utf8',timeout:15000,maxBuffer:5000000}));
  const response=await fetch('https://elbilsagenten.se/data/public_ev_variants.json',{redirect:'error',signal:AbortSignal.timeout(15000)});
  assert(response.ok);
  assert.equal(catalogHash((await response.json()).records),catalogHash(baseline),'Deployed catalog differs from main');
  const image=readEvolutionImage();
  await verifyRenault4PairMedia(join(pairRoot,'source'),image,ui);
  const original=readPairCapture(values.capture);
  const current=values.fresh?readPairCapture(values.fresh):null;
  if(!current) {
    // Only the isolated exercise uses a clock-shifted copy of the old evidence.
    const intake=structuredClone(original.intake);
    const shift=901000;
    for(const source of [...intake.sources,intake.market.source])
      source.fetched_at=new Date(Date.parse(source.fetched_at)+shift).toISOString();
    original.simulation={intake,now:new Date(original.now.getTime()+shift)};
  }
  const candidate=current??original.simulation;
  const now=current?new Date():candidate.now;
  const path=join(root,'data/local/db-tools/source-client.mjs');
  await unlinked(path);
  const connector=await import(pathToFileURL(path).href);
  assert.equal(connector.PROJECT_REF,'eutcryxbitudllcnpnex');
  const client=await connector.openSourceSnapshot();
  let reviewed,fresh,fixture;
  try {
    useCalendarDateText(client);
    const historic=await readRenault4Scope(client,original.intake,image,original.now);
    reviewed=renault4PairReview(historic.plan,readback,baseline);
    const {plan,found}=await readRenault4Scope(client,candidate.intake,image,now);
    assert.equal(found,readback.production_locator_present,'Renault shared locator presence changed');
    fresh={plan,plan_hash:publicationHash(plan)};
    fixture=await readPublishedFixture(client);
  } finally {await connector.closeSourceSnapshot(client);}
  const approval=renault4PairApproval(reviewed,ui);
  proveRenault4PairRelease(reviewed,fresh,ui,approval,now);
  const transaction=await verifyTransaction(fixture,reviewed,fresh,ui,approval,now);
  const output=await mkdtemp(join(evidence,'renault-4-pair-release-review-'));
  const report={status:current?'fresh_readonly_and_isolated_transaction_passed':'historical_fixture_only',
    reviewed,reviewed_scope_sha256:approval,transaction,ui_path:uiPath,
    publication_approved:false,production_writes:0,paid_calls:0};
  await writeFile(join(output,'release-review.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:report.status,output,transaction,production_writes:0}));
}

if(process.argv[1]&&pathToFileURL(process.argv[1]).href===import.meta.url) main().catch(error=>{
  console.error(JSON.stringify({status:'held',error:error.name,code:error.code??null,
    ...(['ERR_ASSERTION','ENOENT'].includes(error.code)?{reason:error.message.split('\n')[0]}:{}),production_writes:0}));
  process.exitCode=1;
});
