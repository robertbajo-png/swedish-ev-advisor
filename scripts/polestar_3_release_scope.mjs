import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, realpath } from 'node:fs/promises';
import { join } from 'node:path';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';
import { publicationHash, validateNewModelIntake } from './new_model_publication.mjs';
import { ADAPTER, MODEL, policy, readPolestar3Image } from './polestar_3_publication.mjs';
import { catalogHash, compareCatalogs, variantKey } from './sync_public_catalog.mjs';
import { specQualifications } from '../src/spec-qualifications.js';

const sha = /^[a-f0-9]{64}$/;
const revision = /^[a-f0-9]{40}$/;
const key = variantKey({...MODEL,variant_name:'Performance'});
const isP3 = row=>row.brand.toLowerCase()==='polestar'&&row.model.toLowerCase()==='3';
const compareHash = rows=>catalogHash(catalogWithComparableTimes(rows));
const stable = value=>JSON.parse(JSON.stringify(value,(field,item)=>
  ['fetched_at','source_hash','content_hash'].includes(field)?undefined:item));
const captureTimes = plan=>[...plan.intake.sources,plan.intake.market.source,plan.intake.market.article]
  .map(row=>Date.parse(row.fetched_at));

export function polestar3Media(photo) {
  assert.equal(photo.model_key,'polestar|3');
  assert.equal(photo.asset_url,'/media/vehicles/polestar-3-press-450c917205da.jpg');
  return [
    {url:photo.asset_url,sha256:photo.content_sha256},
    {url:'/media/responsive/polestar-3-press-450c917205da-746.webp',
      sha256:'c4423dc606812862886358d167f3b313d9aff0521a31d8f8d9a9c409ba4cc877'},
    {url:'/media/responsive/polestar-3-press-450c917205da-1782.webp',
      sha256:'8892e7843d3a75339289fc3eef7055561eeba218b928b6a8c2b751697e572ee7'},
  ];
}

export function validatePolestar3Delta(baseline,candidate,plan) {
  assert.equal(plan.adapter,ADAPTER);
  assert.equal(plan.targets.length,1);
  assert(!baseline.some(isP3),'An existing Polestar 3 requires a refresh instead');
  const additions=candidate.filter(isP3);
  policy.verifyPublic(additions,plan);
  const [row]=additions;
  const {id,draft}=plan.targets[0];
  assert.equal(variantKey(row),key);
  if(Object.hasOwn(row,'id')) assert.equal(row.id,id,'Unexpected Polestar variant ID');
  if(Object.hasOwn(row,'canonical_model_id')) assert.equal(row.canonical_model_id,plan.expected_model.id,'Unexpected Polestar model ID');
  assert.equal(row.source_hash,plan.intake.sources.find(source=>source.final_url===policy.primaryUrl).content_hash);
  assert.equal(row.price_source_quote,draft.price_evidence.quote);
  assert.equal(row.source_quote,[...new Set(Object.values(draft.field_evidence).map(e=>e.source_url+' | '+e.quote))].join(' | '));
  assert.equal(row.extraction_confidence,draft.extraction_confidence);
  for(const flag of ['discontinued_candidate','coming_or_low_volume']) assert.equal(row[flag],plan.expected_model[flag]);
  const {rangeMinimum,rangeInterval,consumptionInterval,rangeIsTarget}=specQualifications(row);
  assert.deepEqual([rangeMinimum,rangeInterval,consumptionInterval,rangeIsTarget],
    [524,'524\u2013601 km','20,5\u201323,1 kWh/100 km',false],'Require the certified combined range and consumption intervals');
  assert.equal(candidate.length,baseline.length+1);
  assert.equal(new Set(candidate.map(variantKey)).size,candidate.length);
  assert(compareCatalogs(catalogWithComparableTimes(baseline),catalogWithComparableTimes(candidate.filter(row=>!isP3(row)))).ok,
    'The Polestar addition changed an existing catalog record');
  return {preserved:baseline.length,added:1,database_baseline_sha256:compareHash(baseline)};
}

export function preparePolestar3ReleaseReview({report,plan,ui,baseline,candidate}) {
  assert.deepEqual([report.status,report.variants,report.technical_fields,report.publication_approved,report.production_writes],
    ['polestar_3_local_insertion_verified',1,9,false,0]);
  assert(report.anonymous_before_commit&&report.exact_replay_noop&&report.late_rollback);
  assert.match(report.commit,revision);
  assert.equal(publicationHash(plan),report.plan_sha256);
  assert.equal(catalogHash(baseline),report.baseline_sha256);
  assert.equal(catalogHash(candidate),report.candidate_sha256);
  assert.deepEqual([report.baseline_count,report.candidate_count],[baseline.length,candidate.length]);
  assert.deepEqual([ui.status,ui.source_commit,ui.plan_sha256,ui.candidate_sha256,ui.exact_main_code,ui.production_writes,ui.publication_approved],
    ['polestar_3_private_ui_verified',report.commit,report.plan_sha256,report.candidate_sha256,true,0,false]);
  assert.equal(ui.photo_sha256,plan.image.content_sha256);
  assert.match(ui.native_media_evidence,sha);
  assert.deepEqual(ui.media,polestar3Media(plan.image));
  assert.deepEqual(ui.checks.map(check=>check.width),[390,1440]);
  assert.deepEqual(ui.checks.map(check=>check.image),ui.media.slice(1).map(asset=>asset.url));
  assert(ui.checks.every(check=>check.exact_image&&check.certified_interval&&check.no_overflow));
  const delta=validatePolestar3Delta(baseline,candidate,plan);
  return {plan,ui,commit:report.commit,baseline_sha256:report.baseline_sha256,candidate_sha256:report.candidate_sha256,...delta};
}

export const polestar3ApprovalHash = reviewed=>publicationHash(reviewed);

export function proveFreshPolestar3Release(reviewed,fresh,approval,now=new Date()) {
  assert.equal(approval,polestar3ApprovalHash(reviewed),'Require the exact reviewed Polestar scope');
  const {plan}=fresh;
  assert.equal(fresh.plan_hash,publicationHash(plan),'Fresh Polestar plan changed');
  assert.equal(plan.adapter,ADAPTER);
  assert.equal(plan.expected_model.validation_status,'draft');
  assert.match(reviewed.commit,revision);
  assert.match(reviewed.database_baseline_sha256,sha);
  assert.deepEqual(plan.image,readPolestar3Image());
  validateNewModelIntake(plan.intake,now);
  assert(Math.min(...captureTimes(plan))>Math.max(...captureTimes(reviewed.plan)),'Re-fetch all sources after review');
  for(const field of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources','image']) {
    assert.deepEqual(plan[field],reviewed.plan[field],'Reviewed Polestar scope changed: '+field);
  }
  assert.equal(plan.intake.market.source.content_hash,reviewed.plan.intake.market.source.content_hash,'Mobility Sweden workbook changed');
  for(const field of ['intake','targets']) assert.deepEqual(stable(plan[field]),stable(reviewed.plan[field]),'Reviewed Polestar evidence changed: '+field);
}

export async function verifyRegisteredPolestar3Media(root,photo,ui) {
  const read = async file=>{
    const path=join(root,file);
    assert.equal(await realpath(path),path,'Require a real registered media path');
    return readFile(path);
  };
  const json=async file=>JSON.parse(await read(file));
  assert.equal((await json('src/model-images.json'))[photo.model_key],photo.asset_url);
  const view=(await json('src/image-presentation.json')).models[photo.model_key];
  assert.deepEqual([view.asset_url,view.content_sha256,view.status,view.object_fit],
    [photo.asset_url,photo.content_sha256,'approved','contain']);
  const rights=(await json('src/image-rights.json')).assets.filter(row=>row.model_key===photo.model_key);
  assert.deepEqual(rights,[{...photo,changes:'Originalfilen har inte redigerats.'}]);
  const entry=(await json('src/image-variants.json'))[photo.asset_url];
  assert.deepEqual([entry.width,entry.height,entry.source_sha256],[12302,9227,photo.content_sha256]);
  assert.deepEqual(entry.variants.map(asset=>asset.width),[746,1782]);
  const files=[{url:photo.asset_url,sha256:photo.content_sha256},...entry.variants.map(({url,sha256})=>({url,sha256}))];
  assert.deepEqual(files,polestar3Media(photo),'Preserve the publisher-supplied native image sizes');
  assert.deepEqual(files,ui.media,'Registered Polestar media changed since the browser proof');
  for(const file of files) assert.equal(createHash('sha256').update(await read('public'+file.url)).digest('hex'),file.sha256);
}
