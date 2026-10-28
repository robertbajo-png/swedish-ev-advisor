import assert from 'node:assert/strict';
import { verifyDeployment } from './verify_deployment.mjs';
import { catalogHash } from './sync_public_catalog.mjs';
import { SITE_ORIGIN } from '../src/site-info.js';

const row = { brand: 'Test', model: 'EV', variant_name: 'QA fixture', validation_status: 'published', source_hash: 'fixture-hash', source_url: 'https://example.com/model' };
const app = '<html><title>Elbilsagenten</title><div id="root"></div></html>';
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

const productionRow = {...row,source_hash:'a'.repeat(64),source_quote:'Synthetic production transport fixture, not published data.',
  wltp_range_km:500,extraction_confidence:0.99,market_seen:true,available_confirmed:false,discontinued_candidate:false,coming_or_low_volume:false};
const hash = catalogHash([productionRow]);
const sitemap = `<urlset><url><loc>${SITE_ORIGIN}/bilar/test-ev</loc></url></urlset>`;
let productionMode = 'valid';
const productionFetch = async (url, options) => {
  requests++;
  assert.equal(options.method,undefined,'Production verification never makes a provider/POST request');
  const parsed = new URL(url), path = parsed.pathname;
  assert.equal(parsed.origin,SITE_ORIGIN,'Do not follow production redirects into preview');
  if (productionMode === 'foreign-redirect') return new Response(null,{status:302,headers:{location:'https://codex-ai-preview.seekev-ai-preview.pages.dev/'}});
  if (path === '/health') return Response.json(parsed.search ? {ok:true,service:'seekev-api',ai_enabled:productionMode!=='ai-disabled',
    provider_tested:false,paid_calls:0,checks:{catalog:productionMode!=='catalog-not-ready',ai_configuration:true,budget_storage:productionMode!=='budget-missing'}}
    : {ok:true,service:'seekev-api'});
  if (path === '/data/public_ev_variants.json') return Response.json({source:'supabase_public_ev_variants',
    catalog_sha256:productionMode==='wrong-hash'?'b'.repeat(64):hash,
    records:[productionMode==='changed-record'?{...productionRow,wltp_range_km:600}:productionRow]});
  if (path === '/sitemap.xml') return new Response(productionMode==='wrong-sitemap'?sitemap.replace('test-ev','other'):sitemap,{headers:{'content-type':'application/xml'}});
  if (path === '/robots.txt') return new Response(`User-agent: *\n${productionMode==='blocked-robots'?'Disallow':'Allow'}: /\nSitemap: ${SITE_ORIGIN}/sitemap.xml`);
  const canonical = SITE_ORIGIN+(path.replace(/\/$/,'')||'/');
  const tag = `<link href='${productionMode==='wrong-canonical'?SITE_ORIGIN+'/wrong':canonical}' rel='canonical'>`;
  const content = `<html><head><title>Elbilsagenten</title>${productionMode==='comment-canonical'?'<!--'+tag+'-->':tag}
    ${productionMode==='duplicate-canonical'?tag:''}${productionMode==='meta-noindex'?"<meta content='noindex' name='ROBOTS'>":''}</head><body><div id="root"></div></body></html>`;
  return new Response(content,{headers:{'content-type':'text/html',
    ...(productionMode==='missing-security-header'?{}:{'x-content-type-options':'nosniff'}),
    ...(productionMode==='header-noindex'?{'x-robots-tag':'noindex'}:{})}});
};
const productionOptions = {fetchImpl:productionFetch,expectProduction:true,expectedCatalogHash:hash,expectedSitemap:sitemap};
assert((await verifyDeployment(SITE_ORIGIN,productionOptions)).ok);
for(productionMode of ['foreign-redirect','ai-disabled','catalog-not-ready','budget-missing','wrong-hash','changed-record',
  'wrong-sitemap','blocked-robots','wrong-canonical','comment-canonical','duplicate-canonical','meta-noindex','header-noindex','missing-security-header']) {
  assert.equal((await verifyDeployment(SITE_ORIGIN,productionOptions)).ok,false,'Reject production '+productionMode);
}
const noRequests = requests;
for(const target of ['http://elbilsagenten.se',SITE_ORIGIN+'/bilar','https://codex-ai-preview.seekev-ai-preview.pages.dev']) {
  await assert.rejects(verifyDeployment(target,productionOptions));
}
await assert.rejects(verifyDeployment(SITE_ORIGIN,{...productionOptions,expectPreview:true}));
await assert.rejects(verifyDeployment(SITE_ORIGIN,{...productionOptions,expectedCatalogHash:undefined}));
await assert.rejects(verifyDeployment(SITE_ORIGIN,{fetchImpl:productionFetch}));
await assert.rejects(verifyDeployment('http://elbilsagenten.se',{fetchImpl:productionFetch}));
assert.equal(requests,noRequests,'Invalid production targets/configuration are rejected before fetching');
console.log(JSON.stringify({ deployment_contract_ok: true, rejected: ['parking', 'localhost redirect', 'HTML API', 'draft', 'missing provenance', 'duplicate', 'indexed preview', 'credential URL'], apiPostsMade: false }));
console.log(JSON.stringify({production_contract_ok:true,negative_cases:21,exact_artifact_bound:true,paid_calls:0,publications:0}));
