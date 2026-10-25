import assert from 'node:assert/strict';
import { appendFile, readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { checkCommitCi, cloudflareResult, commitConfig, readApi } from './pages_preview.mjs';
import { NEWS_PREVIEW, newsHash, normalizeNews } from './sync_news_snapshot.mjs';

export const PROJECT = 'seekev-ai-preview';
export const BRANCH = 'codex-ai-preview';

export function distributionConfig(env) {
  assert(/^[a-f0-9]{32}$/i.test(env.CLOUDFLARE_ACCOUNT_ID || ''), 'Configure CLOUDFLARE_ACCOUNT_ID in the preview environment');
  assert(env.CLOUDFLARE_API_TOKEN?.trim(), 'Configure a Pages-scoped Cloudflare token in the preview environment');
  return { ...commitConfig(env), account: env.CLOUDFLARE_ACCOUNT_ID, token: env.CLOUDFLARE_API_TOKEN, project: PROJECT };
}

export async function checkDistributionCi(config, { fetchImpl = fetch } = {}) {
  const result = await checkCommitCi(config, { fetchImpl });
  const ref = await readApi(`https://api.github.com/repos/${config.repo}/git/ref/heads/main`, config.githubToken, 'GitHub', fetchImpl);
  assert.equal(ref.object?.sha, config.sha, 'A newer main commit exists; do not deploy an older worker');
  return result;
}

export function distributionStamp(env) {
  assert(/^[a-f0-9]{64}$/.test(env.NEWS_SNAPSHOT_HASH || '') && /^\d+$/.test(env.GITHUB_RUN_ID || '') && /^\d+$/.test(env.GITHUB_RUN_ATTEMPT || ''), 'An exact snapshot and workflow attempt are required');
  return `news-snapshot:${env.NEWS_SNAPSHOT_HASH}:${env.GITHUB_RUN_ID}:${env.GITHUB_RUN_ATTEMPT}`;
}

export async function checkDistributionTarget(config, { fetchImpl = fetch } = {}) {
  assert.equal(config.project, PROJECT, 'Only the existing AI preview project is allowed');
  await checkDistributionCi(config, { fetchImpl });
  const p = cloudflareResult(await readApi(`https://api.cloudflare.com/client/v4/accounts/${config.account}/pages/projects/${PROJECT}`, config.token, 'Cloudflare', fetchImpl));
  assert(p.name === PROJECT && typeof p.production_branch === 'string' && p.production_branch.trim() && p.production_branch.trim().toLowerCase() !== BRANCH, 'News preview must be distinct from the production branch');
  return { project: PROJECT, branch: BRANCH, sha: config.sha, production_upload: false };
}

export async function resolveDistribution(config, { fetchImpl = fetch } = {}) {
  assert.equal(config.project, PROJECT, 'Only the existing AI preview project is allowed');
  assert(/^news-snapshot:[a-f0-9]{64}:\d+:\d+$/.test(config.commitMessage || ''), 'An exact deployment attempt is required');
  const rows = cloudflareResult(await readApi(`https://api.cloudflare.com/client/v4/accounts/${config.account}/pages/projects/${PROJECT}/deployments?env=preview&per_page=25`, config.token, 'Cloudflare', fetchImpl));
  assert(Array.isArray(rows), 'Invalid deployment list');
  const row = rows.find((r) => r.project_name === PROJECT && r.environment === 'preview' && r.is_skipped === false && r.latest_stage?.status === 'success' && r.deployment_trigger?.metadata?.branch === BRANCH && r.deployment_trigger.metadata.commit_hash === config.sha && r.deployment_trigger.metadata.commit_dirty === false && r.deployment_trigger.metadata.commit_message === config.commitMessage);
  assert(row, 'No exact successful news-preview deployment found');
  const url = new URL(row.url);
  assert(url.protocol === 'https:' && !url.username && !url.password && !url.port && !url.search && !url.hash && url.pathname === '/' && new RegExp(`^[a-f0-9]{8,64}\\.${PROJECT}\\.pages\\.dev$`).test(url.hostname), 'Unsafe preview deployment URL');
  return { url: url.origin, project: PROJECT, branch: BRANCH, sha: config.sha };
}

export async function verifyNewsDistribution(baseUrl, expected, { fetchImpl = fetch } = {}) {
  const base = new URL(baseUrl);
  assert(base.origin === NEWS_PREVIEW || new RegExp(`^https://[a-f0-9]{8,64}\\.${PROJECT}\\.pages\\.dev$`).test(base.origin), 'Only the existing news preview can be checked');
  assert(!base.username && !base.password && !base.port && !base.search && !base.hash && base.pathname === '/', 'Use a plain preview origin');
  const records = normalizeNews(expected);
  async function get(path) {
    const response = await fetchImpl(base.origin + path, { method: 'GET', redirect: 'error', signal: AbortSignal.timeout(15000) });
    assert(response.ok, `News deployment read failed (HTTP ${response.status})`);
    return { response, body: await response.text() };
  }
  const snapshot = await get('/data/news_articles.json');
  assert(/application\/json/i.test(snapshot.response.headers.get('content-type') || ''), 'News export is not JSON');
  assert.equal(newsHash(JSON.parse(snapshot.body).records), newsHash(records), 'Deployed news snapshot does not match the public view');
  const sitemap = await get('/sitemap.xml');
  assert(/<urlset[\s>]/.test(sitemap.body) && records.every((r) => sitemap.body.includes('/nyheter/' + r.slug)), 'Published news is missing from sitemap');
  const escape = (s) => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
  for (const record of records.slice(0, 20)) {
    const page = await get('/nyheter/' + record.slug + '/');
    assert(/noindex/i.test(page.response.headers.get('x-robots-tag') || ''), 'News preview must remain noindex');
    assert(page.body.includes(escape(record.title)) && page.body.includes('NewsArticle'), 'Article HTML or structured data is missing');
  }
  return { ok: true, published_count: records.length, article_pages_checked: Math.min(records.length, 20),
    snapshot_hash: newsHash(records), provider_calls: 0, articles_published: 0, production_writes: 0 };
}

async function main() {
  const mode = process.argv[2];
  let result;
  if (mode === 'ci') result = await checkDistributionCi(commitConfig(process.env));
  else if (mode === 'check') result = await checkDistributionTarget(distributionConfig(process.env));
  else if (mode === 'resolve') {
    result = await resolveDistribution({ ...distributionConfig(process.env), commitMessage: distributionStamp(process.env) });
    if (process.env.GITHUB_OUTPUT) await appendFile(process.env.GITHUB_OUTPUT, `url=${result.url}\n`);
  } else if (mode === 'verify') {
    const snapshot = JSON.parse(await readFile('public/data/news_articles.json', 'utf8'));
    result = await verifyNewsDistribution(process.env.PREVIEW_URL, snapshot.records);
  } else throw new Error('Usage: node scripts/news_distribution.mjs ci|check|resolve|verify');
  console.log(JSON.stringify(result));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => { console.error(error.name === 'AssertionError' ? error.message : 'News distribution check failed; credentials/provider bodies are not logged.'); process.exitCode = 1; });
}
