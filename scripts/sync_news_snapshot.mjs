import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { appendFile, readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { parseEnv } from 'node:util';
import { atomicJson, publicHeaders } from './sync_public_catalog.mjs';

export const NEWS_PREVIEW = 'https://codex-ai-preview.seekev-ai-preview.pages.dev';
const FIELDS = ['id', 'slug', 'published_at', 'title', 'intro', 'paragraphs', 'category',
  'brands', 'sources', 'related_models', 'editorial_method', 'image'];
const text = (value) => typeof value === 'string' && value.trim().length > 0;
const secure = (value) => {
  const url = new URL(value);
  assert(url.protocol === 'https:' && !url.username && !url.password, 'Expected a public HTTPS URL');
  return url;
};

export function normalizeNews(rows) {
  assert(Array.isArray(rows) && rows.length <= 10000, 'Invalid public news collection');
  const ids = new Set(), slugs = new Set();
  return rows.map((input) => {
    const p = input.payload ? { ...input.payload, id: input.id, slug: input.slug, published_at: input.published_at } : input;
    assert(!input.status || input.status === 'published', 'Unpublished news cannot be exported');
    assert(text(p.id) && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(p.slug || ''), 'Invalid public article identity');
    assert(!ids.has(p.id) && !slugs.has(p.slug), 'Duplicate public article');
    ids.add(p.id); slugs.add(p.slug);
    assert(text(p.published_at) && Number.isFinite(Date.parse(p.published_at)), 'Missing publication date');
    for (const key of ['title', 'intro', 'category', 'editorial_method']) assert(text(p[key]), `Missing public ${key}`);
    assert(Array.isArray(p.paragraphs) && p.paragraphs.length > 0 && p.paragraphs.every((v) => text(v.text) && ['reporting', 'analysis'].includes(v.kind)), 'Invalid article paragraphs');
    assert(Array.isArray(p.sources) && p.sources.length > 0, 'Missing article attribution');
    const sources = p.sources.map((s) => {
      secure(s.url);
      assert(text(s.publisher), 'Missing source publisher');
      return Object.fromEntries(['url', 'publisher', 'title', 'published_at', 'kind'].filter((k) => Object.hasOwn(s, k)).map((k) => [k, s[k]]));
    });
    assert(Array.isArray(p.brands) && p.brands.every(text) && Array.isArray(p.related_models), 'Invalid public associations');
    return { ...Object.fromEntries(FIELDS.map((key) => [key, p[key] ?? null])), sources,
      paragraphs: p.paragraphs.map(({ text, kind }) => ({ text, kind })) };
  }).sort((a, b) => b.published_at.localeCompare(a.published_at) || a.id.localeCompare(b.id));
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  return value;
}

export const newsHash = (rows) => createHash('sha256').update(JSON.stringify(stable(normalizeNews(rows)))).digest('hex');

async function readJson(url, options, fetchImpl) {
  const response = await fetchImpl(url, { ...options, method: 'GET', redirect: 'error', signal: AbortSignal.timeout(15000) });
  assert(response.ok, `Public news read failed (HTTP ${response.status})`);
  assert(/application\/json/i.test(response.headers.get('content-type') || ''), 'Expected public news JSON');
  const body = await response.text();
  assert(body.length <= 8000000, 'Public news response exceeds size limit');
  return { response, value: JSON.parse(body) };
}

export async function fetchPublishedNews({ url, key, fetchImpl = fetch, pageSize = 250 }) {
  const base = secure(url);
  assert(/^[a-z0-9-]+\.supabase\.co$/.test(base.hostname) && base.pathname === '/' && !base.search && !base.hash && !base.port, 'Use the plain Supabase project URL');
  assert(Number.isInteger(pageSize) && pageSize >= 1 && pageSize <= 500, 'Invalid public page size');
  const headers = { ...publicHeaders(key), prefer: 'count=exact' };
  let total;
  const rows = [];
  for (let offset = 0; total === undefined || offset < total; offset += pageSize) {
    const endpoint = new URL('/rest/v1/public_news_articles', base);
    endpoint.search = new URLSearchParams({ select: 'id,slug,published_at,payload', order: 'published_at.desc,id.asc', offset: String(offset), limit: String(pageSize) });
    const { response, value } = await readJson(endpoint, { headers }, fetchImpl);
    const range = response.headers.get('content-range');
    if (range === '*/0' && offset === 0 && Array.isArray(value) && value.length === 0) return [];
    const match = /^(\d+)-(\d+)\/(\d+)$/.exec(range || '');
    assert(match && Number(match[1]) === offset, 'Missing/invalid news pagination');
    const count = Number(match[3]);
    assert(count > 0 && count <= 10000 && (total === undefined || count === total), 'Public news changed during pagination');
    total = count;
    assert(Array.isArray(value) && value.length === Math.min(pageSize, total - offset) && Number(match[2]) - offset + 1 === value.length, 'Truncated public news page');
    rows.push(...value);
  }
  return normalizeNews(rows);
}

export async function planNewsSync(config, { fetchImpl = fetch } = {}) {
  const records = await fetchPublishedNews({ ...config, fetchImpl });
  const confirmation = await fetchPublishedNews({ ...config, fetchImpl });
  const hash = newsHash(records);
  assert.equal(hash, newsHash(confirmation), 'Public news changed during synchronization; retry later');
  const live = await readJson(NEWS_PREVIEW + '/data/news_articles.json', {}, fetchImpl);
  const current = normalizeNews(live.value.records);
  assert(records.length > 0 || current.length === 0, 'Refusing to erase an existing public news snapshot');
  return { records, snapshot_hash: hash, previous_preview_hash: newsHash(current),
    changed: hash !== newsHash(current), published_count: records.length,
    provider_calls: 0, production_writes: 0, articles_published: 0 };
}

export function authorizeNewsDistribution(plan, env = {}) {
  assert.equal(typeof plan.changed, 'boolean', 'Missing snapshot change decision');
  assert.equal(newsHash(plan.records), plan.snapshot_hash, 'Invalid snapshot identity');
  const requested = env.NEWS_REDISTRIBUTE_HASH || '';
  if (requested) {
    assert(env.GITHUB_EVENT_NAME === 'workflow_dispatch' && env.GITHUB_REF === 'refs/heads/main',
      'Redistribution is only allowed by an explicit main-branch manual dispatch');
    assert(/^[a-f0-9]{64}$/.test(requested), 'Redistribution requires an exact SHA-256');
    assert(plan.records.length > 0, 'Cannot redistribute an empty news snapshot');
    assert.equal(plan.snapshot_hash, requested, 'Requested articles differ from the public database');
    assert.equal(plan.previous_preview_hash, requested, 'Requested articles differ from the existing preview');
    assert.equal(plan.changed, false, 'Redistribution requires unchanged published content');
  }
  return { ...plan, redistribution_requested: Boolean(requested), upload_required: plan.changed || Boolean(requested) };
}

async function main() {
  assert(process.argv.slice(2).every((arg) => arg === '--write' || /^--expect-hash=[a-f0-9]{64}$/.test(arg)), 'Usage: node scripts/sync_news_snapshot.mjs [--write] [--expect-hash=SHA256]');
  const env = {};
  for (const name of ['.env', '.env.local']) {
    try { Object.assign(env, parseEnv((await readFile(name, 'utf8')).replace(/^\uFEFF/, ''))); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  Object.assign(env, process.env);
  const plan = authorizeNewsDistribution(await planNewsSync({ url: env.SUPABASE_URL || env.VITE_SUPABASE_URL,
    key: env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY }), env);
  const expected = process.argv.find((arg) => arg.startsWith('--expect-hash='))?.split('=')[1];
  if (expected) assert.equal(plan.snapshot_hash, expected, 'Published news changed after the build; abort this deployment');
  const write = process.argv.includes('--write');
  if (write) {
    await atomicJson('public/data/news_articles.json', { generated_at: new Date().toISOString(), records: plan.records });
    if (env.GITHUB_OUTPUT) await appendFile(env.GITHUB_OUTPUT, `changed=${plan.changed}\nsnapshot_hash=${plan.snapshot_hash}\nupload_required=${plan.upload_required}\nredistribution_requested=${plan.redistribution_requested}\n`);
  }
  console.log(JSON.stringify({ ...plan, records: undefined, local_snapshot_written: write, deploy_performed: false }, null, 2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error.name === 'AssertionError' ? error.message : 'Public news synchronization failed; no deployment. Credentials and response bodies are not logged.');
    process.exitCode = 1;
  });
}
