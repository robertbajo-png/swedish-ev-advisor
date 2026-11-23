import assert from 'node:assert/strict';
import {mkdtemp,realpath,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {PGlite} from '@electric-sql/pglite';
import {anonymousCatalogRows,catalogWithComparableTimes,readPublishedFixture,seedCatalogFixture} from './isolated_catalog_review.mjs';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {applyNewModelPlan,buildNewModelPlan,publicationHash,publicationSnapshot} from './new_model_publication.mjs';
import {policy,readMacanRehearsal} from './porsche_macan_publication.mjs';
import {readMacanScope} from './porsche_macan_scope.mjs';
import {compareCatalogs} from './sync_public_catalog.mjs';

async function readSnapshot(db,intake){
  const expected=await readMacanScope(db,intake.market.row);
  const urls=intake.sources.map(s=>s.final_url);
  const rows=async(sql,args)=>(await db.query(sql,args)).rows.map(({row})=>row);
  expected.expected_sources=await rows('SELECT to_jsonb(s) AS row FROM public.manufacturer_sources s WHERE url=ANY($1::text[]) ORDER BY id',[urls]);
  assert(expected.expected_sources.every(row=>row.canonical_model_id===null||row.canonical_model_id===expected.expected_model.id),
    'A Macan source belongs to another model');
  const collisions=await rows('SELECT to_jsonb(d) AS row FROM public.extracted_variant_drafts d WHERE source_url=$1 AND variant_name=$2',
    [policy.primaryUrl,intake.drafts[0].variant_name]);
  assert.equal(collisions.length,0,'Existing Macan extraction needs separate review');
  return {expected,fixture:await readPublishedFixture(db),
    publicRows:await rows('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')};
}

async function rehearse({expected,fixture,publicRows},intake,image,now){
  const db=new PGlite();
  try{
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db,fixture,[expected]);
    const initial=await anonymousCatalogRows(db);
    assert(compareCatalogs(catalogWithComparableTimes(publicRows),catalogWithComparableTimes(initial)).ok,
      'Isolated Macan baseline differs from the canonical view');
    const before=await publicationSnapshot(db);
    const plan=buildNewModelPlan(before,intake,image,now);
    const apply=(candidate=plan,at=now)=>applyNewModelPlan(db,candidate,publicationHash(candidate),at);
    await assert.rejects(applyNewModelPlan({query:()=>assert.fail('Remote query attempted')},plan,publicationHash(plan),now),/local PGlite/);
    for(const dirty of [
      p=>{p.intake.drafts[0].facts.seats=6;},
      p=>{p.intake.drafts[0].price_evidence.price_type='list_price';},
      p=>{p.intake.drafts[0].price_evidence.source_url=p.intake.market.source.final_url;},
      p=>{p.image.catalog_use_confirmed=true;},
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
    assert.deepEqual(await publicationSnapshot(db),before);
    await db.exec(`CREATE FUNCTION public.macan_late_failure() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (SELECT count(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id)<>1
          OR (SELECT count(*) FROM public.extracted_variant_drafts WHERE canonical_model_id=NEW.canonical_model_id)<>1
        THEN RAISE EXCEPTION 'Macan rollback probe did not reach both insertions'; END IF;
        RAISE EXCEPTION 'Macan late rollback probe';
      END $$;
      CREATE TRIGGER macan_late_failure BEFORE UPDATE ON public.market_models
        FOR EACH ROW EXECUTE FUNCTION public.macan_late_failure()`);
    await assert.rejects(apply(),/Macan late rollback probe/);
    assert.deepEqual(await publicationSnapshot(db),before,'Late failure left catalog data');
    assert.deepEqual(await anonymousCatalogRows(db),initial);
    await db.exec('DROP TRIGGER macan_late_failure ON public.market_models');
    const result=await apply();
    assert.deepEqual([result.committed,result.variants_inserted,result.anonymous_before_commit],[true,1,true]);
    const final=await publicationSnapshot(db);
    assert.equal((await apply()).already_applied,true);
    assert.deepEqual(await publicationSnapshot(db),final,'Exact Macan replay changed rows');
    const [id]=result.canonical_variant_ids,visible=await anonymousCatalogRows(db);
    assert.deepEqual(visible.filter(row=>row.id!==id),initial,'Existing Macan test baseline rows changed');
    policy.verifyPublic(visible.filter(row=>row.id===id),plan);
    const oldMonths=new Set(before.market_model_monthly_stats.map(r=>r.id));
    assert.deepEqual(final.market_model_monthly_stats.filter(r=>oldMonths.has(r.id)),before.market_model_monthly_stats);
    assert.deepEqual(final.market_model_monthly_stats.filter(r=>!oldMonths.has(r.id)).map(r=>[r.month,r.registrations]),
      before.market_model_monthly_stats.some(r=>r.month==='2026-10-01'&&r.county===null&&r.municipality===null)?[]:[['2026-10-01',43]]);
    return {status:'macan_local_atomic_rehearsal_verified',public_baseline:initial.length,local_variants:visible.length,
      technical_fields:9,history_rows_preserved:expected.expected_monthly.length,anonymous_before_commit:true,
      late_rollback:true,exact_replay_noop:true,remote_write_rejected:true,scope_conflicts_rejected:true,photo_use:'private_only',
      publication_approved:false,production_writes:0,paid_calls:0};
  }finally{await db.close();}
}

async function main(){
  const {values}=parseArgs({options:{specs:{type:'string'},market:{type:'string'},photo:{type:'string'},'client-module':{type:'string'}}});
  assert(values.specs&&values.market&&values.photo,'Supply fresh Macan specification, market and photo packets');
  const root=await realpath('.'),release=join(root,'data','local','release-data');
  assert.equal(await realpath(release),release);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  const {intake,image}=readMacanRehearsal(values);
  const connector=await openCatalogSnapshot(await catalogConnectorPath(root,values['client-module']));
  let snapshot;
  try{snapshot=await readSnapshot(connector.client,intake);}finally{await connector.close();}
  const report=await rehearse(snapshot,intake,image,new Date());
  const folder=await mkdtemp(join(release,'porsche-macan-local-'));
  await writeFile(join(folder,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({...report,folder}));
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main().catch(error=>{
  console.error(JSON.stringify({status:'held',reason:error.code==='ERR_ASSERTION'
    ?error.message.split('\n')[0]:'Macan atomic rehearsal could not be verified',production_writes:0}));
  process.exitCode=1;
});
