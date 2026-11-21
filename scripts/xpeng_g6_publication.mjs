import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ADAPTER = 'xpeng_g6_sweden_facelift_local_v1';
const root = fileURLToPath(new URL('..', import.meta.url));
const primary = 'https://store.xpeng.com/se/configurator/new_G6';
const uk = 'https://store.xpeng.com/gb/configurator/New_G6R';
const tech = 'https://s-cdn.xpeng.com/commoncms/prod/2026-11-11/a6130a4e376b4711806b741f07b2f4ca.pdf';
const dealer = 'https://lecab.se/erbjudande/xpeng-g6-5/';
const appointment = 'https://news.cision.com/se/xpeng/r/xpeng-expanderar-och-oppnar-i-karlstad,c4032912';
const pressRoom = 'https://www.mynewsdesk.com/se/xpeng-motors-sweden-ab/';
const press = pressRoom + 'pressreleases/nya-xpeng-g6-svenska-priser-och-foersaeljningsstart-3396446';
const photoUrl = pressRoom + 'images/g6-launch-2025-exterior-urban-road-punkt-jpg-3287677';
const marketUrl = 'https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx';
const model = {brand: 'Xpeng', model: 'G6', normalized_brand: 'xpeng', normalized_model: 'g6', body_type: 'SUV'};
const imageFile = 'xpeng-g6-press-3d0ad9b81b94.jpg';
const imageHash = '3d0ad9b81b948e2d6bbb36a2530a9434bd2a36cda5551e58d246dbba10c2a727';
const imageReceiptHash = '1bdbf437b29d422b803cc09d0d40c35a6a40cf7273555270eeb0dbabfc64c529';
const photoFolder = 'xpeng-g6-press-l7ecvwjq';
const assetUrl = '/media/vehicles/' + imageFile;
const aliasRule = 'mobility_sweden_exact_raw_name';
const modelKey = 'xpeng|g6';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const json = bytes => JSON.parse(bytes.toString('utf8'));
const metadata = (source_type, source_name, country = 'SE', language = 'sv', source_authority = 'manufacturer',
  authorization_evidence_url = null) => ({source_type, source_name, country, language, source_authority,
  authorization_evidence_url, shared: false});
const scopes = [
  ['config.html', primary, metadata('manufacturer_configurator', 'XPENG Sverige')],
  ['uk.html', uk, metadata('manufacturer_configurator', 'XPENG UK', 'GB', 'en')],
  ['specs.pdf', tech, metadata('technical_pdf', 'XPENG (internationellt teknikblad)', 'GLOBAL', 'en')],
  ['dealer.html', dealer, metadata('authorized_dealer_model_page', 'Lecab Bil', 'SE', 'sv', 'authorized_dealer', appointment)],
  ['appointment.html', appointment, metadata('manufacturer_page', 'XPENG Sverige')],
  ['press.html', press, metadata('manufacturer_page', 'XPENG Sverige')],
];
const profiles = [
  ['RWD Standard Range', 'FFCB', '2761', 499900, 470, 16.9, 68.5, 382, 'RWD', tech, uk],
  ['RWD Long Range', 'FFAB', '1881', 579900, 525, 17.9, 80.8, 451, 'RWD', press, press],
  ['AWD Performance', 'FFBB', '1886', 619900, 510, 18.4, 80.8, 451, 'AWD', press, press],
].map(([trim, code, id, cash, km, consumption, battery, dc, drivetrain, seatsSource, towingSource]) => ({
  trim, name: trim + ' 20 tum', identity: 'F30bV$' + code, code, id, cash, seatsSource, towingSource,
  facts: {wltp_range_km: km, wltp_consumption_kwh_100km: consumption, battery_kwh: battery, dc_charge_kw: dc,
    ac_charge_kw: 11, boot_liters: 571, tow_kg: 1500, seats: 5, drivetrain},
}));
const market = {brand_raw: 'XPENG', model_raw: 'G6', fuel_type_raw: 'EL', normalized_brand: 'xpeng', normalized_model: 'g6',
  needs_mapping: false, last_seen_month: '2026-10-01', registrations_last_month: 115, registrations_ytd: 643,
  source_name: 'Mobility Sweden', source_url: marketUrl};

function privateRoot() {
  const path = join(realpathSync(root), 'data', 'local', 'release-data');
  assert.equal(realpathSync(path), path, 'Require the unlinked project evidence directory');
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(path));
  return path;
}

function readPrivate(folder, name) {
  assert.equal(basename(name), name);
  const path = join(folder, name);
  assert.equal(realpathSync(path), path, 'Do not follow linked evidence files');
  return readFileSync(path);
}

export function readReviewedImage() {
  const folder = join(privateRoot(), photoFolder);
  const receipt = readPrivate(folder, 'g6-mynewsdesk-3287677.json');
  assert.equal(hash(receipt), imageReceiptHash, 'Reviewed G6 photo receipt changed');
  const candidate = json(receipt);
  assert.equal(candidate.model_key, modelKey);
  assert.equal(candidate.source_url, photoUrl);
  assert.equal(candidate.review_filename, imageFile);
  assert.equal(candidate.content_sha256, imageHash);
  assert.equal(hash(readPrivate(folder, candidate.metadata_sha256 + '.html')), candidate.metadata_sha256);
  const image = Object.fromEntries(['model_key', 'source_url', 'evidence_url', 'evidence_quote', 'license_id', 'license_url',
    'author', 'credit', 'content_sha256', 'metadata_sha256', 'source_content_sha256', 'publisher_id', 'full_frame']
    .map(key => [key, candidate[key]]));
  return {...image, asset_url: assetUrl, downloaded_from: candidate.asset_url, original_url: candidate.original_url,
    status: 'documented', reviewed_at: '2026-11-20', reviewed_candidate_sha256: imageReceiptHash,
    usage_scope: 'independent_vehicle_editorial', prohibited_uses: ['advertising', 'commercial_promotion', 'endorsement'],
    model_image_notice: 'Pressbild. Utrustning kan skilja mellan versioner.'};
}

export function readReviewedImageBytes(image) {
  assert.deepEqual(image, readReviewedImage(), 'Require the exact private reviewed photo');
  return readPrivate(join(privateRoot(), photoFolder), imageFile);
}

export function assertXpG6PublicVariants(rows, plan) {
  assert.equal(plan.adapter, ADAPTER);
  assert.deepEqual(plan.intake.model, model);
  assert.equal(plan.image.model_key, modelKey);
  assert.equal(plan.targets.length, profiles.length);
  assert.equal(rows.length, profiles.length, 'All three G6 variants must be visible anonymously');
  const byName = new Map(rows.map(row => [row.variant_name, row]));
  assert.equal(byName.size, profiles.length);
  const primarySource = plan.intake.sources.find(source => source.final_url === primary);
  assert(primarySource);
  for (const {draft} of plan.targets) {
    const row = byName.get(draft.variant_name);
    assert(row, 'Missing reviewed public G6 variant');
    const expected = {...draft.facts, brand: model.brand, model: model.model, body_type: model.body_type,
      validation_status: 'published', extraction_confidence: draft.extraction_confidence,
      image_url: plan.image.asset_url, image_source_url: plan.image.source_url,
      price_type: 'list_price', price_sek: draft.price_evidence.value,
      price_source_url: draft.price_evidence.source_url, price_source_hash: draft.price_evidence.source_hash,
      price_source_quote: draft.price_evidence.quote, price_source_name: primarySource.source_name,
      price_valid_until: draft.price_evidence.price_valid_until,
      source_url: primary, source_hash: primarySource.content_hash, market_seen: true,
      ...Object.fromEntries(['available_confirmed', 'discontinued_candidate', 'coming_or_low_volume']
        .map(key => [key, plan.expected_model[key]]))};
    for (const [key, value] of Object.entries(expected)) assert.equal(row[key], value, 'Unexpected public G6 field: ' + key);
    assert.equal(Date.parse(row.price_verified_at), Date.parse(primarySource.fetched_at), 'Unexpected public G6 price evidence date');
  }
}

const matches = (evidence, expected) => {
  for (const [key, value] of Object.entries(expected)) assert.equal(evidence?.[key], value, 'G6 evidence changed: ' + key);
};

export function validateIntake(intake) {
  assert.equal(intake.adapter, ADAPTER);
  assert.deepEqual(intake.model, model);
  assert.deepEqual(intake.market.row, market);
  assert.equal(intake.market.sheet, 'Elbil ranking');
  assert.equal(intake.market.source.final_url, marketUrl);
  assert.equal(intake.sources.length, scopes.length);
  const sources = new Map(intake.sources.map(source => [source.final_url, source]));
  for (const [, url, expected] of scopes) matches(sources.get(url), expected);
  const bind = (evidence, url, value) => matches(evidence, {source_url: url, source_hash: sources.get(url).content_hash, value});
  bind(intake.model_evidence.body, primary, 'SUV');
  assert.equal(intake.drafts.length, profiles.length);
  for (const p of profiles) {
    const draft = intake.drafts.find(row => row.variant_name === p.name);
    assert(draft, 'Exact Swedish 20-inch variant required');
    matches(draft, {manufacturer_identity: p.identity});
    bind(draft.identity_evidence, primary, p.identity);
    matches(draft.identity_evidence, {version_code: p.code, series_code: 'F30bV', version_id: p.id, power_type: 'BEV', list_price_sek: p.cash});
    assert.deepEqual(draft.facts, p.facts);
    for (const [field, value] of Object.entries(p.facts)) {
      bind(draft.field_evidence[field], field === 'seats' ? p.seatsSource : field === 'tow_kg' ? p.towingSource : primary, value);
    }
    matches(draft.field_evidence.battery_kwh, {capacity_basis: 'gross'});
    matches(draft.field_evidence.wltp_range_km, {wheels_inches: 20, scope: 'SE_WLTP'});
    matches(draft.field_evidence.wltp_consumption_kwh_100km, {wheels_inches: 20, scope: 'SE_WLTP'});
    bind(draft.field_evidence.tow_kg.swedish_reference, primary, 1500);
    bind(draft.price_evidence, primary, p.cash);
    matches(draft.price_evidence, {price_type: 'list_price', price_valid_until: null, market: 'SE'});
    bind(draft.price_evidence.corroboration, dealer, p.cash);
    matches(draft.price_evidence.corroboration, {authorization_url: appointment,
      authorization_hash: sources.get(appointment).content_hash});
    bind(draft.price_evidence.authorization, appointment, 'Lecab Bil Karlstad');
  }
}

export function prepareXpG6Intake(review, identities) {
  matches(review, {status: 'private_variant_review_not_publication_approval',
    model_key: modelKey, market: 'SE', publication_approved: false, database_writes: 0, photo_source: photoUrl});
  matches(review.market_index, {quote: 'XPENG | G6 | EL', source_url: marketUrl, value: 115,
    registrations_ytd: 643, report_month: '2026-10-01'});
  const receipt = (final_url, content_hash) => ({final_url, content_hash,
    fetched_at: review.captured_at, status: 'reachable', http_status: 200});
  const sources = scopes.map(([name, url, data]) => {
    matches(review.sources[name], {url});
    return {...data, ...receipt(url, review.sources[name].sha256)};
  });
  assert.equal(Object.keys(review.variants).length, profiles.length);
  const drafts = profiles.map(p => {
    const row = review.variants[p.trim];
    const identity = identities[p.trim];
    const field_evidence = Object.fromEntries(Object.entries(row.facts)
      .map(([key, value]) => [key, {...value, variant_name: p.name}]));
    field_evidence.tow_kg.swedish_reference = row.towing_reference;
    return {variant_name: p.name, manufacturer_identity: identity.value, identity_evidence: identity, extraction_confidence: 1,
      facts: Object.fromEntries(Object.entries(row.facts).map(([key, value]) => [key, value.value])), field_evidence,
      price_evidence: {...row.price, price_valid_until: null, corroboration: row.dealer_price,
        authorization: review.dealer_appointment}};
  });
  const intake = {adapter: ADAPTER, model, model_evidence: {body: review.body, scope: 'Swedish F30bV, 20-inch factory trims'},
    sources, drafts, market: {source: receipt(marketUrl, review.market_index.source_hash), sheet: 'Elbil ranking', row: market},
    source_decisions: ['Keep Sweden-specific 20-inch WLTP, not 18-inch or foreign figures.',
      'Lecab corroborates XPENG list prices; no finance or inventory prices.',
      'Only Standard Range uses matching international seating and UK braked-towing evidence.']};
  validateIntake(intake);
  return intake;
}

export function readXpG6Capture(folder) {
  const path = realpathSync(folder);
  assert.equal(dirname(path), privateRoot());
  assert.match(basename(path), /^xpeng-g6-review-[a-z0-9_]+$/);
  const report = readPrivate(path, 'review.json');
  const identities = json(execFileSync(process.execPath, ['scripts/run_python.mjs', 'scripts/xpeng_g6_review.py',
    '--replay', path, '--identities'], {cwd: root, timeout: 90000, windowsHide: true}));
  assert.equal(hash(readPrivate(path, 'review.json')), hash(report), 'Source review changed during replay');
  const review = json(report);
  return {intake: prepareXpG6Intake(review, identities), reviewHash: hash(report), capturedAt: review.captured_at};
}

export const policy = {adapter: ADAPTER, primaryUrl: primary, aliasRule, imageKey: modelKey, imageHash,
  maxVariants: 3, mixedSources: true, localOnly: true, readPrivateImage: readReviewedImageBytes, validateIntake};
