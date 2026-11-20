import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

export const ADAPTER = 'volkswagen_id_buzz_local_pilot_v1';
const origin = 'https://www.volkswagen-transportbilar.se';
const modelUrl = origin + '/sv/modeller/id-buzz.html';
const technical = modelUrl.replace('.html', '/tekniska-data.html');
const dealer = 'https://mollerbil.se/erbjudanden/id-buzz-pro-sweden-olympic-edition';
const authorization = origin + '/sv/om-oss/transportmagasinet/foretag-och-forare/anpassa-transportbilen-efter-dina-behov.html';
const finnish = 'https://api.k-auto.fi/priceCatalog/api/PriceCatalog/d1c60397-8685-48d3-b954-e08eb0b50361';
const french = 'https://www.volkswagen-utilitaires.fr/idhub/content/dam/onehub_nfz/importers/fr/documentation/fiches-tarifs/Tarif_ID_Buzz.pdf';
const photo = JSON.parse(readFileSync(new URL('../src/id-buzz-photo-policy.json', import.meta.url), 'utf8'));
export const marketUrl = 'https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx';
const model = { brand: 'Volkswagen', model: 'Id. Buzz', normalized_brand: 'volkswagen', normalized_model: 'id buzz', body_type: 'Minibuss' };
const availabilityIndependent = { brand_raw: 'VW', model_raw: 'ID. BUZZ', fuel_type_raw: 'EL', normalized_brand: 'volkswagen',
  normalized_model: 'id buzz', needs_mapping: false, last_seen_month: '2026-10-01', source_name: 'Mobility Sweden',
  source_url: marketUrl, registrations_last_month: 147, registrations_ytd: 910 };

const source = ([country, language, source_authority, source_type, source_name, authorization_evidence_url = null]) =>
  ({ country, language, source_authority, source_type, source_name, authorization_evidence_url });
const official = (...args) => source(['SE', 'sv', 'manufacturer', ...args]);
const exactSources = new Map([
  [modelUrl, official('manufacturer_page', 'Volkswagen Transportbilar')],
  [technical, official('manufacturer_page', 'Volkswagen Transportbilar')],
  [authorization, official('manufacturer_page', 'Volkswagen Transportbilar')],
  [dealer, source(['SE', 'sv', 'authorized_dealer', 'authorized_dealer_model_page', 'M\u00f6ller Bil', authorization])],
  [finnish, source(['FI', 'fi', 'importer', 'technical_pdf', 'K Auto Oy'])],
  [french, source(['FR', 'fr', 'importer', 'technical_pdf', 'Volkswagen Utilitaires France'])],
]);

const profiles = [
  ['Pro', 'pro', 'EBBR7R', 589900, 452, 19.6, 1121, 1200, 'RWD'],
  ['Pro 4MOTION', 'pro-4motion', 'EBBR5R', 625900, 416, 21.5, 1131, 1800, 'AWD'],
].map(([trim, slug, code, cash, km, consumption, boot, tow, drivetrain]) => ({
  trim, code, cash, variantName: `${trim} Sweden Olympic Edition 5-sits MY2027`,
  config: origin + `/sv/bygg-din-bil.html/__app/72006/edition/${slug}.app`,
  facts: { wltp_range_km: km, wltp_consumption_kwh_100km: consumption, battery_kwh: 79,
    dc_charge_kw: 185, ac_charge_kw: 11, boot_liters: boot, tow_kg: tow, seats: 5, drivetrain },
}));

const configSource = official('manufacturer_configurator', 'Volkswagen Transportbilar');
const metadataMatches = (row, expected) => {
  for (const [key, value] of Object.entries(expected)) assert.equal(row[key], value, `Invalid source attribution: ${key}`);
};
const lengthAndScope = (rows, length) => assert.equal(new Set(rows).size, length, 'Exact distinct pilot scope required');
const byField = (profile, field) => ({ wltp_range_km: profile.config, wltp_consumption_kwh_100km: profile.config,
  ac_charge_kw: french, tow_kg: technical, boot_liters: profile.trim === 'Pro' ? technical : modelUrl }[field] ?? modelUrl);

export function validateIntake(intake) {
  assert.equal(intake.adapter, ADAPTER);
  assert.deepEqual(intake.model, model);
  assert.equal(intake.sources.length, 8);
  const sources = new Map(intake.sources.map(row => [row.final_url, row]));
  lengthAndScope(sources.keys(), 8);
  for (const [url, expected] of [...exactSources, ...profiles.map(p => [p.config, configSource])]) {
    const row = sources.get(url); assert(row, 'Exact registered source required');
    metadataMatches(row, expected);
    assert.equal(row.shared, false);
  }
  assert.equal(intake.market?.source?.final_url, marketUrl);
  assert.equal(intake.market.sheet, 'Elbil ranking');
  metadataMatches(intake.market.row, availabilityIndependent);
  assert.equal(intake.drafts.length, 2);
  lengthAndScope(intake.drafts.map(draft => draft.variant_name), 2);
  for (const p of profiles) {
    const draft = intake.drafts.find(row => row.variant_name === p.variantName); assert(draft);
    assert.match(draft.manufacturer_identity, new RegExp(`^${p.code}(?:\\$[A-Z0-9]+)+$`));
    assert.deepEqual(draft.facts, p.facts);
    for (const field of Object.keys(p.facts)) assert.equal(draft.field_evidence[field]?.source_url, byField(p, field));
    const dc = draft.field_evidence.dc_charge_kw;
    assert.equal(dc.corroboration?.source_url, finnish);
    assert.equal(dc.corroboration?.source_hash, sources.get(finnish).content_hash);
    assert.equal(dc.corroboration?.value, 185);
    assert.equal(dc.alternative?.source_url, french);
    assert.equal(dc.alternative?.source_hash, sources.get(french).content_hash);
    assert.equal(dc.alternative?.value, 183);
    const ac = draft.field_evidence.ac_charge_kw;
    assert.equal(ac.corroboration?.source_url, finnish);
    assert.equal(ac.corroboration?.source_hash, sources.get(finnish).content_hash);
    assert.equal(ac.corroboration?.value, 11);
    const tow = draft.field_evidence.tow_kg.alternative;
    assert.equal(tow?.source_url, p.config);
    assert.equal(tow?.source_hash, sources.get(p.config).content_hash);
    assert.equal(tow?.value, 1800);
    const price = draft.price_evidence;
    metadataMatches(price, { value: p.cash, price_type: 'dealer_offer', price_valid_until: '2026-12-31', source_url: dealer });
    assert.equal(price.authorization?.source_url, authorization);
    assert.equal(price.authorization?.source_hash, sources.get(authorization).content_hash);
    assert.equal(price.manufacturer_base_cash?.source_url, p.config);
    assert.equal(price.manufacturer_base_cash?.source_hash, sources.get(p.config).content_hash);
    assert.equal(price.manufacturer_base_cash?.value, p.cash);
    assert.equal(price.quote, `ID. Buzz ${p.trim} Sweden Olympic Edition 5-sits pris fr\u00e5n ${String(p.cash).replace(/(\d{3})$/, ' $1')} kr inkl. moms`);
    assert.match(price.expiry_quote, /31\/12 2026$/u);
  }
}

// Convert the private, hash-checked review into an intake for the local transaction only.
export function prepareIdBuzzIntake(review, market) {
  assert.equal(review.status, 'needs_review');
  assert.equal(review.publication_approved, false);
  assert.equal(review.photo?.content_sha256, photo.content_sha256);
  assert.equal(review.variants.length, 2);
  assert.equal(review.configurations.length, 2);
  const sources = [...exactSources].map(([final_url, meta]) => {
    const proof = review.sources[final_url]; assert(proof, 'Missing captured source');
    return { ...meta, status: 'reachable', http_status: 200, final_url, content_hash: proof.content_hash,
      fetched_at: proof.fetched_at, shared: false };
  });
  const configUrls = new Map();
  for (const p of profiles) {
    const record = review.configurations.find(row => row.trim === p.trim);
    assert(record && record.source_url === p.config && record.motor_id === p.code && record.model_year === 2027
      && record.wheelbase_mm === 2989 && record.seats === 5);
    const url = new URL(record.summary.final_url);
    assert.equal(url.origin + url.pathname, p.config);
    assert.deepEqual(url.searchParams.getAll('modelId-app'), [record.configuration_id]);
    assert(!url.username && !url.password && !url.hash);
    configUrls.set(url.href, p.config);
    sources.push({ ...configSource, status: 'reachable', http_status: 200, final_url: p.config,
      content_hash: record.summary.evidence_sha256, fetched_at: record.captured_at, shared: false, capture_kind: 'rendered_configuration' });
  }

  const bind = evidence => {
    assert(evidence && typeof evidence.quote === 'string' && evidence.quote.trim().length > 5);
    const source_url = configUrls.get(evidence.source_url) ?? evidence.source_url;
    const capture = sources.find(row => row.final_url === source_url); assert(capture);
    return { ...evidence, source_url, source_hash: capture.content_hash,
      ...(capture.capture_kind ? { configuration_url: evidence.source_url } : {}) };
  };
  const drafts = profiles.map(p => {
    const row = review.variants.find(v => v.trim === p.trim); assert(row && row.model_code === p.code);
    assert.equal(row.configuration_id, review.configurations.find(v => v.trim === p.trim).configuration_id);
    const field_evidence = Object.fromEntries(Object.entries(row.facts).map(([field, value]) =>
      [field, { ...bind(value), variant_name: p.variantName,
        ...(value.corroboration ? { corroboration: bind(value.corroboration) } : {}),
        ...(value.alternative ? { alternative: bind(value.alternative) } : {}) }]));
    field_evidence.tow_kg.alternative = bind(row.observed_configurator_tow);
    return { variant_name: p.variantName, manufacturer_identity: row.configuration_id, extraction_confidence: 1,
      facts: Object.fromEntries(Object.entries(row.facts).map(([field, evidence]) => [field, evidence.value])), field_evidence,
      price_evidence: { ...bind(row.price), authorization: bind(row.price.authorization),
        manufacturer_base_cash: bind(row.price.manufacturer_base_cash) } };
  });
  const intake = { adapter: ADAPTER, model, model_evidence: { scope: 'Short Swedish passenger ID. Buzz, not Cargo' },
    sources, drafts, market, source_decisions: ['Use dated M\u00f6ller Bil offers, not nationwide list prices.',
      'Use the Swedish 185 kW claim corroborated by both Finnish model codes; retain the French 183 kW alternative.',
      'Use Swedish braked towing by exact drive and short body. Registry proves presence, not availability.'] };
  validateIntake(intake);
  return intake;
}

export const policy = { adapter: ADAPTER, validateIntake, primaryUrl: modelUrl, imageKey: photo.model_key,
  imageHash: photo.content_sha256, aliasRule: 'mobility_sweden_exact_raw_name', maxVariants: 2, mixedSources: true, localOnly: true };
