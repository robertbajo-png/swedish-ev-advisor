import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { pathToFileURL } from 'node:url';

export const PRIVATE_VEHICLE_TABLES = ['canonical_models', 'canonical_model_variants', 'extracted_variant_drafts', 'manufacturer_sources', 'market_models', 'market_model_monthly_stats', 'model_aliases'];

function headers(key, expectedRole) {
  if (expectedRole === 'anon' && key?.startsWith('sb_publishable_')) return { apikey: key };
  if (expectedRole === 'service_role' && key?.startsWith('sb_secret_')) return { apikey: key };
  let role;
  try { role = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString()).role; } catch {}
  assert.equal(role, expectedRole, `Expected a ${expectedRole} credential; refusing to use a different role`);
  return { apikey: key, authorization: `Bearer ${key}` };
}

export async function verifySupabaseAccess({ url, publicKey, serviceKey, fetchImpl = fetch }) {
  const base = new URL(url);
  assert.equal(base.protocol, 'https:', 'Remote checks require HTTPS');
  assert(!base.username && !base.password && !base.search && !base.hash, 'Use the plain project URL');
  const publicHeaders = headers(publicKey, 'anon');
  const serviceHeaders = serviceKey ? headers(serviceKey, 'service_role') : null;
  const request = (table, auth, query, method = 'GET') => fetchImpl(new URL(`/rest/v1/${table}?${query}`, base), {
    method, headers: { ...auth, prefer: 'count=exact' }, redirect: 'error', signal: AbortSignal.timeout(15000),
  });
  const report = { public_views: {}, private_tables: [], service_reads_checked: !!serviceKey, remote_writes: false, ok: false };
  for (const name of ['public_ev_models', 'public_ev_variants']) {
    const response = await request(name, publicHeaders, 'select=*');
    assert(response.ok, `${name}: public read returned HTTP ${response.status}`);
    const rows = await response.json();
    assert(Array.isArray(rows) && rows.length > 0, `${name}: expected published records`);
    if (name === 'public_ev_variants') for (const row of rows) {
      assert(['published', 'published_reviewed'].includes(row.validation_status), 'Non-published variant in public view');
      assert(row.source_hash && /^https:\/\//.test(row.source_url), 'Published variant missing source evidence');
    }
    report.public_views[name] = rows.length;
  }
  for (const table of PRIVATE_VEHICLE_TABLES) {
    const response = await request(table, publicHeaders, 'select=id&limit=1');
    const error = await response.json().catch(() => null);
    assert([401, 403].includes(response.status) && error?.code === '42501', `${table}: expected a permission denial, got HTTP ${response.status}`);
    const check = { table, anonymous_status: response.status, permission_denied: true };
    if (serviceHeaders) {
      const serverRead = await request(table, serviceHeaders, 'select=id&limit=1', 'HEAD');
      assert(serverRead.ok, `${table}: service-role read returned HTTP ${serverRead.status}`);
      check.service_read_ok = true;
    }
    report.private_tables.push(check);
  }
  report.ok = true;
  return report;
}

export async function fixtureTests() {
  const key = (role) => `fixture.${Buffer.from(JSON.stringify({ role })).toString('base64url')}.not-a-real-token`;
  const fixture = { validation_status: 'published', source_hash: 'fixture', source_url: 'https://www.kia.com/se/' };
  const calls = [];
  let failure = '';
  const fakeFetch = async (url, options) => {
    calls.push(options);
    assert(['GET', 'HEAD'].includes(options.method), 'The remote verifier must never write');
    const name = new URL(url).pathname.split('/').pop();
    if (name.startsWith('public_ev_')) return Response.json(failure === 'draft' ? [{ ...fixture, validation_status: 'draft' }] : [fixture]);
    if (options.method === 'HEAD') return new Response(null, { status: failure === 'service' ? 403 : 200 });
    if (failure === 'empty') return Response.json([]);
    return Response.json({ code: failure === 'invalid-key' ? 'PGRST301' : '42501' }, { status: 401 });
  };
  const config = { url: 'https://example.supabase.co', publicKey: key('anon'), serviceKey: key('service_role'), fetchImpl: fakeFetch };
  assert((await verifySupabaseAccess(config)).ok);
  for (const value of ['draft', 'service', 'empty', 'invalid-key']) {
    failure = value;
    await assert.rejects(() => verifySupabaseAccess(config));
  }
  failure = '';
  await assert.rejects(() => verifySupabaseAccess({ ...config, publicKey: key('service_role') }));
  assert((await verifySupabaseAccess({ ...config, publicKey: 'sb_publishable_fixture', serviceKey: 'sb_secret_fixture' })).ok);
  console.log(JSON.stringify({ supabase_access_verifier_ok: true, live_requests: 0, remote_writes: false, privileged_public_key_rejected: true, empty_private_response_rejected: true, invalid_credentials_rejected: true, simulated_requests: calls.length }));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    if (!process.argv.includes('--remote')) await fixtureTests();
    else {
      const env = {};
      for (const name of ['.env', '.env.local']) if (existsSync(name)) Object.assign(env, parseEnv(readFileSync(name, 'utf8').replace(/^\uFEFF/, '')));
      Object.assign(env, process.env);
      const report = await verifySupabaseAccess({
        url: env.SUPABASE_URL || env.VITE_SUPABASE_URL,
        publicKey: env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY,
        serviceKey: process.argv.includes('--service') ? env.SUPABASE_SERVICE_ROLE_KEY : undefined,
      });
      console.log(JSON.stringify(report, null, 2));
    }
  } catch (error) {
    console.error(error.name === 'AssertionError' ? error.message : 'Access verification failed; provider bodies and credentials are not logged.');
    process.exitCode = 1;
  }
}
