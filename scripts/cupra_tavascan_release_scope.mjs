import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { ADAPTER, MODEL, VARIANT, policy, readDriveImage } from './cupra_tavascan_drive_publication.mjs';
import { catalogHash, compareCatalogs, normalizeCatalog, variantKey } from './sync_public_catalog.mjs';

export const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const hashPattern = /^[a-f0-9]{64}$/;
export const variant = variantKey({...MODEL, variant_name: VARIANT});
const scopedHash = rows => catalogHash(rows.map(row => ({...row,
  ...Object.fromEntries(['verified_at','price_verified_at'].filter(k => row[k]).map(k => [k,new Date(row[k]).toISOString()])),
})));
export const tavascanCatalogHash = scopedHash;
const expires = plan => Math.min(...[plan.intake.market.source,...plan.intake.sources].map(source=>Date.parse(source.fetched_at))) + 900000;
const omit = (value, fields) => JSON.parse(JSON.stringify(value,(key,entry)=>fields.includes(key)?undefined:entry));
const immutableIntake = intake => omit(intake,['fetched_at','content_hash','source_hash']);
const documents = intake => [intake.market.source,...intake.sources.filter(source=>source.source_type==='price_list_pdf')]
  .map(source=>omit(source,['fetched_at']));

export function assertTavascanPlan(plan) {
  assert.equal(plan.adapter,ADAPTER);
  assert.equal(plan.intake.adapter,ADAPTER);
  assert.deepEqual(plan.intake.model,MODEL);
  assert.equal(plan.expected_model.validation_status,'draft');
  assert.equal(plan.expected_alias.canonical_model_id,plan.expected_model.id);
  assert.equal(plan.expected_alias.needs_mapping,false);
  assert.equal(plan.expected_alias.alias_rule,policy.aliasRule);
  assert.equal(plan.targets.length,1);
  const [{id,draft}]=plan.targets;
  assert.match(id,/^[a-f0-9-]{36}$/);
  assert.equal(draft.variant_name,VARIANT);
  assert.deepEqual(draft,plan.intake.drafts[0]);
  const [{price_evidence}]=plan.intake.drafts;
  assert.equal(price_evidence.price_type,'list_price');
  assert.equal(price_evidence.source_url,policy.primaryUrl);
  policy.validateIntake(plan.intake);
  assert.deepEqual(plan.image,readDriveImage());
}

export function reviewApproval(reviewed, ui) {
  assertTavascanPlan(reviewed.plan);
  assert.equal(reviewed.plan_hash,digest(reviewed.plan));
  assert.deepEqual([reviewed.status,reviewed.production_writes,reviewed.publication_approved],['tavascan_drive_local_only_passed',0,false]);
  assert.equal(reviewed.candidate_count,reviewed.baseline_count+1);
  assert.match(reviewed.commit,/^[a-f0-9]{40}$/);
  for (const key of ['baseline_sha256','candidate_sha256','public_projection_sha256','capture_sha256']) assert.match(reviewed[key],hashPattern);
  assert.deepEqual([ui.status,ui.plan_hash,ui.candidate_sha256,ui.records,ui.production_writes,ui.publication_approved],
    ['private_ui_passed',reviewed.plan_hash,reviewed.candidate_sha256,reviewed.candidate_count,0,false]);
  assert(ui.real_built_catalog&&ui.real_image_files&&ui.exact_editorial_credit&&ui.full_photo_frame
    &&ui.mobile_layout_checked&&ui.retail_badges_removed&&ui.mobile_comparison_checked);
  assert.deepEqual(ui.runs.map(run=>run.width),[320,390,768,1440]);
  assert.deepEqual(ui.media.map(asset=>asset.url),[reviewed.plan.image.asset_url,...[480,800,1280].map(width=>
    reviewed.plan.image.asset_url.replace('/vehicles/','/responsive/').replace('.jpg',`-${width}.webp`))]);
  assert.equal(ui.media[0].sha256,reviewed.plan.image.content_sha256);
  for (const asset of ui.media) assert.match(asset.sha256,hashPattern);
  return digest({policy:ADAPTER,plan:reviewed.plan_hash,baseline:reviewed.baseline_sha256,
    projection:reviewed.public_projection_sha256,commit:reviewed.commit,capture:reviewed.capture_sha256,ui:digest(ui)});
}

export function proveTavascanRelease(reviewed, fresh, ui, approval, now) {
  assert.equal(approval,reviewApproval(reviewed,ui),'Invalid Tavascan release approval');
  assertTavascanPlan(fresh.plan);
  assert.equal(fresh.plan_hash,digest(fresh.plan),'Fresh Tavascan plan changed');
  assert.match(fresh.capture_sha256,hashPattern);
  assert.notEqual(fresh.capture_sha256,reviewed.capture_sha256,'Re-fetch official evidence for this release');
  const sourceWindow=expires(fresh.plan);
  assert(sourceWindow>now.getTime(),'Fresh Tavascan source window expired');
  for (const field of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources','image'])
    assert.deepEqual(fresh.plan[field],reviewed.plan[field],'Tavascan scope changed: '+field);
  assert.equal(fresh.plan.targets[0].id,reviewed.plan.targets[0].id,'Tavascan variant identity changed');
  assert.deepEqual(documents(fresh.plan.intake),documents(reviewed.plan.intake),'Swedish price PDF or market workbook changed');
  assert.deepEqual(immutableIntake(fresh.plan.intake),immutableIntake(reviewed.plan.intake),'Reviewed Swedish model evidence changed');
  return new Date(sourceWindow).toISOString();
}

export function verifyTavascanProjection(before, after, plan, baselineHash) {
  const base=normalizeCatalog(before), result=normalizeCatalog(after);
  assert.equal(scopedHash(base),baselineHash,'Catalog changed since Tavascan review');
  const delta=compareCatalogs(base,result);
  assert.deepEqual(delta.local_only,[]);
  assert.deepEqual(delta.changed,[]);
  assert.deepEqual(delta.remote_only,[variant],'Only the reviewed Tavascan variant may be added');
  const added=result.filter(row=>variantKey(row)===variant);
  policy.verifyPublic(added,plan);
  const [row]=added;
  const [{id,draft}]=plan.targets;
  const raw=after.find(item=>variantKey(item)===variant);
  if(Object.hasOwn(raw,'id')||Object.hasOwn(raw,'canonical_model_id')){
    assert.equal(raw.id,id,'Unexpected public Tavascan field: id');
    assert.equal(raw.canonical_model_id,plan.expected_model.id,'Unexpected public Tavascan field: canonical_model_id');
  }
  const source=plan.intake.sources.find(item=>item.final_url===policy.primaryUrl);
  const quote=[...new Set(Object.values(draft.field_evidence).map(item=>item.source_url+' | '+item.quote))].join(' | ');
  for (const [key,value] of Object.entries({
    brand:MODEL.brand,model:MODEL.model,body_type:MODEL.body_type,validation_status:'published',
    source_url:source.final_url,source_hash:source.content_hash,source_quote:quote,source_name:source.source_name,
    price_source_hash:source.content_hash,price_source_name:source.source_name,price_source_quote:draft.price_evidence.quote,
    price_valid_until:null,market_seen:true,extraction_confidence:draft.extraction_confidence,
    discontinued_candidate:plan.expected_model.discontinued_candidate,coming_or_low_volume:plan.expected_model.coming_or_low_volume,
  })) assert.equal(row[key],value,'Unexpected public Tavascan field: '+key);
  assert.equal(Date.parse(row.price_verified_at),Date.parse(source.fetched_at));
  return result;
}
