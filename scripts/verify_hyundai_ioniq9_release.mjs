import assert from 'node:assert/strict';
import {readFile,realpath,writeFile} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {PGlite} from '@electric-sql/pglite';
import {readIoniq9Capture} from './hyundai_ioniq9_publication.mjs';
import {ioniq9ReleaseHash,runIoniq9Release} from './hyundai_ioniq9_release.mjs';
import {anonymousCatalogRows,seedCatalogFixture} from './isolated_catalog_review.mjs';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {applyIoniq9Release,publicationSnapshot} from './new_model_publication.mjs';
import {catalogHash} from './sync_public_catalog.mjs';
import {readIoniq9Snapshot} from './verify_hyundai_ioniq9_local.mjs';

async function main(){
  const {values}=parseArgs({options:{scope:{type:'string'},fresh:{type:'string'},readback:{type:'string'},'client-module':{type:'string'}}});
  const root=await realpath('.'),release=join(root,'data','local','release-data');
  assert.equal(await realpath(release),release);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  const scopeFile=resolve(values.scope),candidate=resolve(values.readback);
  for(const [file,folder,prefix] of [[scopeFile,'scope.json','hyundai-ioniq9-scope-'],
    [join(candidate,'main-source','public','data','public_ev_variants.json'),'public_ev_variants.json','hyundai-ioniq9-local-']]){
    assert.equal(await realpath(file),file);
    const container=folder==='scope.json'?dirname(file):candidate;
    assert.equal(dirname(container),release);
    assert.match(basename(container),new RegExp('^'+prefix+'[0-9a-z]+$','i'));
    assert.equal(basename(file),folder);
  }
  const json=async path=>JSON.parse(await readFile(path,'utf8'));
  const scope=await json(scopeFile);
  const baseline=(await json(join(candidate,'main-source','public','data','public_ev_variants.json'))).records;
  assert.equal(catalogHash(baseline),scope.baseline_sha256);
  const fresh=readIoniq9Capture(values.fresh);
  const source=await openCatalogSnapshot(await catalogConnectorPath(root,values['client-module']));
  let fixture;
  try{fixture=await readIoniq9Snapshot(source.client,fresh.intake);}finally{await source.close();}
  const db=new PGlite();
  try{
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db,fixture.fixture,[fixture.expected]);
    const initial=await publicationSnapshot(db);
    // Replay real source times without claiming this is an online production authorization.
    const now=new Date(Math.max(...[...fresh.intake.sources,fresh.intake.market.source,fresh.intake.market.article,
      ...['downloads','factory_trim','factory_wltp'].map(key=>fresh.intake.source_decisions[key])]
      .map(item=>Date.parse(item.fetched_at)))+1000);
    const target={commit:scope.baseline_commit,reader_sha256:'b'.repeat(64)};
    const seal=ioniq9ReleaseHash(scope,target);
    let attempt,receipt,exported,attempts=0,commits=0,exports=0;
    const io={
      now:()=>now,
      verifyProduction(reviewed,requested){assert.deepEqual([reviewed,requested],[scope,target]);},
      baseline:()=>baseline,liveBaseline:()=>baseline,
      async publicRows(){
        if(!db.isInTransaction())return anonymousCatalogRows(db);
        // Production uses a separate REST connection during its read-only snapshot.
        // Don't run intentionally denied queries inside this local test transaction.
        await db.exec('SET LOCAL ROLE anon');
        try{
          return (await db.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')).rows.map(r=>r.row);
        }finally{await db.exec('RESET ROLE');}
      },
      freshSource:()=>fresh,
      async openSnapshot(){await db.exec('BEGIN READ ONLY');return db;},
      readSnapshot:readIoniq9Snapshot,
      async closeSnapshot(){if(db.isInTransaction())await db.exec('ROLLBACK');},
      saveAttempt(row){assert.equal(++attempts,1);attempt=row;},
      async commit(client,plan,approved){
        assert.equal(++commits,1);
        await client.exec('ROLLBACK');
        return applyIoniq9Release(client,plan,scope,target,approved,now);
      },
      saveCommit(row){receipt=row;},
      readJournal:()=>({attempt,receipt}),
      saveExport(rows){assert.equal(++exports,1);exported=rows;},
    };
    const run=(mode,options={},adapter=io)=>runIoniq9Release({mode,scope,target,seal,...options},adapter);
    const checked=await run('check');
    assert.equal(checked.scope_sha256,seal);
    assert.equal(checked.production_writes,0);
    await assert.rejects(run('commit',{seal:'0'.repeat(64)}),/release seal mismatch/);
    await assert.rejects(run('check',{}, {...io,freshSource:()=>({intake:scope.plan.intake,image:scope.plan.image})}),
      /Require new official source capture|Fresh source capture|Expired or invalid/);
    assert.deepEqual(await publicationSnapshot(db),initial);
    const inserted=await run('commit');
    assert.deepEqual([inserted.added,inserted.deployed],[1,false]);
    const after=await publicationSnapshot(db);
    await assert.rejects(run('commit'),/Anonymous Supabase baseline changed/);
    await assert.rejects(run('export',{}, {...io,readJournal:()=>({attempt,receipt:{...receipt,attempt_sha256:'0'.repeat(64)}})}),
      /journal do not match/);
    const recovered=await run('export',{}, {...io,commit:()=>assert.fail('Recovery cannot write')});
    assert.equal(recovered.catalog_sha256,catalogHash(exported));
    assert.equal(exported.length,baseline.length+1);
    assert.deepEqual(await publicationSnapshot(db),after);
    assert.deepEqual([attempts,commits,exports],[1,1,1]);
    const report={status:'ioniq9_guarded_release_rehearsal_passed',baseline:baseline.length,added:1,
      catalog_sha256:recovered.catalog_sha256,stale_and_duplicate_blocked:true,read_only_recovery:true,
      publication_approved:false,production_writes:0,paid_calls:0};
    await writeFile(join(dirname(scopeFile),'guarded-rehearsal.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
    console.log(JSON.stringify(report));
  }finally{await db.close();}
}

await main().catch(error=>{
  console.error(JSON.stringify({status:'held',reason:error.message.split('\n')[0],
    location:error.stack?.split('\n').find(line=>/\.mjs:\d+:\d+/.test(line))?.trim(),production_writes:0}));
  process.exitCode=1;
});
