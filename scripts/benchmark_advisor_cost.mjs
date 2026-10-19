import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseEnv } from 'node:util';
import { createAdvisorResult, normalizePublicVariants } from '../functions/_shared/advisor-core.mjs';

export const PRICES = Object.freeze({
  model: 'gpt-5.4-mini', verified_on: '2026-10-19',
  input_per_million_usd: 0.75, cached_input_per_million_usd: 0.075, output_per_million_usd: 4.50,
  source: 'https://developers.openai.com/api/docs/models/gpt-5.4-mini',
});
export const SEARCHES = [
  { label: 'Familjebil', prompt: 'Vi \u00e4r tv\u00e5 vuxna och tv\u00e5 barn. Jag s\u00f6ker en familjebil under 600 000 kr med minst 450 km WLTP och plats f\u00f6r barnvagn.', budget: 600000, range: 450, need: 'familj' },
  { label: 'Budget och pendling', prompt: 'Jag pendlar fem mil om dagen och vill ha en prisv\u00e4rd elbil under 400 000 kr med minst 350 km WLTP.', budget: 400000, range: 350, need: 'budget' },
  { label: 'L\u00e5ngresor', prompt: 'Vi k\u00f6r ofta l\u00e5nga resor. Budget 750 000 kr, minst 550 km WLTP och snabb DC-laddning \u00e4r viktigast.', budget: 750000, range: 550, need: 'langresor' },
  { label: 'Dragkrok och husvagn', prompt: 'Jag beh\u00f6ver dra en husvagn p\u00e5 1 500 kg. Budget 800 000 kr och minst 450 km WLTP. Var tydlig om dragvikt inte kan verifieras.', budget: 800000, range: 450, need: 'dragkrok' },
  { label: 'Fyrhjulsdrift och vinter', prompt: 'Jag vill ha fyrhjulsdrift f\u00f6r vinter och fj\u00e4llresor, max 700 000 kr och minst 500 km WLTP. Var tydlig om en uppgift saknas.', budget: 700000, range: 500, need: 'vinter' },
];

export function tokenCost(usage, model, tier) {
  assert.match(model || '', /^gpt-5\.4-mini(?:-\d{4}-\d{2}-\d{2})?$/, 'No verified price for the returned model.');
  assert.equal(tier, 'default', 'No verified price for the returned service tier.');
  const input = usage?.input_tokens;
  const output = usage?.output_tokens;
  const cached = usage?.input_tokens_details?.cached_tokens;
  const writes = usage?.input_tokens_details?.cache_write_tokens ?? 0;
  for (const value of [input, output, cached, writes]) assert.ok(Number.isSafeInteger(value) && value >= 0, 'Missing or invalid token usage.');
  assert.ok(cached <= input, 'Cached tokens exceed total input.');
  assert.equal(writes, 0, 'Cache-write pricing is not covered by this benchmark.');
  return ((input - cached) * PRICES.input_per_million_usd + cached * PRICES.cached_input_per_million_usd + output * PRICES.output_per_million_usd) / 1e6;
}

async function localApiKey() {
  if (process.env.OPENAI_API_KEY?.trim()) return process.env.OPENAI_API_KEY.trim();
  for (const filename of ['.env.local', '.env']) {
    try {
      const env = parseEnv((await readFile(filename, 'utf8')).replace(/^\uFEFF/, ''));
      if (env.OPENAI_API_KEY?.trim()) return env.OPENAI_API_KEY.trim();
    } catch (error) { if (error.code !== 'ENOENT') throw new Error('Could not read local environment file.'); }
  }
  throw new Error('No server API key configured.');
}

export async function runBenchmark({ variants, apiKey, fetchImpl = fetch, searches = SEARCHES, onResult = () => {} }) {
  assert.ok(searches.length > 0 && searches.length <= 5, 'At most five searches are allowed.');
  assert.ok(variants.length > 0 && variants.length <= 200, 'Unexpected public snapshot size.');
  const results = [];
  let calls = 0;
  for (const search of searches) {
    let observation;
    const start = performance.now();
    const measuredFetch = async (url, options) => {
      assert.equal(url, 'https://api.openai.com/v1/responses');
      assert.ok(++calls <= 5, 'Provider call limit reached.');
      const request = JSON.parse(options.body);
      assert.equal(request.model, PRICES.model);
      assert.equal(request.store, false);
      assert.equal(request.max_output_tokens, 512);
      assert.equal(request.text.format.name, 'ev_search_requirements');
      assert.equal(request.text.format.schema.properties.shortlist, undefined);
      assert.ok(!JSON.stringify(request.input).includes('public_variants'));
      assert.equal(request.tools, undefined, 'Paid tools are not part of this benchmark.');
      assert.ok(Buffer.byteLength(options.body) <= 10000, 'Unexpected requirement prompt size.');
      const response = await fetchImpl(url, options);
      const payload = await response.clone().json().catch(() => ({}));
      observation = { http_status: response.status, model: payload.model, service_tier: payload.service_tier, usage: payload.usage };
      return response;
    };
    const advice = await createAdvisorResult({ request: search, variants, apiKey, model: PRICES.model, fetchImpl: measuredFetch });
    const record = {
      label: search.label, prompt: search.prompt, mode: advice.mode,
      elapsed_ms: Math.round(performance.now() - start),
      http_status: observation?.http_status ?? null,
      model: observation?.model ?? null, service_tier: observation?.service_tier ?? null,
      usage: observation?.usage ?? null, calculated_cost_usd: null,
      summary: advice.summary, interpreted_requirements: advice.interpreted_requirements,
      shortlist: advice.shortlist,
    };
    // Failed/fallback responses may still consume tokens; never price them as zero.
    try { record.calculated_cost_usd = tokenCost(record.usage, record.model, record.service_tier); }
    catch { record.cost_error = 'Provider usage or pricing could not be verified.'; }
    const byId = new Map(variants.map((row) => [row.id, row]));
    record.canonical_identity_and_sources_ok = advice.shortlist.every((item) => {
      const row = byId.get(item.id);
      return row && row.brand === item.brand && row.model === item.model && row.variant_name === item.variant_name && row.source_url === item.source_url;
    });
    results.push(record);
    onResult(record);
    if (record.http_status !== 200 || record.calculated_cost_usd === null || advice.mode !== 'openai' || !record.canonical_identity_and_sources_ok) break;
  }
  return { provider_calls: calls, results };
}

async function main() {
  if (!process.argv.includes('--live')) {
    console.log(JSON.stringify({ dry_run: true, provider_calls: 0, model: PRICES.model, planned_searches: SEARCHES.map((s) => s.label), instruction: 'Add --live to authorize up to five paid model requests. No retries.' }, null, 2));
    return;
  }
  const apiKey = await localApiKey();
  assert.ok(/^sk-/.test(apiKey), 'Invalid server key format.');
  const snapshotUrl = 'https://codex-ai-preview.seekev-ai-preview.pages.dev/data/public_ev_variants.json';
  const response = await fetch(snapshotUrl, { redirect: 'error', signal: AbortSignal.timeout(15000) });
  assert.equal(response.status, 200, 'Public snapshot is unavailable.');
  const snapshotText = await response.text();
  const rows = JSON.parse(snapshotText).records;
  const variants = normalizePublicVariants(rows);
  assert.equal(variants.length, rows.length, 'Snapshot contains non-public or untraceable records.');
  const observed = await runBenchmark({ variants, apiKey, onResult: (row) => console.log(JSON.stringify({ search: row.label, mode: row.mode, input: row.usage?.input_tokens, cached: row.usage?.input_tokens_details?.cached_tokens, output: row.usage?.output_tokens, calculated_cost_usd: row.calculated_cost_usd })) });
  const complete = observed.results.length === SEARCHES.length && observed.results.every((r) => r.mode === 'openai' && r.calculated_cost_usd !== null && r.canonical_identity_and_sources_ok);
  const knownCost = observed.results.reduce((sum, row) => sum + (row.calculated_cost_usd ?? 0), 0);
  const report = {
    measured_at: new Date().toISOString(), method: 'Real requirements-only provider requests through Pages advisor core, followed by deterministic database matching; not browser/Pages HTTP requests.',
    snapshot_url: snapshotUrl, snapshot_sha256: createHash('sha256').update(snapshotText).digest('hex'), public_variants: variants.length,
    prices: PRICES, complete, ...observed,
    total_calculated_cost_usd: observed.results.every((r) => r.calculated_cost_usd !== null) ? knownCost : null,
    usd_to_sek_assumption: 10, total_illustrative_sek: observed.results.every((r) => r.calculated_cost_usd !== null) ? knownCost * 10 : null,
    note: 'Token usage is measured. Cost is calculated using published standard prices, not a read of account balance. Excludes tax, hosting, other traffic and earlier tests. SEK uses an illustrative rate, not a market quote.',
  };
  const directory = join(process.cwd(), 'data', 'local', 'ai-cost');
  await mkdir(directory, { recursive: true });
  const path = join(directory, `${report.measured_at.replace(/[:.]/g, '-')}.json`);
  await writeFile(path, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ complete, provider_calls: observed.provider_calls, total_calculated_cost_usd: report.total_calculated_cost_usd, total_illustrative_sek: report.total_illustrative_sek, report: path }, null, 2));
  if (!complete) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { console.error('Cost benchmark stopped. No automatic retries; credentials and provider error bodies are not logged.'); process.exitCode = 1; });
}
