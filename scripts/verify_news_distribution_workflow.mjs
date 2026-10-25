import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PROJECT, BRANCH } from './news_distribution.mjs';

const workflow = Bun.YAML.parse(await readFile(new URL('../.github/workflows/news-distribution.yml', import.meta.url), 'utf8'));
assert.deepEqual(workflow.permissions, { contents: 'read', actions: 'read' });
assert.deepEqual(workflow.on.workflow_run.workflows, ['Automated EV news']);
assert.deepEqual(workflow.on.workflow_run.branches, ['main']);
assert(workflow.on.schedule.length > 0, 'Independent recovery must not require a new paid article');
assert.deepEqual(workflow.on.schedule, [{ cron: '17 1-23/4 * * *' }], 'Distribution stays six times daily, away from the hour boundary');
assert.equal(workflow.on.pull_request, undefined);
assert.deepEqual(Object.keys(workflow.on.workflow_dispatch.inputs), ['redistribute_snapshot_sha256']);
assert.deepEqual(workflow.on.workflow_dispatch.inputs.redistribute_snapshot_sha256, {
  description: 'Manual replay only: exact SHA-256 of the unchanged published snapshot', required: false, type: 'string', default: '',
});
assert.equal(workflow.concurrency['cancel-in-progress'], false);
assert(!JSON.stringify(workflow).match(/OPENAI_API_KEY|SERVICE_ROLE|DEPLOY_HOOK|activation-sql|run_short_news.py/), 'Distribution must not receive a writer key or invoke publication/activation');
const gate = workflow.jobs.eligibility;
assert.equal(gate.environment, undefined);
assert(!JSON.stringify(gate).includes('secrets.'));
for (const condition of ["vars.NEWS_DISTRIBUTION_ENABLED == 'true'", "github.ref == 'refs/heads/main'", 'github.event.workflow_run.head_repository.full_name == github.repository']) assert(gate.if.includes(condition));
assert(gate.steps.some((s) => s.run === 'node scripts/news_distribution.mjs ci'));
const job = workflow.jobs.distribute;
assert.equal(job.needs, 'eligibility');
assert.equal(job.environment, 'preview');
assert.equal(job.env.NEWS_BUILD_SYNC, '0');
assert.equal(job.env.VITE_SUPABASE_ANON_KEY, '');
assert(!JSON.stringify(job.env).includes('secrets.'));
for (const name of ['Build article HTML and sitemap for the authorized snapshot', 'Verify built routes',
  'Require the same public snapshot immediately before upload', 'Recheck current CI and the existing AI preview target',
  'Upload to the existing AI preview only', 'Resolve this exact snapshot and workflow attempt',
  'Verify deployed snapshot, article HTML, sitemap and noindex']) {
  const step = job.steps.find((s) => s.name === name);
  assert(step, name);
  assert.equal(step.if, "steps.snapshot.outputs.upload_required == 'true'");
}
const reader = job.steps.find((s) => s.id === 'snapshot');
assert.equal(reader.env.SUPABASE_ANON_KEY, '${{ secrets.SUPABASE_ANON_KEY }}');
assert.equal(reader.env.NEWS_REDISTRIBUTE_HASH, "${{ inputs.redistribute_snapshot_sha256 || '' }}");
assert.equal(reader.run, 'node scripts/sync_news_snapshot.mjs --write');
const unchanged = job.steps.find((s) => s.name === 'Verify an unchanged preview instead of silently assuming healthy HTML');
assert.equal(unchanged.if, "steps.snapshot.outputs.upload_required == 'false'");
assert.equal(unchanged.run, 'node scripts/news_distribution.mjs verify');
assert(job.steps.indexOf(reader) < job.steps.findIndex((s) => s.run === 'bun install --frozen-lockfile'));
for (const step of job.steps.filter((s) => s.uses?.startsWith('oven-sh/') || s.uses?.startsWith('actions/setup-python') || s.run?.startsWith('bun '))) assert.equal(step.if, "steps.snapshot.outputs.upload_required == 'true'");
assert(!JSON.stringify(job.steps.filter((s) => s.id !== 'snapshot')).includes('inputs.'), 'Only the validated snapshot step may read replay inputs');
const upload = job.steps.find((s) => s.name === 'Upload to the existing AI preview only');
assert(upload.run.includes('wrangler@4.151.1 pages deploy dist'));
assert(upload.run.includes(`--project-name=${PROJECT}`) && upload.run.includes(`--branch=${BRANCH}`));
assert(upload.run.includes('--commit-message="news-snapshot:${NEWS_SNAPSHOT_HASH}:${GITHUB_RUN_ID}:${GITHUB_RUN_ATTEMPT}"'));
assert(!JSON.stringify(job.steps.filter((s) => s.name?.includes('Read only'))).includes('CLOUDFLARE_API_TOKEN'));
const ci = Bun.YAML.parse(await readFile(new URL('../.github/workflows/ci.yml', import.meta.url), 'utf8'));
for (const command of ['bun run verify:news-distribution', 'bun run verify:news-distribution-workflow']) assert(ci.jobs.verify.steps.some((s) => s.run === command));
console.log(JSON.stringify({ news_distribution_workflow_ok: true, default_off: true, credential_free_ci_gate: true,
  public_database_key_only: true, existing_ai_preview_only: true, hash_bound_manual_replay: true, paid_calls: 0, publications: 0, deployments: 0 }));
