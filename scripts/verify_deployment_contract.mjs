import assert from 'node:assert/strict';
import { verifyDeployment } from './verify_deployment.mjs';

const row = { brand: 'Test', model: 'EV', variant_name: 'QA fixture', validation_status: 'published', source_hash: 'fixture-hash', source_url: 'https://example.com/model' };
const app = '<html><title>Elbilsguiden</title><div id="root"></div></html>';
let mode = 'valid';
let requests = 0;
const fetchImpl = async (url, options) => {
  requests++;
  assert.equal(options.method, undefined, 'Deployment preflight only performs GET requests.');
  const path = new URL(url).pathname;
  if (mode === 'redirect') return new Response(null, { status: 302, headers: { location: 'http://127.0.0.1:5174/' } });
  if (mode === 'parking') return new Response('<title>Parked at Loopia</title>', { headers: { 'content-type': 'text/html' } });
  if (path === '/health' && mode !== 'html-api') return Response.json({ ok: true, service: 'seekev-api' });
  if (path.endsWith('/data/public_ev_variants.json')) return Response.json({ records: mode === 'draft' ? [{ ...row, validation_status: 'draft' }] : mode === 'unsourced' ? [{ ...row, source_hash: '' }] : mode === 'duplicate' ? [row, row] : [row] });
  if (path === '/sitemap.xml') return new Response('<urlset><url><loc>https://example.com/bilar/test-ev</loc></url></urlset>', { headers: { 'content-type': 'application/xml' } });
  return new Response(app, { headers: { 'content-type': 'text/html', ...(mode !== 'indexed-preview' ? { 'x-robots-tag': 'noindex' } : {}) } });
};
assert((await verifyDeployment('https://example.com', { fetchImpl, expectPreview: true })).ok);
for (mode of ['parking', 'redirect', 'html-api', 'draft', 'unsourced', 'duplicate', 'indexed-preview']) {
  const report = await verifyDeployment('https://example.com', { fetchImpl, expectPreview: true });
  assert.equal(report.ok, false, 'Reject ' + mode);
  assert(report.checks.some((check) => !check.ok));
}
const before = requests;
await assert.rejects(verifyDeployment('https://user:secret@example.com', { fetchImpl }));
assert.equal(requests, before, 'Credential URLs are rejected before fetching.');
console.log(JSON.stringify({ deployment_contract_ok: true, rejected: ['parking', 'localhost redirect', 'HTML API', 'draft', 'missing provenance', 'duplicate', 'indexed preview', 'credential URL'], apiPostsMade: false }));
