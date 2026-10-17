import assert from 'node:assert/strict';
import { checkCommitCi, checkPreviewTarget, commitConfig, previewConfig, resolvePreview, PREVIEW_BRANCH } from './pages_preview.mjs';

const env = { CLOUDFLARE_API_TOKEN: 'test-only-not-a-credential', CLOUDFLARE_ACCOUNT_ID: 'a'.repeat(32), CLOUDFLARE_PAGES_PROJECT: 'seekev-preview', DEPLOY_SHA: 'b'.repeat(40), GITHUB_REPOSITORY: 'owner/repo', GH_TOKEN: 'test-only-github-token' };
const config = previewConfig(env);
for (const key of ['CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_PAGES_PROJECT', 'DEPLOY_SHA', 'GITHUB_REPOSITORY']) assert.throws(() => previewConfig({ ...env, [key]: '' }));
assert.throws(() => previewConfig({ ...env, CLOUDFLARE_PAGES_PROJECT: '../production' }));

let mode = 'valid';
let calls = [];
const fetchImpl = async (url, options) => {
  assert.equal(options.method, undefined, 'Preflight and resolution only perform GET.');
  assert.equal(options.redirect, 'error', 'Do not forward authorization across redirects.');
  calls.push(url);
  if (url.startsWith('https://api.github.com/')) {
    assert.equal(options.headers.authorization, `Bearer ${env.GH_TOKEN}`);
    return Response.json({ workflow_runs: [{ head_sha: mode === 'wrong-ci-sha' ? 'c'.repeat(40) : config.sha, head_branch: mode === 'other-branch' ? 'feature' : 'main', event: 'push', status: 'completed', conclusion: mode === 'failed-ci' ? 'failure' : 'success', head_repository: { full_name: mode === 'fork' ? 'stranger/repo' : config.repo } }] });
  }
  assert.equal(options.headers.authorization, `Bearer ${env.CLOUDFLARE_API_TOKEN}`);
  if (mode === 'denied') return new Response('private-provider-body', { status: 403 });
  if (mode === 'api-error') return Response.json({ success: false, errors: [{ message: 'private-provider-body' }] });
  if (!url.includes('/deployments?')) {
    return Response.json({ success: true, result: { name: config.project, production_branch: mode === 'production-branch' ? PREVIEW_BRANCH : 'main', deployment_configs: { preview: { env_vars: mode === 'ai-binding' ? { OPENAI_API_KEY: { type: 'secret_text' } } : mode === 'database-binding' ? { SUPABASE_URL: { type: 'plain_text' } } : mode === 'service-role' ? { SUPABASE_SERVICE_ROLE_KEY: { type: 'secret_text' } } : {} } } } });
  }
  const item = { project_name: config.project, environment: mode === 'production-deployment' ? 'production' : 'preview', is_skipped: false, latest_stage: { status: mode === 'failed-deployment' ? 'failure' : 'success' }, deployment_trigger: { metadata: { branch: mode === 'wrong-deployment-branch' ? 'main' : PREVIEW_BRANCH, commit_hash: mode === 'wrong-deployment-sha' ? 'c'.repeat(40) : config.sha, commit_dirty: mode === 'dirty' } }, url: mode === 'unsafe-url' ? 'https://seekev.se/' : mode === 'foreign-preview' ? 'https://abcd1234.other-project.pages.dev/' : 'https://abcd1234.seekev-preview.pages.dev/' };
  return Response.json({ success: true, result: mode === 'missing-deployment' ? [] : [item] });
};

assert.deepEqual(await checkCommitCi(commitConfig({ DEPLOY_SHA: env.DEPLOY_SHA, GITHUB_REPOSITORY: env.GITHUB_REPOSITORY, GH_TOKEN: env.GH_TOKEN }), { fetchImpl }), { ciVerified: true, sha: config.sha });
assert.equal(calls.length, 1, 'The first CI gate needs no Cloudflare credentials or calls.');
assert.deepEqual(await checkPreviewTarget(config, { fetchImpl }), { project: config.project, branch: PREVIEW_BRANCH, productionBranch: 'main', sha: config.sha });
assert.equal((await resolvePreview(config, { fetchImpl })).url, 'https://abcd1234.seekev-preview.pages.dev');
for (mode of ['wrong-ci-sha', 'other-branch', 'failed-ci', 'fork', 'production-branch', 'ai-binding', 'database-binding', 'service-role', 'denied', 'api-error']) {
  calls = [];
  await assert.rejects(checkPreviewTarget(config, { fetchImpl }), (error) => !error.message.includes('private-provider-body'));
  if (['wrong-ci-sha', 'other-branch', 'failed-ci', 'fork'].includes(mode)) assert.equal(calls.length, 1, 'Unverified code must not reach the Cloudflare API.');
}
for (mode of ['production-deployment', 'failed-deployment', 'wrong-deployment-branch', 'wrong-deployment-sha', 'dirty', 'unsafe-url', 'foreign-preview', 'missing-deployment']) await assert.rejects(resolvePreview(config, { fetchImpl }));
await assert.rejects(checkPreviewTarget(config, { fetchImpl: async () => { throw new Error('private-provider-body'); } }), /GitHub API could not be reached/);
console.log(JSON.stringify({ pages_preview_contract_ok: true, realProviderRequests: 0, publicationRequests: 0 }));
