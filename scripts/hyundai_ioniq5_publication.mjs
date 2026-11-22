import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync, statSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

export const ADAPTER = 'hyundai_ioniq5_sweden_local_v1';
const root = fileURLToPath(new URL('..', import.meta.url));
const run = promisify(execFile);
const primaryUrl = 'https://www.hyundai.com/se/sv/bilar/ioniq5.html';
const assetRoot = 'https://dmassets.hyundai.com/is/content/hyundaiautoever/';
const priceUrl = assetRoot + 'Hyundai_Sverige_Prislista_20261102pdf';
const brochure = assetRoot + 'Nya_IONIQ_5_Modellbrochyr_202505_webpdf-AFpdf';
const practical = assetRoot + 'Prislista_Nya_IONIQ5_202507pdf';
const dealer = 'https://karmauto.se/ioniq-5';
const locator = 'https://www.hyundai.com/se/sv/tjanster/online-tjanster/hitta-aterforsaljare.html';
const dc = 'https://www.hyundai.com/no/no/bilguide/velge-elbil/kjope-brukt-elbil.html';
const seats = 'https://www.hyundai.com/no/no/bilguide/velge-elbil/elbil-familiebil.html';
const raNLine = 'https://ramotor.se/lagerbilar/hyundai-ioniq-5-qnr278/';
const rwdIdentity = 'MY27$RWD84-NLINE';
const marketUrl = 'https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx';
const imageKey = 'hyundai|ioniq 5';
const model = {brand: 'Hyundai', model: 'Ioniq 5', normalized_brand: 'hyundai', normalized_model: 'ioniq 5', body_type: 'SUV'};
const aliasRule = 'mobility_sweden_exact_raw_name';
const withheld = '84 kWh RWD N Line';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const ordering = (code, color) => `https://lager.hyundai.se/model/IONIQ%205/${code}?customer=private&ext=${color}&int=NNB`;
const photos = {
  base: {id: '2976415', name: 'hyundai-ioniq-5-press-6c3fdfee7a67.jpg',
    sha: '6c3fdfee7a67d2be41af312088681d670a20aa2fb0eda045c573dcdf330292b5',
    receipt: 'ce9ca83b2c6ed77ef5bab2f64576c79523998e18b948623a6fda2141a1d71724',
    url: 'https://www.mynewsdesk.com/se/hyundai/images/image-1-enhanced-ioniq-5-ext-2976415'},
  nLine: {id: '2976416', name: 'hyundai-ioniq-5-press-a2c20db010ce.jpg',
    sha: 'a2c20db010ce320057d26adfb3b11cb692274a7ca7b3c76e561aff10a73d30dd',
    receipt: 'f955f3976ba0f79c8f25b06b6cd2e7a790d0fbbce6329afafb740ddb10a7e2c6',
    url: 'https://www.mynewsdesk.com/se/hyundai/images/image-2-new-ioniq-5-n-line-ext-2976416'},
};
const profiles = [
  ['63 kWh RWD Essential', 'GIW5ZHZ7ZGG2L7', 'SAW', 554900, 440, 15.6, 63, 'RWD', '19'],
  ['84 kWh RWD Essential', 'GIW5ZHZ7ZGG2HC', 'A2B', 594900, 570, 16.0, 84, 'RWD', '19'],
  ['84 kWh AWD Essential', 'GIW5YCZ7ZGG2L8', 'SAW', 629900, 546, 16.8, 84, 'AWD', '19'],
  ['84 kWh RWD Advanced', 'GIW5ZHZ7ZHH2GQ', 'A2B', 637900, 570, 16.0, 84, 'RWD', '19'],
  ['84 kWh AWD Advanced', 'GIW5YCZ7ZHH2TP', 'SAW', 672900, 546, 16.8, 84, 'AWD', '19'],
  ['84 kWh AWD N Line', 'GIW5YCZ7ZMM325', 'R2P', 689900, 495, 18.1, 84, 'AWD', '20 N Line'],
  [withheld, null, null, 654900, 515, 17.2, 84, 'RWD', '20 N Line'],
].map(([name, code, color, price, range, consumption, battery, drivetrain, wheels]) => ({
  name, code, color, price, wheels, identity: code ? 'MY27$' + code : rwdIdentity,
  identityUrl: code ? ordering(code, color) : raNLine, photo: wheels === '19' ? 'base' : 'nLine',
  facts: {wltp_range_km: range, wltp_consumption_kwh_100km: consumption, battery_kwh: battery,
    dc_charge_kw: battery === 63 ? 195 : 260, ac_charge_kw: 10.5, boot_liters: 520,
    tow_kg: battery === 63 ? 750 : 1600, seats: 5, drivetrain},
}));
const evidenceMap = {
  wltp_range_km: ['wltp_range_km', brochure], wltp_consumption_kwh_100km: ['wltp_consumption_kwh_100km', priceUrl],
  battery_kwh: ['battery_kwh', brochure], dc_charge_kw: ['dc_charge_max_kw', dc],
  ac_charge_kw: ['ac_charge_max_kw', brochure], boot_liters: ['cargo_liters', practical],
  tow_kg: ['tow_capacity_kg', practical], seats: ['seats', seats], drivetrain: ['drivetrain', priceUrl],
};
const meta = (source_type, source_name, country = 'SE', language = 'sv', source_authority = 'manufacturer',
  authorization_evidence_url = null) => ({source_type, source_name, country, language, source_authority,
  authorization_evidence_url, shared: false});
const sites = [
  ['swedish-model.html', primaryUrl, meta('manufacturer_model_page', 'Hyundai Sverige')],
  ['swedish-price-list.pdf', priceUrl, meta('price_list_pdf', 'Hyundai Sverige')],
  ['swedish-brochure.pdf', brochure, meta('technical_pdf', 'Hyundai Sverige')],
  ['swedish-technical-archive.pdf', practical, meta('technical_pdf', 'Hyundai Sverige')],
  ['authorized-dealer.html', dealer, meta('authorized_dealer_model_page', 'Karmauto', 'SE', 'sv', 'authorized_dealer', locator)],
  ['dealer-locator.html', locator, meta('manufacturer_page', 'Hyundai Sverige')],
  ['norwegian-dc-reference.html', dc, meta('manufacturer_specs_page', 'Hyundai Norge', 'NO', 'no')],
  ['norwegian-seats-reference.html', seats, meta('manufacturer_specs_page', 'Hyundai Norge', 'NO', 'no')],
  ...profiles.filter(p => p.code).map(p => [
    'ordering-' + p.code + '.html', p.identityUrl, meta('manufacturer_configurator', 'Hyundai Sverige')]),
];
const raSource = ['authorized-n-line-identity.html', raNLine,
  meta('authorized_dealer_stock_page', 'RA Motor Haninge', 'SE', 'sv', 'authorized_dealer', locator)];
const hold = { [withheld]: 'no_independent_swedish_material_number' };
const market = {brand_raw: 'HYUNDAI', model_raw: 'IONIQ 5', fuel_type_raw: 'EL', normalized_brand: 'hyundai',
  normalized_model: 'ioniq 5', needs_mapping: false, last_seen_month: '2026-10-01',
  registrations_last_month: 70, registrations_ytd: 479, source_name: 'Mobility Sweden', source_url: marketUrl};

function privateRoot() {
  const path = join(realpathSync(root), 'data', 'local', 'release-data');
  assert.equal(realpathSync(path), path);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(path));
  return path;
}

function readPrivate(folder, name) {
  assert.equal(basename(name), name);
  const file = join(folder, name);
  assert.equal(realpathSync(file), file);
  const stat = statSync(file);
  assert(stat.isFile() && stat.size > 0 && stat.size < 32000000);
  return readFileSync(file);
}

export function readReviewedPhoto(edition = 'base') {
  const p = photos[edition];
  assert(p, 'Exact Ioniq 5 photo edition required');
  const folder = join(privateRoot(), 'hyundai-ioniq5-photo-review-2026-11-20');
  const receipt = readPrivate(folder, 'ioniq 5-mynewsdesk-' + p.id + '.json');
  assert.equal(hash(receipt), p.receipt);
  const candidate = JSON.parse(receipt);
  assert.equal(candidate.model_key, imageKey);
  assert.equal(candidate.source_url, p.url);
  assert.equal(candidate.review_filename, p.name);
  const body = readPrivate(folder, p.name);
  assert.equal(hash(body), p.sha);
  assert.equal(candidate.content_sha256, p.sha);
  assert.equal(hash(readPrivate(folder, candidate.metadata_sha256 + '.html')), candidate.metadata_sha256);
  const image = Object.fromEntries(['model_key', 'source_url', 'evidence_url', 'evidence_quote', 'license_id', 'license_url',
    'author', 'credit', 'content_sha256', 'metadata_sha256', 'source_content_sha256', 'publisher_id', 'full_frame']
    .map(key => [key, candidate[key]]));
  return {body, image: {...image, asset_url: '/media/vehicles/' + p.name, downloaded_from: candidate.asset_url,
    original_url: candidate.original_url, status: 'documented', reviewed_at: '2026-11-20',
    reviewed_candidate_sha256: p.receipt, usage_scope: 'independent_vehicle_editorial',
    prohibited_uses: ['advertising', 'commercial_promotion', 'endorsement'],
    model_image_notice: 'Pressbild. Utrustning kan skilja mellan versioner.'}};
}

const matches = (actual, expected) => {
  for (const [key, value] of Object.entries(expected)) assert.equal(actual?.[key], value, 'Unexpected Ioniq 5 evidence: ' + key);
};

export function validateIntake(intake) {
  assert.equal(intake.adapter, ADAPTER);
  assert.deepEqual(intake.model, model);
  assert.deepEqual(intake.market.row, market);
  assert.equal(intake.market.sheet, 'Elbil ranking');
  assert.equal(intake.market.source.final_url, marketUrl);
  const sources = new Map(intake.sources.map(s => [s.final_url, s]));
  const includeRwd = sources.has(raNLine);
  const registeredSites = includeRwd ? [...sites, raSource] : sites;
  assert.equal(sources.size, registeredSites.length);
  assert.equal(intake.sources.length, registeredSites.length);
  for (const [, url, expected] of registeredSites) matches(sources.get(url), expected);
  const bind = (proof, url, value) => matches(proof, {source_url: url, source_hash: sources.get(url).content_hash, value});
  bind(intake.model_evidence.body, primaryUrl, 'SUV');
  assert.deepEqual(intake.model_evidence.identity_holds, includeRwd ? {} : hold);
  const expectedProfiles = profiles.filter(row => includeRwd || row.code);
  assert.equal(intake.drafts.length, expectedProfiles.length);
  for (const p of expectedProfiles) {
    const draft = intake.drafts.find(row => row.variant_name === p.name);
    assert(draft, 'Exact MY27 trim required');
    matches(draft, {manufacturer_identity: p.identity});
    bind(draft.identity_evidence, p.identityUrl, p.identity);
    matches(draft.identity_evidence, {material_number: p.code, model_year: 2027,
      reviewed_photo_sha256: photos[p.photo].sha, reviewed_photo_source: photos[p.photo].url});
    if (!p.code) {
      assert.equal(draft.identity_evidence.kind, 'authorized_swedish_variant_identity');
      bind(draft.identity_evidence.authorization, locator, 'C18AS20015');
    }
    assert.deepEqual(draft.facts, p.facts);
    for (const [field, value] of Object.entries(p.facts)) bind(draft.field_evidence[field], evidenceMap[field][1], value);
    matches(draft.field_evidence.wltp_range_km, {wheel_scope: p.wheels, page: 18});
    matches(draft.field_evidence.ac_charge_kw, {phases: 3});
    matches(draft.field_evidence.tow_kg, {braked: true});
    matches(draft.field_evidence.boot_liters, {seats_up: true, volume_standard: 'VDA'});
    bind(draft.price_evidence, priceUrl, p.price);
    matches(draft.price_evidence, {price_type: 'list_price', price_valid_until: null});
    bind(draft.price_evidence.corroboration, dealer, p.price);
    bind(draft.price_evidence.corroboration.authorization, locator, true);
  }
}

export async function readIoniq5Capture(folder) {
  const path = realpathSync(folder);
  assert.equal(dirname(path), privateRoot());
  assert.match(basename(path), /^hyundai-ioniq5-review-[a-z0-9_]+$/);
  const raw = readPrivate(path, 'review.json');
  const {stdout} = await run(process.execPath, ['scripts/run_python.mjs', 'scripts/hyundai_ioniq5_review.py', '--replay', path],
    {cwd: root, timeout: 120000, windowsHide: true, maxBuffer: 256000});
  matches(JSON.parse(stdout), {replayed_offline: true, checked_prices: 7, publication_approved: false});
  assert.equal(hash(readPrivate(path, 'review.json')), hash(raw));
  const review = JSON.parse(raw);
  matches(review, {status: 'private_source_review', model: 'Hyundai Ioniq 5', issued_on: '2026-11-02',
    publication_approved: false, database_writes: 0, paid_calls: 0});
  assert.equal(review.variants.length, 7);
  const includeRwd = Boolean(review.sources['authorized-n-line-identity.html']);
  assert.deepEqual(review.identity_holds, includeRwd ? {} : hold);
  const rwd = review.variants.find(row => row.variant === withheld);
  assert(rwd);
  if (!includeRwd) assert.equal(rwd.identity_evidence, undefined);
  matches(review.market_index, {source_url: marketUrl, value: 70, registrations_ytd: 479,
    quote: 'HYUNDAI | IONIQ 5 | EL', report_month: '2026-10-01'});
  const sourceReceipt = (final_url, content_hash) => ({final_url, content_hash, fetched_at: review.captured_at,
    http_status: 200, status: 'reachable'});
  const sources = (includeRwd ? [...sites, raSource] : sites).map(([name, url, metadata]) => {
    matches(review.sources[name], {url, http_status: 200});
    return {...metadata, ...sourceReceipt(url, review.sources[name].sha256)};
  });
  const images = {base: readReviewedPhoto('base').image, nLine: readReviewedPhoto('nLine').image};
  const drafts = profiles.filter(p => includeRwd || p.code).map(p => {
    const row = review.variants.find(v => v.variant === p.name);
    matches(row, {variant: p.name, standard_wheels: p.wheels});
    matches(row.identity_evidence, {value: p.code ?? p.identity, model_year: 2027});
    const field_evidence = Object.fromEntries(Object.entries(evidenceMap).map(([field, [key]]) =>
      [field, {...row.evidence[key], variant_name: p.name}]));
    return {variant_name: p.name, manufacturer_identity: p.identity, extraction_confidence: 1,
      identity_evidence: {...row.identity_evidence, value: p.identity, material_number: p.code,
        reviewed_photo_sha256: images[p.photo].content_sha256, reviewed_photo_source: images[p.photo].source_url},
      facts: Object.fromEntries(Object.entries(field_evidence).map(([field, proof]) => [field, proof.value])),
      field_evidence, price_evidence: {...row.evidence.price_sek, price_valid_until: null}};
  });
  const intake = {adapter: ADAPTER, model, sources, drafts,
    model_evidence: {body: review.variants[0].evidence.body_type, identity_holds: review.identity_holds},
    market: {row: market, sheet: 'Elbil ranking', source: sourceReceipt(marketUrl, review.market_index.source_hash)},
    source_decisions: ['Swedish ordinary prices with named dealer corroboration; no finance offers or optional prices.',
      'Retain wheel-specific Swedish WLTP and 10.5 kW onboard AC; Norwegian sources only corroborate matching hardware.',
      'Two approved photo receipts are scoped to base/N Line; the shared model photo is not N Line-specific.',
      includeRwd ? '84 kWh RWD N Line uses an exact authorized MY27 identity, not an invented manufacturer material number.'
        : '84 kWh RWD N Line remains in identity review; no 2027 material number inferred.']};
  validateIntake(intake);
  return {intake, images, capturedAt: review.captured_at, reviewHash: hash(raw)};
}

export const policy = {adapter: ADAPTER, primaryUrl, aliasRule, imageKey, imageHash: photos.base.sha,
  mixedSources: true, localOnly: true, maxVariants: profiles.length, validateIntake,
  variantPhoto(draft) {
    const profile = profiles.find(p => p.name === draft.variant_name);
    assert(profile, 'Unknown Ioniq 5 edition');
    return profile.photo === 'nLine' ? readReviewedPhoto('nLine') : null;
  },
  readPrivateImage(image) {
    const reviewed = readReviewedPhoto('base');
    assert.deepEqual(image, reviewed.image, 'Only the exact reviewed Ioniq 5 parent photo is allowed');
    return reviewed.body;
  }};
