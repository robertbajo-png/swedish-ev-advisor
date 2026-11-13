import assert from 'node:assert/strict';
import { applySpecPlan as apply, buildSpecPlan as build, specPlanHash } from './kia_spec_sync.mjs';
export { specPlanHash };
export const ADAPTER = 'skoda_sweden_model_page_v1';
const scopes = {
  Elroq: ['60 Selection Explore Edition', '60 Sportline Explore Edition', '85 Selection Explore Edition',
    '85 Sportline Explore Edition', '85x Selection Explore Edition', '85x Sportline Explore Edition', 'RS Explore Edition'],
  Enyaq: ['Solid Edition 85', 'Solid Edition 85x', 'Solid Edition 85x Sportline', 'Solid Edition RS'],
};
const technicalRelease = 'https://www.skoda.se/nyheter-och-pressklipp/nyhet/skoda-uppdaterar-elroq-och-enyaq-infor-modellar-2027';
const priceSources = { Elroq: 'https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb',
  Enyaq: 'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660' };
const resolution = 'owner_2026_11_13_exact_current_edition_faq_over_estimated_price_list';
const oldRsSource = 'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660';
const clean = text => text.replace(/\s+([:.,])/g, '$1');
const engine = row => row.variant_name.includes('RS') ? 'RS' : row.variant_name.includes('85x') ? '85x' : row.variant_name.includes('60') ? '60' : '85';
const rangeLabel = row => row.model === 'Elroq'
  ? row.variant_name.includes('Sportline') ? 'Elroq Sportline ' + engine(row) : 'Elroq ' + (['85', '85x'].includes(engine(row)) ? '85 och 85x' : engine(row))
  : row.variant_name.includes('Sportline') ? 'Enyaq 85x Sportline' : engine(row) === 'RS' ? 'Enyaq RS' : 'Enyaq 85 och Enyaq 85x';
const towLabel = row => row.model === 'Elroq' ? engine(row) === '60' ? 'Elroq 60' : 'Elroq 85, 85x och RS'
  : engine(row) === 'RS' ? 'Enyaq RS' : 'Enyaq 85, 85x och 85x Sportline';
function fresh(source, now) {
  assert.equal(source.status, 'reachable'); assert.equal(source.http_status, 200);
  assert.match(source.content_hash, /^[a-f0-9]{64}$/);
  const age = now.getTime() - Date.parse(source.fetched_at);
  assert(Number.isFinite(age) && age >= -60000 && age <= 900000, 'Fresh manufacturer source required');
}

export function validateSpecDraft(row, now = new Date()) {
  assert.equal(row.adapter, ADAPTER); assert.equal(row.brand, 'Skoda');
  assert(scopes[row.model]?.includes(row.variant_name), 'Exact current edition required');
  assert(row.extraction_confidence >= 0.92 && row.extraction_confidence <= 1);
  const source = row.source;
  fresh(source, now);
  assert.equal(source.final_url, `https://www.skoda.se/modeller/${row.model.toLowerCase()}/${row.model.toLowerCase()}`);
  assert.equal(row.source_resolution, resolution);
  if (row.model_facts) {
    assert.deepEqual(row.model_facts, { body_type: 'SUV' });
    const proof = row.model_field_evidence.body_type;
    assert.equal(proof.value, 'SUV'); assert.equal(proof.scope, 'exact_model_description');
    assert.equal(proof.source_url, source.final_url); assert.equal(proof.source_hash, source.content_hash);
    assert(proof.quote.startsWith('Upptäck Škoda ' + row.model + ', ') && proof.quote.includes('el-SUV'));
  }
  const sources = new Map([[source.final_url, source.content_hash]]);
  assert([1, 2].includes(row.supporting_sources?.length));
  assert.equal(new Set(row.supporting_sources.map(item => item.final_url)).size, row.supporting_sources.length);
  for (const extra of row.supporting_sources) {
    assert([technicalRelease, priceSources[row.model]].includes(extra.final_url)); fresh(extra, now);
    sources.set(extra.final_url, extra.content_hash);
  }
  assert.deepEqual(Object.keys(row.field_evidence).sort(), Object.keys(row.facts).sort());
  assert(Object.keys(row.facts).length > 0);
  for (const field of ['wltp_range_km', 'dc_charge_kw', 'boot_liters', 'tow_kg', 'ac_charge_kw', 'battery_kwh', 'drivetrain'])
    assert(Object.hasOwn(row.facts, field), 'A complete technical profile is required');
  for (const [field, value] of Object.entries(row.facts)) {
    assert(['boot_liters', 'battery_kwh', 'dc_charge_kw', 'drivetrain', 'seats', 'wltp_range_km', 'ac_charge_kw', 'tow_kg', 'wltp_consumption_kwh_100km'].includes(field), 'No prices, identities or unsourced fields');
    const evidence = row.field_evidence[field];
    assert.equal(evidence.value, value); assert.equal(evidence.variant_name, row.variant_name);
    assert(sources.has(evidence.source_url)); assert.equal(sources.get(evidence.source_url), evidence.source_hash);
    assert.equal(evidence.model_heading, row.model + (row.model === 'Elroq' ? ' Explore Edition' : ' Solid Edition'));
    const quote = evidence.quote;
    assert(typeof quote === 'string' && quote.length > 20);
    if (field === 'boot_liters') {
      assert.equal(evidence.scope, 'model_rear_boot_seats_up');
      assert.equal(value, Number(/bagageutrymme på ([0-9]+) liter/.exec(quote)?.[1]));
      assert(value >= 50 && value <= 3500);
      assert(quote.startsWith(row.model === 'Elroq' ? 'Trots sin kompakta storlek har Elroq' : 'Stort bagageutrymme'));
    } else if (field === 'battery_kwh') {
      assert.equal(evidence.scope, 'my2027_engine_net_battery');
      assert.equal(evidence.source_url, technicalRelease);
      assert.equal(evidence.engine_label, row.model + ' ' + engine(row));
      assert(quote.startsWith(evidence.engine_label + ' '));
      assert.equal(value, Number(/Batterikapacitet \([Bb]rutto\/netto\) \[kWh\] [0-9]+\s*\/\s*([0-9]+)/.exec(quote)?.[1]));
      assert(value >= 10 && value <= 250);
    } else if (field === 'dc_charge_kw') {
      assert.equal(evidence.scope, 'faq_variant_dc');
      assert.equal(evidence.question, 'Hur snabbt kan ' + row.model + ' laddas?');
      assert.equal(value, Number(/maximal (?:DC-)?laddeffekt på ([0-9]+) kW/.exec(quote)?.[1]));
      assert(value >= 20 && value <= 600);
      if (row.model === 'Elroq') assert(clean(quote).startsWith(row.variant_name.startsWith('60 ') ? 'Elroq 60:' : 'Elroq 85, 85x och RS:'));
      else assert(quote.startsWith('Snabbladdning (DC): Enyaq 85, 85x, 85x Sportline och RS'));
    } else if (field === 'drivetrain') {
      assert.equal(evidence.scope, 'explicit_engine_drivetrain');
      const awd = row.variant_name.includes('85x') || row.variant_name.includes('RS');
      assert.equal(value, awd ? 'AWD' : 'RWD');
      assert(awd ? quote.startsWith('Ja, ' + row.model + ' 85x, 85x Sportline och RS har fyrhjulsdrift') : quote.includes('bakhjulsdrift'));
    } else if (field === 'seats') {
      assert.equal(value, 5);
      if (row.model === 'Enyaq') {
        assert.equal(evidence.scope, 'model_seating');
        assert(quote.startsWith('Enyaq har fem sittplatser och ett bagageutrymme'));
      } else {
        assert.equal(evidence.scope, 'model_gallery_seating');
        assert.equal(quote, 'När baksätets ryggstöd förblir upprättstående finns det 470 liters bagageutrymme för upp till fem passagerare.');
      }
    } else if (field === 'wltp_consumption_kwh_100km') {
      assert.equal(evidence.scope, 'price_table_engine_standard_consumption');
      assert.equal(evidence.source_url, priceSources[row.model]);
      assert.equal(evidence.engine_label, row.model === 'Enyaq' && row.variant_name.includes('Sportline') ? '85x Sportline' : engine(row));
      const cells = quote.split(' | ');
      assert.equal(cells.length, 10);
      assert.equal(cells[0], 'Škoda ' + evidence.model_heading);
      assert.equal(cells[1], evidence.engine_label);
      assert.equal(cells[4], String(evidence.raw_wh_km));
      assert(Number.isInteger(evidence.raw_wh_km) && evidence.raw_wh_km >= 100 && evidence.raw_wh_km <= 500);
      assert.equal(value, evidence.raw_wh_km / 10);
      assert.equal(cells[9], '*Värde gäller för motor i grundutförande.');
      assert.equal(evidence.unit_source_url, source.final_url);
      assert.equal(evidence.unit_source_hash, source.content_hash);
      assert(evidence.unit_quote.startsWith('Elförbrukning, blandad körning') && evidence.unit_quote.endsWith('Wh/km'));
      assert.equal(evidence.qualification, 'Motor i grundutförande; utrustning och hjul kan påverka förbrukningen.');
    } else if (field === 'wltp_range_km') {
      assert.equal(evidence.scope, 'faq_variant_wltp');
      assert.equal(evidence.question, 'Hur lång räckvidd har ' + row.model + '?');
      assert.equal(evidence.engine_label, rangeLabel(row));
      assert.equal(value, Number(/: upp till ([0-9]+) km\./.exec(clean(quote))?.[1]));
      assert(value >= 50 && value <= 1200 && clean(quote).startsWith(evidence.engine_label + ':'));
      assert.equal(evidence.qualification, 'WLTP, upp till; versionens angivna standardutförande');
    } else if (field === 'ac_charge_kw') {
      assert.equal(evidence.scope, 'faq_model_ac');
      assert.equal(evidence.question, 'Hur snabbt kan ' + row.model + ' laddas?');
      assert.equal(value, Number(/kan laddas med upp till ([0-9]+) kW AC/.exec(quote)?.[1]));
      assert(Number.isInteger(value) && value >= 1 && value <= 50);
    } else if (field === 'tow_kg') {
      assert.equal(evidence.scope, 'faq_braked_towing');
      assert.equal(evidence.question, 'Hur mycket får ' + row.model + ' dra?');
      assert.equal(evidence.engine_label, towLabel(row));
      assert.equal(value, Number(/: upp till ([0-9 ]+) kg\./.exec(clean(quote))?.[1]?.replaceAll(' ', '')));
      assert(value >= 0 && value <= 4000 && clean(quote).startsWith(evidence.engine_label + ':'));
      assert(evidence.qualification.startsWith('Bromsad släpvagn;'));
    }
  }
  return row;
}

const policy = { adapter: ADAPTER, validate: validateSpecDraft, sourceType: 'manufacturer_model_page',
  sourceName: 'Škoda Sverige', sourceTitle: row => 'Škoda ' + row.model + ' – svenska modelluppgifter', lockKey: 7240016,
  extraFields: ['ac_charge_kw'],
  modelFacts: draft => draft.model_facts || {},
  supportingSource: (source, draft) => source.final_url === technicalRelease
    ? { model: 'Elroq och Enyaq MY2027', sourceType: 'manufacturer_page', title: 'Skoda MY2027 tekniska data', shared: true }
    : source.final_url === priceSources[draft.model]
      ? { model: draft.model, sourceType: 'price_list_pdf', title: 'Skoda ' + draft.model + ' aktuell versionsprislista', shared: false } : null,
  reviewResetFields: ['validation_status', 'review_approved_by', 'review_reason', 'review_promoted_at'],
  reviewRefresh: (previous, draft) => previous.brand === 'Skoda' && previous.model === 'Enyaq' && previous.variant_name === 'Solid Edition RS' &&
    previous.review_approved_by === 'pipeline_auto_review' && previous.source_url === oldRsSource && draft.source_resolution === resolution,
  resolveConflict: (field, prior, value, previous, draft) => field === 'dc_charge_kw' && Number(prior) === 185 && value === 165 &&
    previous.brand === 'Skoda' && previous.model === 'Enyaq' && previous.variant_name === 'Solid Edition RS' &&
    previous.source_url === oldRsSource && draft.source_resolution === resolution,
};
export const buildSpecPlan = (variants, intake, now) => build(variants, intake, now, policy);
export const applySpecPlan = (client, plan, hash, now) => apply(client, plan, hash, now, policy);
