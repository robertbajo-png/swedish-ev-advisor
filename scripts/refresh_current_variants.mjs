import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { buildReplacementPlan, applyReplacementPlan, replacementPlanHash, recollectedFacts } from './current_variant_sync.mjs';
import { validateVehicleRedirects } from '../src/vehicle-redirects.js';

const folder = resolve('data/local/release-data/current-variants');
const read = async path => JSON.parse(await readFile(path, 'utf8'));
const save = async (path, value) => writeFile(path, JSON.stringify(value, null, 2) + '\n');
const controlsSql = "select * from public.news_ai_config where id='production'";
const newsSql = 'select * from public.public_news_articles order by id';
const plain = value => JSON.parse(JSON.stringify(value));

async function main() {
  const args = process.argv.slice(2);
  assert(args.length >= 2 && args[0] === '--client-module', 'Supply a server-side TLS client module exporting openSourceSnapshot/closeSourceSnapshot');
  assert(args.length === 2 || (args.length === 4 && args[2] === '--apply'), 'Dry-run is default; apply requires exact prepared hash');
  const connector = await import(pathToFileURL(resolve(args[1])));
  let client;
  await mkdir(folder, { recursive: true });
  try {
    client = await connector.openSourceSnapshot();
    const controls = plain((await client.query(controlsSql)).rows);
    assert.equal(controls.length, 1);
    assert.equal(controls[0].enabled, false);
    assert.equal(controls[0].publication_enabled, false);
    assert.equal(String(controls[0].daily_limit_micro_usd), '250000');
    assert.equal(String(controls[0].monthly_limit_micro_usd), '5000000');
    const articles = plain((await client.query(newsSql)).rows);
    assert.equal(articles.length, 2);
    if (args.length === 2) {
      const intake = await read(resolve(folder, 'intake.json'));
      const variants = (await client.query(`select v.*,m.brand,m.model from public.canonical_model_variants v
        join public.canonical_models m on m.id=v.canonical_model_id order by v.id`)).rows;
      const plan = buildReplacementPlan(variants, intake);
      const hash = replacementPlanHash(plan);
      const receipt = { hash, plan, controls, articles };
      await save(resolve(folder, 'prepared-plan.json'), receipt);
      console.log(JSON.stringify({ dry_run: true, plan_sha256: hash,
        groups: plan.groups.map(g => ({ brand: g.brand, model: g.model, retired: g.expected.length,
          profiles: g.profiles.map(v => ({ variant: v.variant_name, price: v.price_sek })) })), paid_calls: 0, database_writes: 0 }));
      return;
    }
    const prepared = await read(resolve(folder, 'prepared-plan.json'));
    assert.equal(args[3], prepared.hash);
    assert.equal(replacementPlanHash(prepared.plan), prepared.hash);
    assert.deepEqual(controls, prepared.controls, 'News controls changed');
    assert.deepEqual(articles, prepared.articles, 'Production articles changed');
    // Re-fetch and independently re-extract the current real documents before any write.
    const freshPath = resolve(folder, 'fresh-intake.json');
    const fetch = spawnSync(process.execPath, ['scripts/run_python.mjs', 'scripts/current_variant_intake.py', '--output', freshPath],
      { encoding: 'utf8', windowsHide: true, timeout: 180000 });
    assert.equal(fetch.status, 0, 'Fresh manufacturer-source revalidation failed');
    const fresh = await read(freshPath);
    const original = { groups: prepared.plan.groups.map(g => ({ brand: g.brand, model: g.model,
      retire: g.expected.map(row => row.variant_name), profiles: g.profiles })) };
    assert.deepEqual(recollectedFacts(fresh), recollectedFacts(original), 'Price-document bytes or exact-variant evidence changed; prepare again');
    await client.query('ROLLBACK');
    const result = await applyReplacementPlan(client, prepared.plan, prepared.hash);
    await save(resolve(folder, 'committed-receipt.json'), result);
    assert.deepEqual(plain((await client.query(controlsSql)).rows), controls);
    assert.deepEqual(plain((await client.query(newsSql)).rows), articles);
    const path = resolve('src/vehicle-redirects.json');
    const registry = await read(path);
    const redirects = new Map(registry.redirects.map(row => [row.slug, row]));
    for (const row of result.redirects) {
      assert(!redirects.has(row.slug) || JSON.stringify(redirects.get(row.slug)) === JSON.stringify(row));
      redirects.set(row.slug, row);
    }
    registry.redirects = [...redirects.values()].sort((a, b) => a.slug.localeCompare(b.slug));
    validateVehicleRedirects(registry);
    await save(path, registry);
    console.log(JSON.stringify({ ...result, news_unchanged: true }));
  } finally { await connector.closeSourceSnapshot(client); }
}

main().catch(error => {
  console.error(JSON.stringify({ error: error.name, code: error.code || null,
    reason: error.code === 'ERR_ASSERTION' ? error.message.split('\n')[0] : 'Source/connection guard failed',
    location: error.code === 'ERR_ASSERTION' ? error.stack?.split('\n').find(line => line.includes(' at ') && line.includes('.mjs:'))?.trim() : undefined,
    instruction: 'Check committed-receipt and actual canonical state before retrying any possible commit. No secrets logged.' }));
  process.exitCode = 1;
});
