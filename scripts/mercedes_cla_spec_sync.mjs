import assert from 'node:assert/strict';
import { applySpecPlan as apply, buildSpecPlan as build, specPlanHash, TECHNICAL_FIELDS } from './kia_spec_sync.mjs';
export { specPlanHash };
export const ADAPTER = 'mercedes_cla_sweden_browser_specs_v1';
const url = 'https://www.mercedes-benz.se/passengercars/models/saloon/cla-electric/overview.html';
const stockUrl = 'https://www.hoglundsbil.se/bilar?sort=0';
const authUrl = 'https://www.hoglundsbil.mercedes-benz.se/passengercars/startpage.html';
const qualifier = 'Detta värde kan avvika beroende på vilken utrustning som valts.';
const rows = [
  ['CLA 200', '19043773', 559000, 528, 12.7, 58, 200, 1500, 'RWD', 'mercedes-benz-cla-200-advanced-edition-2-95-ranta'],
  ['CLA 250+', '19003980', 599000, 772, 12.6, 85, 320, 1500, 'RWD', 'mercedes-benz-cla-250-advanced-edition-2-95-ranta-3'],
  ['CLA 350 4MATIC', '19004063', 639000, 751, 13.1, 85, 320, 1800, 'AWD', 'mercedes-benz-cla-350-4matic-advanced-edition-2-95-ranta'],
];
const priceFields = ['price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote',
  'price_verified_at','price_source_name','price_refresh_batch_id'];
const number = s => Number(s.replaceAll(' ', '').replace(',', '.'));
const fresh = (s, now) => {
  assert.match(s.content_hash, /^[a-f0-9]{64}$/);
  const age = now - Date.parse(s.fetched_at);
  assert(Number.isFinite(age) && age >= -60000 && age <= 900000, 'Fresh source evidence required');
};
const scope = r => rows.find(s => [s[0]+' Advanced Edition MY2027 (lagerbil)',s[0]+' Advanced Edition MY2027 (beställningsbil)'].includes(r.variant_name));

export function validateSpecDraft(r, now = new Date()) {
  assert.equal(r.adapter, ADAPTER); assert.equal(r.brand, 'Mercedes-Benz'); assert.equal(r.model, 'Cla');
  const s = scope(r); assert(s, 'One of the three exact existing offers required');
  const [header, id, cash, range, consumption, battery, dc, tow, drive, slug] = s;
  assert.equal(r.replacement_variant_name, header+' Advanced Edition MY2027 (beställningsbil)');
  assert.equal(r.source_resolution, 'owner_2026_11_13_exact_version_current_sources');
  assert(r.extraction_confidence >= 0.92 && r.extraction_confidence <= 1);
  assert.equal(r.source.final_url, url); assert.equal(r.source.status, 'browser_reachable');
  assert.equal(r.source.http_status, null); assert.equal(r.source.retrieval_method, 'connected_browser_dom');
  assert.equal(r.source.hash_basis, 'normalized_named_technical_dialog_and_identity_v1'); fresh(r.source, now);
  assert.deepEqual(r.supporting_sources, []); assert.deepEqual(r.held_fields, {});
  assert.deepEqual(Object.keys(r.facts).sort(), [...TECHNICAL_FIELDS, 'ac_charge_kw'].sort());
  assert.deepEqual(r.facts, {wltp_range_km:range,wltp_consumption_kwh_100km:consumption,battery_kwh:battery,
    dc_charge_kw:dc,ac_charge_kw:11,boot_liters:405,seats:5,tow_kg:tow,drivetrain:drive});
  assert.deepEqual(Object.keys(r.field_evidence).sort(), Object.keys(r.facts).sort());
  const labels = {wltp_range_km:'Elektrisk räckvidd, blandad körning',
    wltp_consumption_kwh_100km:'Förbrukning blandad körning',battery_kwh:'Användbart energiinnehåll batteri',
    dc_charge_kw:'Maximal laddeffekt DC'+qualifier,ac_charge_kw:'Maximal laddeffekt AC'+qualifier,
    boot_liters:'BagageutrymmesvolymBagageutrymmesvolymen kan avvika beroende på tillval.',seats:'Sittplatser',
    tow_kg:'Tillåten släpvagnsvikt (bromsad släpvagn vid 12 %)'+qualifier,drivetrain:'Drivlina'};
  const units = {wltp_range_km:'km',wltp_consumption_kwh_100km:'kWh/100km',battery_kwh:'kWh',dc_charge_kw:'kW',ac_charge_kw:'kW',boot_liters:'l'};
  for (const [field, value] of Object.entries(r.facts)) {
    const p = r.field_evidence[field]; assert.equal(p.value, value); assert.equal(p.variant_name, r.variant_name);
    assert.equal(p.column_header, header); assert.equal(p.source_url, url); assert.equal(p.source_hash, r.source.content_hash);
    const prefix = header+' | '+labels[field]+' | '; assert(p.quote.startsWith(prefix)); const raw = p.quote.slice(prefix.length);
    if (field === 'tow_kg') {
      assert.equal(p.scope, 'maximum_braked_towing_with_required_equipment');
      const m = /^750 kg \(([0-9 ]+) kg\)$/.exec(raw); assert(m); assert.equal(number(m[1]), value);
    } else {
      assert.equal(p.scope, 'swedish_c174_exact_powertrain_column');
      if (field === 'drivetrain') assert.equal(raw, drive === 'AWD' ? 'Fyrhjulsdrift' : 'Bakhjulsdrift');
      else {
        const suffix = units[field] ? ' '+units[field] : ''; assert(raw.endsWith(suffix));
        assert.equal(number(suffix ? raw.slice(0,-suffix.length) : raw), value);
        const bound = {wltp_range_km:[50,1200],wltp_consumption_kwh_100km:[5,50],battery_kwh:[10,250],dc_charge_kw:[20,600],ac_charge_kw:[1,50],boot_liters:[50,3500],seats:[1,9]}[field];
        assert(Number.isFinite(value) && value >= bound[0] && value <= bound[1]);
      }
    }
  }
  const p = r.price_evidence; assert.equal(p.value, cash); assert.equal(p.price_type, 'dealer_offer'); assert.equal(p.price_valid_until, null);
  assert.equal(p.source_url, stockUrl); assert.match(p.source_hash, /^[a-f0-9]{64}$/);
  const stock = JSON.parse(p.quote); assert.deepEqual(stock,p.stock_identity);
  assert.equal(stock.car_id,id); assert.equal(stock.year,2027); assert.equal(stock.noveltyType,'new_car');
  assert.equal(stock.mileage,0); assert.equal(stock.fuel_type_name,'El'); assert.equal(stock.body_type_name,'Sedan');
  assert.equal(stock.price,cash); assert.equal(stock.car_exkl_moms,cash*4/5); assert.equal(stock.sale_price,'');
  assert.equal(p.classification,'exact_current_swedish_order_offer_cash_inclusive_vat');
  assert.equal(p.authorization_review.url,authUrl); assert.match(p.authorization_review.supporting_hash,/^[a-f0-9]{64}$/);
  fresh({fetched_at:p.authorization_review.fetched_at,content_hash:p.authorization_review.supporting_hash},now);
  assert.equal(p.order_source.status,'reachable'); assert.equal(p.order_source.http_status,200); fresh(p.order_source,now);
  assert.equal(p.order_source.final_url,'https://www.hoglundsbil.se/bil/'+slug);
  assert.equal(p.order_quote,'Denna bil är en beställningsbil och finns ej på plats hos oss - kontakta en säljare för mer information.');
  assert.deepEqual(r.model_facts,{body_type:'Sedan'});
  const body = r.model_field_evidence.body_type; assert.equal(body.value,'Sedan');
  assert.equal(body.source_url,p.order_source.final_url); assert.equal(body.source_hash,p.order_source.content_hash);
  assert.equal(body.quote,header+' Advanced Edition MY2027 | Kaross Sedan | Bränsle El');
  assert(r.source_decisions.length>=7);
  return r;
}

const extras = (r, old) => {
  assert.equal(Number(old.price_sek),r.price_evidence.value); assert.equal(old.price_type,'dealer_offer'); assert(!old.price_valid_until);
  return {variant_name:r.replacement_variant_name,price_type:'dealer_offer',price_valid_until:null,
    price_source_url:r.price_evidence.source_url,price_source_hash:r.price_evidence.source_hash,
    price_source_quote:r.price_evidence.quote,price_source_name:'Höglunds Bil',
    price_verified_at:new Date(r.price_evidence.order_source.fetched_at).toISOString(),
    price_refresh_batch_id:specPlanHash({adapter:ADAPTER,price_evidence:r.price_evidence})};
};
const policy = {adapter:ADAPTER,validate:validateSpecDraft,sourceType:'manufacturer_model_page',sourceName:'Mercedes-Benz Sverige',
  sourceTitle:()=>'CLA C174 svenska tekniska uppgifter (webbläsarverifierad originaltabell)',lockKey:7240016,
  extraFields:['ac_charge_kw'],allowedBodyTypes:['Sedan'],modelFacts:r=>r.model_facts,
  browserSource:r=>r.source.final_url===url && r.source.retrieval_method==='connected_browser_dom',
  canonicalFields:[...priceFields,'variant_name'],canonicalExtras:extras,
  replacementVariantName:(_old,r)=>r.replacement_variant_name,
  priceRefresh:(old,r)=>Number(old.price_sek)===r.price_evidence.value && old.price_type==='dealer_offer' && !old.price_valid_until};
export const buildSpecPlan = (rows,intake,now) => {
  const p = build(rows,intake,now,policy); assert.equal(p.targets.length,3,'All three CLA offers must be reconciled together');
  for (const t of p.targets) extras(t.draft,t.expected); return p;
};
export const applySpecPlan = (client,plan,hash,now) => apply(client,plan,hash,now,policy);
export const intakeFingerprint = intake => intake.drafts.map(r=>JSON.parse(JSON.stringify(r,
  (key,value)=>['content_hash','source_hash','supporting_hash','fetched_at'].includes(key)?undefined:value)));
