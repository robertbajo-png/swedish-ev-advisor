import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { parseArgs } from 'node:util';
import { buildReplacementPlan, applyReplacementPlan, replacementPlanHash, recollectedFacts } from './current_variant_sync.mjs';
import { validateVehicleRedirects } from '../src/vehicle-redirects.js';

const read = async path => JSON.parse(await readFile(path, 'utf8'));
const save = async (path, value) => writeFile(path, JSON.stringify(value, null, 2) + '\n');
const controlsSql = "select * from public.news_ai_config where id='production'";
const newsSql = 'select * from public.public_news_articles order by id';
const plain = value => JSON.parse(JSON.stringify(value));

async function main() {
  const {values}=parseArgs({options:{'client-module':{type:'string'},batch:{type:'string',default:'first'},apply:{type:'string'}}});
  assert(values['client-module'],'Supply a server-side TLS client module exporting openSourceSnapshot/closeSourceSnapshot');
  assert(['first','remaining'].includes(values.batch),'Unknown reviewed batch');
  const folder=resolve('data/local/release-data/'+(values.batch==='first'?'current-variants':'remaining-variants'));
  const rules=values.batch==='remaining'?(await import('./remaining_variant_policy.mjs')).remainingRules:undefined;
  const script=values.batch==='remaining'?'scripts/remaining_variant_intake.py':'scripts/current_variant_intake.py';
  const connector = await import(pathToFileURL(resolve(values['client-module'])));
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
    if (!values.apply) {
      const intake = await read(resolve(folder, 'intake.json'));
      if(!intake.groups.length) {
        assert.equal(intake.held.length,0,'All remaining sources held for review');
        console.log(JSON.stringify({dry_run:true,status:'no_pending_replacements',database_writes:0,paid_calls:0}));return;
      }
      const variants = (await client.query(`select v.*,m.brand,m.model from public.canonical_model_variants v
        join public.canonical_models m on m.id=v.canonical_model_id order by v.id`)).rows;
      const plan = buildReplacementPlan(variants, intake, new Date(), rules);
      const hash = replacementPlanHash(plan);
      const receipt = { hash, plan, controls, articles };
      await save(resolve(folder, 'prepared-'+hash+'.json'), receipt);
      await save(resolve(folder, 'prepared-plan.json'), receipt);
      console.log(JSON.stringify({ dry_run: true, plan_sha256: hash,
        groups: plan.groups.map(g => ({ brand: g.brand, model: g.model, retired: g.expected.length,
          profiles: g.profiles.map(v => ({ variant: v.variant_name, price: v.price_sek })) })), paid_calls: 0, database_writes: 0 }));
      return;
    }
    const prepared = await read(resolve(folder, 'prepared-plan.json'));
    assert.equal(values.apply, prepared.hash);
    assert.equal(replacementPlanHash(prepared.plan), prepared.hash);
    assert.deepEqual(controls, prepared.controls, 'News controls changed');
    assert.deepEqual(articles, prepared.articles, 'Production articles changed');
    // Re-fetch and independently re-extract the current real documents before any write.
    const freshPath = resolve(folder, 'fresh-intake.json');
    const selection=values.batch==='remaining'?prepared.plan.groups.flatMap(group=>['--only',group.brand+'|'+group.model]):[];
    const fetch = spawnSync(process.execPath, ['scripts/run_python.mjs', script, '--output', freshPath,...selection],
      { encoding: 'utf8', windowsHide: true, timeout: 180000 });
    assert.equal(fetch.status, 0, 'Fresh manufacturer-source revalidation failed');
    const fresh = await read(freshPath);
    const original = { groups: prepared.plan.groups.map(g => ({ brand: g.brand, model: g.model,
      retire: g.expected.map(row => row.variant_name), profiles: g.profiles,...(g.retention_evidence?{retention_evidence:g.retention_evidence}:{}) })) };
    const comparable=rules?.recollectedFacts||recollectedFacts;
    assert.deepEqual(comparable(fresh), comparable(original), 'Material source context, PDF bytes or exact-variant evidence changed; prepare again');
    const effectivePlan=rules?.freshProofs?buildReplacementPlan(prepared.plan.groups.flatMap(group=>[...group.expected,...(group.retained||[])]),fresh,new Date(),rules):prepared.plan;
    const effectiveHash=replacementPlanHash(effectivePlan);
    await client.query('ROLLBACK');
    const result = await applyReplacementPlan(client, effectivePlan, effectiveHash,new Date(),rules);
    result.prepared_plan_sha256=prepared.hash;
    if(effectiveHash!==prepared.hash)await save(resolve(folder,'applied-plan-'+effectiveHash+'.json'),{prepared_hash:prepared.hash,plan:effectivePlan});
    await save(resolve(folder, 'receipt-'+prepared.hash+'.json'), result);
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
