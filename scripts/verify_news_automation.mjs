import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { configuration, checkTarget, snapshot, verify, ORIGIN } from './production_news_distribution.mjs';
import { newsHash } from './sync_news_snapshot.mjs';

const env = { DEPLOY_SHA: 'a'.repeat(40), GITHUB_REPOSITORY: 'robertbajo-png/swedish-ev-advisor',
  GITHUB_REF: 'refs/heads/main', CLOUDFLARE_ACCOUNT_ID: 'e52a9db99ad554c58db919e0c8296e81',
  CLOUDFLARE_API_TOKEN: 'synthetic-fixture-not-a-credential' };
const config = configuration(env);
for (const patch of [{ GITHUB_REF: 'refs/heads/untrusted' }, { GITHUB_REPOSITORY: 'another/repo' },
  { CLOUDFLARE_ACCOUNT_ID: 'f'.repeat(32) }, { CLOUDFLARE_API_TOKEN: '' }]) {
  assert.throws(() => configuration({ ...env, ...patch }));
}
const project = { name: 'elbilsagenten', production_branch: 'main', deployment_configs: { production: {
  d1_databases: { AI_BUDGET_DB: { id: '206ce4df-f219-4d67-be24-e4b56f52a6be' } },
  env_vars: { AI_ENABLED: { value: 'true' }, OPENAI_MODEL: { value: 'gpt-5.4-mini' },
    VEHICLE_DATA_MODE: { value: 'snapshot' } } } } };
const json = value => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } });
const ciFetch = (p = project, { green = true, current = true } = {}) => async (url, options) => {
  assert(!options.method || options.method === 'GET', 'Deployment guards never mutate external state');
  if (url.includes('ci.yml/runs')) return json({ workflow_runs: green ? [{ head_sha: env.DEPLOY_SHA,
    head_branch: 'main', event: 'push', status: 'completed', conclusion: 'success',
    head_repository: { full_name: env.GITHUB_REPOSITORY } }] : [] });
  if (url.includes('git/ref/heads/main')) return json({ object: { sha: current ? env.DEPLOY_SHA : 'b'.repeat(40) } });
  return json({ success: true, result: p });
};
assert((await checkTarget(config, { fetchImpl: ciFetch() })).budget_binding_preserved);
for (const patch of [{ name: 'seekev-ai-preview' }, { production_branch: 'another' }, { deployment_configs: {} }]) {
  await assert.rejects(checkTarget(config, { fetchImpl: ciFetch({ ...project, ...patch }) }));
}
for (const opts of [{ green: false }, { current: false }]) {
  await assert.rejects(checkTarget(config, { fetchImpl: ciFetch(project, opts) }));
}

const article = { id: 'synthetic-1', slug: 'syntetisk-testartikel', published_at: '2026-11-01T12:00:00Z',
  title: 'Syntetiskt test & kontroll', intro: 'En syntetisk testinledning.', category: 'technology',
  editorial_method: 'independent_ai', paragraphs: [{ kind: 'reporting', text: 'Syntetiskt faktastycke.' }],
  brands: [], related_models: [], sources: [{ publisher: 'Synthetic source', url: 'https://press.example.org/test' }] };
const publicKey = 'sb_publishable_synthetic-fixture';
const snapshotFetch = (rows, live = [article]) => async (url, options) => {
  assert.equal(options.method, 'GET');
  if (String(url).startsWith(ORIGIN)) return json({ records: live });
  assert.equal(options.headers.apikey, publicKey);
  return new Response(JSON.stringify(rows), { headers: { 'content-type': 'application/json',
    'content-range': rows.length ? `0-${rows.length - 1}/${rows.length}` : '*/0' } });
};
const publicConfig = { url: 'https://eutcryxbitudllcnpnex.supabase.co', key: publicKey };
assert.equal((await snapshot(publicConfig, { fetchImpl: snapshotFetch([article]) })).upload_required, false);
assert.equal((await snapshot(publicConfig, { fetchImpl: snapshotFetch([article], []) })).upload_required, true);
await assert.rejects(snapshot(publicConfig, { fetchImpl: snapshotFetch([]) }));
await assert.rejects(snapshot({ ...publicConfig, key: 'not-a-public-key' }, { fetchImpl: snapshotFetch([article]) }));
await assert.rejects(snapshot(publicConfig, { fetchImpl: snapshotFetch([{ ...article, status: 'draft' }]) }));
const htmlFetch = ({ missing = false, noindex = false } = {}) => async (url, options) => {
  assert.equal(options.method, 'GET');
  if (url.endsWith('/data/news_articles.json')) return json({ records: [article] });
  return new Response(url.endsWith('/sitemap.xml') ? `<urlset><loc>/nyheter/${article.slug}</loc></urlset>`
    : missing ? '<html>Unavailable</html>' : '<html>Syntetiskt test &amp; kontroll NewsArticle</html>',
  { headers: noindex ? { 'x-robots-tag': 'noindex' } : {} });
};
assert((await verify([article], { fetchImpl: htmlFetch() })).production_news_verified);
await assert.rejects(verify([article], { fetchImpl: htmlFetch({ missing: true }) }));
await assert.rejects(verify([article], { fetchImpl: htmlFetch({ noindex: true }) }));
assert.equal(newsHash([article]).length, 64);

for (const file of ['news.yml', 'news-production-distribution.yml']) {
  const wf = Bun.YAML.parse(await readFile('.github/workflows/' + file, 'utf8'));
  assert.equal(wf.on.pull_request, undefined);
  assert.equal(wf.on.pull_request_target, undefined);
  const eligible = wf.jobs.eligible;
  assert(eligible.if.includes("refs/heads/main"));
  assert.equal(eligible.environment, undefined);
  assert(!JSON.stringify(eligible).includes('secrets.'));
  const worker = wf.jobs.news || wf.jobs.distribute;
  assert.equal(worker.needs, 'eligible');
  if (wf.jobs.news) {
    assert.equal(worker.environment, 'production-news');
    assert(wf.concurrency.group === 'seekev-news-production');
    assert(!JSON.stringify(worker.steps).includes(' run_short_news.py matrix'));
  } else {
    const source = JSON.stringify(worker);
    assert(!source.includes('SUPABASE_SERVICE_ROLE_KEY'));
    assert(!source.includes('OPENAI_API_KEY'));
    const upload = worker.steps.find(s => s.name === 'Upload only to the existing production project');
    assert(upload.run.includes('--project-name=elbilsagenten --branch=main'));
    assert.equal(upload['working-directory'], 'news-deploy');
    assert(source.includes('production_news_distribution.mjs confirm'));
    assert(source.includes('verify_deployment.mjs https://elbilsagenten.se --production'));
  }
}
console.log(JSON.stringify({ news_automation_guards: 'passed', network_calls: 0, paid_calls: 0, publications: 0 }));
