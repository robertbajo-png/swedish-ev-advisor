import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { authorizeNewsDistribution, fetchPublishedNews, NEWS_PREVIEW, newsHash, normalizeNews, planNewsSync } from './sync_news_snapshot.mjs';
import { BRANCH, PROJECT, checkDistributionCi, checkDistributionTarget, distributionConfig,
  distributionStamp, resolveDistribution, verifyNewsDistribution } from './news_distribution.mjs';

// Existing published fixtures, used offline. No new live editorial proof is claimed.
const records = normalizeNews(JSON.parse(await readFile(new URL('../public/data/news_articles.json', import.meta.url), 'utf8')).records);
assert(records.length >= 2, 'Distribution regressions need two published test fixtures');
const rows = records.map((payload) => ({ id: payload.id, slug: payload.slug, published_at: payload.published_at, payload }));
const config = { url: 'https://testproject.supabase.co', key: 'sb_publishable_test_only' };
const json = (value, extra = {}) => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json', ...extra } });
let checks = 0;
function ok(check) { assert(check); checks++; }
async function rejects(fn, message) { await assert.rejects(fn, message); checks++; }

ok(newsHash(records) === newsHash([...records].reverse()));
const internal = structuredClone(rows);
internal[0].payload.short_brief = { private: true };
internal[0].payload.sources[0].source_quote = 'private source body';
internal[0].payload.paragraphs[0].fact_ids = ['private-fact'];
const cleaned = JSON.stringify(normalizeNews(internal));
ok(!cleaned.includes('short_brief') && !cleaned.includes('source_quote') && !cleaned.includes('fact_ids'));
for (const mutate of [
  (r) => { r[0].status = 'draft'; },
  (r) => { r[0].slug = '../private'; },
  (r) => { r[1].id = r[0].id; },
  (r) => { r[0].payload.sources = []; },
  (r) => { r[0].payload.sources[0].url = 'javascript:alert(1)'; },
  (r) => { r[0].published_at = null; },
  (r) => { r[0].payload.paragraphs[0].kind = 'unsupported'; },
]) {
  const changed = structuredClone(rows); mutate(changed);
  assert.throws(() => normalizeNews(changed)); checks++;
}

const gets = [];
const paged = async (url, options) => {
  url = new URL(url); gets.push({ url, options });
  const offset = Number(url.searchParams.get('offset'));
  return json([rows[offset]], { 'content-range': `${offset}-${offset}/${rows.length}` });
};
ok(newsHash(await fetchPublishedNews({ ...config, pageSize: 1, fetchImpl: paged })) === newsHash(records));
ok(gets.length === rows.length && gets.every(({ url, options }) => url.pathname === '/rest/v1/public_news_articles' && options.method === 'GET' && options.redirect === 'error'));
ok(gets.every(({ options }) => options.headers.apikey === config.key && !options.headers.authorization));
const serverKey = 'x.' + Buffer.from(JSON.stringify({ role: 'service_role' })).toString('base64url') + '.x';
await rejects(() => fetchPublishedNews({ ...config, key: serverKey, fetchImpl: () => { throw Error('Must not fetch'); } }), /public key/);
for (const url of ['http://testproject.supabase.co', 'https://127.0.0.1', config.url + '/rest/v1/', config.url + '?x=1']) {
  await rejects(() => fetchPublishedNews({ ...config, url, fetchImpl: () => { throw Error('Must not fetch'); } }));
}
await rejects(() => fetchPublishedNews({ ...config, fetchImpl: async () => json(rows) }), /pagination/);
await rejects(() => fetchPublishedNews({ ...config, fetchImpl: async () => json(rows.slice(0, 1), { 'content-range': '0-0/2' }) }), /Truncated/);
let page = 0;
await rejects(() => fetchPublishedNews({ ...config, pageSize: 1, fetchImpl: async () => json([rows[page]], { 'content-range': `${page}-${page++}/${page === 1 ? 2 : 3}` }) }), /changed during pagination/);
ok((await fetchPublishedNews({ ...config, fetchImpl: async () => json([], { 'content-range': '*/0' }) })).length === 0);
await rejects(() => fetchPublishedNews({ ...config, fetchImpl: async () => new Response('secret error body', { status: 403 }) }), /HTTP 403/);

function sourceAndPreview(remoteRows = rows, live = records) {
  return async (url, options) => {
    if (String(url).startsWith(config.url)) return json(remoteRows, { 'content-range': remoteRows.length ? `0-${remoteRows.length - 1}/${remoteRows.length}` : '*/0' });
    assert.equal(String(url), NEWS_PREVIEW + '/data/news_articles.json');
    assert(!options.headers?.apikey && !options.headers?.authorization, 'Never send a database key to the website');
    return json({ records: live });
  };
}
const unchanged = await planNewsSync(config, { fetchImpl: sourceAndPreview() });
ok(!unchanged.changed && unchanged.published_count === records.length && unchanged.provider_calls === 0 && unchanged.production_writes === 0);
ok(!authorizeNewsDistribution(unchanged).upload_required);
const manualReplay = { NEWS_REDISTRIBUTE_HASH: newsHash(records), GITHUB_EVENT_NAME: 'workflow_dispatch', GITHUB_REF: 'refs/heads/main' };
const replay = authorizeNewsDistribution(unchanged, manualReplay);
ok(replay.upload_required && replay.redistribution_requested && !replay.changed);
ok(replay.snapshot_hash === unchanged.snapshot_hash && newsHash(replay.records) === newsHash(records));
for (const env of [
  { ...manualReplay, GITHUB_EVENT_NAME: 'schedule' },
  { ...manualReplay, GITHUB_EVENT_NAME: 'workflow_run' },
  { ...manualReplay, GITHUB_EVENT_NAME: 'pull_request' },
  { ...manualReplay, GITHUB_REF: 'refs/heads/feature' },
  { ...manualReplay, NEWS_REDISTRIBUTE_HASH: 'true' },
  { ...manualReplay, NEWS_REDISTRIBUTE_HASH: 'a'.repeat(64) },
]) {
  assert.throws(() => authorizeNewsDistribution(unchanged, env)); checks++;
}
assert.throws(() => authorizeNewsDistribution({ ...unchanged, previous_preview_hash: 'a'.repeat(64) }, manualReplay)); checks++;
assert.throws(() => authorizeNewsDistribution({ ...unchanged, changed: true }, manualReplay)); checks++;
assert.throws(() => authorizeNewsDistribution({ ...unchanged, records: [] }, manualReplay)); checks++;
assert.throws(() => authorizeNewsDistribution({ ...unchanged, snapshot_hash: 'a'.repeat(64) })); checks++;
const behind = await planNewsSync(config, { fetchImpl: sourceAndPreview(rows, records.slice(1)) });
ok(authorizeNewsDistribution(behind, { GITHUB_EVENT_NAME: 'schedule' }).upload_required);
ok(!authorizeNewsDistribution(behind).redistribution_requested);
ok((await planNewsSync(config, { fetchImpl: sourceAndPreview(rows, records.slice(1)) })).changed);
await rejects(() => planNewsSync(config, { fetchImpl: sourceAndPreview([], records) }), /erase/);
let reads = 0;
await rejects(() => planNewsSync(config, { fetchImpl: async () => {
  const r = reads++ === 0 ? rows : rows.slice(1);
  return json(r, { 'content-range': `0-${r.length - 1}/${r.length}` });
} }), /changed during synchronization/);

const sha = 'a'.repeat(40), hash = 'b'.repeat(64);
const env = { DEPLOY_SHA: sha, GITHUB_REPOSITORY: 'example/repo', CLOUDFLARE_ACCOUNT_ID: 'c'.repeat(32),
  CLOUDFLARE_API_TOKEN: 'test-token-only', NEWS_SNAPSHOT_HASH: hash, GITHUB_RUN_ID: '123', GITHUB_RUN_ATTEMPT: '1' };
const cfg = { ...distributionConfig(env), commitMessage: distributionStamp(env) };
const ci = { workflow_runs: [{ head_sha: sha, head_branch: 'main', event: 'push', status: 'completed', conclusion: 'success', head_repository: { full_name: env.GITHUB_REPOSITORY } }] };
function infrastructure({ head = sha, project = PROJECT, productionBranch = 'main', green = true } = {}) {
  return async (url) => {
    if (url.includes('/actions/workflows/')) return json(green ? ci : { workflow_runs: [] });
    if (url.includes('/git/ref/heads/main')) return json({ object: { sha: head } });
    return json({ success: true, result: { name: project, production_branch: productionBranch } });
  };
}
ok((await checkDistributionTarget(cfg, { fetchImpl: infrastructure() })).branch === BRANCH);
await rejects(() => checkDistributionCi(cfg, { fetchImpl: infrastructure({ head: 'd'.repeat(40) }) }), /newer main commit/);
await rejects(() => checkDistributionTarget(cfg, { fetchImpl: infrastructure({ green: false }) }), /Successful main-branch CI/);
await rejects(() => checkDistributionTarget(cfg, { fetchImpl: infrastructure({ productionBranch: BRANCH }) }), /distinct/);
await rejects(() => checkDistributionTarget({ ...cfg, project: 'production' }, { fetchImpl: infrastructure() }), /existing AI preview/);
await rejects(() => checkDistributionTarget(cfg, { fetchImpl: infrastructure({ project: 'other-preview' }) }), /distinct/);
assert.throws(() => distributionConfig({ ...env, CLOUDFLARE_API_TOKEN: '' })); checks++;
assert.throws(() => distributionStamp({ ...env, NEWS_SNAPSHOT_HASH: 'invalid' })); checks++;

const deployment = { project_name: PROJECT, environment: 'preview', is_skipped: false, latest_stage: { status: 'success' },
  deployment_trigger: { metadata: { branch: BRANCH, commit_hash: sha, commit_dirty: false, commit_message: cfg.commitMessage } },
  url: `https://1234abcd.${PROJECT}.pages.dev` };
ok((await resolveDistribution(cfg, { fetchImpl: async () => json({ success: true, result: [deployment] }) })).url === deployment.url);
for (const mutate of [(r) => { r.deployment_trigger.metadata.commit_message = 'old attempt'; },
  (r) => { r.environment = 'production'; }, (r) => { r.deployment_trigger.metadata.commit_dirty = true; },
  (r) => { r.latest_stage.status = 'failure'; }, (r) => { r.url = 'https://seekev.se/'; }]) {
  const changed = structuredClone(deployment); mutate(changed);
  await rejects(() => resolveDistribution(cfg, { fetchImpl: async () => json({ success: true, result: [changed] }) }));
}

const escape = (s) => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
function website({ live = records, noindex = true, sitemap = true, html = true } = {}) {
  return async (url, options) => {
    assert.equal(options.method, 'GET');
    const path = new URL(url).pathname;
    if (path === '/data/news_articles.json') return json({ records: live });
    if (path === '/sitemap.xml') return new Response('<urlset>' + (sitemap ? records.map((r) => '/nyheter/' + r.slug).join(' ') : '') + '</urlset>');
    const r = records.find((r) => path === '/nyheter/' + r.slug + '/');
    assert(r);
    return new Response(html ? '<h1>' + escape(r.title) + '</h1><script>NewsArticle</script>' : '<div id="root"></div>', { headers: { 'x-robots-tag': noindex ? 'noindex' : '' } });
  };
}
ok((await verifyNewsDistribution(deployment.url, records, { fetchImpl: website() })).ok);
for (const settings of [{ live: records.slice(1) }, { noindex: false }, { sitemap: false }, { html: false }]) {
  await rejects(() => verifyNewsDistribution(deployment.url, records, { fetchImpl: website(settings) }));
}
await rejects(() => verifyNewsDistribution('https://seekev.se', records, { fetchImpl: website() }), /existing news preview/);

console.log(JSON.stringify({ news_distribution_contract_ok: true, checks, network: 'offline_fixtures_only', paid_calls: 0, publications: 0, deployments: 0 }));
