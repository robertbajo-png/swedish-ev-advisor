import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync, statSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = realpathSync(fileURLToPath(new URL('../', import.meta.url)));
const imageKey = 'polestar|3';
const publisher = 'polestar-3-have-private-3332240';
const press = JSON.parse(readFileSync(new URL('../src/press-image-publishers.json', import.meta.url), 'utf8'))[publisher];
const photoReceiptHash = '274370847f9921f8df1e5cf91afccc9d4478d8a3fb33f583da907f7a98bf771a';
const pressReleaseHash = '41dcfc45bdcf4f9b117e0ebe12e2ff3b0754913953ea3a4a2c8de45ba5207071';
const photoSource = press.origin + press.approved_image_paths[0];
const filename = 'polestar-3-press-' + press.approved_source_sha256.slice(0, 12) + '.jpg';
const variant = 'Performance';
const identity = 'SE|MY27|359|DA|XPFWHE';
export const MODEL = Object.freeze({brand: 'Polestar', model: '3', normalized_brand: 'polestar', normalized_model: '3', body_type: 'SUV'});
export const ADAPTER = 'polestar_3_performance_se_my27';

const se = 'https://www.polestar.com/se/';
const manual = tail => se + 'manual/polestar-3/2027/article/0ed816eed33d98cac0a8cc377bc12bc7-' + tail + '-8664b2fa77a7e089c0a8296870d1a409/';
const urls = {
  'overview.html': se + 'polestar-3/',
  'specs.html': se + 'polestar-3/specifications/',
  'configuration.html': se + 'configure/polestar-3/versions/performance?customerSubtype=None&customerType=B2C&productType=Cash',
  'wltp.html': manual('32882fb459557dbec0a8b097072c55bf'),
  'tow.html': manual('70bede2dc073ca71c0a8b0975b1e6fa3'),
  'seats.html': manual('30eab915efda26f3c0a8b08a3ef5efb7'),
};
const types = {'overview.html': 'manufacturer_model_page', 'configuration.html': 'manufacturer_configurator'};
const marketUrl = 'https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx';
const articleUrl = 'https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober';
const market = {brand_raw: 'POLESTAR', model_raw: '3', fuel_type_raw: 'EL', normalized_brand: 'polestar',
  normalized_model: '3', last_seen_month: '2026-10-01', registrations_last_month: 15, registrations_ytd: 390};
const reviewedFacts = {
  wltp_range_km: [601, 'wltp.html', 'my27_performance_quoted_combined_wltp_maximum'],
  wltp_consumption_kwh_100km: [20.5, 'wltp.html', 'my27_performance_paired_combined_wltp_minimum'],
  battery_kwh: [106, 'specs.html', '800_v_capacity_not_usable_claim'],
  dc_charge_kw: [350, 'specs.html', 'peak_dc_at_800_v'],
  ac_charge_kw: [11, 'specs.html', 'ac_charging_basis'],
  boot_liters: [484, 'specs.html', 'rear_seats_up_to_backrests_includes_underfloor_not_frunk'],
  tow_kg: [2200, 'tow.html', 'braked'],
  seats: [5, 'seats.html', 'my27_five_unique_left_hand_drive_seat_positions'],
  drivetrain: ['AWD', 'specs.html', 'performance_column'],
};
const hash = body => createHash('sha256').update(body).digest('hex');
const fields = (row, expected) => {
  for (const [key, value] of Object.entries(expected)) assert.deepEqual(row?.[key], value, 'Polestar 3 scope changed: ' + key);
};
const privateRoot = () => {
  const folder = join(root, 'data', 'local', 'release-data');
  assert.equal(realpathSync(folder), folder);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(folder));
  return folder;
};
function evidence(folder, name, limit = 8_000_000) {
  assert.equal(basename(name), name);
  const path = join(folder, name);
  assert.equal(realpathSync(path), path);
  const info = statSync(path);
  assert(info.isFile() && info.size > 0 && info.size <= limit);
  return readFileSync(path);
}

export function readPolestar3Image() {
  const folder = join(privateRoot(), 'polestar-3-image-review-3cyf4kup');
  const bytes = evidence(folder, '3-mynewsdesk-3332240.json', 32_768);
  assert.equal(hash(bytes), photoReceiptHash);
  const receipt = JSON.parse(bytes);
  fields(receipt, {model_key: imageKey, publisher_id: publisher, source_url: photoSource, evidence_url: photoSource,
    license_url: photoSource, license_id: press.license_id, full_frame: true, review_filename: filename, width: 12302, height: 9227,
    asset_url: press.approved_asset_url, content_sha256: press.approved_source_sha256, source_content_sha256: press.approved_source_sha256});
  assert.match(receipt.metadata_sha256, /^[a-f0-9]{64}$/);
  assert.equal(hash(evidence(folder, receipt.metadata_sha256 + '.html')), receipt.metadata_sha256);
  assert.equal(hash(evidence(folder, pressReleaseHash + '.html')), pressReleaseHash);
  const keys = ['model_key','publisher_id','source_url','evidence_url','license_url','license_id','evidence_quote',
    'full_frame','content_sha256','source_content_sha256','metadata_sha256','author','credit'];
  return {...Object.fromEntries(keys.map(key => [key, receipt[key]])), status: 'documented', reviewed_at: '2026-11-21',
    asset_url: '/media/vehicles/' + filename, downloaded_from: receipt.asset_url, reviewed_candidate_sha256: photoReceiptHash,
    usage_scope: 'independent_vehicle_editorial', prohibited_uses: ['advertising','commercial_promotion','endorsement'],
    model_image_notice: 'Polestar 3 med 800 V. Bilden visar inte en viss svensk konfiguration.'};
}
function readPrivateImage(image) {
  assert.deepEqual(image, readPolestar3Image(), 'Require the exact reviewed 800 V model image');
  return evidence(join(privateRoot(), 'polestar-3-image-review-3cyf4kup'), filename, press.max_asset_bytes);
}

function validateIntake(intake, now) {
  fields(intake, {adapter: ADAPTER, model: MODEL});
  assert.equal(intake.sources.length, Object.keys(urls).length);
  for (const [name, url] of Object.entries(urls)) {
    const matches = intake.sources.filter(source => source.final_url === url);
    assert.equal(matches.length, 1);
    fields(matches[0], {source_type: types[name] ?? 'manufacturer_specs_page', country: 'SE', language: 'sv',
      source_authority: 'manufacturer', source_name: 'Polestar Sverige', shared: false});
  }
  const bind = (p, name, value, scope) => {
    fields(p, {value, scope, source_url: urls[name], source_hash: intake.sources.find(s => s.final_url === urls[name]).content_hash});
    assert(typeof p.quote === 'string' && p.quote.length > 5);
  };
  const {row, source, article, sheet} = intake.market;
  assert.equal(sheet, 'Elbil ranking');
  fields(row, {...market, needs_mapping: false, source_url: marketUrl, source_name: 'Mobility Sweden'});
  fields(source, {final_url: marketUrl, source_type: 'mobility_sweden_export', source_name: 'Mobility Sweden'});
  fields(article, {final_url: articleUrl, status: 'reachable', http_status: 200});
  assert.match(article.content_hash, /^[a-f0-9]{64}$/);
  assert(Math.abs(Date.parse(article.fetched_at) - Date.parse(source.fetched_at)) <= 180_000);
  assert(now - Date.parse(article.fetched_at) <= 900_000, 'Fresh market index required');
  bind(intake.model_evidence, 'overview.html', 'SUV', 'model_body');
  assert.equal(intake.drafts.length, 1);
  const draft = intake.drafts[0];
  fields(draft, {variant_name: variant, manufacturer_identity: identity, extraction_confidence: 1});
  assert.deepEqual(draft.facts, Object.fromEntries(Object.entries(reviewedFacts).map(([key,[value]]) => [key,value])));
  for (const [key, [value, name, scope]] of Object.entries(reviewedFacts)) bind(draft.field_evidence[key], name, value, scope);
  bind(draft.price_evidence, 'specs.html', 999000, 'manufacturer_listed_variant_price_sek');
  fields(draft.price_evidence, {price_type: 'list_price', price_valid_until: null});
  assert.match(draft.price_evidence.quote, /^Pris 999 000 kr$/);
  fields(draft.identity_evidence, {model_year: 2027, wheel_inches: 22, configuration_price_returned: false});
  bind(draft.identity_evidence.configuration, 'configuration.html', '359/DA/XPFWHE', 'swedish_b2c_cash_model_engine_and_standard_wheels');
  bind(draft.identity_evidence.powertrain, 'specs.html', 500, 'performance_column_kw');
}

export function readPolestar3Capture(path) {
  const folder = realpathSync(path);
  assert.equal(folder, resolve(path));
  assert.equal(dirname(folder), privateRoot());
  assert.match(basename(folder), /^polestar-3-review-[a-z0-9_]+$/i);
  const bytes = evidence(folder, 'review.json', 100_000);
  const report = JSON.parse(bytes);
  fields(report, {status: 'technical_source_review_held', model: 'Polestar 3', variant, market: 'SE',
    technical_manual_model_year: 2027, market_configuration_model_year: 2027, publication_approved: false, database_writes: 0, paid_calls: 0});
  execFileSync(process.execPath, ['scripts/run_python.mjs', 'scripts/polestar_3_review.py', '--replay', folder],
    {cwd: root, encoding: 'utf8', timeout: 45_000, windowsHide: true});
  const receipt = (name, p, type, source_name) => ({final_url: p.source_url, content_hash: p.source_hash, source_type: type,
    source_name, fetched_at: report.source_capture_times[name], status: 'reachable', http_status: 200});
  const proof = ({source_quote, ...rest}) => ({...rest, quote: source_quote});
  const sources = Object.keys(urls).map(name => ({...receipt(name, report.sources[name], types[name] ?? 'manufacturer_specs_page', 'Polestar Sverige'),
    country: 'SE', language: 'sv', source_authority: 'manufacturer', shared: false}));
  const row = report.market_index.row;
  const field_evidence = Object.fromEntries(Object.entries(report.facts).map(([key,p]) => [key,{...proof(p),variant_name:variant}]));
  const draft = {variant_name: variant, manufacturer_identity: identity, extraction_confidence: 1,
    facts: Object.fromEntries(Object.entries(report.facts).map(([key,p]) => [key,p.value])), field_evidence,
    price_evidence: {...proof(report.price),price_type:'list_price',price_valid_until:null},
    identity_evidence: {model_year: 2027, wheel_inches: report.configuration.wheel_inches,
      configuration_price_returned: report.configuration.configuration_price_returned,
      configuration: proof(report.configuration), powertrain: proof(report.powertrain)}};
  return {reviewHash: hash(bytes), intake: {adapter: ADAPTER, model: MODEL, model_evidence: proof(report.body), sources, drafts: [draft],
    market: {sheet: 'Elbil ranking', row: {...row, needs_mapping:false, source_url:marketUrl, source_name:'Mobility Sweden'},
      source: receipt('market.xlsx', report.market_index.sources['market.xlsx'], 'mobility_sweden_export','Mobility Sweden'),
      article: receipt('market.html', report.market_index.sources['market.html'], 'mobility_sweden_export','Mobility Sweden')}}};
}

function verifyPublic(rows, plan) {
  assert.equal(rows.length, 1);
  const draft = plan.targets[0].draft;
  fields(rows[0], {...draft.facts, brand: MODEL.brand, model: MODEL.model, body_type: MODEL.body_type, variant_name: variant,
    validation_status: 'published', market_seen: true, available_confirmed: plan.expected_model.available_confirmed,
    source_url: urls['specs.html'], price_source_url: urls['specs.html'], price_source_hash: draft.price_evidence.source_hash,
    price_sek: 999000, price_type: 'list_price', price_valid_until: null, image_url: plan.image.asset_url, image_source_url: photoSource});
}

export const policy = {adapter: ADAPTER, primaryUrl: urls['specs.html'], aliasRule: 'mobility_sweden_exact_raw_name',
  imageKey, imageHash: press.approved_source_sha256, maxVariants: 1, localOnly: true, readPrivateImage, validateIntake, verifyPublic};
