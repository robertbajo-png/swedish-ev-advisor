import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { readFile, writeFile, rename, mkdir, unlink } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseEnv } from 'node:util';

export const SOURCE = 'supabase_public_ev_variants';
export const FIELDS = ['brand', 'model', 'variant_name', 'body_type', 'price_sek', 'price_type', 'price_valid_until',
  'wltp_range_km', 'wltp_consumption_kwh_100km', 'battery_kwh', 'dc_charge_kw', 'ac_charge_kw', 'boot_liters',
  'tow_kg', 'seats', 'drivetrain', 'source_url', 'source_name', 'source_hash', 'source_quote', 'extraction_confidence',
  'validation_status', 'market_seen', 'available_confirmed', 'discontinued_candidate', 'coming_or_low_volume',
  'image_url', 'image_source_url', 'verified_at'];
const NUMERIC = { price_sek: [100000, 3000000], wltp_range_km: [50, 1200], wltp_consumption_kwh_100km: [5, 50],
  battery_kwh: [5, 300], dc_charge_kw: [20, 600], ac_charge_kw: [1, 50], boot_liters: [50, 3500], tow_kg: [0, 4000], seats: [1, 9] };
const FLAGS = ['market_seen', 'available_confirmed', 'discontinued_candidate', 'coming_or_low_volume'];
export const variantKey = (row) => [row.brand, row.model, row.variant_name].map((s) => String(s || '').normalize('NFC').trim().toLowerCase()).join('|');

function secureUrl(value) {
  const url = new URL(value);
  assert(url.protocol === 'https:' && !url.username && !url.password, 'Expected a safe HTTPS URL');
  return url;
}

export function publicHeaders(key) {
  if (key?.startsWith('sb_publishable_')) return { apikey: key };
  let role;
  try { role = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString()).role; } catch {}
  assert.equal(role, 'anon', 'Catalog export requires a public key, never a server/service key');
  return { apikey: key, authorization: `Bearer ${key}` };
}

export function normalizeCatalog(rows) {
  assert(Array.isArray(rows) && rows.length > 0 && rows.length <= 10000, 'Empty or excessive public catalog');
  const keys = new Set();
  return rows.map((input) => {
    const row = Object.fromEntries(FIELDS.map((field) => [field, input[field] ?? null]));
    for (const field of ['brand', 'model', 'variant_name', 'source_url', 'source_hash', 'source_quote']) {
      assert(typeof row[field] === 'string' && row[field].trim(), `Missing published evidence/identity: ${field}`);
    }
    assert(['published', 'published_reviewed'].includes(row.validation_status), 'Non-published record in catalog');
    const source = secureUrl(row.source_url);
    assert(!/mobilitysweden|ev-database|car\.info/.test(source.hostname), 'Market/comparison source is not specification evidence');
    assert(/^[a-f0-9]{64}$/i.test(row.source_hash), 'Missing SHA-256 source hash');
    for (const flag of FLAGS) assert.equal(typeof row[flag], 'boolean', `Missing boolean market flag: ${flag}`);
    for (const [field, [min, max]] of Object.entries(NUMERIC)) {
      const value = row[field];
      assert(value === null || (typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max), `Invalid numeric field: ${field}`);
    }
    assert(row.price_sek !== null || row.wltp_range_km !== null, 'Missing both price and WLTP');
    assert([null, 'list_price', 'campaign_price', 'dealer_offer'].includes(row.price_type), 'Invalid price classification');
    for (const field of ['verified_at', 'price_valid_until']) if (row[field] !== null) assert(Number.isFinite(Date.parse(row[field])), `Invalid ${field}`);
    assert(typeof row.extraction_confidence === 'number' && row.extraction_confidence >= 0 && row.extraction_confidence <= 1, 'Invalid confidence');
    assert(row.validation_status === 'published_reviewed' || row.extraction_confidence >= 0.92, 'Unreviewed low-confidence record');
    const key = variantKey(row);
    assert(!keys.has(key), 'Duplicate public variant'); keys.add(key);
    return row;
  }).sort((a, b) => variantKey(a) < variantKey(b) ? -1 : variantKey(a) > variantKey(b) ? 1 : 0);
}

export function catalogHash(rows) {
  return createHash('sha256').update(JSON.stringify(normalizeCatalog(rows))).digest('hex');
}

export async function fetchCatalog({ url, key, fetchImpl = fetch, pageSize = 250, onSchema = () => {} }) {
  const base = secureUrl(url);
  assert(base.pathname === '/' && !base.search && !base.hash, 'Use the plain Supabase project URL');
  const headers = { ...publicHeaders(key), prefer: 'count=exact' };
  const rows = [];
  let total;
  for (let offset = 0; total === undefined || offset < total; offset += pageSize) {
    const endpoint = new URL('/rest/v1/public_ev_variants', base);
    endpoint.search = new URLSearchParams({ select: '*', order: 'brand.asc,model.asc,variant_name.asc,id.asc', offset: String(offset), limit: String(pageSize) });
    const response = await fetchImpl(endpoint, { headers, redirect: 'error', signal: AbortSignal.timeout(15000) });
    assert(response.ok, `Canonical public read returned HTTP ${response.status}`);
    const range = /^(\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('content-range') || '');
    assert(range && Number(range[1]) === offset, 'Missing/incomplete canonical pagination');
    const count = Number(range[3]);
    assert(count > 0 && count <= 10000 && (total === undefined || total === count), 'Catalog changed or is empty/excessive during pagination');
    total = count;
    const page = await response.json();
    assert(Array.isArray(page) && page.length === Number(range[2]) - offset + 1
      && page.length === Math.min(pageSize, total - offset), 'Truncated canonical public page');
    if (offset === 0) onSchema(FIELDS.filter((field) => !Object.hasOwn(page[0], field)));
    rows.push(...page);
  }
  assert.equal(rows.length, total);
  return normalizeCatalog(rows);
}

export function compareCatalogs(local, remote) {
  const byKey = (rows) => new Map(rows.map((row) => [variantKey(row), row]));
  const a = byKey(normalizeCatalog(local)), b = byKey(normalizeCatalog(remote));
  const localOnly = [...a.keys()].filter((key) => !b.has(key));
  const remoteOnly = [...b.keys()].filter((key) => !a.has(key));
  const changed = [...a.keys()].filter((key) => b.has(key)).flatMap((key) => {
    const fields = FIELDS.filter((field) => JSON.stringify(a.get(key)[field]) !== JSON.stringify(b.get(key)[field]));
    return fields.length ? [{ key, fields }] : [];
  });
  return { ok: !localOnly.length && !remoteOnly.length && !changed.length, local_count: a.size, remote_count: b.size,
    local_only: localOnly, remote_only: remoteOnly, changed,
    quarantine: localOnly.map((key) => ({ ...a.get(key), previous_validation_status: a.get(key).validation_status,
      validation_status: 'needs_review', reason: 'not_in_canonical_public_view', next_action: 'exact_variant_source_verification' })) };
}

export function mergeQuarantine(previous, current, remote) {
  const published = new Set(remote.map(variantKey));
  return [...new Map([...previous, ...current].map((row) => [variantKey(row), row])).values()]
    .filter((row) => !published.has(variantKey(row)));
}

export async function atomicJson(path, value) {
  const destination = resolve(path), temporary = `${destination}.${randomUUID()}.tmp`;
  await mkdir(dirname(destination), { recursive: true });
  try { await writeFile(temporary, JSON.stringify(value, null, 2) + '\n'); await rename(temporary, destination); }
  finally { await unlink(temporary).catch((error) => { if (error.code !== 'ENOENT') throw error; }); }
}

async function main() {
  const env = {};
  for (const name of ['.env', '.env.local']) {
    try { Object.assign(env, parseEnv((await readFile(name, 'utf8')).replace(/^\uFEFF/, ''))); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  Object.assign(env, process.env);
  const config = { url: env.SUPABASE_URL || env.VITE_SUPABASE_URL, key: env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY };
  const path = 'public/data/public_ev_variants.json';
  const previous = JSON.parse(await readFile(path, 'utf8'));
  let missingFields, confirmationMissing;
  const rows = await fetchCatalog({ ...config, onSchema: (fields) => { missingFields = fields; } });
  const confirmation = await fetchCatalog({ ...config, onSchema: (fields) => { confirmationMissing = fields; } });
  assert.equal(catalogHash(rows), catalogHash(confirmation), 'Canonical catalog changed during export; retry later');
  assert.deepEqual(missingFields, confirmationMissing, 'Canonical view schema changed during export; retry later');
  const difference = compareCatalogs(previous.records, rows);
  if (!process.argv.includes('--write')) {
    console.log(JSON.stringify({ ...difference, quarantine: difference.quarantine.map(variantKey), missing_view_columns: missingFields, remote_writes: false }, null, 2));
    if (!difference.ok) process.exitCode = 1;
    return;
  }
  const reportPath = 'data/review/catalog_reconciliation.json';
  let previousQuarantine = [];
  try { previousQuarantine = JSON.parse(await readFile(reportPath, 'utf8')).quarantine || []; }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const quarantine = mergeQuarantine(previousQuarantine, difference.quarantine, rows);
  await atomicJson(reportPath, { checked_at: new Date().toISOString(), ...difference,
    quarantine, missing_view_columns: missingFields, remote_writes: false });
  await atomicJson(path, { generated_at: new Date().toISOString(), source: SOURCE, schema_version: 1,
    missing_view_columns: missingFields, catalog_sha256: catalogHash(rows), records: rows });
  console.log(JSON.stringify({ canonical_snapshot_written: true, records: rows.length, new_local_only: difference.local_only, pending_review: quarantine.length,
    changed_rows: difference.changed.length, missing_view_columns: missingFields, remote_writes: false }));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => { console.error(error.name === 'AssertionError' ? error.message : 'Catalog synchronization failed; existing snapshot retained. Credentials/provider bodies are not logged.'); process.exitCode = 1; });
}
