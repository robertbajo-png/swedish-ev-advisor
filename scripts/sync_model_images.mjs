import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { spawnSync } from 'node:child_process';
import { buildImagePlan, applyImagePlan, imagePlanHash } from './model_image_sync.mjs';

async function main() {
  const { values } = parseArgs({ options: { 'client-module': { type: 'string' }, apply: { type: 'string' },
    output: { type: 'string', default: 'data/local/release-data/vehicle-quality-2026-11-12/photos' } } });
  assert(values['client-module'], 'Existing TLS client required');
  const audit = spawnSync(process.execPath, ['scripts/run_python.mjs', 'scripts/audit_image_rights.py', '--candidate-registry', '--check'],
    { encoding: 'utf8', windowsHide: true, timeout: 120000 });
  assert.equal(audit.status, 0, 'Image bytes/permission evidence must pass before connecting');
  const registry = JSON.parse(await readFile('src/image-rights.json', 'utf8'));
  const folder = resolve(values.output);
  await mkdir(folder, { recursive: true });
  const path = resolve(folder, 'prepared-image-plan.json');
  const connector = await import(pathToFileURL(resolve(values['client-module'])).href);
  let client;
  try {
    client = await connector.openSourceSnapshot();
    const models = (await client.query('SELECT * FROM public.canonical_models ORDER BY id')).rows;
    const publicModels = (await client.query('SELECT * FROM public.public_ev_models ORDER BY id')).rows;
    const plan = buildImagePlan(models, publicModels, registry);
    if (!values.apply) {
      const hash = imagePlanHash(plan);
      await writeFile(path, JSON.stringify({ hash, plan }, null, 2) + '\n');
      console.log(JSON.stringify({ dry_run: true, models_to_update: plan.map(row => row.model_key), plan_sha256: hash, database_writes: 0 }));
      return;
    }
    const prepared = JSON.parse(await readFile(path, 'utf8'));
    assert.equal(prepared.hash, values.apply);
    assert.equal(imagePlanHash(prepared.plan), prepared.hash);
    assert.equal(imagePlanHash(plan), prepared.hash, 'Registry or canonical images changed; prepare again');
    await client.query('ROLLBACK');
    const result = await applyImagePlan(client, plan, prepared.hash);
    await writeFile(resolve(folder, 'committed-image-receipt.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result));
  } finally { await connector.closeSourceSnapshot(client); }
}

main().catch(error => {
  console.error(JSON.stringify({ error: error.name, code: error.code || null,
    reason: error.code === 'ERR_ASSERTION' ? error.message.split('\n')[0] : 'Image source/transaction failed',
    instruction: 'Check the committed image receipt and actual canonical state before retrying. No secrets logged.' }));
  process.exitCode = 1;
});
