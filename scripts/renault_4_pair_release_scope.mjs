import assert from 'node:assert/strict';
import { ADAPTER, policy, renault4LocatorRow } from './renault_4_pair_publication.mjs';
import { publicationHash, validateNewModelIntake } from './new_model_publication.mjs';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';
import { catalogHash } from './sync_public_catalog.mjs';
import { vehicleSlug } from '../src/vehicle-names.js';

const sha = /^[a-f0-9]{64}$/;
const times = intake => [...intake.sources,intake.market.source].map(row=>Date.parse(row.fetched_at));
const strip = (value,keys) => JSON.parse(JSON.stringify(value,(key,entry)=>keys.includes(key)?undefined:entry));

export function renault4PairReview(plan,readback,baseline) {
  assert.equal(plan.adapter,ADAPTER);
  assert.equal(plan.targets.length,2);
  assert.equal(readback.status,'source_setup_and_pair_passed_local_only');
  assert.equal(readback.publication_approved,false);
  assert.equal(readback.production_writes,0);
  assert.equal(readback.paired_late_rollback,true);
  assert.equal(readback.prior_catalog_preserved,true);
  assert.match(readback.commit,/^[a-f0-9]{40}$/);
  assert.match(readback.baseline_sha256,sha);
  assert.match(readback.candidate_sha256,sha);
  assert.equal(readback.candidate_count,readback.baseline_count+2);
  assert.equal(baseline.length,readback.baseline_count);
  assert.equal(catalogHash(baseline),readback.baseline_sha256);
  assert.equal(catalogHash(catalogWithComparableTimes([...baseline,...readback.added_variants])),readback.candidate_sha256);
  assertRenault4PairPublishedRows(readback.added_variants,plan);
  return {
    plan,plan_hash:publicationHash(plan),commit:readback.commit,
    baseline_hash:readback.baseline_sha256,baseline_count:readback.baseline_count,
    database_baseline_hash:catalogHash(catalogWithComparableTimes(baseline)),
    candidate_hash:readback.candidate_sha256
  };
}

export function renault4PairApproval(reviewed,ui) {
  assert.equal(reviewed.plan_hash,publicationHash(reviewed.plan),'Reviewed Renault 4 plan changed');
  assert.equal(ui.status,'private_pair_ui_passed');
  assert.equal(ui.commit,reviewed.commit);
  assert.equal(ui.candidate_sha256,reviewed.candidate_hash);
  assert.equal(ui.records,reviewed.baseline_count+2);
  assert.equal(ui.production_writes,0);
  assert.equal(ui.paid_calls,0);
  assert.equal(ui.publication_approved,false);
  assert.equal(ui.static_catalog_and_media,true);
  assert.equal(ui.mobile_comparison,true);
  assert.equal(ui.media.length,4);
  assert.deepEqual(ui.media[0],{url:reviewed.plan.image.asset_url,sha256:reviewed.plan.image.content_sha256});
  for(const [index,width] of [480,800,1280].entries()){
    assert.equal(ui.media[index+1].url,ui.media[0].url.replace('/vehicles/','/responsive/').replace(/\.jpg$/,`-${width}.webp`));
    assert.match(ui.media[index+1].sha256,sha);
  }
  const slugs=reviewed.plan.targets.map(({draft})=>vehicleSlug('Renault','4',draft.variant_name));
  assert.deepEqual(ui.runs.map(row=>row.width+':'+row.slug).sort(),
    [320,390,768,1440].flatMap(width=>slugs.map(slug=>width+':'+slug)).sort());
  assert.deepEqual(ui.comparisons.map(({width,variants,range_cells,horizontal_scroll})=>({width,variants,range_cells,horizontal_scroll})),
    [320,390,1440].map(width=>({width,variants:reviewed.plan.targets.map(({draft})=>'Renault 4 '+draft.variant_name),
      range_cells:reviewed.plan.targets.map(({draft})=>draft.facts.wltp_range_km+' km'),horizontal_scroll:width<700})));
  return publicationHash({reviewed,ui});
}

export function proveRenault4PairRelease(reviewed,fresh,ui,approval,now=new Date()) {
  assert.equal(approval,renault4PairApproval(reviewed,ui),'Require the exact approved Renault 4 pair hash');
  assert.equal(fresh.plan_hash,publicationHash(fresh.plan),'Fresh Renault 4 scope changed');
  const {plan} = fresh;
  assert.equal(plan.adapter,ADAPTER);
  assert.equal(plan.intake.adapter,ADAPTER);
  assert.equal(plan.targets.length,2);
  assert.equal(plan.expected_model.validation_status,'draft');
  assert(Math.min(...times(plan.intake))>Math.max(...times(reviewed.plan.intake)),
    'Capture both Renault 4 grades again after the reviewed capture');
  validateNewModelIntake(plan.intake,now);
  for(const key of ['expected_model','expected_alias','expected_market','expected_monthly','expected_sources','image']){
    assert.deepEqual(plan[key],reviewed.plan[key],'Reviewed Renault 4 scope changed: '+key);
  }
  assert.deepEqual(strip(plan.intake.market,['fetched_at']),strip(reviewed.plan.intake.market,['fetched_at']),
    'Reviewed Mobility Sweden workbook changed');
  const price = v => v.intake.sources.find(source=>source.final_url===policy.primaryUrl);
  assert.deepEqual(strip(price(plan),['fetched_at']),strip(price(reviewed.plan),['fetched_at']),
    'Reviewed Renault 4 price list changed');
  const volatile=['fetched_at','content_hash','source_hash'];
  for(const key of ['intake','targets']){
    assert.deepEqual(strip(plan[key],volatile),strip(reviewed.plan[key],volatile),'Renault 4 facts or evidence changed: '+key);
  }
  const source=plan.intake.sources.find(row=>row.shared);
  const locator=renault4LocatorRow(source);
  const existing=plan.expected_sources.filter(row=>row.url===source.final_url);
  assert(existing.length<=1);
  if(existing.length) for(const [key,value] of Object.entries(locator))
    assert.equal(existing[0][key],value,'Existing Renault locator differs: '+key);
}

export function assertRenault4PairPublishedRows(rows,plan,{requireIds=true}={}) {
  assert.equal(plan.adapter,ADAPTER);
  assert.equal(plan.targets.length,2);
  policy.verifyPublic(rows,plan);
  const primary=plan.intake.sources.find(source=>source.final_url===policy.primaryUrl);
  for(const {id,draft} of plan.targets){
    const row=rows.find(row=>requireIds?row.id===id:row.variant_name===draft.variant_name);
    assert(row);
    const {price_evidence:price} = draft;
    const priceSource=plan.intake.sources.find(source=>source.final_url===price.source_url);
    const sourceQuote=[...new Set(Object.values(draft.field_evidence).map(p=>p.source_url+' | '+p.quote))].join(' | ');
    const expected={...(requireIds?{canonical_model_id:plan.expected_model.id}:{}),
      brand:'Renault',model:'4',body_type:plan.intake.model.body_type,
      variant_name:draft.variant_name,...draft.facts,validation_status:'published',extraction_confidence:draft.extraction_confidence,
      source_url:primary.final_url,source_hash:primary.content_hash,source_quote:sourceQuote,
      price_sek:price.value,price_type:'list_price',price_source_url:price.source_url,price_source_hash:price.source_hash,
      price_valid_until:null,price_source_name:priceSource.source_name,price_source_quote:price.quote,market_seen:true,
      ...Object.fromEntries(['available_confirmed','coming_or_low_volume','discontinued_candidate']
        .map(key=>[key,plan.expected_model[key]]))};
    for(const [key,value] of Object.entries(expected)) assert.equal(row[key],value,'Unexpected public Renault 4 field: '+key);
    assert.equal(Date.parse(row.price_verified_at),Date.parse(priceSource.fetched_at));
  }
}
