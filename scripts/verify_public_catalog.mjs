import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { SOURCE, FIELDS, publicHeaders, normalizeCatalog, catalogHash, fetchCatalog, compareCatalogs, mergeQuarantine } from './sync_public_catalog.mjs';
import { loadPublicVariants } from '../functions/_shared/http.mjs';

const fixture = {
  brand: 'Kia', model: 'EV3', variant_name: 'Long Range', price_sek: 500000, price_type: null,
  wltp_range_km: 500, tow_kg: 0, source_url: 'https://www.kia.com/se/nya-bilar/ev3/', source_quote: 'Fixture evidence only.',
  source_hash: 'a'.repeat(64), extraction_confidence: 0.93, validation_status: 'published',
  market_seen: true, available_confirmed: false, discontinued_candidate: false, coming_or_low_volume: false,
};
const key = (role) => `fixture.${Buffer.from(JSON.stringify({ role })).toString('base64url')}.signature`;
const rows = [fixture, { ...fixture, variant_name: 'Base', price_sek: null }];
const normalized = normalizeCatalog(rows);
assert.equal(normalized[1].price_type, null, 'Unknown price classification must remain unknown');
assert.equal(normalized[0].verified_at, null, 'Export does not invent verification dates');
assert.equal(normalized[1].tow_kg, 0, 'Explicit zero is preserved');
assert.equal(normalized[0].dc_charge_kw, null);
assert.equal(catalogHash(rows), catalogHash([...rows].reverse()));
for (const change of [{ validation_status: 'extracted' }, { source_hash: null }, { source_quote: '' },
  { source_url: 'https://user:secret@www.kia.com/se/' }, { source_url: 'https://ev-database.org/car/1' },
  { price_sek: -1 }, { wltp_range_km: 1201 }, { extraction_confidence: 0.91 }, { available_confirmed: 'false' },
  { price_type: 'cheap' }, { verified_at: 'not a date' }]) {
  assert.throws(() => normalizeCatalog([{ ...fixture, ...change }]));
}
assert.throws(() => normalizeCatalog([]));
assert.throws(() => normalizeCatalog([fixture, fixture]));
assert.throws(() => publicHeaders(key('service_role')));
assert.throws(() => publicHeaders('sb_secret_fixture'));
assert.deepEqual(publicHeaders('sb_publishable_fixture'), { apikey: 'sb_publishable_fixture' });
let calls = 0;
const fakeFetch = async (url, options) => {
  calls++;
  assert.equal(new URL(url).pathname, '/rest/v1/public_ev_variants');
  assert.equal(options.redirect, 'error');
  assert.equal(options.headers.authorization, `Bearer ${key('anon')}`);
  assert.equal(options.method, undefined, 'Only GET reads');
  assert.equal(new URL(url).searchParams.get('select'), '*', 'Read public view only; nullable legacy columns stay unknown');
  const offset = Number(new URL(url).searchParams.get('offset'));
  return Response.json([rows[offset]], { headers: { 'content-range': `${offset}-${offset}/2` } });
};
assert.deepEqual(await fetchCatalog({ url: 'https://fixture.supabase.co', key: key('anon'), pageSize: 1, fetchImpl: fakeFetch }), normalized);
assert.equal(calls, 2);
for (const response of [Response.json([], { headers: { 'content-range': '0-0/2' } }), Response.json(rows),
  Response.json(rows, { headers: { 'content-range': '0-1/10001' } }), new Response(null, { status: 302 }),
  Response.json({}, { status: 401 }), Response.json(rows.slice(0, 1), { headers: { 'content-range': '0-1/2' } })]) {
  await assert.rejects(fetchCatalog({ url: 'https://fixture.supabase.co', key: key('anon'), fetchImpl: async () => response.clone() }));
}
await assert.rejects(fetchCatalog({ url: 'https://fixture.supabase.co', key: key('anon'), pageSize: 1,
  fetchImpl: async (url) => Response.json([rows[Number(new URL(url).searchParams.get('offset'))]], {
    headers: { 'content-range': new URL(url).searchParams.get('offset') === '0' ? '0-0/2' : '1-1/3' },
  }) }));
const difference = compareCatalogs(rows, [{ ...fixture, price_type: 'campaign_price', tow_kg: 1500 }]);
assert.equal(difference.ok, false);
assert.deepEqual(difference.changed[0].fields, ['price_type', 'tow_kg']);
assert.equal(difference.quarantine.length, 1);
assert.equal(difference.quarantine[0].validation_status, 'needs_review');
assert.equal(mergeQuarantine(difference.quarantine, [], [fixture]).length, 1, 'Rerun retains unresolved quarantine');
assert.equal(mergeQuarantine(difference.quarantine, [], rows).length, 0);
assert.equal(compareCatalogs(rows, [...rows].reverse()).ok, true);
const originalFetch = globalThis.fetch;
try {
  globalThis.fetch = async () => { assert.fail('Snapshot mode must not silently read a different live catalog'); };
  const pinned = await loadPublicVariants({ request: new Request('https://preview.example/api/advisor'),
    env: { SUPABASE_URL: 'https://fixture.supabase.co', SUPABASE_ANON_KEY: key('anon'),
      ASSETS: { fetch: async () => Response.json({ records: [fixture] }) } } });
  assert.equal(pinned.length, 1);
} finally { globalThis.fetch = originalFetch; }
if (!process.argv.includes('--fixtures-only')) {
  const snapshot = JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8'));
  assert.equal(snapshot.source, SOURCE, 'Release builds require a canonical Supabase public-view snapshot, not local candidates');
  assert.equal(snapshot.schema_version, 1);
  assert.equal(snapshot.catalog_sha256, catalogHash(snapshot.records), 'Snapshot content fingerprint mismatch');
}
console.log(JSON.stringify({ catalog_contract_ok: true, pagination: true, fields_compared: FIELDS.length,
  unknowns_preserved: true, quarantine_idempotent: true, public_keys_only: true, remote_calls: 0 }));
