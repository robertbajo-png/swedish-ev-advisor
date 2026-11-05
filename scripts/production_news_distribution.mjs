import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { appendFile, cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { checkDistributionCi } from './news_distribution.mjs';
import { cloudflareResult, commitConfig, readApi } from './pages_preview.mjs';
import { fetchPublishedNews, newsHash, normalizeNews } from './sync_news_snapshot.mjs';
import { atomicJson } from './sync_public_catalog.mjs';
import { PUBLIC_CONTENT_VERSION } from '../src/public-content-version.js';

export const PROJECT = 'elbilsagenten';
export const ORIGIN = 'https://elbilsagenten.se';
const ACCOUNT = 'e52a9db99ad554c58db919e0c8296e81';
const BUDGET_ID = '206ce4df-f219-4d67-be24-e4b56f52a6be';
const REPO = 'robertbajo-png/swedish-ev-advisor';

export function configuration(env) {
  const config = commitConfig(env);
  assert.equal(config.repo, REPO, 'Unexpected production repository');
  assert.equal(env.GITHUB_REF, 'refs/heads/main', 'Production news requires main');
  assert.equal(env.CLOUDFLARE_ACCOUNT_ID, ACCOUNT, 'Unexpected production account');
  assert(env.CLOUDFLARE_API_TOKEN?.trim(), 'Missing existing Pages credential');
  return { ...config, account: ACCOUNT, token: env.CLOUDFLARE_API_TOKEN };
}

async function get(base, pathname, fetchImpl) {
  const response = await fetchImpl(base + pathname, { method: 'GET', redirect: 'error', signal: AbortSignal.timeout(20000) });
  assert(response.ok, `Production news GET failed: ${response.status}`);
  return { response, body: await response.text() };
}

async function currentRss(rows, fetchImpl) {
  const response = await fetchImpl(ORIGIN + '/nyheter/rss.xml', {
    method: 'GET', redirect: 'error', signal: AbortSignal.timeout(20000) });
  if (response.status === 404) return false;
  assert(response.ok, `Production RSS GET failed: ${response.status}`);
  if (!/application\/rss\+xml/i.test(response.headers.get('content-type') || '')) return false;
  const body = await response.text();
  // The build's XML is tested with ElementTree; this detects legacy SPA/cache replies
  // and missing current links, not a substitute for source or editorial validation.
  return body.startsWith('<?xml ') && body.includes('<rss ') && body.includes('<channel>') &&
    body.includes(ORIGIN + '/nyheter/rss.xml') && [...rows]
      .sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at)).slice(0, 50)
      .every(row => body.includes(ORIGIN + '/nyheter/' + row.slug + '/'));
}

export async function snapshot(config, { fetchImpl = fetch } = {}) {
  const records = await fetchPublishedNews({ ...config, fetchImpl });
  const confirmation = await fetchPublishedNews({ ...config, fetchImpl });
  const hash = newsHash(records);
  assert.equal(hash, newsHash(confirmation), 'Published news changed during export');
  const current = JSON.parse((await get(ORIGIN, '/data/news_articles.json', fetchImpl)).body);
  assert(records.length > 0 || current.records.length === 0, 'Refusing to erase production news');
  const rss_update_required = !await currentRss(records, fetchImpl);
  const home = (await get(ORIGIN, '/', fetchImpl)).body;
  const public_content_update_required = !home.includes(`<meta name="public-content-version" content="${PUBLIC_CONTENT_VERSION}"`);
  return { records, snapshot_hash: hash, rss_update_required, public_content_update_required,
    upload_required: hash !== newsHash(current.records) || rss_update_required || public_content_update_required };
}

export async function checkTarget(config, { fetchImpl = fetch } = {}) {
  await checkDistributionCi(config, { fetchImpl });
  const project = cloudflareResult(await readApi(`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/pages/projects/${PROJECT}`,
    config.token, 'Cloudflare', fetchImpl));
  assert.equal(project.name, PROJECT);
  assert.equal(project.production_branch, 'main');
  const prod = project.deployment_configs?.production;
  assert.equal(prod?.d1_databases?.AI_BUDGET_DB?.id, BUDGET_ID, 'Production budget binding changed');
  assert.equal(prod?.env_vars?.AI_ENABLED?.value, 'true', 'Advisor configuration changed');
  assert.equal(prod?.env_vars?.OPENAI_MODEL?.value, 'gpt-5.4-mini', 'Advisor model changed');
  assert.equal(prod?.env_vars?.VEHICLE_DATA_MODE?.value, 'snapshot', 'Catalog mode changed');
  return { project: PROJECT, branch: 'main', sha: config.sha, budget_binding_preserved: true };
}

export async function verify(expected, { fetchImpl = fetch } = {}) {
  const rows = normalizeNews(expected);
  const home = (await get(ORIGIN, '/', fetchImpl)).body;
  assert(home.includes(`<meta name="public-content-version" content="${PUBLIC_CONTENT_VERSION}"`) && home.includes('id="public-page-data"') && home.includes('<h1'),
    'Reviewed public HTML content was not deployed');
  const exported = JSON.parse((await get(ORIGIN, '/data/news_articles.json', fetchImpl)).body);
  assert.equal(newsHash(exported.records), newsHash(rows), 'Production news snapshot mismatch');
  const sitemap = await get(ORIGIN, '/sitemap.xml', fetchImpl);
  assert(rows.every(r => sitemap.body.includes('/nyheter/' + r.slug)), 'Article missing from production sitemap');
  const escape = s => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
  for (const row of rows) {
    const page = await get(ORIGIN, '/nyheter/' + row.slug + '/', fetchImpl);
    assert(!/noindex/i.test(page.response.headers.get('x-robots-tag') || ''), 'Production article is noindex');
    assert(page.body.includes(escape(row.title)) && page.body.includes('NewsArticle'), 'Article HTML missing');
  }
  assert(await currentRss(rows, fetchImpl), 'Production RSS missing or stale');
  return { production_news_verified: true, articles: rows.length, paid_calls: 0, publications: 0 };
}

export async function packageBuild(sha, expectedHash) {
  const git = (...args) => execFileSync('git', args, { encoding: 'utf8', windowsHide: true });
  assert.equal(git('rev-parse', 'HEAD').trim(), sha, 'Package must use the reviewed commit');
  assert.equal(git('diff', '--name-only', sha, '--', 'src', 'functions', 'wrangler.production.toml').trim(), '', 'Application source changed');
  assert.equal(newsHash(JSON.parse(await readFile('dist/data/news_articles.json')).records), expectedHash);
  const catalog = JSON.parse(await readFile('dist/data/public_ev_variants.json'));
  const canonical = JSON.parse(git('show', `${sha}:public/data/public_ev_variants.json`));
  assert.deepEqual(catalog, canonical, 'A news deployment must not change the vehicle catalog');
  const stage = path.resolve('news-deploy');
  await mkdir(stage); // A reused or partial package is never accepted.
  const files = git('ls-tree', '-r', '--name-only', sha, '--', 'functions', 'src/advisor-matching.js',
    'src/price-evidence.js', 'src/vehicle-names.js').trim().split('\n');
  for (const file of files) {
    assert(/^(?:functions\/.*\.(?:js|mjs)|src\/[\w-]+\.js)$/.test(file), 'Unexpected function source');
    await mkdir(path.dirname(path.join(stage, file)), { recursive: true });
    await writeFile(path.join(stage, file), git('show', `${sha}:${file}`));
  }
  const wrangler = git('show', `${sha}:wrangler.production.toml`);
  assert(wrangler.includes(`name = "${PROJECT}"`) && wrangler.includes(BUDGET_ID), 'Wrong Wrangler production configuration');
  await writeFile(path.join(stage, 'wrangler.toml'), wrangler);
  await writeFile(path.join(stage, 'package.json'), '{"type":"module"}\n');
  await cp('dist', path.join(stage, 'dist'), { recursive: true, errorOnExist: true, force: false });
  return { package: 'news-deploy', catalog_unchanged: true, secrets_copied: 0 };
}

async function main() {
  const mode = process.argv[2];
  let result;
  if (mode === 'snapshot' || mode === 'confirm') {
    result = await snapshot({ url: process.env.SUPABASE_URL, key: process.env.SUPABASE_ANON_KEY });
    if (mode === 'confirm') assert.equal(result.snapshot_hash, process.env.NEWS_SNAPSHOT_HASH, 'News changed after build');
    else {
      await atomicJson('public/data/news_articles.json', { generated_at: new Date().toISOString(), records: result.records });
      if (process.env.GITHUB_OUTPUT) await appendFile(process.env.GITHUB_OUTPUT,
        `upload_required=${result.upload_required}\nsnapshot_hash=${result.snapshot_hash}\n`);
    }
    result = { ...result, records: undefined };
  } else if (mode === 'check') result = await checkTarget(configuration(process.env));
  else if (mode === 'package') result = await packageBuild(process.env.DEPLOY_SHA, process.env.NEWS_SNAPSHOT_HASH);
  else if (mode === 'verify') result = await verify(JSON.parse(await readFile('public/data/news_articles.json')).records);
  else throw Error('Use snapshot|confirm|check|package|verify');
  console.log(JSON.stringify(result));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => {
    console.error(error.name === 'AssertionError' ? error.message : 'Production news delivery failed; credentials and provider bodies suppressed');
    process.exitCode = 1;
  });
}
