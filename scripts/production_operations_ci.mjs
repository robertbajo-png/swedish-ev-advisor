import { api, REPOSITORY } from './production_monitor.mjs';

if (process.env.GITHUB_REPOSITORY !== REPOSITORY || process.env.GITHUB_REF !== 'refs/heads/main'
  || !/^[a-f0-9]{40}$/.test(process.env.GITHUB_SHA || '')) throw Error('Unexpected operations revision');
const runs = await api(`actions/workflows/ci.yml/runs?head_sha=${process.env.GITHUB_SHA}&event=push&per_page=30`);
if (!runs.workflow_runs.some(r => r.head_sha === process.env.GITHUB_SHA && r.status === 'completed'
  && r.conclusion === 'success' && r.head_repository.full_name === REPOSITORY)) {
  throw Error('Exact main CI must pass before the backup environment is accessed');
}
console.log(JSON.stringify({ exact_main_ci_verified: true, secrets_used: false }));
