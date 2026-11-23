import assert from 'node:assert/strict';
import {mkdtemp,readFile,realpath,writeFile} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {PGlite} from '@electric-sql/pglite';
import {anonymousCatalogRows,catalogWithComparableTimes,readPublishedFixture,seedCatalogFixture} from './isolated_catalog_review.mjs';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {applyLexusRelease,applyMacanRelease,applyNewModelPlan,buildNewModelPlan,publicationHash,publicationSnapshot} from './new_model_publication.mjs';
import {policy,readMacanRehearsal} from './porsche_macan_publication.mjs';
import {policy as lexusPolicy,readLexusCapture,readLexusScope} from './lexus_rz_publication.mjs';
import {macanReleaseHash} from './porsche_macan_release_scope.mjs';
import {lexusReleaseHash} from './lexus_rz_release_scope.mjs';
import {readMacanScope} from './porsche_macan_scope.mjs';
import {catalogHash,compareCatalogs} from './sync_public_catalog.mjs';
import {assertExactDcInstalled} from './verify_exact_dc_migration.mjs';

export const readMacanSnapshot=(db,intake,options)=>readScopedSnapshot(db,intake,readMacanScope,policy,options);
export const readLexusSnapshot=(db,intake,options)=>readScopedSnapshot(db,intake,readLexusScope,lexusPolicy,options);
async function readScopedSnapshot(db,intake,readScope,policy,{fixture=true}={}){
  await assertExactDcInstalled(db);
  const expected=await readScope(db,intake.market.row);
  const urls=intake.sources.map(s=>s.final_url);
  const rows=async(sql,args)=>(await db.query(sql,args)).rows.map(({row})=>row);
  expected.expected_sources=await rows('SELECT to_jsonb(s) AS row FROM public.manufacturer_sources s WHERE url=ANY($1::text[]) ORDER BY id',[urls]);
  assert(expected.expected_sources.every(row=>row.canonical_model_id===null||row.canonical_model_id===expected.expected_model.id),
    'A selected source belongs to another model');
  const collisions=await rows('SELECT to_jsonb(d) AS row FROM public.extracted_variant_drafts d WHERE source_url=$1 AND variant_name=$2',
    [policy.primaryUrl,intake.drafts[0].variant_name]);
  assert.equal(collisions.length,0,'Existing exact extraction needs separate review');
  return {expected,fixture:fixture?await readPublishedFixture(db):null,
    publicRows:await rows('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')};
}

async function rehearse({expected,fixture,publicRows},intake,image,now,reviewed,profile){
  const db=new PGlite();
  try{
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db,fixture,[expected]);
    const initial=await anonymousCatalogRows(db);
    assert(compareCatalogs(catalogWithComparableTimes(publicRows),catalogWithComparableTimes(initial)).ok,
      'Isolated baseline differs from the canonical view');
    const exact={exactJson:true};
    const before=await publicationSnapshot(db,false,exact);
    const plan=buildNewModelPlan(before,intake,image,now);
    const apply=(candidate=plan,at=now)=>applyNewModelPlan(db,candidate,publicationHash(candidate),at);
    const target={commit:'1'.repeat(40),reader_sha256:'2'.repeat(64)};
    const release=reviewed?()=>profile.apply(db,plan,reviewed,target,profile.hash(reviewed,target),now):apply;
    await assert.rejects(applyNewModelPlan({query:()=>assert.fail('Remote query attempted')},plan,publicationHash(plan),now),/local PGlite/);
    for(const dirty of [
      p=>{p.intake.drafts[0].facts.seats=6;},
      p=>{p.intake.drafts[0].price_evidence.price_type='list_price';},
      p=>{p.intake.drafts[0].price_evidence.source_url=p.intake.market.source.final_url;},
      p=>{p.image.credit='Unreviewed credit';},
    ]){
      const wrong=structuredClone(plan);
      dirty(wrong);
      await assert.rejects(apply(wrong));
    }
    await assert.rejects(apply(plan,new Date(+now+910000)),/Fresh source capture/);
    const changedAlias=structuredClone(plan);
    changedAlias.expected_alias.confidence=0.91;
    await assert.rejects(apply(changedAlias),/Concurrent alias change/);
    const collidingTarget=structuredClone(plan);
    collidingTarget.targets[0].id=initial[0].id;
    await assert.rejects(apply(collidingTarget),/Publication scope changed/);
    assert.deepEqual(await publicationSnapshot(db,false,exact),before);
    await db.exec(`CREATE FUNCTION public.single_variant_late_failure() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (SELECT count(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id)<>1
          OR (SELECT count(*) FROM public.extracted_variant_drafts WHERE canonical_model_id=NEW.canonical_model_id)<>1
        THEN RAISE EXCEPTION 'Rollback probe did not reach both insertions'; END IF;
        RAISE EXCEPTION 'Late single-variant rollback probe';
      END $$;
      CREATE TRIGGER single_variant_late_failure BEFORE UPDATE ON public.market_models
        FOR EACH ROW EXECUTE FUNCTION public.single_variant_late_failure()`);
    await assert.rejects(release(),/Late single-variant rollback probe/);
    assert.deepEqual(await publicationSnapshot(db,false,exact),before,'Late failure left catalog data');
    assert.deepEqual(await anonymousCatalogRows(db),initial);
    await db.exec('DROP TRIGGER single_variant_late_failure ON public.market_models');
    const result=await release();
    assert.deepEqual([result.committed,result.variants_inserted,result.anonymous_before_commit],[true,1,true]);
    const final=await publicationSnapshot(db,false,exact);
    if(reviewed)await assert.rejects(release(),/requires an unpublished canonical model/);
    assert.equal((await apply()).already_applied,true);
    assert.deepEqual(await publicationSnapshot(db,false,exact),final,'Exact single-variant replay changed rows');
    const [id]=result.canonical_variant_ids,visible=await anonymousCatalogRows(db);
    assert.deepEqual(visible.filter(row=>row.id!==id),initial,'Existing test baseline rows changed');
    profile.policy.verifyPublic(visible.filter(row=>row.id===id),plan);
    const oldMonths=new Set(before.market_model_monthly_stats.map(r=>r.id));
    assert.deepEqual(final.market_model_monthly_stats.filter(r=>oldMonths.has(r.id)),before.market_model_monthly_stats);
    const {last_seen_month:month,registrations_last_month:registrations}=intake.market.row;
    assert.deepEqual(final.market_model_monthly_stats.filter(r=>!oldMonths.has(r.id)).map(r=>[r.month,r.registrations]),
      before.market_model_monthly_stats.some(r=>r.month===month&&r.county===null&&r.municipality===null)?[]:[[month,registrations]]);
    const candidate=catalogWithComparableTimes(visible);
    return {plan,candidate,report:{status:profile.id+'_local_atomic_rehearsal_verified',public_baseline:initial.length,local_variants:visible.length,
      plan_sha256:publicationHash(plan),candidate_sha256:catalogHash(candidate),
      baseline_sha256:catalogHash(catalogWithComparableTimes(publicRows)),
      technical_fields:9,history_rows_preserved:expected.expected_monthly.length,anonymous_before_commit:true,
      late_rollback:true,exact_replay_noop:true,remote_write_rejected:true,scope_conflicts_rejected:true,
      reviewed_transaction_tested:Boolean(reviewed),
      photo_use:'licensed_model_photo_in_private_rehearsal',
      publication_approved:false,production_writes:0,paid_calls:0}};
  }finally{await db.close();}
}

async function main(){
  const {values}=parseArgs({options:{specs:{type:'string'},market:{type:'string'},photo:{type:'string'},
    'client-module':{type:'string'},'reviewed-scope':{type:'string'},lexus:{type:'boolean'},fresh:{type:'string'}}});
  assert(values.lexus?values.fresh&&!values.specs&&!values.market&&!values.photo:values.specs&&values.market&&values.photo&&!values.fresh,
    'Supply one complete private source packet set');
  const profile=values.lexus?{
    id:'lexus',policy:lexusPolicy,hash:lexusReleaseHash,apply:applyLexusRelease,
    read:readLexusSnapshot,prefix:'lexus-rz-local-',scope:/^lexus-release-scope-[a-z0-9]+$/i,
  }:{
    id:'macan',policy,hash:macanReleaseHash,apply:applyMacanRelease,
    read:readMacanSnapshot,prefix:'porsche-macan-local-',scope:/^macan-release-scope-[a-z0-9]+$/i,
  };
  const root=await realpath('.'),release=join(root,'data','local','release-data');
  assert.equal(await realpath(release),release);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  let reviewed;
  if(values['reviewed-scope']){
    const file=resolve(values['reviewed-scope']);
    assert(await realpath(file)===file&&dirname(dirname(file))===release&&basename(file)==='scope.json'
      &&profile.scope.test(basename(dirname(file))),'Require a reviewed local release scope');
    reviewed=JSON.parse(await readFile(file,'utf8'));
  }
  const {intake,image}=values.lexus?readLexusCapture(values.fresh):readMacanRehearsal(values);
  const connector=await openCatalogSnapshot(await catalogConnectorPath(root,values['client-module']));
  let snapshot;
  try{snapshot=await profile.read(connector.client,intake);}finally{await connector.close();}
  const {plan,candidate,report}=await rehearse(snapshot,intake,image,new Date(),reviewed,profile);
  const folder=await mkdtemp(join(release,profile.prefix));
  const candidateFile={status:'local_only',publication_approved:false,catalog_sha256:report.candidate_sha256,records:candidate};
  for(const [name,data] of Object.entries({report,plan,'baseline-catalog':snapshot.publicRows,'candidate-catalog':candidateFile})){
    await writeFile(join(folder,name+'.json'),JSON.stringify(data,null,2)+'\n',{flag:'wx'});
  }
  console.log(JSON.stringify({...report,folder}));
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main().catch(error=>{
  console.error(JSON.stringify({status:'held',reason:error.code==='ERR_ASSERTION'
    ?error.message.split('\n')[0]:'Single-variant atomic rehearsal could not be verified',production_writes:0}));
  process.exitCode=1;
});
