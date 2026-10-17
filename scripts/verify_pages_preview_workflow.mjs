import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PREVIEW_BRANCH } from './pages_preview.mjs';
import './verify_pages_preview_contract.mjs';

const workflow = Bun.YAML.parse(await readFile(new URL('../.github/workflows/preview.yml', import.meta.url), 'utf8'));
assert.deepEqual(workflow.permissions, { contents: 'read', actions: 'read' });
assert.deepEqual(workflow.on.workflow_run.workflows, ['Verify SeekEV']);
assert.deepEqual(workflow.on.workflow_run.branches, ['main']);
assert.equal(workflow.on.pull_request, undefined);
assert(!JSON.stringify(workflow.env).includes('secrets.'));

const gate = workflow.jobs.eligibility;
assert.equal(gate.environment, undefined, 'No environment credentials before CI is verified.');
assert(!JSON.stringify(gate).includes('secrets.'));
assert(gate.steps.some((step) => step.run === 'node scripts/pages_preview.mjs ci'));
for (const condition of ["github.ref == 'refs/heads/main'", "vars.PREVIEW_DEPLOY_ENABLED == 'true'", "github.event.workflow_run.event == 'push'", 'github.event.workflow_run.head_repository.full_name == github.repository']) assert(gate.if.includes(condition));

const preview = workflow.jobs.preview;
assert.equal(preview.needs, 'eligibility');
assert.equal(preview.environment, 'preview');
assert.equal(preview.env.VITE_SUPABASE_URL, '');
assert.equal(preview.env.VITE_SUPABASE_ANON_KEY, '');
const upload = preview.steps.find((step) => step.name === 'Upload to preview branch only');
assert(upload.run.includes('wrangler@4.151.1 pages deploy dist'));
assert.deepEqual(upload.run.split(/\s+/).filter((argument) => argument.startsWith('--branch=')), [`--branch=${PREVIEW_BRANCH}`]);
for (const argument of ['--project-name="$CLOUDFLARE_PAGES_PROJECT"', '--commit-hash="$DEPLOY_SHA"', '--commit-dirty=false']) assert(upload.run.includes(argument));
assert(preview.steps.some((step) => step.run?.includes('--expect-preview')));
console.log(JSON.stringify({ preview_workflow_ok: true, credentialFreeCiGate: true, productionUploadEnabled: false }));
