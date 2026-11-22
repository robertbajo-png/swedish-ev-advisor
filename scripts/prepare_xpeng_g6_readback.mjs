import assert from 'node:assert/strict';
import { mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { buildNewModelPlan, publicationHash, validateNewModelIntake } from './new_model_publication.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { ADAPTER, readReviewedImage, readXpG6Capture } from './xpeng_g6_publication.mjs';

const one = (rows, message) => {
  assert.equal(rows.length, 1, message);
  return rows[0];
};
const dateFields = ['first_seen_month', 'last_seen_month', 'month'];

export async function prepareXpG6Readback(client, intake, image, now = new Date()) {
  assert.equal(intake.adapter, ADAPTER);
  const policy = validateNewModelIntake(intake, now);
  assert(policy.localOnly);
  const rows = async (sql, args) => JSON.parse(JSON.stringify((await client.query(sql, args)).rows)).map(row => {
    for (const field of dateFields) if (row[field] != null) {
      assert.match(row[field], /^\d{4}-\d{2}-\d{2}(?:T00:00:00\.000Z)?$/);
      row[field] = row[field].slice(0, 10);
    }
    return row;
  });
  assert.equal(one(await rows('SHOW transaction_read_only')).transaction_read_only, 'on', 'Read-only transaction required');
  assert.equal(one(await rows('SHOW transaction_isolation')).transaction_isolation, 'repeatable read', 'Repeatable read required');
  const key = ['xpeng', 'g6'];
  const models = await rows('SELECT * FROM public.canonical_models WHERE normalized_brand=$1 AND normalized_model=$2', key);
  const model = one(models, 'One G6 discovery draft required');
  assert.equal(model.validation_status, 'draft', 'Require the existing unpublished G6 discovery draft');
  const alias = await rows('SELECT * FROM public.model_aliases WHERE normalized_brand=$1 AND normalized_model=$2 ORDER BY id', key);
  const market = await rows("SELECT * FROM public.market_models WHERE normalized_brand=$1 AND normalized_model=$2 AND fuel_type_raw='EL'", key);
  const observed = one(market, 'One Swedish G6 BEV market row required');
  const monthly = await rows('SELECT * FROM public.market_model_monthly_stats WHERE market_model_id=$1 ORDER BY id', [observed.id]);
  const sameMonth = monthly.filter(r => r.month === intake.market.row.last_seen_month && r.county === null && r.municipality === null);
  assert(sameMonth.length <= 1, 'Ambiguous existing G6 nationwide count');
  if (sameMonth.length) assert.equal(sameMonth[0].registrations, intake.market.row.registrations_last_month, 'G6 market count conflict');
  const variants = await rows('SELECT * FROM public.canonical_model_variants WHERE canonical_model_id=$1 ORDER BY id', [model.id]);
  const sources = await rows('SELECT * FROM public.manufacturer_sources WHERE url=ANY($1::text[]) ORDER BY id', [intake.sources.map(s => s.final_url)]);
  for (const row of sources) {
    assert.equal(row.brand, model.brand, 'An exact source is already registered to another brand');
    assert.equal(row.model, model.model, 'An exact source is already registered to another model');
    assert([null, model.id].includes(row.canonical_model_id), 'An exact source is already linked elsewhere');
  }
  const plan = buildNewModelPlan({canonical_models: models, model_aliases: alias, market_models: market,
    market_model_monthly_stats: monthly, canonical_model_variants: variants, manufacturer_sources: sources}, intake, image, now);
  assert.equal((await rows('SELECT id FROM public.canonical_model_variants WHERE id=ANY($1::uuid[]) OR source_id=ANY($2::uuid[])',
    [plan.targets.map(target => target.id), sources.map(s => s.id)])).length, 0, 'Target ID or exact source is in use');
  assert.equal((await rows('SELECT id FROM public.extracted_variant_drafts WHERE source_url=$1 AND variant_name=ANY($2::text[])',
    [policy.primaryUrl, intake.drafts.map(d => d.variant_name)])).length, 0, 'An existing draft needs separate review');
  const evidenceExpiry = Math.min(...[intake.market.source, ...intake.sources].map(s => Date.parse(s.fetched_at))) + 900000;
  assert(evidenceExpiry > now.getTime(), 'Source evidence expired during preparation');
  return {status: 'ready_for_review', apply_allowed: false, production_writes: 0,
    evidence_expires_at: new Date(evidenceExpiry).toISOString(), plan_hash: publicationHash(plan), plan};
}

async function main() {
  const {values} = parseArgs({options: {review: {type: 'string'}}});
  assert(values.review, 'Supply the fresh private source review directory');
  const {intake, reviewHash} = readXpG6Capture(values.review);
  const image = readReviewedImage();
  validateNewModelIntake(intake);
  const evidence = await realpath(new URL('../data/local/release-data', import.meta.url));
  const local = await realpath(new URL('../data/local', import.meta.url));
  const connector = join(local, 'db-tools', 'source-client.mjs');
  assert.equal(await realpath(connector), connector, 'Require the local read-only connector');
  const {openSourceSnapshot, closeSourceSnapshot} = await import(pathToFileURL(connector).href);
  const client = await openSourceSnapshot();
  let review;
  try {
    useCalendarDateText(client);
    review = await prepareXpG6Readback(client, intake, image);
  } finally {
    await closeSourceSnapshot(client);
  }
  const output = join(await mkdtemp(join(evidence, 'xpeng-g6-readback-')), 'readback.json');
  await writeFile(output, JSON.stringify({...review, review_hash: reviewHash}, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({status: review.status, output, variants: review.plan.targets.length,
    historical_months: review.plan.expected_monthly.length, existing_exact_sources: review.plan.expected_sources.length,
    evidence_expires_at: review.evidence_expires_at, apply_allowed: false, production_writes: 0}));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(error => {
  console.error(JSON.stringify({status: 'held', error: error.name, code: error.code ?? null,
    ...(error.code === 'ERR_ASSERTION' ? {reason: error.message.split('\n')[0]} : {}), production_writes: 0}));
  process.exitCode = 1;
});
