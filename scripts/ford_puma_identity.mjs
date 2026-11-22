import assert from 'node:assert/strict';
import { mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const brand = 'ford';
const legacyKey = 'puma';
export const PUMA_MODEL = { brand: 'Ford', model: 'Puma Gen-E', normalized_brand: brand, normalized_model: 'puma gen e', body_type: 'SUV' };
export const PUMA_MARKET = { brand_raw: 'FORD', model_raw: 'PUMA', fuel_type_raw: 'EL', normalized_brand: brand, normalized_model: legacyKey };
export const PUMA_ALIAS = {
  brand_raw: 'FORD', model_raw: 'PUMA GEN-E', normalized_brand: brand, normalized_model: PUMA_MODEL.normalized_model,
  alias_rule: 'mobility_sweden_ford_puma_el_only_v1', model_group: null, needs_mapping: false, confidence: 1,
};
const normalizedKeys = [brand, [legacyKey, PUMA_MODEL.normalized_model]];
const rowFields = (row, expected, reason) => {
  for (const [key, value] of Object.entries(expected)) assert.equal(row?.[key], value, reason + ': ' + key);
};
const only = (rows, reason) => { assert.equal(rows.length, 1, reason); return rows[0]; };

export async function pumaIdentitySnapshot(client) {
  const rows = async (sql, params) => (await client.query(sql, params)).rows.map(row => row.row);
  const models = await rows('SELECT to_jsonb(m) AS row FROM public.canonical_models m WHERE normalized_brand=$1 AND normalized_model=ANY($2::text[]) ORDER BY id', normalizedKeys);
  const aliases = await rows('SELECT to_jsonb(a) AS row FROM public.model_aliases a WHERE normalized_brand=$1 AND normalized_model=ANY($2::text[]) ORDER BY id', normalizedKeys);
  const market = await rows('SELECT to_jsonb(m) AS row FROM public.market_models m WHERE normalized_brand=$1 AND normalized_model=ANY($2::text[]) ORDER BY id', normalizedKeys);
  const months = await rows('SELECT to_jsonb(s) AS row FROM public.market_model_monthly_stats s WHERE market_model_id=ANY($1::uuid[]) ORDER BY id', [market.map(m => m.id)]);
  const variants = await rows('SELECT to_jsonb(v) AS row FROM public.canonical_model_variants v WHERE canonical_model_id=ANY($1::uuid[]) ORDER BY id', [models.map(m => m.id)]);
  return { models, aliases, market, months, variants };
}

export function planPumaIdentity(snapshot) {
  const model = only(snapshot.models, 'Require only the unresolved Ford Puma parent before staging');
  rowFields(model, {brand: 'Ford', model: 'Puma', normalized_brand: brand, normalized_model: legacyKey, validation_status: 'draft'}, 'Generic parent changed');
  const alias = only(snapshot.aliases, 'Gen-E or another overlapping Ford Puma alias already exists');
  rowFields(alias, {canonical_model_id: model.id, brand_raw: 'FORD', model_raw: 'PUMA',
    normalized_brand: brand, normalized_model: legacyKey, alias_rule: 'mobility_sweden_exact_raw_name',
    needs_mapping: false, model_group: null}, 'Generic Puma alias changed');
  assert.equal(snapshot.variants.length, 0, 'Existing Puma variants require separate review');
  const market = only(snapshot.market.filter(row => row.fuel_type_raw === 'EL'), 'Require exactly one Puma BEV market row');
  rowFields(market, {...PUMA_MARKET, canonical_model_id: null, model_group: null, needs_mapping: false,
    source_name: 'Mobility Sweden'}, 'Exact unlinked Mobility Sweden BEV row required');
  const other = snapshot.market.filter(row => row.id !== market.id);
  for (const row of other) {
    assert.equal(row.normalized_model, legacyKey, 'Distinct Gen-E market candidate needs separate review');
    assert([null, model.id].includes(row.canonical_model_id), 'Unexpected non-BEV Puma mapping');
  }
  const months = snapshot.months.filter(row => row.market_model_id === market.id);
  for (const row of months) rowFields(row, {brand_raw: 'FORD', model_raw: 'PUMA', fuel_type_raw: 'EL'}, 'Mixed Puma registration history');
  const nationwide = months.filter(row => row.county === null && row.municipality === null);
  assert(nationwide.some(row => row.month === market.first_seen_month && row.registrations > 0), 'Require original BEV registration month');
  assert.equal(new Set(nationwide.map(row => row.month)).size, nationwide.length, 'Duplicate national Puma registration month');
  return {
    status: 'puma_bev_identity_plan_private', target_model: PUMA_MODEL, target_alias: PUMA_ALIAS,
    expected: snapshot, market_id: market.id, bev_historical_rows: months.length,
    preserved_non_bev_rows: other.length, publication_approved: false, production_writes: 0,
  };
}

export async function readPumaIdentity(client) {
  const readOnly = await client.query('SHOW transaction_read_only');
  const isolation = await client.query('SHOW transaction_isolation');
  assert.equal(readOnly.rows[0]?.transaction_read_only, 'on', 'Require a read-only transaction');
  assert.equal(isolation.rows[0]?.transaction_isolation, 'repeatable read', 'Require repeatable read');
  return planPumaIdentity(await pumaIdentitySnapshot(client));
}

export async function stagePumaIdentityLocally(db, reviewed) {
  const { PGlite } = await import('@electric-sql/pglite');
  assert(db instanceof PGlite, 'Puma identity staging requires a local PGlite database');
  await db.exec('BEGIN ISOLATION LEVEL SERIALIZABLE READ WRITE');
  try {
    const staged = await writePumaIdentityInLocalTransaction(db, reviewed);
    await db.exec('COMMIT');
    return staged;
  } catch (error) {
    await db.exec('ROLLBACK');
    throw error;
  }
}

export async function writePumaIdentityInLocalTransaction(db, reviewed, ids = {}) {
  const { PGlite } = await import('@electric-sql/pglite');
  assert(db instanceof PGlite && db.isInTransaction(), 'Puma identity requires an open local PGlite transaction');
  return writeReviewedPumaIdentity(db, reviewed, ids);
}

// Only call from the scoped Puma transaction, after its source and approval checks.
export async function writeReviewedPumaIdentity(db, reviewed, ids) {
  const readOnly = await db.query('SHOW transaction_read_only');
  const isolation = await db.query('SHOW transaction_isolation');
  assert.equal(readOnly.rows[0]?.transaction_read_only, 'off', 'Puma identity needs the scoped write transaction');
  assert.equal(isolation.rows[0]?.transaction_isolation, 'serializable', 'Puma identity needs serializable isolation');
  const before = await pumaIdentitySnapshot(db);
    assert.deepEqual(planPumaIdentity(before), reviewed, 'Puma identity changed since review');
    const {rows: [model]} = await db.query(
      'INSERT INTO public.canonical_models(brand,model,normalized_brand,normalized_model,body_type,id) VALUES($1,$2,$3,$4,$5,COALESCE($6::uuid,gen_random_uuid())) RETURNING id',
      [...Object.values(PUMA_MODEL), ids.model_id ?? null]);
    const {rows: [alias]} = await db.query(
      'INSERT INTO public.model_aliases(canonical_model_id,brand_raw,model_raw,normalized_brand,normalized_model,alias_rule,id) VALUES($1,$2,$3,$4,$5,$6,COALESCE($7::uuid,gen_random_uuid())) RETURNING id',
      [model.id, PUMA_ALIAS.brand_raw, PUMA_ALIAS.model_raw, PUMA_ALIAS.normalized_brand, PUMA_ALIAS.normalized_model, PUMA_ALIAS.alias_rule, ids.alias_id ?? null]);
    const linked = await db.query(
      "UPDATE public.market_models SET canonical_model_id=$1 WHERE id=$2 AND canonical_model_id IS NULL AND brand_raw='FORD' AND model_raw='PUMA' AND fuel_type_raw='EL' RETURNING id",
      [model.id, reviewed.market_id]);
    assert.deepEqual(linked.rows, [{id: reviewed.market_id}], 'Exact BEV-only link was not staged');
    const after = await pumaIdentitySnapshot(db);
    rowFields(after.models.find(row => row.id === model.id), {...PUMA_MODEL, validation_status: 'draft'}, 'Gen-E draft changed');
    const savedAlias = after.aliases.find(row => row.id === alias.id);
    rowFields({...savedAlias, confidence: Number(savedAlias.confidence)},
      {...PUMA_ALIAS, canonical_model_id: model.id}, 'Gen-E alias changed');
    assert.deepEqual(after.models.filter(row => row.id !== model.id), before.models);
    assert.deepEqual(after.aliases.filter(row => row.id !== alias.id), before.aliases);
    assert.deepEqual(after.market, before.market.map(row => row.id === reviewed.market_id ? {...row, canonical_model_id: model.id} : row));
    assert.deepEqual(after.months, before.months);
    assert.deepEqual(after.variants, before.variants);
    return {model_id: model.id, alias_id: alias.id, market_id: reviewed.market_id};
}

async function main() {
  assert.equal(process.argv.length, 2, 'Only read-only identity preparation is supported');
  const root = await realpath(fileURLToPath(new URL('../', import.meta.url)));
  assert.equal(await realpath('.'), root);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(root));
  const evidence = join(root, 'data', 'local', 'release-data');
  const connector = join(root, 'data', 'local', 'db-tools', 'source-client.mjs');
  assert.equal(await realpath(evidence), evidence);
  assert.equal(await realpath(connector), connector);
  const {openSourceSnapshot, closeSourceSnapshot} = await import(pathToFileURL(connector).href);
  const client = await openSourceSnapshot();
  let plan;
  try { plan = await readPumaIdentity(client); }
  finally { await closeSourceSnapshot(client); }
  const output = join(await mkdtemp(join(evidence, 'ford-puma-identity-')), 'readback.json');
  await writeFile(output, JSON.stringify({checked_at: new Date().toISOString(), ...plan}, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({status: plan.status, output, bev_historical_rows: plan.bev_historical_rows,
    preserved_non_bev_rows: plan.preserved_non_bev_rows, publication_approved: false, production_writes: 0}));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(error => {
  console.error(JSON.stringify({status: 'held', code: error.code ?? null,
    ...(error.code === 'ERR_ASSERTION' ? {reason: error.message.split('\n')[0]} : {}), production_writes: 0}));
  process.exitCode = 1;
});
