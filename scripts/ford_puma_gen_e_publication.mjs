import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PUMA_ALIAS, PUMA_MARKET, PUMA_MODEL } from './ford_puma_identity.mjs';
import { MANUFACTURER_FROM_PRICE } from '../src/price-evidence.js';

const root = realpathSync(fileURLToPath(new URL('../', import.meta.url)));
export const ADAPTER = 'ford_puma_gen_e_sweden_my27_local_v2';
const imageKey = 'ford|puma gen e';
const pressPublisher = 'ford-puma-gen-e-private-review';
const photoPolicy = JSON.parse(readFileSync(join(root, 'src', 'press-image-publishers.json'), 'utf8'))[pressPublisher];
const imageHash = photoPolicy.approved_source_sha256;
const photoUrl = photoPolicy.origin + photoPolicy.approved_image_paths[0];
const photoFilename = 'ford-puma-gen-e-press-' + imageHash.slice(0, 12) + '.jpg';
const photoReceiptHash = '8251e64e17f567759a40ef20786ed02c241653cf1a82c71d793d15be0c59f0ea';
const primary = 'https://www.ford.se/bilar/personbilar-och-suver/puma-gen-e';
const priceUrl = 'https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/fordsesite/cardocuments/puma-gen-e/prislista-puma-gen-e.pdf';
const sheetUrl = 'https://mnd-assets.mynewsdesk.com/image/upload/f_pdf,fl_attachment/azzjl64uf6du139svior94';
const dkPrices = 'https://katalog.ford.dk/prislister/personbiler/puma_gen-E/';
const dkTech = 'https://katalog.ford.dk/specifikationer/puma-gen-e/';
const workbook = 'https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx';
const marketArticle = 'https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober';
const sourceSpecs = [
  ['model.html', primary, 'manufacturer_page', 'SE', 'sv'],
  ['prices.pdf', priceUrl, 'price_list_pdf', 'SE', 'sv'],
  ['ford-se-factsheet.pdf', sheetUrl, 'technical_pdf', 'SE', 'en'],
  ['ford-dk-prices.html', dkPrices, 'price_list', 'DK', 'da'],
  ['ford-dk-technical.html', dkTech, 'manufacturer_specs_page', 'DK', 'da'],
].map(([name, final_url, source_type, country, language]) => ({
  name, final_url, source_type, country, language, source_authority: 'manufacturer',
  source_name: country === 'SE' ? 'Ford Sverige' : 'Ford Danmark', shared: false,
}));
const marketRow = {...PUMA_MARKET, source_name: 'Mobility Sweden', source_url: workbook, needs_mapping: false,
  last_seen_month: '2026-10-01', registrations_last_month: 37, registrations_ytd: 382};
const profiles = [
  ['Gen-E', '168hk-46.8kwh', 389000, 397000, 417, 13],
  ['Gen-E Premium', 'premium-168hk-46.8kwh', 409000, 414000, 404, 13.7],
].map(([sourceName, code, price, listPrice, wltp_range_km, wltp_consumption_kwh_100km], index) => ({
  sourceName, variant: index === 0 ? '168 hk' : 'Premium 168 hk', identity: 'se-my27-' + code, price, listPrice,
  facts: {wltp_range_km, wltp_consumption_kwh_100km, battery_kwh: 46.8, dc_charge_kw: 100, ac_charge_kw: 11,
    boot_liters: 523, tow_kg: 750, seats: 5, drivetrain: 'FWD'},
}));
const sourceForField = {
  wltp_range_km: priceUrl, wltp_consumption_kwh_100km: priceUrl, battery_kwh: priceUrl, dc_charge_kw: priceUrl,
  ac_charge_kw: priceUrl, boot_liters: primary, tow_kg: sheetUrl, seats: sheetUrl, drivetrain: primary,
};
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const fields = (record, expected, label) => {
  for (const [key, value] of Object.entries(expected)) assert.equal(record?.[key], value, label + ': ' + key);
};

function privateRoot() {
  const dir = join(root, 'data', 'local', 'release-data');
  assert.equal(realpathSync(dir), dir);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(dir));
  return dir;
}

function evidence(folder, name) {
  assert.equal(basename(name), name);
  const file = join(folder, name);
  assert.equal(realpathSync(file), file);
  return readFileSync(file);
}

export function readPumaImage() {
  const folder = join(privateRoot(), 'ford-puma-original-a1462827');
  const bytes = evidence(folder, 'puma gen e-mynewsdesk-3363679.json');
  assert.equal(hash(bytes), photoReceiptHash);
  const receipt = JSON.parse(bytes);
  fields(receipt, {model_key: imageKey, source_url: photoUrl, publisher_id: pressPublisher, width: 7334, height: 4889,
    content_sha256: imageHash, source_content_sha256: imageHash, original_url: photoPolicy.approved_asset_url,
    review_filename: photoFilename, full_frame: true}, 'Unexpected Puma press photo');
  assert.match(receipt.metadata_sha256, /^[a-f0-9]{64}$/);
  assert.equal(hash(evidence(folder, receipt.metadata_sha256 + '.html')), receipt.metadata_sha256);
  const asset = Object.fromEntries(['model_key', 'source_url', 'evidence_url', 'license_url', 'license_id', 'evidence_quote',
    'publisher_id', 'author', 'credit', 'content_sha256', 'source_content_sha256', 'metadata_sha256', 'full_frame']
    .map(key => [key, receipt[key]]));
  return {...asset, asset_url: '/media/vehicles/' + photoFilename, downloaded_from: receipt.asset_url,
    original_url: receipt.original_url, status: 'documented', reviewed_at: '2026-11-21',
    reviewed_candidate_sha256: photoReceiptHash, usage_scope: 'independent_vehicle_editorial',
    prohibited_uses: ['advertising', 'commercial_promotion', 'endorsement'],
    model_image_notice: 'Pressbild av Ford Puma Gen-E. Utrustningen kan skilja mellan versioner.'};
}

export function readPrivatePumaImage(image) {
  assert.deepEqual(image, readPumaImage(), 'Require the exact reviewed Gen-E photo');
  return evidence(join(privateRoot(), 'ford-puma-original-a1462827'), photoFilename);
}

function validateIntake(intake) {
  assert.equal(intake.adapter, ADAPTER);
  assert.deepEqual(intake.model, PUMA_MODEL);
  assert.deepEqual(intake.market.row, marketRow);
  assert.equal(intake.market.sheet, 'Elbil ranking');
  assert.equal(intake.market.source.final_url, workbook);
  fields(intake.market.article, {final_url: marketArticle, status: 'reachable', http_status: 200}, 'Invalid October report');
  assert.match(intake.market.article.content_hash, /^[a-f0-9]{64}$/);
  assert(Math.abs(Date.parse(intake.market.article.fetched_at) - Date.parse(intake.market.source.fetched_at)) <= 120000);
  assert.equal(intake.sources.length, sourceSpecs.length);
  const byUrl = new Map(intake.sources.map(row => [row.final_url, row]));
  for (const {name: _name, ...source} of sourceSpecs) fields(byUrl.get(source.final_url), source, 'Puma source changed');
  const bind = (proof, url, value) => {
    fields(proof, {value, source_url: url, source_hash: byUrl.get(url)?.content_hash}, 'Puma field evidence changed');
    assert(proof.quote?.trim());
  };
  bind(intake.model_evidence, primary, 'SUV');
  assert.equal(intake.drafts.length, profiles.length);
  for (const {variant, sourceName, identity, price, listPrice, facts} of profiles) {
    const draft = intake.drafts.find(row => row.variant_name === variant);
    fields(draft, {manufacturer_identity: identity, extraction_confidence: 1}, 'Puma trim changed');
    assert.deepEqual(draft.facts, facts);
    fields(draft.identity_evidence, {model_year: 2027, swedish_price_row: sourceName}, 'Puma model year changed');
    for (const [field, value] of Object.entries(facts)) bind(draft.field_evidence[field], sourceForField[field], value);
    const p = draft.price_evidence;
    bind(p, primary, price);
    fields(p, {scope: 'swedish_trim_card_manufacturer_from', price_type: MANUFACTURER_FROM_PRICE,
      price_valid_until: null}, 'Require the manufacturer starting price, not list price');
    const displayed = String(price).replace(/(\d)(\d{3})$/, '$1 $2');
    assert(p.quote.startsWith('Puma ' + sourceName + ' Pris fr\u00e5n ' + displayed + ' kr. FWD 168 hk '));
    bind(p.corroboration, priceUrl, price);
    assert.equal(p.corroboration.scope, 'swedish_my27_edition_column_matches_model_card');
    bind(p.ordinary_price_reference, priceUrl, listPrice);
    assert.equal(p.ordinary_price_reference.scope, 'swedish_recommended_price_column');
    const battery = draft.field_evidence.battery_kwh;
    assert.equal(battery.scope, 'swedish_my27_capacity_confirmed_usable_by_ford_dk_my27');
    bind(battery.corroboration[0], dkPrices, facts.battery_kwh);
    const tow = draft.field_evidence.tow_kg;
    assert.equal(tow.scope, 'braked_12_percent_gradient_requires_towbar');
    bind(tow.corroboration[0], dkPrices, facts.tow_kg);
    bind(tow.corroboration[1], priceUrl, true);
    const cargo = draft.field_evidence.boot_liters;
    assert.equal(cargo.scope, 'rear_to_seatback_including_gigabox_excluding_frunk');
    bind(cargo.corroboration[0], sheetUrl, facts.boot_liters);
    bind(cargo.corroboration[1], dkTech, facts.boot_liters);
  }
}

export function readPumaCapture(path) {
  const folder = realpathSync(path);
  assert.equal(folder, resolve(path));
  assert.equal(dirname(folder), privateRoot());
  assert.match(basename(folder), /^ford-puma-review-[a-z0-9_]+$/);
  const input = evidence(folder, 'review.json');
  const result = JSON.parse(execFileSync(process.execPath, ['scripts/run_python.mjs', 'scripts/ford_puma_gen_e_review.py',
    '--replay', folder], {cwd: root, timeout: 90000, windowsHide: true}));
  assert.deepEqual([result.variants, result.fields, result.publication_approved], [2, 18, false]);
  assert.equal(hash(evidence(folder, 'review.json')), hash(input));
  const review = JSON.parse(input);
  assert.deepEqual([review.brand, review.model, review.market, review.production_writes, review.paid_calls], ['Ford', 'Puma Gen-E', 'SE', 0, 0]);
  const receipt = (name, url) => {
    assert.equal(review.sources[name].source_url, url);
    return {final_url: url, content_hash: review.sources[name].source_hash, fetched_at: review.source_capture_times[name],
      http_status: 200, status: 'reachable'};
  };
  const proof = ({source_quote, corroboration, ...p}) => ({...p, quote: source_quote,
    ...(corroboration ? {corroboration: corroboration.map(proof)} : {})});
  const drafts = profiles.map(profile => {
    const row = review.variants.find(item => item.variant === profile.sourceName);
    return {variant_name: profile.variant, manufacturer_identity: profile.identity, extraction_confidence: 1,
      identity_evidence: {model_year: row.model_year, swedish_price_row: row.variant},
      price_evidence: {...proof(row.facts.drivetrain), value: row.edition_price_reference.value,
        scope: 'swedish_trim_card_manufacturer_from', price_type: MANUFACTURER_FROM_PRICE, price_valid_until: null,
        corroboration: {...proof(row.edition_price_reference), scope: 'swedish_my27_edition_column_matches_model_card'},
        ordinary_price_reference: proof(row.list_price)},
      facts: Object.fromEntries(Object.entries(row.facts).map(([key, p]) => [key, p.value])),
      field_evidence: Object.fromEntries(Object.entries(row.facts).map(([key, p]) =>
        [key, {...proof(p), variant_name: profile.variant}])),
    };
  });
  const intake = {adapter: ADAPTER, model: PUMA_MODEL, model_evidence: proof(review.model_evidence),
    drafts, sources: sourceSpecs.map(({name, ...meta}) => ({...receipt(name, meta.final_url), ...meta})),
    market: {sheet: 'Elbil ranking', source: receipt('market.xlsx', workbook), article: receipt('market.html', marketArticle), row: review.market_index}};
  validateIntake(intake);
  return {intake, reviewHash: hash(input)};
}

function checkDiscovery(snapshot, model, market) {
  fields(market, {...PUMA_MARKET, canonical_model_id: model.id}, 'Gen-E must be staged against the exact EL row');
  const parents = snapshot.canonical_models.filter(row => row.normalized_brand === 'ford' && row.normalized_model === 'puma');
  assert.equal(parents.length, 1);
  const legacy = parents[0];
  fields(legacy, {brand: 'Ford', model: 'Puma', validation_status: 'draft'}, 'Generic Puma parent must remain separate');
  const aliases = snapshot.model_aliases.filter(row => row.normalized_brand === 'ford' && row.normalized_model === 'puma');
  assert.equal(aliases.length, 1);
  fields(aliases[0], {canonical_model_id: legacy.id, brand_raw: 'FORD', model_raw: 'PUMA',
    alias_rule: 'mobility_sweden_exact_raw_name'}, 'Generic Puma alias must remain separate');
  const linked = snapshot.market_models.filter(row => row.canonical_model_id === model.id);
  assert.deepEqual(linked, [market], 'No other fuel or model may borrow the Puma Gen-E identity');
}

function verifyPublic(rows, plan) {
  assert.equal(rows.length, profiles.length);
  for (const {variant, facts, price} of profiles) {
    const matching = rows.filter(row => row.variant_name === variant);
    assert.equal(matching.length, 1);
    fields(matching[0], {...facts, model: 'Puma Gen-E', brand: 'Ford', body_type: 'SUV',
      price_sek: price, price_type: MANUFACTURER_FROM_PRICE, price_valid_until: null, validation_status: 'published', market_seen: true,
      source_url: primary, price_source_url: primary, image_url: plan.image.asset_url, image_source_url: photoUrl}, 'Anonymous Gen-E readback changed');
  }
}

export const policy = {adapter: ADAPTER, primaryUrl: primary, aliasRule: PUMA_ALIAS.alias_rule, imageKey, imageHash,
  maxVariants: 2, mixedSources: true, localOnly: true, scopedDiscovery: {alias: PUMA_ALIAS, market: PUMA_MARKET, check: checkDiscovery},
  readPrivateImage: readPrivatePumaImage, validateIntake, verifyPublic};
