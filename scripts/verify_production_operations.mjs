import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { backupFresh, checkWebsite, notify, ORIGIN } from './production_monitor.mjs';

const now = new Date('2026-11-01T14:00:00Z');
const artifact = { name: 'production-backup-123-1', expired: false, size_in_bytes: 2048,
  workflow_run: { id: 123, head_branch: 'main' }, created_at: now.toISOString() };
const trusted = new Set([123]);
assert(backupFresh([artifact], now, trusted));
assert(!backupFresh([artifact], now, new Set()), 'Only a successful real backup workflow is trusted');
for (const patch of [{ expired: true }, { size_in_bytes: 0 }, { name: 'public-export' },
  { created_at: 'invalid' }, { created_at: '2026-11-02T00:00:00Z' },
  { created_at: '2026-10-29T00:00:00Z' }, { workflow_run: { head_branch: 'unreviewed' } }]) {
  assert(!backupFresh([{ ...artifact, ...patch }], now, trusted));
}
const fetchHealthy = async (url, options) => {
  assert.equal(options.method, undefined, 'Monitoring must make no paid POST');
  if (url.startsWith('http://www.') || url.startsWith('https://www.')) {
    return { status: 301, headers: new Headers({ location: ORIGIN + '/bilar/?monitor=1' }) };
  }
  return { ok: true, url, text: async () => url.includes('/health?')
    ? JSON.stringify({ ok: true, ai_enabled: true, checks: { budget_storage: true } })
    : '<html>Elbilsagenten</html>' };
};
assert.deepEqual(await checkWebsite(fetchHealthy), []);
assert.equal((await checkWebsite(async () => { throw Error('TLS failure'); })).length, 9);
const calls = [];
const call = async (path, options) => { calls.push({ path, options }); return options ? { html_url: 'fixture' } : []; };
await notify(['website:/'], { call });
assert.equal(calls[1].options.body.assignees[0], 'robertbajo-png');
assert(calls[1].options.body.body.includes('website:/'));
const existing = { number: 42, user: { login: 'github-actions[bot]' }, body: calls[1].options.body.body };
const updates = [];
await notify(['website:/'], { call: async (path, opts) => { updates.push({ path, opts }); return [existing]; } });
assert.equal(updates.length, 1, 'Repeated failure must not spam duplicate alerts');
await notify([], { call: async (path, opts) => { updates.push({ path, opts }); return opts ? {} : [existing]; } });
assert.equal(updates.at(-1).opts.body.state, 'closed');
const spoofCalls = [];
await notify(['website:/'], { call: async (path, opts) => {
  spoofCalls.push({ path, opts });
  return opts ? {} : [{ ...existing, user: { login: 'untrusted-reporter' } }];
} });
assert.equal(spoofCalls.length, 2, 'A public issue must not suppress the genuine automated alert');

for (const filename of ['production-backup.yml', 'production-monitor.yml']) {
  const wf = Bun.YAML.parse(await readFile(new URL('../.github/workflows/' + filename, import.meta.url), 'utf8'));
  assert(wf.on.schedule.length === 1);
  assert.equal(wf.on.pull_request, undefined);
  assert.equal(wf.on.pull_request_target, undefined);
  for (const job of Object.values(wf.jobs)) assert(job.if?.includes("github.ref == 'refs/heads/main'"));
  const source = JSON.stringify(wf);
  assert(!source.includes('OPENAI_API_KEY'));
  assert(!source.includes('news_engine.py'));
  assert(!source.includes('SUPABASE_SERVICE_ROLE_KEY'));
  if (filename.includes('backup')) {
    assert.equal(wf.jobs.backup.needs, 'eligible');
    assert.equal(wf.jobs.eligible.environment, undefined);
    assert(!JSON.stringify(wf.jobs.eligible).includes('secrets.'));
    assert.equal(wf.jobs.backup.environment, 'production-operations');
    const upload = wf.jobs.backup.steps.find(s => s.uses?.startsWith('actions/upload-artifact'));
    assert.equal(upload.with.path, 'backup-output/database.tar.gz.age');
    assert.equal(upload.with['retention-days'], 14);
    assert(!source.includes('AGE_SECRET_KEY'));
  } else assert(!source.includes('secrets.'));
}
console.log(JSON.stringify({ operations_checks: 'passed', network_calls: 0, paid_calls: 0, publications: 0 }));
