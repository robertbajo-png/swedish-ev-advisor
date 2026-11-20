import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { ADAPTER, prepareIdBuzzIntake } from './volkswagen_id_buzz_publication.mjs';
import { buildNewModelPlan, publicationHash, validateNewModelIntake } from './new_model_publication.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { replayCapture } from './volkswagen_id_buzz_configurator.mjs';

const hash = body => createHash('sha256').update(body).digest('hex');
const asJson = bytes => JSON.parse(bytes.toString('utf8'));
const one = (rows, message) => { assert.equal(rows.length, 1, message); return rows[0]; };
const dates = new Set(['first_seen_month', 'last_seen_month', 'month']);
const jsonRows = rows => JSON.parse(JSON.stringify(rows)).map(row => {
  for (const key of dates) if (row[key] != null) {
    assert.match(row[key], /^\d{4}-\d{2}-\d{2}(?:T00:00:00\.000Z)?$/);
    row[key] = row[key].slice(0, 10);
  }
  return row;
});

export function verifyReviewedConfigurations(review, replayed) {
  assert.equal(replayed.length, 2);
  assert.deepEqual(review.configurations, replayed, 'Reviewed configurations differ from the raw capture');
  for (const config of replayed) {
    const variant = one(review.variants.filter(v => v.trim === config.trim), 'Require one reviewed variant per configuration');
    assert.equal(variant.configuration_id, config.configuration_id, 'Reviewed variant uses a different configuration');
    const pairs = [
      [variant.facts.wltp_range_km, 'configured_wltp_range_km'],
      [variant.facts.wltp_consumption_kwh_100km, 'configured_wltp_consumption_kwh_100km'],
      [variant.price.manufacturer_base_cash, 'configured_cash_price_sek_including_vat'],
      [variant.observed_configurator_tow, 'configured_braked_towing_kg'],
    ];
    for (const [claim, metric] of pairs) {
      assert.equal(claim.source_url, config.summary.final_url, `Wrong configuration URL: ${metric}`);
      assert.equal(claim.value, config.summary.observations[metric].value, `Configuration value changed: ${metric}`);
      assert.equal(claim.quote, config.summary.observations[metric].quote, `Configuration quote changed: ${metric}`);
    }
  }
}

export async function readIdBuzzReview(path) {
  const root = await realpath('data/local/release-data');
  const folder = await realpath(path);
  assert.equal(dirname(root), await realpath('data/local'));
  assert.equal(dirname(await realpath('data/local')), await realpath('data'));
  assert.equal(dirname(await realpath('data')), await realpath('.'));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(root));
  assert.equal(dirname(folder), root, 'The review must remain in the project evidence directory');
  assert.match(basename(folder), /^volkswagen-id-buzz-review-[a-z0-9_]+$/i);
  const read = async name => {
    const path = join(folder, name);
    assert.equal(await realpath(path), path, 'Do not follow linked evidence files');
    return readFile(path);
  };
  const bytes = await read('review.json');
  const review = asJson(bytes);
  assert.equal(Object.keys(review.sources).length, 6);
  const names = new Set();
  for (const source of Object.values(review.sources)) {
    assert.match(source.text_file, /^source-\d+\.txt$/);
    assert(!names.has(source.text_file), 'Duplicate source artifact');
    names.add(source.text_file);
    assert.equal(hash(await read(source.text_file)), source.text_hash, 'Source artifact changed');
  }
  if (review.market) {
    assert.equal(review.market.workbook_file, 'mobility-october.xlsx');
    assert.equal(hash(await read(review.market.workbook_file)), review.market.source.content_hash, 'Market workbook changed');
  }
  assert.match(review.configurator_capture ?? '', /^volkswagen-id-buzz-configurator-[a-z0-9]+$/i, 'A fresh raw configurator capture is required');
  const configFolder = join(root, review.configurator_capture);
  assert.equal(await realpath(configFolder), configFolder, 'Do not follow linked captures');
  verifyReviewedConfigurations(review, await replayCapture(configFolder));
  return { review, reviewHash: hash(bytes), root };
}

export async function prepareIdBuzzReadback(client, intake, image, now = new Date()) {
  assert.equal(intake.adapter, ADAPTER);
  const policy = validateNewModelIntake(intake, now);
  assert(policy.localOnly);
  const rows = async (sql, params) => jsonRows((await client.query(sql, params)).rows);
  assert.equal((await rows('SHOW transaction_read_only'))[0]?.transaction_read_only, 'on', 'A read-only transaction is required');
  assert.equal((await rows('SHOW transaction_isolation'))[0]?.transaction_isolation, 'repeatable read', 'A repeatable read is required');
  const key = [intake.model.normalized_brand, intake.model.normalized_model];
  const models = await rows(`SELECT * FROM public.canonical_models WHERE normalized_brand=$1 AND normalized_model=$2`, key);
  const model = one(models, 'Require one existing ID. Buzz draft');
  assert.equal(model.validation_status, 'draft');
  const market = await rows(`SELECT * FROM public.market_models WHERE normalized_brand=$1 AND normalized_model=$2 AND fuel_type_raw='EL'`, key);
  const old = one(market, 'Require one existing Swedish electric market row');
  const canon = await rows('SELECT * FROM public.canonical_model_variants WHERE canonical_model_id=$1 ORDER BY id', [model.id]);
  const alias = await rows('SELECT * FROM public.model_aliases WHERE normalized_brand=$1 AND normalized_model=$2 ORDER BY id', key);
  const monthly = await rows('SELECT * FROM public.market_model_monthly_stats WHERE market_model_id=$1 ORDER BY id', [old.id]);
  const latest = monthly.filter(row => row.month === intake.market.row.last_seen_month && row.county === null && row.municipality === null);
  assert(latest.length <= 1, 'Ambiguous nationwide market count');
  if (latest.length) assert.equal(latest[0].registrations, intake.market.row.registrations_last_month, 'Existing market month disagrees');
  const sources = await rows('SELECT * FROM public.manufacturer_sources WHERE url=ANY($1::text[]) ORDER BY id', [intake.sources.map(s => s.final_url)]);
  for (const s of sources) {
    assert.equal(s.brand, model.brand, 'A source is registered for a different brand');
    assert.equal(s.model, model.model, 'A source is registered for a different model');
    assert([null, model.id].includes(s.canonical_model_id), 'A source is linked to a different model');
  }
  const plan = buildNewModelPlan({ canonical_models: models, market_models: market, model_aliases: alias,
    canonical_model_variants: canon, market_model_monthly_stats: monthly, manufacturer_sources: sources }, intake, image, now);
  assert.equal((await rows('SELECT id FROM public.canonical_model_variants WHERE id=ANY($1::uuid[]) OR source_id=ANY($2::uuid[])',
    [plan.targets.map(target => target.id), sources.map(s => s.id)])).length, 0, 'A target ID or source is already used');
  assert.equal((await rows('SELECT id FROM public.extracted_variant_drafts WHERE source_url=$1 AND variant_name=ANY($2::text[])',
    [policy.primaryUrl, intake.drafts.map(d => d.variant_name)])).length, 0, 'An existing draft needs separate review');
  const captureExpiry = Math.min(...[intake.market.source, ...intake.sources].map(s => Date.parse(s.fetched_at))) + 900000;
  assert(captureExpiry > now.getTime(), 'The evidence expired before preparation');
  return { status: 'ready_for_review', apply_allowed: false, production_writes: 0, paid_calls: 0,
    evidence_expires_at: new Date(captureExpiry).toISOString(), plan_hash: publicationHash(plan), plan };
}

async function main() {
  const { values } = parseArgs({ options: { review: { type: 'string' } } });
  assert(values.review, 'Supply the fresh private review directory');
  const { review, reviewHash, root } = await readIdBuzzReview(values.review);
  assert(review.market, 'A real market workbook is required, not the local test fixture');
  const intake = prepareIdBuzzIntake(review, review.market);
  validateNewModelIntake(intake);
  const registry = asJson(await readFile('src/image-rights.json'));
  const image = one(registry.assets.filter(v => v.model_key === 'volkswagen|id buzz'), 'Require the reviewed ID. Buzz image');
  const connectorPath = join(await realpath('data/local'), 'db-tools', 'source-client.mjs');
  assert.equal(await realpath(connectorPath), connectorPath, 'Require the existing local read-only connector');
  const { openSourceSnapshot, closeSourceSnapshot } = await import(pathToFileURL(connectorPath));
  let client;
  try {
    client = await openSourceSnapshot();
    useCalendarDateText(client);
    const report = await prepareIdBuzzReadback(client, intake, image);
    const output = await mkdtemp(join(root, 'volkswagen-id-buzz-readback-'));
    await writeFile(join(output, 'readback.json'), JSON.stringify({ ...report, review_hash: reviewHash }, null, 2) + '\n', { flag: 'wx' });
    console.log(JSON.stringify({ status: report.status, output, variants: report.plan.targets.length,
      existing_market_month: report.plan.expected_market.last_seen_month, historical_rows: report.plan.expected_monthly.length,
      evidence_expires_at: report.evidence_expires_at, apply_allowed: false, production_writes: 0, paid_calls: 0 }));
  } finally {
    if (client) await closeSourceSnapshot(client);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => {
    console.error(JSON.stringify({ status: 'held', error: error.name, code: error.code ?? null,
      ...(error.code === 'ERR_ASSERTION' ? { reason: error.message.split('\n')[0] } : {}), production_writes: 0 }));
    process.exitCode = 1;
  });
}
