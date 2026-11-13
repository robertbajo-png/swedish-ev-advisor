import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import * as kia from './kia_spec_sync.mjs';

const read = async path => JSON.parse(await readFile(path, 'utf8'));
const save = async (path, data) => writeFile(path, JSON.stringify(data, null, 2) + '\n');
const plain = value => JSON.parse(JSON.stringify(value));
const sourceFingerprint = source => Object.fromEntries(Object.entries(source).filter(([name]) => name !== 'fetched_at'));
const facts = intake => intake.drafts.map(({ source, supporting_sources, ...row }) => ({ ...row,
  source: sourceFingerprint(source), ...(supporting_sources ? { supporting_sources: supporting_sources.map(sourceFingerprint) } : {}) }));

export async function runTechnicalRefresh({ sync = kia, collector = 'scripts/kia_specs_intake.py',
  defaultOutput = 'data/local/release-data/vehicle-quality-2026-11-12/kia' } = {}) {
  const { applySpecPlan, buildSpecPlan, specPlanHash } = sync;
  const { values } = parseArgs({ options: { 'client-module': { type: 'string' }, apply: { type: 'string' },
    output: { type: 'string', default: defaultOutput } } });
  assert(values['client-module'], 'Existing server-side TLS client required');
  const folder = resolve(values.output);
  await mkdir(folder, { recursive: true });
  const connector = await import(pathToFileURL(resolve(values['client-module'])).href);
  let client;
  try {
    client = await connector.openSourceSnapshot();
    const variants = (await client.query(`SELECT v.*,m.brand,m.model FROM public.canonical_model_variants v
      JOIN public.canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id`)).rows;
    const controls = plain((await client.query('SELECT * FROM public.news_ai_config ORDER BY id')).rows);
    const articles = plain((await client.query('SELECT id,status,updated_at FROM public.news_articles ORDER BY id')).rows);
    if (!values.apply) {
      const intake = await read(resolve(folder, 'intake.json'));
      const plan = buildSpecPlan(variants, intake);
      const hash = specPlanHash(plan);
      await save(resolve(folder, 'prepared-plan.json'), { hash, plan, controls, articles });
      console.log(JSON.stringify({ dry_run: true, plan_sha256: hash, variants: plan.targets.length,
        new_values: plan.targets.reduce((sum, row) => sum + Object.keys(row.draft.facts).filter(field => row.expected[field] == null).length, 0),
        database_writes: 0, paid_calls: 0 }));
      return;
    }
    const prepared = await read(resolve(folder, 'prepared-plan.json'));
    assert.equal(values.apply, prepared.hash);
    assert.equal(specPlanHash(prepared.plan), prepared.hash);
    assert.deepEqual(controls, prepared.controls, 'News controls changed; prepare again');
    assert.deepEqual(articles, prepared.articles, 'News articles changed; prepare again');
    await client.query('ROLLBACK');
    const freshFolder = resolve(folder, 'fresh');
    const collection = spawnSync(process.execPath, ['scripts/run_python.mjs', collector, '--output', freshFolder],
      { encoding: 'utf8', windowsHide: true, timeout: 240000 });
    assert.equal(collection.status, 0, 'Fresh source collection failed');
    const fresh = await read(resolve(freshFolder, 'intake.json'));
    assert.equal(fresh.held.length, 0, 'A current technical source needs review');
    const expectedIntake = { drafts: prepared.plan.targets.map(row => row.draft) };
    const sorted = rows => rows.sort((a,b) => (a.model + a.variant_name).localeCompare(b.model + b.variant_name));
    assert.deepEqual(sorted(facts(fresh)), sorted(facts(expectedIntake)), 'Source bytes, exact variants or extracted facts changed');
    const plan = buildSpecPlan(variants, fresh);
    const hash = specPlanHash(plan);
    const result = await applySpecPlan(client, plan, hash);
    await save(resolve(folder, 'committed-receipt.json'), { ...result, prepared_plan_sha256: prepared.hash });
    assert.deepEqual(plain((await client.query('SELECT * FROM public.news_ai_config ORDER BY id')).rows), controls);
    assert.deepEqual(plain((await client.query('SELECT id,status,updated_at FROM public.news_articles ORDER BY id')).rows), articles);
    console.log(JSON.stringify({ ...result, news_unchanged: true }));
  } finally { await connector.closeSourceSnapshot(client); }
}

export function reportFailure(error) {
  console.error(JSON.stringify({ error: error.name, code: error.code || null,
    reason: error.code === 'ERR_ASSERTION' ? error.message.split('\n')[0] : 'Technical source or transaction failed',
    instruction: 'Check the local committed receipt and actual canonical state before retrying. No secrets logged.' }));
  process.exitCode = 1;
}

if (import.meta.url === pathToFileURL(resolve(process.argv[1] || '')).href) runTechnicalRefresh().catch(reportFailure);
