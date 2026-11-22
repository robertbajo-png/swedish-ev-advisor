import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdtemp, readFile, realpath, writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {PGlite} from '@electric-sql/pglite';
import {anonymousCatalogRows, catalogWithComparableTimes, readCommittedPublicBaseline, readPublishedFixture,
  seedCatalogFixture} from './isolated_catalog_review.mjs';
import {MODEL, policy, readGlbCapture, readGlbImage} from './mercedes_glb_publication.mjs';
import {applyNewModelPlan, buildNewModelPlan, publicationHash, publicationSnapshot} from './new_model_publication.mjs';
import {catalogHash, compareCatalogs, normalizeCatalog, variantKey} from './sync_public_catalog.mjs';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';

const constraintCount = async db => (await db.query(`SELECT count(*)::int AS count FROM pg_constraint WHERE convalidated
  AND ((conrelid='public.canonical_model_variants'::regclass AND conname='canonical_manufacturer_from_evidence')
  OR (conrelid='public.extracted_variant_drafts'::regclass AND conname='draft_manufacturer_from_evidence'))`)).rows[0].count;

async function readOnly(root,intake,clientModule) {
  const snapshot=await openCatalogSnapshot(await catalogConnectorPath(root,clientModule));
  try {return await readGlbSnapshot(snapshot.client,intake);}
  finally {await snapshot.close();}
}

export async function readGlbSnapshot(db,intake) {
    assert.equal((await db.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
    if(typeof db.setTypeParser==='function')db.setTypeParser(1082,value=>value);
    const rows=async(sql,args)=>JSON.parse(JSON.stringify((await db.query(sql,args)).rows)).map(row=>{
      for(const key of ['month','first_seen_month','last_seen_month'])if(row[key]!=null){
        assert.match(row[key],/^\d{4}-\d{2}-\d{2}(?:T00:00:00\.000Z)?$/);
        row[key]=row[key].slice(0,10);
      }
      return row;
    });
    const one=rs=>{assert.equal(rs.length,1,'Require one exact canonical discovery row');return rs[0];};
    const terms=[MODEL.normalized_brand,MODEL.normalized_model];
    const model=one(await rows('SELECT m.* FROM public.canonical_models m WHERE normalized_brand=$1 AND normalized_model=$2',terms));
    assert.deepEqual([model.brand,model.model,model.validation_status],[MODEL.brand,MODEL.model,'draft']);
    const alias=one(await rows('SELECT a.* FROM public.model_aliases a WHERE normalized_brand=$1 AND normalized_model=$2',terms));
    const market=await rows(`SELECT m.* FROM public.market_models m WHERE
      (normalized_brand=$1 AND normalized_model=$2) OR canonical_model_id=$3 ORDER BY id`,[...terms,model.id]);
    const electric=one(market.filter(r=>r.fuel_type_raw==='EL'&&r.normalized_brand===terms[0]&&r.normalized_model===terms[1]));
    policy.scopedDiscovery.check({market_models:market},model,electric);
    const months=await rows('SELECT s.* FROM public.market_model_monthly_stats s WHERE market_model_id=ANY($1::uuid[]) ORDER BY id',
      [market.map(r=>r.id)]);
    const sources=await rows('SELECT s.* FROM public.manufacturer_sources s WHERE url=ANY($1::text[]) ORDER BY id',
      [intake.sources.map(source=>source.final_url)]);
    assert(sources.every(source=>source.brand===MODEL.brand&&source.model===MODEL.model
      && [null,model.id].includes(source.canonical_model_id)),'A source is already owned outside the GLB draft');
    assert.equal((await db.query('SELECT id FROM public.canonical_model_variants WHERE canonical_model_id=$1',[model.id])).rows.length,0);
    assert.equal((await db.query(`SELECT id FROM public.extracted_variant_drafts
      WHERE canonical_model_id=$1 OR (source_url=$2 AND variant_name=ANY($3::text[]))`,
      [model.id,policy.primaryUrl,intake.drafts.map(d=>d.variant_name)])).rows.length,0);
    return {model,fixture:await readPublishedFixture(db),migrationConstraints:await constraintCount(db),
      databaseRows:(await rows('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')).map(r=>r.row),
      plans:market.map(row=>({expected_model:model,expected_alias:alias,expected_market:row,
        expected_monthly:months.filter(s=>s.market_model_id===row.id),expected_sources:sources}))};
}

export async function rehearseGlb({fixture,model,plans},intake,image,baseline,now) {
  const db=new PGlite();
  try {
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db,fixture,plans);
    const initial=await anonymousCatalogRows(db);
    assert(compareCatalogs(catalogWithComparableTimes(baseline),catalogWithComparableTimes(initial)).ok,'Isolated baseline differs from live');
    const initialState=await publicationSnapshot(db);
    assert.equal(await constraintCount(db),fixture.variants.some(row=>row.price_type==='manufacturer_from')?2:0);
    const migration=await readFile(new URL('../database/migrations/026_manufacturer_from_price.sql',import.meta.url),'utf8');
    await db.exec(migration);
    await db.exec(migration);
    assert.equal(await constraintCount(db),2);
    assert.deepEqual(await publicationSnapshot(db),initialState,'Migration changed data');
    assert.deepEqual(await anonymousCatalogRows(db),initial,'Migration changed the anonymous catalog');
    if(!initialState.market_models.some(r=>r.fuel_type_raw!=='EL')) {
      await db.exec(`INSERT INTO public.market_models(brand_raw,model_raw,fuel_type_raw,normalized_brand,normalized_model)
        VALUES ('MERCEDES','GLB','BENSIN','mercedes benz','glb')`);
    }
    const before=await publicationSnapshot(db);
    const plan=buildNewModelPlan(before,intake,image,now);
    const apply=(candidate=plan,at=now)=>applyNewModelPlan(db,candidate,publicationHash(candidate),at);
    const wrongLink=structuredClone(before);
    wrongLink.market_models.find(r=>r.fuel_type_raw!=='EL').canonical_model_id=model.id;
    assert.throws(()=>buildNewModelPlan(wrongLink,intake,image,now),/Only the exact EL row/);
    await assert.rejects(applyNewModelPlan({query:()=>assert.fail('Remote query attempted')},plan,publicationHash(plan),now),/local PGlite/);
    const wrongPrice=structuredClone(plan);
    wrongPrice.intake.drafts[0].price_evidence.price_type='list_price';
    await assert.rejects(apply(wrongPrice));
    const wrongSeats=structuredClone(plan);
    wrongSeats.intake.drafts[1].facts.seats=7;
    await assert.rejects(apply(wrongSeats));
    const wrongPhoto=structuredClone(plan);
    wrongPhoto.image.author='Mercedes-Benz Sverige AB';
    await assert.rejects(apply(wrongPhoto));
    await assert.rejects(apply(plan,new Date(+now+910000)),/Fresh source capture/);
    assert.deepEqual(await publicationSnapshot(db),before);
    await db.exec(`CREATE FUNCTION public.glb_late_failure() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (SELECT count(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id)<>2
          OR (SELECT count(*) FROM public.extracted_variant_drafts WHERE canonical_model_id=NEW.canonical_model_id)<>2
        THEN RAISE EXCEPTION 'GLB failure probe did not reach both insertions'; END IF;
        RAISE EXCEPTION 'GLB late rollback probe';
      END $$;
      CREATE TRIGGER glb_late_failure BEFORE UPDATE ON public.market_models
        FOR EACH ROW EXECUTE FUNCTION public.glb_late_failure()`);
    await assert.rejects(apply(),/GLB late rollback probe/);
    assert.deepEqual(await publicationSnapshot(db),before,'Late failure left changes');
    assert.deepEqual(await anonymousCatalogRows(db),initial);
    await db.exec('DROP TRIGGER glb_late_failure ON public.market_models');
    const receipt=await apply();
    assert.deepEqual([receipt.committed,receipt.variants_inserted,receipt.anonymous_before_commit],[true,2,true]);
    const after=await publicationSnapshot(db);
    assert.equal((await apply()).already_applied,true);
    assert.deepEqual(await publicationSnapshot(db),after,'Exact replay changed rows');
    const targetId=receipt.canonical_variant_ids[0];
    await assert.rejects(db.query('UPDATE public.canonical_model_variants SET price_source_hash=NULL WHERE id=$1',[targetId]),{code:'23514'});
    await assert.rejects(db.query("UPDATE public.extracted_variant_drafts SET extraction_payload='{}' WHERE canonical_model_id=$1",[model.id]),{code:'23514'});
    const resolved=after.market_models.find(r=>r.id===plan.expected_market.id);
    assert.equal(resolved.canonical_model_id,model.id);
    assert.deepEqual(after.market_models.filter(row=>row.id!==resolved.id),before.market_models.filter(row=>row.id!==resolved.id));
    const oldMonths=new Set(before.market_model_monthly_stats.map(r=>r.id));
    assert.deepEqual(after.market_model_monthly_stats.filter(r=>oldMonths.has(r.id)),before.market_model_monthly_stats);
    const publicRows=await anonymousCatalogRows(db);
    const ids=new Set(receipt.canonical_variant_ids);
    assert.deepEqual(publicRows.filter(r=>!ids.has(r.id)),initial,'Existing variants changed');
    const added=catalogWithComparableTimes(publicRows.filter(r=>ids.has(r.id)));
    assert.equal(added.length,2);
    return {plan,added};
  } finally {await db.close();}
}

export async function verifyGlb(reviewPath, readScope=readOnly) {
  assert(reviewPath,'Supply the fresh private GLB capture including its market evidence');
  const root=await realpath('.');
  const release=await realpath('data/local/release-data');
  assert.equal(release,join(root,'data','local','release-data'));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
  const {intake,reviewHash}=readGlbCapture(reviewPath);
  const image=readGlbImage();
  const scope=await readScope(root,intake);
  const output=await mkdtemp(join(release,'mercedes-glb-local-'));
  const {base,proof}=await readCommittedPublicBaseline(release,output,{imageTools:true});
  assert.equal(execFileSync('git',['ls-remote','origin','refs/heads/main'],{encoding:'utf8',timeout:20000}).trim(),
    proof.commit+'\trefs/heads/main','Local origin/main is stale');
  assert(compareCatalogs(catalogWithComparableTimes(base),catalogWithComparableTimes(scope.databaseRows)).ok,
    'Live export differs from canonical projection');
  const now=new Date();
  const {plan,added}=await rehearseGlb(scope,intake,image,base,now);
  const records=normalizeCatalog([...base,...added]), old=new Set(base.map(variantKey));
  assert.equal(records.length,base.length+2);
  assert.deepEqual(records.filter(row=>old.has(variantKey(row))),base);
  const report={status:'glb_local_insertion_verified',...proof,variants:2,technical_fields:18,candidate_count:records.length,
    candidate_sha256:catalogHash(records),plan_sha256:publicationHash(plan),review_sha256:reviewHash,
    historical_months_preserved:plan.expected_monthly.length,other_fuels_preserved:true,anonymous_before_commit:true,
    exact_replay_noop:true,late_rollback:true,starting_price_migration_local:true,
    starting_price_constraints_live:scope.migrationConstraints,publication_approved:false,production_writes:0,paid_calls:0};
  const save=(file,data)=>writeFile(join(output,file),JSON.stringify(data,null,2)+'\n',{flag:'wx'});
  await save('candidate-catalog.json',{status:'local_only',publication_approved:false,records});
  await save('plan.json',plan);
  await save('report.json',report);
  return {...report,output};
}
async function main() {
  const {values}=parseArgs({options:{review:{type:'string'},'client-module':{type:'string'}}});
  console.log(JSON.stringify(await verifyGlb(values.review,(root,intake)=>readOnly(root,intake,values['client-module']))));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href) await main().catch(error=>{
  console.error(JSON.stringify({status:'held',reason:error.message.split('\n')[0],
    location:error.stack?.split('\n').find(line=>/\.mjs:\d+:\d+/.test(line))?.trim(),production_writes:0}));
  process.exitCode=1;
});
