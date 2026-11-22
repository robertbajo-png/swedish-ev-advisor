import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { evolutionIntakeFromReplay, policy as evolution } from './renault_4_evolution_publication.mjs';

export const ADAPTER = 'renault_4_evolution_techno_sweden_local_v1';
const name = 'Techno EV52';
const versionId = '63132d5d-7c23-44cc-9606-f9dd4c2e50e2';
const stockFile = 'hedin-techno-18.html';
const dealer = 'https://hedinautomotive.se/bilar/kop-bil/258900/pc-nc-renault-4-e-tech-2026';
const versions = 'https://www.renault.se/personbilar/elbilar/r4-e-tech-electric/versioner-och-priser';
const facts = {wltp_range_km:398,wltp_consumption_kwh_100km:15.5,battery_kwh:52,dc_charge_kw:100,
  ac_charge_kw:11,boot_liters:420,tow_kg:750,seats:5,drivetrain:'FWD'};
const factUrls = {...Object.fromEntries(Object.keys(facts).map(key => [key,evolution.primaryUrl])),
  wltp_range_km:dealer,wltp_consumption_kwh_100km:dealer,drivetrain:dealer,dc_charge_kw:versions};
const root = fileURLToPath(new URL('..',import.meta.url));

export function renault4LocatorRow(source) {
  assert.equal(source.final_url,'https://www.renault.se/om-oss/aterforsaljare');
  assert.equal(source.shared,true);
  assert.equal(source.source_type,'manufacturer_model_page');
  assert.equal(source.source_authority,'manufacturer');
  assert.equal(source.authorization_evidence_url,null);
  return {canonical_model_id:null,brand:'Renault',model:'*',url:source.final_url,
    final_url:source.final_url,source_type:source.source_type,content_hash:source.content_hash,country:'SE',language:'sv',
    http_status:200,source_authority:'manufacturer',source_validation:'reachable_official_model_source',
    authorization_evidence_url:null,is_primary:false};
}

export function readPairCapture(path) {
  const r = JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs','scripts/renault_4_review.py',
    '--replay',resolve(path),'--emit-pair'],{cwd:root,encoding:'utf8',timeout:120000,maxBuffer:300000,windowsHide:true}));
  const t = r.techno_candidate;
  assert.equal(r.review_format,5);
  assert.equal(r.publication_approved,false);
  assert.equal(t.status,'private_techno_candidate');
  assert.equal(t.publication_approved,false);
  const {intake,now} = evolutionIntakeFromReplay(r.evolution_candidate);
  assert.equal(now.toISOString(),new Date(r.captured_at).toISOString());
  const {url,sha256:content_hash} = r.sources[stockFile];
  const authority = intake.sources.find(s => s.shared);
  assert.equal(url,dealer);
  const field_evidence = Object.fromEntries(Object.entries(t.fields).map(([key,p]) => [key,{...p,variant_name:name}]));
  return {now,intake:{...intake,adapter:ADAPTER,
    sources:[...intake.sources,{final_url:dealer,content_hash,source_type:'authorized_dealer_stock_page',
      source_name:'Hedin Automotive Helsingborg',country:'SE',language:'sv',status:'reachable',http_status:200,
      fetched_at:r.fetched_at[stockFile],shared:false,source_authority:'authorized_dealer',authorization_evidence_url:authority.final_url}],
    drafts:[...intake.drafts,{variant_name:name,manufacturer_identity:t.manufacturer_version_id+'/EV52/MY26',
      identity_evidence:{model_year:t.model_year,wheel_evidence:t.wheel_evidence,appointment:t.stock_authorization},
      extraction_confidence:0.99,facts:Object.fromEntries(Object.entries(field_evidence).map(([key,p])=>[key,p.value])),
      field_evidence,price_evidence:{...t.price,price_valid_until:null}}],
    source_decisions:{evolution:intake.source_decisions,techno:{range_alternative:t.range_alternative,selection_reason:t.selection_reason}}}};
}

export const policy = {...evolution,adapter:ADAPTER,maxVariants:2,
  validateIntake(intake) {
    assert.equal(intake.drafts.length,2,'The local pair requires Evolution and Techno');
    const [evo,techno] = intake.drafts;
    const base = intake.sources.filter(s=>s.final_url!==dealer);
    evolution.validateIntake({...intake,adapter:evolution.adapter,sources:base,drafts:[evo]});
    const source = intake.sources.find(s=>s.final_url===dealer), authority = base.find(s=>s.shared);
    assert.equal(intake.sources.length,base.length+1);
    assert.equal(source.source_type,'authorized_dealer_stock_page');
    assert.equal(source.source_authority,'authorized_dealer');
    assert.equal(source.authorization_evidence_url,authority.final_url);
    assert.equal(source.shared,false);
    assert.deepEqual([source.country,source.language],['SE','sv']);
    assert.equal(techno.variant_name,name);
    assert.equal(techno.manufacturer_identity,versionId+'/EV52/MY26');
    assert.equal(techno.identity_evidence.model_year,2026);
    assert.deepEqual(techno.facts,facts);
    const prove = (p,url,value) => {
      assert.equal(p?.value,value);
      assert.equal(p.source_url,url);
      assert.equal(p.source_hash,intake.sources.find(s=>s.final_url===url)?.content_hash);
      assert(p.quote?.trim().length>5);
    };
    for (const [field,url] of Object.entries(factUrls)) prove(techno.field_evidence[field],url,facts[field]);
    prove(techno.identity_evidence.wheel_evidence,dealer,18);
    prove(techno.identity_evidence.appointment,authority.final_url,'Hedin Automotive Helsingborg');
    prove(techno.price_evidence,evolution.primaryUrl,434900);
    assert.equal(techno.price_evidence.price_type,'list_price');
    assert.equal(techno.price_evidence.price_valid_until,null);
  },
  verifyPublic(rows,plan) {
    assert.equal(rows.length,2);
    const [t] = rows.filter(r=>r.variant_name===name);
    assert(t,'Missing public Techno');
    evolution.verifyPublic(rows.filter(r=>r.variant_name!==name),plan);
    for(const [field,value] of Object.entries(facts)) assert.equal(t[field],value,field);
    assert.equal(t.price_sek,434900);
    assert.equal(t.price_type,'list_price');
    assert.equal(t.price_source_url,evolution.primaryUrl);
    assert.equal(t.price_source_hash,plan.intake.drafts[1].price_evidence.source_hash);
    assert.equal(t.image_url,plan.image.asset_url);
    assert.equal(t.image_source_url,plan.image.source_url);
    assert.equal(t.available_confirmed,plan.expected_model.available_confirmed);
  },
};
