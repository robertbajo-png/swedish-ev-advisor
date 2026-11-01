import { pathToFileURL } from 'node:url';

export const ORIGIN = 'https://elbilsagenten.se';
export const REPOSITORY = 'robertbajo-png/swedish-ev-advisor';
const OWNER = 'robertbajo-png';
const marker = '<!-- elbilsagenten-operations:v1 -->';

export async function api(path, { method = 'GET', body, token = process.env.GITHUB_TOKEN, fetchImpl = fetch } = {}) {
  if (!token) throw new Error('Missing GitHub operations token');
  const r = await fetchImpl(`https://api.github.com/repos/${REPOSITORY}${path ? '/' + path : ''}`, {
    method, redirect: 'error', signal: AbortSignal.timeout(20000),
    headers: { authorization: `Bearer ${token}`, accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28', 'content-type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!r.ok) throw new Error(`GitHub operations HTTP ${r.status}`);
  return r.status === 204 ? null : r.json();
}

export function backupFresh(artifacts, now = new Date(), successfulRunIds = new Set()) {
  return artifacts.some(a => /^production-backup-\d+-\d+$/.test(a.name) && !a.expired
    && a.size_in_bytes > 1000 && a.workflow_run?.head_branch === 'main'
    && successfulRunIds.has(a.workflow_run.id)
    && Number.isFinite(Date.parse(a.created_at)) && Date.parse(a.created_at) <= +now
    && +now - Date.parse(a.created_at) <= 36 * 3600000);
}

export async function checkWebsite(fetchImpl = fetch) {
  const failures = [];
  for (const path of ['/', '/bilar/', '/jamfor/', '/nyheter/', '/integritet/', '/kontakt/', '/health?readiness=1']) {
    try {
      const r = await fetchImpl(ORIGIN + path, { redirect: 'error', signal: AbortSignal.timeout(15000) });
      if (!r.ok || new URL(r.url).origin !== ORIGIN) throw new Error('route');
      const body = await r.text();
      if (path.startsWith('/health')) {
        const health = JSON.parse(body);
        if (health.ok !== true || health.ai_enabled !== true || health.checks?.budget_storage !== true) throw new Error('readiness');
      } else if (!/Elbilsagenten/.test(body) || /Parked at Loopia|domänen är parkerad/i.test(body)) throw new Error('parking');
    } catch { failures.push('website:' + path.split('?')[0]); }
  }
  for (const scheme of ['http:', 'https:']) {
    try {
      const r = await fetchImpl(`${scheme}//www.elbilsagenten.se/bilar/?monitor=1`, {
        redirect: 'manual', signal: AbortSignal.timeout(15000) });
      if (r.status !== 301 || r.headers.get('location') !== ORIGIN + '/bilar/?monitor=1') throw new Error('redirect');
      await r.body?.cancel();
    } catch { failures.push('www:' + scheme); }
  }
  return failures;
}

export async function notify(failures, { call = api, test = false } = {}) {
  const tag = test ? '<!-- elbilsagenten-operations:test -->' : marker;
  const issues = await call('issues?state=open&per_page=100');
  const existing = issues.find(i => !i.pull_request && i.user?.login === 'github-actions[bot]' && i.body?.includes(tag));
  const run = `${process.env.GITHUB_RUN_ID || ''}`;
  const runLink = /^\d+$/.test(run) ? `https://github.com/${REPOSITORY}/actions/runs/${run}` : null;
  if (failures.length && !existing) {
    return call('issues', { method: 'POST', body: {
      title: test ? '[Driftprov] Elbilsagentens larmkedja' : '[Driftlarm] Elbilsagenten behöver kontrolleras',
      assignees: [OWNER], body: `${tag}\n\n${test ? 'Märkt leveransprov, inte ett verkligt driftfel.' : 'Automatisk kontroll misslyckades.'}\n\n`
        + failures.map(f => `- ${f}`).join('\n') + (runLink ? `\n\n[Kontrollens körning](${runLink})` : '')
        + '\n\nInga AI-anrop eller automatiska reparationer görs. Inga databasuppgifter visas.',
    } });
  }
  if (!failures.length && existing) {
    await call(`issues/${existing.number}/comments`, { method: 'POST', body: { body: 'Kontrollerna passerar igen. Larmet stängs automatiskt.' } });
    await call(`issues/${existing.number}`, { method: 'PATCH', body: { state: 'closed', state_reason: 'completed' } });
  }
  return existing || null;
}

export async function main() {
  if (process.env.GITHUB_REPOSITORY !== REPOSITORY || process.env.GITHUB_REF !== 'refs/heads/main') {
    throw new Error('Operations may run only on the expected repository main branch');
  }
  if (process.argv.includes('--alert-test')) {
    const issue = await notify(['delivery-test'], { test: true });
    console.log(JSON.stringify({ alert_test: true, issue: issue.html_url, paid_calls: 0 }));
    return;
  }
  const failures = process.argv.includes('--backup-failed') ? ['backup:job-failed'] : await checkWebsite();
  if (!process.argv.includes('--backup-failed')) {
    const { artifacts } = await api('actions/artifacts?per_page=100');
    const { workflow_runs: runs } = await api('actions/workflows/production-backup.yml/runs?branch=main&status=success&per_page=50');
    const successfulRunIds = new Set(runs.filter(r => r.head_repository?.full_name === REPOSITORY).map(r => r.id));
    if (!backupFresh(artifacts, new Date(), successfulRunIds)) failures.push('backup:no-encrypted-copy-within-36-hours');
  }
  await notify(failures);
  console.log(JSON.stringify({ ok: failures.length === 0, failures, paid_calls: 0, repairs: 0 }));
  if (failures.length) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { console.error('Production operations failed; check Actions. No private response body logged.'); process.exitCode = 1; });
}
