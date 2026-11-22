import assert from 'node:assert/strict';
import { PGlite } from '@electric-sql/pglite';
import { applyNewModelPlan, applyTavascanDriveRelease, publicationHash, publicationSnapshot } from './new_model_publication.mjs';
import { proveTavascanRelease, variant } from './cupra_tavascan_release_scope.mjs';
import { anonymousCatalogRows, seedCatalogFixture } from './isolated_catalog_review.mjs';
import { exportTavascanCommit } from './publish_approved_cupra_tavascan.mjs';
import { catalogHash, variantKey } from './sync_public_catalog.mjs';

export async function verifyTavascanReleaseRehearsal({reviewed,fresh,ui,scope,baseline,fixture,now}) {
  const rejectScope=(r,f,u,s,at,reason)=>assert.throws(()=>proveTavascanRelease(r,f,u,s,at),reason);
  rejectScope(reviewed,fresh,ui,'0'.repeat(64),now,/Invalid Tavascan release approval/);
  rejectScope(reviewed,reviewed,ui,scope,now,/Re-fetch official evidence/);
  rejectScope(reviewed,fresh,ui,scope,new Date(+now+900001),/source window expired/);
  rejectScope(reviewed,fresh,{...ui,full_photo_frame:false},scope,now);
  const wrongModel=structuredClone(fresh);
  wrongModel.plan.intake.model.model='Born';
  wrongModel.plan_hash=publicationHash(wrongModel.plan);
  rejectScope(reviewed,wrongModel,ui,scope,now);
  const wrongAlias=structuredClone(fresh);
  wrongAlias.plan.expected_alias.brand_raw='OTHER';
  wrongAlias.plan_hash=publicationHash(wrongAlias.plan);
  rejectScope(reviewed,wrongAlias,ui,scope,now,/expected_alias/);
  const changedWorkbook=structuredClone(fresh);
  changedWorkbook.plan.intake.market.source.content_hash='0'.repeat(64);
  changedWorkbook.plan_hash=publicationHash(changedWorkbook.plan);
  rejectScope(reviewed,changedWorkbook,ui,scope,now,/workbook changed/);
  await assert.rejects(applyNewModelPlan({query(){assert.fail('Unexpected connection use');}},fresh.plan,fresh.plan_hash,now),/local PGlite/);

  const db=new PGlite();
  try {
    const {plan}=fresh;
    await seedCatalogFixture(db,fixture,[plan]);
    const initial=await publicationSnapshot(db);
    const publicInitial=await anonymousCatalogRows(db);
    const apply=()=>applyTavascanDriveRelease(db,fresh,reviewed,ui,scope,now);

    const prior=initial.canonical_model_variants.find(row=>row.canonical_model_id!==plan.expected_model.id);
    await db.query('UPDATE public.canonical_model_variants SET source_quote=$1 WHERE id=$2',['Synthetic baseline change',prior.id]);
    await assert.rejects(apply(),/Public catalog changed inside/);
    await db.query('UPDATE public.canonical_model_variants SET source_quote=$1 WHERE id=$2',[prior.source_quote,prior.id]);
    assert.deepEqual(await publicationSnapshot(db),initial);

    await db.exec(`CREATE FUNCTION fail_tavascan_release() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Synthetic late Tavascan failure'; END $$;
      CREATE TRIGGER fail_tavascan_release BEFORE UPDATE ON public.market_models
      FOR EACH ROW EXECUTE FUNCTION fail_tavascan_release();`);
    await assert.rejects(apply(),/Synthetic late Tavascan failure/);
    assert.deepEqual(await publicationSnapshot(db),initial);
    assert.deepEqual(await anonymousCatalogRows(db),publicInitial);
    await db.exec('DROP TRIGGER fail_tavascan_release ON public.market_models');

    const result=await apply();
    assert(result.committed&&result.variants_inserted===1&&result.anonymous_before_commit);
    const after=await anonymousCatalogRows(db);
    assert.equal(after.length,publicInitial.length+1);
    assert.deepEqual(after.filter(row=>variantKey(row)!==variant),publicInitial);
    await assert.rejects(apply(),/Public catalog changed inside/);
    const added=after.find(row=>variantKey(row)===variant);
    const attempt={approval:scope,fresh_plan_hash:fresh.plan_hash,baseline_sha256:reviewed.baseline_sha256,ui_sha256:publicationHash(ui)};
    const committed={approval:scope,fresh,reviewed,ui,baseline,result,committed_at:now.toISOString()};
    let exported, writes=0;
    const input={attempt,committed,now,approval:scope,publicRows:async()=>[...baseline,added],
      catalog:async()=>exported??{records:baseline},saveCatalog:async value=>{exported=value;writes++;}};
    await assert.rejects(exportTavascanCommit({...input,attempt:{...attempt,fresh_plan_hash:'0'.repeat(64)}}));
    await assert.rejects(exportTavascanCommit({...input,publicRows:async()=>[...baseline,{...added,price_sek:999999}]}));
    await assert.rejects(exportTavascanCommit({...input,publicRows:async()=>[...baseline,{...added,id:prior.id}]}),
      /Unexpected public Tavascan field: id/);
    assert.equal(writes,0);
    const distribution=await exportTavascanCommit(input);
    assert.equal(distribution.catalog_sha256,catalogHash(exported.records));
    await exportTavascanCommit(input);
    assert.equal(writes,1,'Export recovery must be idempotent');
    return {status:'tavascan_release_rehearsal_passed',scope_sha256:scope,variants:1,preserved:baseline.length,
      late_rollback:true,wrong_approval_and_scope_rejected:true,concurrent_catalog_rejected:true,
      anonymous_before_commit:true,export_recovery_passed:true,production_writes:0,paid_calls:0};
  } finally {await db.close();}
}
