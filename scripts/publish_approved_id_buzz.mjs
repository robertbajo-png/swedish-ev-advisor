import assert from 'node:assert/strict';
import { mkdir, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { loadEnv } from 'vite';
import { applyIdBuzzRelease, assertIdBuzzReleaseScope } from './new_model_publication.mjs';
import { prepareIdBuzzReadback, readIdBuzzReview } from './prepare_id_buzz_readback.mjs';
import { ADAPTER, prepareIdBuzzIntake } from './volkswagen_id_buzz_publication.mjs';
import { atomicJson, catalogHash, compareCatalogs, fetchCatalog, SOURCE, variantKey } from './sync_public_catalog.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';

const catalogFile = 'public/data/public_ev_variants.json';
const projectRef = 'eutcryxbitudllcnpnex';
const json = async path => JSON.parse(await readFile(path, 'utf8'));
const saveNew = (path, value) => writeFile(path, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });

function publicConfig(root) {
  const env = { ...loadEnv('production', root, 'SUPABASE_'), ...loadEnv('production', root, 'VITE_SUPABASE_') };
  const url = env.SUPABASE_URL || env.VITE_SUPABASE_URL;
  assert.equal(new URL(url).origin, `https://${projectRef}.supabase.co`, 'Unexpected canonical public project');
  return { url, key: env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY };
}

async function exportApprovedCatalog(config, baseline, eligible, folder, plan) {
  let missing;
  const rows = await fetchCatalog({ ...config, onSchema: fields => { missing = fields; } });
  const hash = catalogHash(rows);
  assert.equal(catalogHash(await fetchCatalog(config)), hash, 'Public rows changed during export');
  const diff = compareCatalogs(baseline.records, rows);
  assert.deepEqual(diff.local_only, [], 'Existing public rows disappeared');
  assert.deepEqual(diff.changed, [], 'Existing public rows changed');
  assert.deepEqual(diff.remote_only.sort(), eligible, 'Only the two approved rows can be exported');
  for (const target of plan.targets) {
    const { draft } = target;
    const row = rows.find(r => r.brand === 'Volkswagen' && r.model === 'Id. Buzz' && r.variant_name === draft.variant_name);
    assert(row, 'Missing released ID. Buzz variant');
    assert.equal(row.price_type, 'dealer_offer');
    assert.equal(row.price_source_hash, draft.price_evidence.source_hash);
    assert.equal(row.price_source_url, draft.price_evidence.source_url);
    assert.equal(row.price_sek, draft.price_evidence.value);
    assert.equal(row.price_valid_until, draft.price_evidence.price_valid_until);
    assert.equal(row.image_url, plan.image.asset_url);
    for (const [field, value] of Object.entries(draft.facts)) assert.equal(row[field], value);
  }
  await atomicJson(catalogFile, { generated_at: new Date().toISOString(), source: SOURCE, schema_version: 1,
    missing_view_columns: missing, catalog_sha256: hash, records: rows });
  await atomicJson(join(folder, 'export-receipt.json'), { added: eligible, preserved: baseline.records.length,
    count: rows.length, catalog_sha256: hash, paid_calls: 0 });
  return { added: eligible.length, preserved: baseline.records.length, catalog_sha256: hash };
}

export async function publishApprovedIdBuzz(values) {
  assert.equal(values.adapter, ADAPTER);
  assert(!(values['prepare-only'] && values['export-only']));
  assert.match(values.apply ?? '', /^[a-f0-9]{64}$/, 'Supply the exact approved plan hash');
  assert(values['client-module'] && values.output !== 'data/local/release-data/kia-ev2-pilot-2026-11-15/publication');
  const local = await realpath('data/local/release-data');
  const folder = resolve(values.output);
  assert.equal(dirname(folder), local, 'Keep receipts in the private release directory');
  assert.match(basename(folder), /^volkswagen-id-buzz-release-[a-z0-9-]+$/i);
  const approvedPath = await realpath(values['approved-plan']);
  assert.equal(dirname(dirname(approvedPath)), local, 'Require a locally reviewed receipt');
  assert.equal(basename(approvedPath), 'readback.json');
  const approved = await json(approvedPath);
  assert.equal(approved.plan_hash, values.apply, 'Wrong approved receipt');
  const connectorPath = await realpath(values['client-module']);
  const sourceRoot = resolve(dirname(connectorPath), '../../..');
  assert.equal(connectorPath, join(sourceRoot, 'data', 'local', 'db-tools', 'source-client.mjs'), 'Unexpected connector path');
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(sourceRoot));
  assert(!isAbsolute(relative(sourceRoot, local)) && !relative(sourceRoot, local).startsWith('..'), 'Use the existing project connector');
  const config = publicConfig(sourceRoot);
  if (values['export-only']) {
    assert.equal(await realpath(folder), folder);
    const { result, plan, baseline, approved_hash, eligible } = await json(join(folder, 'committed-receipt.json'));
    assert(result.committed && result.variants_inserted === 2 && approved_hash === values.apply);
    assert.equal(catalogHash((await json(catalogFile)).records), catalogHash(baseline.records), 'Release export requires the original checked-in catalog');
    console.log(JSON.stringify(await exportApprovedCatalog(config, baseline, eligible, folder, plan)));
    return;
  }
  const { review, reviewHash } = await readIdBuzzReview(values.review);
  assert(review.market, 'The fetched Mobility Sweden workbook is required');
  const intake = prepareIdBuzzIntake(review, review.market);
  const image = (await json('src/image-rights.json')).assets.filter(row => row.model_key === 'volkswagen|id buzz');
  assert.equal(image.length, 1);
  const baseline = await json(catalogFile);
  assert.equal(catalogHash(await fetchCatalog(config)), catalogHash(baseline.records), 'Production catalog differs from the release baseline');
  const openConnector = await import(pathToFileURL(connectorPath));
  assert.equal(openConnector.PROJECT_REF, projectRef);
  const workingDirectory = process.cwd();
  let client;
  try {
    try {
      process.chdir(sourceRoot);
      client = await openConnector.openSourceSnapshot();
    } finally {
      process.chdir(workingDirectory);
    }
    useCalendarDateText(client);
    const fresh = await prepareIdBuzzReadback(client, intake, image[0]);
    assertIdBuzzReleaseScope(fresh, approved, values.apply);
    if (values['prepare-only']) {
      console.log(JSON.stringify({ scope_matched: true, variants: fresh.plan.targets.length,
        evidence_expires_at: fresh.evidence_expires_at, production_writes: 0, paid_calls: 0 }));
      return;
    }
    await client.query('ROLLBACK');
    const eligible = fresh.plan.targets.map(({ draft }) => variantKey({ ...intake.model, variant_name: draft.variant_name })).sort();
    await mkdir(folder);
    assert.equal(await realpath(folder), folder);
    await saveNew(join(folder, 'attempt.json'), { fresh_plan_hash: fresh.plan_hash, approved_hash: values.apply, review_hash: reviewHash });
    const result = await applyIdBuzzRelease(client, fresh, approved, values.apply);
    assert(result.committed && result.variants_inserted === 2);
    await saveNew(join(folder, 'committed-receipt.json'), { result, plan: fresh.plan, baseline, approved_hash: values.apply, eligible });
    console.log(JSON.stringify({ inserted: result.variants_inserted, ...await exportApprovedCatalog(config, baseline, eligible, folder, fresh.plan), paid_calls: 0 }));
  } finally {
    if (client) await openConnector.closeSourceSnapshot(client);
  }
}
