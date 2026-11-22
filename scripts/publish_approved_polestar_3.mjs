import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { loadEnv } from 'vite';
import { applyPolestar3Release, publicationHash } from './new_model_publication.mjs';
import { readPublishedFixture } from './isolated_catalog_review.mjs';
import { readPolestar3Capture, readPolestar3Image } from './polestar_3_publication.mjs';
import { polestar3ApprovalHash, preparePolestar3ReleaseReview, proveFreshPolestar3Release,
  validatePolestar3Delta, verifyRegisteredPolestar3Media } from './polestar_3_release_scope.mjs';
import { atomicJson, catalogHash, fetchCatalog, normalizeCatalog, publicHeaders, SOURCE } from './sync_public_catalog.mjs';
import { readPolestar3Plan, rehearsePolestar3 } from './verify_polestar_3_local.mjs';

const project = 'eutcryxbitudllcnpnex';
const repo = 'robertbajo-png/swedish-ev-advisor';
const catalogPath = 'public/data/public_ev_variants.json';
const git = (...args) => execFileSync('git', args, {encoding:'utf8', timeout:20000, windowsHide:true}).trim();
const json = async path => {
  assert.equal(await realpath(path), path);
  return JSON.parse(await readFile(path, 'utf8'));
};
const writeOnce = (path, value) => writeFile(path, JSON.stringify(value, null, 2)+'\n', {flag:'wx'});
const isLocal = path => !/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(path);

function requireCommit(result, fresh) {
  assert.deepEqual([result.committed,result.already_applied,result.variants_inserted,result.anonymous_before_commit,result.paid_calls],
    [true,false,1,true,0]);
  assert.equal(result.model_id,fresh.plan.expected_model.id);
  assert.deepEqual(result.canonical_variant_ids,fresh.plan.targets.map(target=>target.id));
  assert.equal(result.publication_batch_id,fresh.plan_hash);
}

export async function exportPolestar3Commit({committed,attempt,scopeHash,publicRows,loadCatalog,saveCatalog,now}) {
  const {reviewed,fresh,result,baseline,committed_at}=committed;
  assert.deepEqual([committed.scope_hash,attempt.scope_hash,attempt.fresh_plan_hash,attempt.baseline_sha256],
    [scopeHash,scopeHash,fresh.plan_hash,reviewed.baseline_sha256]);
  proveFreshPolestar3Release(reviewed,fresh,scopeHash,new Date(committed_at));
  requireCommit(result,fresh);
  assert.equal(catalogHash(baseline),reviewed.baseline_sha256);
  const read=async()=>{
    const rows=await publicRows();
    const target=rows.find(row=>row.brand==='Polestar'&&row.model==='3');
    assert.equal(target?.id,fresh.plan.targets[0].id,'Require exact inserted public variant ID');
    assert.equal(target?.canonical_model_id,fresh.plan.expected_model.id,'Require exact public model ID');
    validatePolestar3Delta(baseline,rows,fresh.plan);
    return rows;
  };
  const rows=await read(), catalog_sha256=catalogHash(rows);
  assert.deepEqual(await read(),rows,'Public catalog changed during export');
  const before=catalogHash((await loadCatalog()).records);
  assert([reviewed.baseline_sha256,catalog_sha256].includes(before),'Local export changed since review');
  if(before!==catalog_sha256) await saveCatalog({
    generated_at:now.toISOString(), source:SOURCE, schema_version:1, missing_view_columns:[],
    catalog_sha256, records:normalizeCatalog(rows)
  });
  return {status:'export_verified',added:1,preserved:baseline.length,catalog_sha256,paid_calls:0};
}

async function main() {
  const {values}=parseArgs({options:{
    reviewed:{type:'string'},ui:{type:'string'},fresh:{type:'string'},connector:{type:'string'},
    output:{type:'string'},apply:{type:'string'},'resume-export':{type:'string'},simulate:{type:'boolean'},
  }});
  const resume=values['resume-export'], scopeHash=values.apply??resume;
  assert([values.apply,resume,values.simulate].filter(Boolean).length<=1,'Choose only one release mode');
  if(scopeHash!==undefined) assert.match(scopeHash,/^[a-f0-9]{64}$/);

  const root=await realpath('.');
  const local=join(root,'data','local','release-data');
  assert(isLocal(root)&&await realpath(local)===local,'Require the real local release directory');
  assert.equal(resolve(git('rev-parse','--show-toplevel')),root);
  assert.equal(git('remote','get-url','origin'),`https://github.com/${repo}.git`);
  const connector=resolve(values.connector??join(root,'data','local','db-tools','source-client.mjs'));
  const sourceRoot=resolve(dirname(connector),'../../..');
  assert.equal(connector,join(sourceRoot,'data','local','db-tools','source-client.mjs'));
  assert(isLocal(sourceRoot)&&await realpath(connector)===connector,'Use the existing local verified database connector');
  const sub=relative(join(sourceRoot,'data','local','release-data'),root);
  assert(root===sourceRoot||(sub&&!isAbsolute(sub)&&!sub.split(/[\\/]/).includes('..')),'Use a release checkout of this workspace');
  const env={...loadEnv('production',sourceRoot,'SUPABASE_'),...loadEnv('production',sourceRoot,'VITE_SUPABASE_')};
  const url=env.SUPABASE_URL||env.VITE_SUPABASE_URL, key=env.SUPABASE_ANON_KEY||env.VITE_SUPABASE_ANON_KEY;
  assert.equal(new URL(url).origin,`https://${project}.supabase.co`);
  publicHeaders(key);
  const publicRows=()=>fetchCatalog({url,key,includeIds:Boolean(resume),onSchema:missing=>assert.deepEqual(missing,[])});
  const output=values.output&&resolve(values.output);
  if(scopeHash) assert(output&&dirname(output)===local&&/^polestar-3-release-[a-z0-9-]+$/.test(basename(output)),
    'Supply a dedicated private release journal');
  else assert(!output,'Checking and simulation do not create a journal');
  const journal=name=>join(output,name+'.json');
  const loadCatalog=()=>json(join(root,catalogPath));
  const requireMain=commit=>{
    assert.match(commit,/^[a-f0-9]{40}$/);
    assert.equal(git('ls-remote','origin','refs/heads/main'),commit+'\trefs/heads/main','Main changed since Polestar review');
    assert.equal(git('rev-parse','HEAD'),commit,'Use the exact main checkout');
    assert.equal(git('status','--porcelain','--untracked-files=no','--','scripts','src','database','public/media'),'Release code or media changed');
  };
  const image=readPolestar3Image();
  if(resume) {
    assert(!values.reviewed&&!values.ui&&!values.fresh,'Recover only from the committed journal');
    const committed=await json(journal('committed-receipt')),attempt=await json(journal('attempt'));
    requireMain(committed.reviewed.commit);
    await verifyRegisteredPolestar3Media(root,image,committed.reviewed.ui);
    console.log(JSON.stringify(await exportPolestar3Commit({committed,attempt,scopeHash,publicRows,loadCatalog,
      saveCatalog:payload=>atomicJson(join(root,catalogPath),payload),now:new Date()})));
    return;
  }

  const reviewedDir=resolve(values.reviewed??'');
  const uiPath=resolve(values.ui??'');
  assert(dirname(reviewedDir)===local&&/^polestar-3-local-[a-z0-9]+$/i.test(basename(reviewedDir)));
  assert(dirname(dirname(uiPath))===local&&/^polestar-ui-[a-z0-9]+$/i.test(basename(dirname(uiPath)))&&basename(uiPath)==='ui-report.json');
  const [report,plan,{records:candidate},ui,{records:baseline}]=await Promise.all([
    json(join(reviewedDir,'report.json')), json(join(reviewedDir,'plan.json')),
    json(join(reviewedDir,'candidate-catalog.json')), json(uiPath), loadCatalog(),
  ]);
  const reviewed=preparePolestar3ReleaseReview({report,plan,ui,baseline,candidate});
  const reviewedHash=polestar3ApprovalHash(reviewed);
  if(values.apply) assert.equal(scopeHash,reviewedHash,'Scope differs from exact Polestar review');
  requireMain(reviewed.commit);
  await verifyRegisteredPolestar3Media(root,image,ui);
  const checkPublic=async()=>assert.equal(catalogHash(await publicRows()),reviewed.baseline_sha256,'Anonymous catalog changed since review');
  await checkPublic();
  const live=await fetch('https://elbilsagenten.se/data/public_ev_variants.json',{redirect:'error',signal:AbortSignal.timeout(15000)});
  assert(live.ok&&catalogHash((await live.json()).records)===reviewed.baseline_sha256,'Deployed catalog differs from review');
  const {intake,reviewHash:capture_sha256}=readPolestar3Capture(values.fresh);
  const connection=await import(pathToFileURL(connector).href);
  assert.equal(connection.PROJECT_REF,project);
  let client;
  try {
    try { process.chdir(sourceRoot); client=await connection.openSourceSnapshot(); }
    finally { process.chdir(root); }
    const freshPlan=await readPolestar3Plan(client,intake,image,new Date());
    const fresh={plan:freshPlan,plan_hash:publicationHash(freshPlan),capture_sha256};
    const evidence_expires_at=proveFreshPolestar3Release(reviewed,fresh,reviewedHash);
    if(values.simulate) {
      const now=new Date();
      const test=await rehearsePolestar3({plan:freshPlan,fixture:await readPublishedFixture(client)},baseline,now,{reviewed,fresh,reviewedHash});
      console.log(JSON.stringify({status:'isolated_release_verified',preserved:baseline.length,inserted:test.added.length,
        anonymous_before_commit:test.receipt.anonymous_before_commit,late_rollback:true,repeat_refused:true,production_writes:0,paid_calls:0}));
      return;
    }
    if(!values.apply) {
      console.log(JSON.stringify({status:'ready_for_scoped_release',scope_sha256:reviewedHash,evidence_expires_at,
        preserved:baseline.length,variants:1,production_writes:0,paid_calls:0}));
      return;
    }
    requireMain(reviewed.commit);
    await checkPublic();
    assert.equal(catalogHash((await loadCatalog()).records),reviewed.baseline_sha256);
    await mkdir(output);
    assert.equal(await realpath(output),output);
    await writeOnce(journal('attempt'),{scope_hash:scopeHash,fresh_plan_hash:fresh.plan_hash,baseline_sha256:reviewed.baseline_sha256});
    await client.query('ROLLBACK');
    const now=new Date();
    const result=await applyPolestar3Release(client,fresh,reviewed,scopeHash,now);
    requireCommit(result,fresh);
    await writeOnce(journal('committed-receipt'),{scope_hash:scopeHash,reviewed,fresh,result,baseline,committed_at:now.toISOString()});
    console.log(JSON.stringify({status:'committed_export_pending',inserted:1,paid_calls:0}));
  } finally { if(client) await connection.closeSourceSnapshot(client); }
}

if(process.argv[1]&&pathToFileURL(process.argv[1]).href===import.meta.url) main().catch(error=>{
  console.error(JSON.stringify({status:'held_or_incomplete',reason:error.code==='ERR_ASSERTION'?
    error.message.split('\n')[0]:'Release step failed; inspect the private journal before retrying'}));
  process.exitCode=1;
});
