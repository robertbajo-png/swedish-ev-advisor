import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { onRequestPost as advisorPost } from '../functions/api/advisor.js';
import { onRequestPost as comparePost } from '../functions/api/compare.js';

const publicExport = await readFile(join(process.cwd(), 'public/data/public_ev_variants.json'), 'utf8');
const exportPayload = JSON.parse(publicExport);
const firstRows = exportPayload.records
  .filter((row) => ['published', 'published_reviewed'].includes(row.validation_status))
  .slice(0, 4);

assert.ok(firstRows.length >= 2, 'The edge contract test needs at least two public variants.');

const assetPayload = JSON.stringify({
  records: [
    ...firstRows,
    {
      ...firstRows[0],
      brand: 'Quarantined',
      model: 'Do Not Publish',
      variant_name: 'Draft',
      validation_status: 'draft',
    },
  ],
});

const env = {
  OPENAI_MODEL: 'gpt-5.4-mini',
  ASSETS: {
    fetch: async () => new Response(assetPayload, {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
  },
};

const advisorRequest = new Request('https://seekev.se/api/advisor', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    prompt: 'Familjebil med lång räckvidd',
    budget: 700000,
    range: 500,
    need: 'familj',
  }),
});

const advisorResponse = await advisorPost({ request: advisorRequest, env });
assert.equal(advisorResponse.status, 200);
const advice = await advisorResponse.json();
assert.equal(advice.mode, 'deterministic_fallback');
assert.ok(advice.shortlist.length >= 1 && advice.shortlist.length <= 3);
assert.ok(advice.shortlist.every((row) => row.brand !== 'Quarantined'));
assert.ok(advice.shortlist.every((row) => row.source_url.startsWith('https://')));

const variantKeys = advice.shortlist.map((row) => `${row.brand}|${row.model}|${row.variant_name}`);
const compareRequest = new Request('https://seekev.se/api/compare', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ variant_keys: variantKeys }),
});

const compareResponse = await comparePost({ request: compareRequest, env });
assert.equal(compareResponse.status, 200);
const report = await compareResponse.json();
assert.equal(report.mode, 'deterministic_fallback');
assert.ok(report.winner?.variant_key);
assert.ok(report.compared.length >= 1 && report.compared.length <= 3);

console.log(JSON.stringify({
  cloudflare_functions_ok: true,
  advisor_mode: advice.mode,
  shortlist_count: advice.shortlist.length,
  compare_mode: report.mode,
  winner: report.winner.name,
}, null, 2));
