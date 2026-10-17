import { appendFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

export const PREVIEW_BRANCH = 'codex-ui-preview';

export function commitConfig(env) {
  if (!/^[a-f0-9]{40}$/i.test(env.DEPLOY_SHA || '')) throw new Error('An exact DEPLOY_SHA is required.');
  if (!/^[\w.-]+\/[\w.-]+$/.test(env.GITHUB_REPOSITORY || '')) throw new Error('A valid GITHUB_REPOSITORY is required.');
  return { sha: env.DEPLOY_SHA, repo: env.GITHUB_REPOSITORY, githubToken: env.GH_TOKEN };
}

export function previewConfig(env) {
  const config = {
    ...commitConfig(env),
    token: env.CLOUDFLARE_API_TOKEN,
    account: env.CLOUDFLARE_ACCOUNT_ID,
    project: env.CLOUDFLARE_PAGES_PROJECT,
  };
  if (!config.token?.trim()) throw new Error('Configure CLOUDFLARE_API_TOKEN in the GitHub preview environment.');
  if (!/^[a-f0-9]{32}$/i.test(config.account || '')) throw new Error('Configure a valid CLOUDFLARE_ACCOUNT_ID variable.');
  if (!/^[a-z0-9][a-z0-9-]{0,57}$/.test(config.project || '')) throw new Error('Configure a valid CLOUDFLARE_PAGES_PROJECT variable.');
  return config;
}

async function readApi(url, token, provider, fetchImpl) {
  let response;
  try {
    response = await fetchImpl(url, {
      headers: { accept: 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) },
      redirect: 'error', signal: AbortSignal.timeout(15000),
    });
  } catch { throw new Error(`${provider} API could not be reached.`); }
  if (!response.ok) throw new Error(`${provider} API returned HTTP ${response.status}. Check account, project and permissions.`);
  try { return await response.json(); }
  catch { throw new Error(`${provider} API did not return valid JSON.`); }
}

function cloudflareResult(payload) {
  if (payload.success !== true || !payload.result) throw new Error('Cloudflare API rejected the request.');
  return payload.result;
}

export async function checkCommitCi(config, { fetchImpl = fetch } = {}) {
  const ci = await readApi(`https://api.github.com/repos/${config.repo}/actions/workflows/ci.yml/runs?head_sha=${config.sha}&event=push&per_page=10`, config.githubToken, 'GitHub', fetchImpl);
  if (!ci.workflow_runs?.some((run) => run.head_sha === config.sha && run.head_branch === 'main' && run.event === 'push' && run.status === 'completed' && run.conclusion === 'success' && run.head_repository?.full_name === config.repo)) {
    throw new Error('Successful main-branch CI for this exact commit is required before upload.');
  }
  return { ciVerified: true, sha: config.sha };
}

export async function checkPreviewTarget(config, { fetchImpl = fetch } = {}) {
  await checkCommitCi(config, { fetchImpl });
  const project = cloudflareResult(await readApi(`https://api.cloudflare.com/client/v4/accounts/${config.account}/pages/projects/${config.project}`, config.token, 'Cloudflare', fetchImpl));
  if (project.name !== config.project || typeof project.production_branch !== 'string' || !project.production_branch.trim() || project.production_branch.trim().toLowerCase() === PREVIEW_BRANCH) throw new Error('Refusing upload: preview target is not distinct from production.');
  const bindings = project.deployment_configs?.preview?.env_vars || {};
  // This first preview must use the same canonical snapshot in browser and API.
  const serviceBindings = ['OPENAI_API_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_URL', 'SUPABASE_ANON_KEY', 'VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY'];
  if (serviceBindings.some((key) => Object.hasOwn(bindings, key))) throw new Error('Use a snapshot-only preview environment without AI or database credentials. Live integrations require a separate release check.');
  return { project: project.name, branch: PREVIEW_BRANCH, productionBranch: project.production_branch, sha: config.sha };
}

export async function resolvePreview(config, { fetchImpl = fetch } = {}) {
  const deployments = cloudflareResult(await readApi(`https://api.cloudflare.com/client/v4/accounts/${config.account}/pages/projects/${config.project}/deployments?env=preview&per_page=25`, config.token, 'Cloudflare', fetchImpl));
  if (!Array.isArray(deployments)) throw new Error('Cloudflare returned an invalid deployment list.');
  const deployment = deployments.find((item) => item.project_name === config.project && item.environment === 'preview' && item.is_skipped === false && item.latest_stage?.status === 'success' && item.deployment_trigger?.metadata?.commit_hash === config.sha && item.deployment_trigger.metadata.branch === PREVIEW_BRANCH && item.deployment_trigger.metadata.commit_dirty === false);
  if (!deployment) throw new Error('No successful preview deployment matches this exact commit and branch.');
  let url;
  try { url = new URL(deployment.url); } catch { throw new Error('Preview deployment URL is invalid.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.port || url.search || url.hash || url.pathname !== '/' || !new RegExp(`^[a-f0-9]{8,64}\\.${config.project}\\.pages\\.dev$`).test(url.hostname)) throw new Error('Refusing a custom, production or unsafe deployment URL.');
  return { url: url.origin, sha: config.sha, branch: PREVIEW_BRANCH };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const mode = process.argv[2];
    if (!['ci', 'check', 'resolve'].includes(mode)) throw new Error('Usage: node scripts/pages_preview.mjs ci|check|resolve');
    const config = mode === 'ci' ? commitConfig(process.env) : previewConfig(process.env);
    const result = mode === 'ci' ? await checkCommitCi(config) : mode === 'check' ? await checkPreviewTarget(config) : await resolvePreview(config);
    if (mode === 'resolve' && process.env.GITHUB_OUTPUT) appendFileSync(process.env.GITHUB_OUTPUT, `url=${result.url}\n`);
    console.log(JSON.stringify(result));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
