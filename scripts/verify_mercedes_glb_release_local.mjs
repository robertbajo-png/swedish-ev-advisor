import assert from 'node:assert/strict';
import {readFile,realpath} from 'node:fs/promises';
import {dirname,join,relative,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {pathToFileURL} from 'node:url';
import {PGlite} from '@electric-sql/pglite';
import {anonymousCatalogRows,seedCatalogFixture} from './isolated_catalog_review.mjs';
import {createGlbScope,glbApprovalHash,glbCatalogHash,runGlbRelease} from './mercedes_glb_release.mjs';
import {applyGlbRelease,publicationSnapshot} from './new_model_publication.mjs';
import {readGlbSnapshot} from './verify_mercedes_glb_local.mjs';
import {catalogHash} from './sync_public_catalog.mjs';

export async function rehearseGlbCommand(scope,baseline,snapshot) {
  const db=new PGlite();
  try {
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db,snapshot.fixture,snapshot.plans);
    const original=await publicationSnapshot(db), prior=await anonymousCatalogRows(db);
    assert.equal(glbCatalogHash(prior),scope.database_baseline_sha256);
    const fresh=structuredClone(scope.plan.intake);
    const captures=[...fresh.sources,fresh.market.source,fresh.market.article];
    const now=new Date(Math.max(...captures.map(s=>Date.parse(s.fetched_at)))+60_000);
    for(const capture of captures)capture.fetched_at=now.toISOString();
    const target={commit:scope.baseline_commit,reader_sha256:'f'.repeat(64)};
    const approved=glbApprovalHash(scope,target);
    let journal={}, writes=0, proofs=0;
    const io={
      now:()=>now,
      async verifyProduction(expected,release){assert.deepEqual([expected,release],[scope,target]);proofs++;},
      baseline:()=>baseline,liveBaseline:()=>baseline,
      async publicRows(){
        if(!db.isInTransaction())return anonymousCatalogRows(db);
        await db.exec('SET LOCAL ROLE anon');
        try{return (await db.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')).rows.map(r=>r.row);}
        finally{await db.exec('RESET ROLE');}
      },
      freshSource:()=>fresh,
      async openSnapshot(){await db.exec('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');return db;},
      readSnapshot:readGlbSnapshot,
      async closeSnapshot(){if(db.isInTransaction())await db.exec('ROLLBACK');},
      async saveAttempt(attempt){assert(!journal.attempt,'Attempt journal already exists');journal.attempt=attempt;},
      async commit(client,plan,hash){writes++;await client.query('ROLLBACK');return applyGlbRelease(client,plan,scope,target,hash,now);},
      async saveCommit(receipt){journal.receipt=receipt;},
      async readJournal(){assert(journal.attempt&&journal.receipt,'No confirmed write to export');return journal;},
      async saveExport(records){assert(!journal.records);journal.records=records;},
    };
    const run=(mode,approval=approved,changes={})=>runGlbRelease({mode,scope,target,approval},{...io,...changes});
    await assert.rejects(run('commit','0'.repeat(64)),/explicit approved hash/);
    assert.equal(proofs,0,'Invalid authorization must fail before external verification');
    await assert.rejects(run('check',undefined,{verifyProduction:()=>assert.fail('Live reader is stale')}),/reader is stale/);
    await assert.rejects(run('check'),/Migration 026 is not installed/);
    assert.equal(writes,0);
    assert.deepEqual(await publicationSnapshot(db),original);

    await db.exec(await readFile(new URL('../database/migrations/026_manufacturer_from_price.sql',import.meta.url),'utf8'));
    const checked=await run('check');
    assert.deepEqual([checked.status,checked.scope_sha256,checked.production_writes],['ready_for_explicit_glb_approval',approved,0]);
    const drift=structuredClone(fresh);
    drift.drafts[0].field_evidence.dc_charge_kw.quote+=' changed';
    await assert.rejects(run('commit',approved,{freshSource:()=>drift}),/facts or literal evidence changed/);
    await assert.rejects(run('commit',approved,{freshSource:()=>scope.plan.intake}),/new capture/);
    assert.equal(writes,0);
    assert.deepEqual(await publicationSnapshot(db),original);

    await db.exec(`CREATE FUNCTION public.glb_release_failure() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (SELECT count(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id)<>2
        THEN RAISE EXCEPTION 'Wrong release rollback probe position'; END IF;
        RAISE EXCEPTION 'GLB release rollback probe';
      END $$;
      CREATE TRIGGER glb_release_failure BEFORE UPDATE ON public.market_models FOR EACH ROW
      EXECUTE FUNCTION public.glb_release_failure()`);
    await assert.rejects(run('commit'),error=>{
      assert.match(error.message,/GLB release rollback probe/,'Expected late rollback, received: '+error.message);
      return true;
    });
    assert(journal.attempt&&!journal.receipt);
    assert.deepEqual(await publicationSnapshot(db),original);
    await assert.rejects(run('export'),/No confirmed write/);
    await assert.rejects(run('commit'),/Attempt journal already exists/);
    assert.equal(writes,1,'Do not retry an uncertain attempt in the same journal');
    await db.exec('DROP TRIGGER glb_release_failure ON public.market_models');
    journal={};
    const committed=await run('commit');
    assert.deepEqual([committed.status,committed.added,committed.deployed],['glb_committed_private_export_pending',2,false]);
    await assert.rejects(run('commit'),/Anonymous Supabase baseline changed/);
    assert.equal(writes,2);
    const exported=await run('export');
    assert.equal(exported.status,'private_glb_export_verified');
    assert.equal(exported.catalog_sha256,catalogHash(journal.records));
    assert.equal(journal.records.length,baseline.length+2);
    const changed=(await anonymousCatalogRows(db)).map(row=>row.brand==='Mercedes-Benz'&&row.model==='Glb'?row:{...row,available_confirmed:!row.available_confirmed});
    await assert.rejects(run('export',approved,{publicRows:()=>changed}),/baseline rows changed/);
    const badIds=(await anonymousCatalogRows(db)).map(row=>row.brand==='Mercedes-Benz'&&row.model==='Glb'?{...row,id:'wrong'}:row);
    await assert.rejects(run('export',approved,{publicRows:()=>badIds}),/Exact GLB variant ID/);
    return {status:'glb_production_command_verified_locally',variants:2,preserved:baseline.length,check_read_only:true,
      wrong_approval_stopped:true,stale_source_stopped:true,missing_migration_stopped:true,late_rollback:true,
      uncertain_attempt_not_retried:true,confirmed_export:true,export_id_and_drift_checked:true,
      deployment_proofs_simulated:true,production_writes:0,paid_calls:0};
  } finally {await db.close();}
}

async function main(){
  const {values}=parseArgs({options:{readback:{type:'string'},ui:{type:'string'}}});
  const root=await realpath('.'), release=join(root,'data','local','release-data');
  assert.equal(await realpath(release),release);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  const local=async path=>{
    const found=resolve(path);
    assert.equal(await realpath(found),found);
    assert(!relative(release,found).startsWith('..')&&relative(release,found)!=='');
    return found;
  };
  const readback=await local(values.readback), uiPath=await local(values.ui);
  assert.equal(dirname(dirname(uiPath)),readback);
  const json=async path=>JSON.parse(await readFile(await local(path),'utf8'));
  const [plan,report,ui,base,candidate]=await Promise.all([
    json(join(readback,'plan.json')),json(join(readback,'report.json')),json(uiPath),
    json(join(readback,'main-source/public/data/public_ev_variants.json')),json(join(readback,'candidate-catalog.json'))]);
  const manifest=(await json(join(dirname(uiPath),'source/src/image-variants.json')))[plan.image.asset_url];
  const scope=createGlbScope({plan,report,ui,baseline:base.records,candidate:candidate.records,code:ui.code_sha256,
    media:[{url:plan.image.asset_url,sha256:plan.image.content_sha256},...manifest.variants.map(({url,sha256})=>({url,sha256}))]});
  const connector=join(root,'data','local','db-tools','source-client.mjs');
  assert.equal(await realpath(connector),connector);
  const {openSourceSnapshot,closeSourceSnapshot}=await import(pathToFileURL(connector).href);
  const db=await openSourceSnapshot();
  let snapshot;
  try {snapshot=await readGlbSnapshot(db,scope.plan.intake);}
  finally {await closeSourceSnapshot(db);}
  assert.equal(glbCatalogHash(snapshot.databaseRows),scope.database_baseline_sha256);
  console.log(JSON.stringify(await rehearseGlbCommand(scope,base.records,snapshot)));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href) await main().catch(error=>{
  console.error(JSON.stringify({status:'held',message:error.message.split('\n')[0],
    location:error.stack?.split('\n').find(line=>/\.mjs:\d+:\d+/.test(line))?.trim(),production_writes:0}));
  process.exitCode=1;
});
