import assert from 'node:assert/strict';
import { readFile, realpath } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { PGlite } from '@electric-sql/pglite';
import { anonymousCatalogRows, readPublishedFixture, seedCatalogFixture } from './isolated_catalog_review.mjs';
import { applyXpG9Release, publicationHash, publicationSnapshot } from './new_model_publication.mjs';
import { runXpG9Release, verifyRegisteredG9Media } from './publish_approved_xpeng_g9.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { catalogHash, variantKey } from './sync_public_catalog.mjs';
import { readG9Plan } from './verify_xpeng_g9_local.mjs';
import { readG9Capture, readG9Image } from './xpeng_g9_publication.mjs';
import { g9ApprovalHash, validateG9PostG6Delta } from './xpeng_g9_release_review.mjs';

export async function rehearseScopedG9({fixture,fresh,reviewed,baseline,now}) {
  const db = new PGlite();
  const {plan} = fresh;
  const approval = g9ApprovalHash(reviewed);
  try {
    await seedCatalogFixture(db,fixture,[plan]);
    // Match the older public model view still deployed in production.
    await db.exec(`DROP VIEW public.public_ev_models;
      CREATE VIEW public.public_ev_models WITH (security_barrier=true) AS
      SELECT id,brand,model,body_type,market_seen,available_confirmed,discontinued_candidate,coming_or_low_volume,published_at
      FROM public.canonical_models cm WHERE validation_status <> 'rejected'
        AND EXISTS (SELECT 1 FROM public.canonical_model_variants cv
          WHERE cv.canonical_model_id=cm.id AND cv.validation_status IN ('published','published_reviewed'));
      GRANT SELECT ON public.public_ev_models TO anon;`);
    const before = await publicationSnapshot(db);
    const original = await anonymousCatalogRows(db);
    const apply = hash => applyXpG9Release(db,fresh,reviewed,hash,now);
    await assert.rejects(apply('0'.repeat(64)),/exact approved G9 release hash/);
    assert.deepEqual(await publicationSnapshot(db),before);
    const old = before.canonical_model_variants[0];
    await db.query('UPDATE public.canonical_model_variants SET source_quote=$1 WHERE id=$2',
      [old.source_quote+' local drift fixture',old.id]);
    const drift = await publicationSnapshot(db);
    await assert.rejects(apply(approval),/Anonymous catalog changed before scoped writes/);
    assert.deepEqual(await publicationSnapshot(db),drift);
    await db.query('UPDATE public.canonical_model_variants SET source_quote=$1 WHERE id=$2',[old.source_quote,old.id]);
    await db.exec(`CREATE FUNCTION local_g9_scoped_failure() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (SELECT COUNT(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id)<>2 THEN
          RAISE EXCEPTION 'Both G9 versions must exist before the scoped rollback';
        END IF;
        RAISE EXCEPTION 'Isolated G9 scoped late rollback';
      END $$;
      CREATE TRIGGER local_g9_scoped_failure BEFORE UPDATE ON public.market_models
        FOR EACH ROW EXECUTE FUNCTION local_g9_scoped_failure();`);
    const restored = await publicationSnapshot(db);
    await assert.rejects(apply(approval),/Isolated G9 scoped late rollback/);
    assert.deepEqual(await publicationSnapshot(db),restored);
    assert.deepEqual(await anonymousCatalogRows(db),original);
    await db.exec('DROP TRIGGER local_g9_scoped_failure ON public.market_models');

    let attempt,committed,exported={records:baseline},writes=0,publicReads=0;
    const io = {
      now:()=>now,
      async assertMain(commit) {assert.equal(commit,reviewed.commit);},
      catalog:()=>exported,
      siteRows:()=>baseline,
      publicRows:()=>{publicReads++;return anonymousCatalogRows(db);},
      verifyMedia:()=>{},
      freshSource:()=>plan.intake,
      openSnapshot:()=>db,
      prepare:()=>fresh,
      closeSnapshot:()=>{},
      beginJournal:value=>{assert(!attempt);attempt=structuredClone(value);},
      commit:(client,data,scope,hash)=>applyXpG9Release(client,data,scope,hash,now),
      saveCommit:value=>{assert(!committed);committed=structuredClone(value);},
      readJournal:()=>({attempt,committed}),
      saveCatalog:value=>{writes++;exported=value;},
    };
    await assert.rejects(runXpG9Release({mode:'commit',reviewed,approval:'0'.repeat(64)},{}),/Invalid G9 scope hash/);
    await assert.rejects(runXpG9Release({mode:'check',reviewed},
      {...io,siteRows:()=>baseline.slice(1),openSnapshot:()=>assert.fail('Opened snapshot despite changed site')}),
      /Website catalog changed/);
    const check = await runXpG9Release({mode:'check',reviewed},io);
    assert.deepEqual([check.status,check.production_writes,attempt],['ready_for_release_review',0,undefined]);
    const result = await runXpG9Release({mode:'commit',reviewed,approval},io);
    assert.equal(result.status,'committed_export_pending');
    assert.equal(writes,0,'The database phase must not export');
    const rows = await anonymousCatalogRows(db);
    validateG9PostG6Delta(baseline,rows,plan);
    assert.deepEqual(rows.filter(row=>!plan.targets.some(({id})=>id===row.id)),original);
    const after = await publicationSnapshot(db);
    await assert.rejects(apply(approval),/requires an unpublished canonical model/);
    assert.deepEqual(await publicationSnapshot(db),after);
    const keys = new Set(baseline.map(variantKey));
    const changed = {...committed,attempt_sha256:'0'.repeat(64)};
    await assert.rejects(runXpG9Release({mode:'export',approval},{...io,readJournal:()=>({attempt,committed:changed})}),
      /Commit receipt does not match/);
    const readCount = publicReads;
    const out = await runXpG9Release({mode:'export',approval},io);
    assert.equal(publicReads-readCount,2,'Export must re-read the canonical catalog');
    assert.equal(out.status,'export_verified');
    assert.equal(writes,1);
    assert.deepEqual(exported.records.filter(row=>keys.has(variantKey(row))),baseline);
    assert.equal(exported.records.length,baseline.length+2);
    assert(exported.records.filter(row=>!keys.has(variantKey(row))).every(row=>!Object.hasOwn(row,'id')));
    assert.deepEqual(await runXpG9Release({mode:'export',approval},io),out);
    assert.equal(writes,1,'The same receipt must not write the export twice');
    assert.deepEqual(await publicationSnapshot(db),after,'Export must not change any canonical records');
    return {status:'isolated_g9_commit_and_export_passed',preserved:baseline.length,added:2,
      stale_baseline_rejected:true,late_rollback:true,receipt_tampering_rejected:true,idempotent_export:true,
      production_writes:0,paid_calls:0};
  } finally { await db.close(); }
}

async function main() {
  const {values} = parseArgs({options:{reviewed:{type:'string'},fresh:{type:'string'},'connection-root':{type:'string'}}});
  assert(values.reviewed&&values.fresh&&values['connection-root']);
  const root = await realpath('.');
  const connectionRoot = await realpath(values['connection-root']);
  const read = async path=>JSON.parse(await readFile(await realpath(path),'utf8'));
  const receipt = await read(resolve(values.reviewed));
  assert.deepEqual([receipt.status,receipt.production_writes,receipt.publication_approved],['ready_for_owner_review',0,false]);
  const {reviewed} = receipt;
  assert.equal(g9ApprovalHash(reviewed),receipt.reviewed_scope_sha256);
  const site = await fetch('https://elbilsagenten.se/data/public_ev_variants.json',{redirect:'error',signal:AbortSignal.timeout(15000)});
  assert(site.ok);
  const {records:baseline} = await site.json();
  assert.equal(catalogHash(baseline),reviewed.baseline_sha256);
  const image = readG9Image();
  await verifyRegisteredG9Media(root,image,reviewed.ui);
  const {intake} = readG9Capture(values.fresh);
  const path = join(connectionRoot,'data','local','db-tools','source-client.mjs');
  assert.equal(await realpath(path),path);
  const connection = await import(pathToFileURL(path).href);
  assert.equal(connection.PROJECT_REF,'eutcryxbitudllcnpnex');
  let snapshot;
  process.chdir(connectionRoot);
  try { snapshot = await connection.openSourceSnapshot(); }
  finally { process.chdir(root); }
  let fixture,plan;
  const now = new Date();
  try {
    useCalendarDateText(snapshot);
    plan = await readG9Plan(snapshot,intake,image,now);
    fixture = await readPublishedFixture(snapshot);
  } finally { await connection.closeSourceSnapshot(snapshot); }
  console.log(JSON.stringify(await rehearseScopedG9({fixture,fresh:{plan,plan_hash:publicationHash(plan)},reviewed,baseline,now})));
}

if(process.argv[1]&&pathToFileURL(process.argv[1]).href===import.meta.url) main().catch(error=>{
  console.error(JSON.stringify({status:'held',reason:error.message.split('\n')[0],
    location:error.stack?.split('\n').find(line=>/^\s+at .*\.mjs:\d+:\d+/.test(line))?.trim(),
    code:error.cause?.code??error.code??null,production_writes:0}));
  process.exitCode=1;
});
