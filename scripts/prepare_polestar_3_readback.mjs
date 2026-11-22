import assert from 'node:assert/strict';
import { mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const key = ['polestar', '3'];
const exactMarketName = row => [row.brand_raw, row.model_raw].join('|') === 'POLESTAR|3';

function one(rows, reason) {
  assert.equal(rows.length, 1, reason);
  return rows[0];
}

export async function readPolestar3Identity(client) {
  const rows = async (sql, params) => (await client.query(sql, params)).rows;
  assert.equal(one(await rows('SHOW transaction_read_only')).transaction_read_only, 'on', 'Read-only transaction required');
  assert.equal(one(await rows('SHOW transaction_isolation')).transaction_isolation, 'repeatable read', 'Repeatable read required');

  const model = one(await rows(`SELECT id, brand, model, body_type, validation_status
    FROM public.canonical_models WHERE normalized_brand=$1 AND normalized_model=$2`, key),
    'Require one existing Polestar 3 canonical identity');
  assert.deepEqual([model.brand, model.model, model.validation_status], ['Polestar', '3', 'draft']);
  assert([null, 'SUV'].includes(model.body_type), 'Unexpected current Polestar 3 body type');

  const alias = one(await rows(`SELECT id, canonical_model_id, brand_raw, model_raw, alias_rule, needs_mapping
    FROM public.model_aliases WHERE normalized_brand=$1 AND normalized_model=$2`, key),
    'Require one exact Polestar 3 alias');
  assert(exactMarketName(alias), 'Polestar 3 raw alias changed');
  assert.deepEqual([alias.canonical_model_id, alias.alias_rule, alias.needs_mapping],
    [model.id, 'mobility_sweden_exact_raw_name', false], 'Polestar 3 requires an unambiguous alias');

  const market = one(await rows(`SELECT id, canonical_model_id, brand_raw, model_raw, fuel_type_raw, needs_mapping,
      first_seen_month::text, last_seen_month::text
    FROM public.market_models WHERE normalized_brand=$1 AND normalized_model=$2 AND fuel_type_raw='EL'`, key),
    'Require one Swedish Polestar 3 BEV market record');
  assert(exactMarketName(market) && market.fuel_type_raw === 'EL' && market.needs_mapping === false &&
    [null, model.id].includes(market.canonical_model_id), 'Polestar 3 BEV source mapping changed');
  const monthly = await rows(`SELECT month::text, registrations FROM public.market_model_monthly_stats
    WHERE market_model_id=$1 AND county IS NULL AND municipality IS NULL ORDER BY month`, [market.id]);
  assert(monthly.length > 0 && new Set(monthly.map(row => row.month)).size === monthly.length,
    'Require non-overlapping nationwide registration history');
  assert(monthly.some(row => row.month === market.first_seen_month && row.registrations > 0),
    'First Swedish activity month needs source history');

  const variants = await rows('SELECT id FROM public.canonical_model_variants WHERE canonical_model_id=$1', [model.id]);
  assert.equal(variants.length, 0, 'Existing Polestar 3 variants need a separate review');
  const count = one(await rows(`SELECT count(*)::int AS count FROM public.public_ev_variants
    WHERE lower(brand)=$1 AND model=$2`, key)).count;
  assert.equal(count, 0, 'Polestar 3 is already in the public catalog');

  return { status: 'polestar_3_identity_verified', model, alias, market, nationwide_months: monthly,
    existing_variants: 0, public_variants: 0, publication_approved: false, production_writes: 0 };
}

async function main() {
  assert.equal(process.argv.length, 2, 'No arguments or apply mode supported');
  const repo = await realpath(fileURLToPath(new URL('../', import.meta.url)));
  assert.equal(await realpath(process.cwd()), repo, 'Run from the repository root');
  const local = join(repo, 'data', 'local');
  const evidence = join(local, 'release-data');
  const connector = join(local, 'db-tools', 'source-client.mjs');
  assert.equal(await realpath(evidence), evidence, 'Require the repository private review directory');
  assert.equal(await realpath(connector), connector, 'Require the local read-only connector');
  assert(!repo.split(/[\\/]/).some(part => /^onedrive(?:commercial|consumer)?$/i.test(part)), 'Repository must be local');
  const { openSourceSnapshot, closeSourceSnapshot } = await import(pathToFileURL(connector).href);
  const client = await openSourceSnapshot();
  let report;
  try {
    report = await readPolestar3Identity(client);
  } finally {
    await closeSourceSnapshot(client);
  }
  const output = join(await mkdtemp(join(evidence, 'polestar-3-readback-')), 'readback.json');
  await writeFile(output, JSON.stringify({ checked_at: new Date().toISOString(), ...report }, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({ status: report.status, output, historical_months: report.nationwide_months.length,
    public_variants: report.public_variants, publication_approved: false, production_writes: 0 }));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(error => {
  console.error(JSON.stringify({ status: 'held', code: error.code ?? null,
    ...(error.code === 'ERR_ASSERTION' ? { reason: error.message.split('\n')[0] } : {}), production_writes: 0 }));
  process.exitCode = 1;
});
