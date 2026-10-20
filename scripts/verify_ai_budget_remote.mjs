import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';

// Private operator check. Never exposed by Pages and never enables a paused policy.
const cli = process.env.WRANGLER_BIN;
assert.ok(cli, 'Set WRANGLER_BIN to the installed Wrangler CLI.');
const base = 'https://codex-ai-preview.seekev-ai-preview.pages.dev';
function sql(command) {
  const result = spawnSync(process.execPath, [cli, 'd1', 'execute', 'elbilsagenten-ai-budget-preview',
    '--env', 'preview', '--remote', '--command', command, '--json'], { encoding: 'utf8', timeout: 30000, windowsHide: true });
  assert.equal(result.status, 0, 'Private budget database command failed.');
  const payload = JSON.parse(result.stdout);
  assert.ok(payload.every((item) => item.success === true));
  return payload[0].results;
}
function ledger() {
  return sql('SELECT count(*) AS requests, coalesce(sum(charged_micro),0) AS charged_micro, coalesce(sum(settled),0) AS settled FROM ai_budget_reservations')[0];
}
const policy = sql('SELECT enabled,daily_limit_micro,monthly_limit_micro,pricing_review_until FROM ai_budget_policy WHERE id=1')[0];
const before = ledger();
if (!process.argv.includes('--exercise')) {
  console.log(JSON.stringify({ private_read_only_check: true, policy, ledger: before, provider_calls: 0 }));
} else {
  assert.equal(policy.enabled, 1, 'The policy is already paused. Leave it paused.');
  const response = await fetch(`${base}/data/public_ev_variants.json`, { redirect: 'error', signal: AbortSignal.timeout(15000) });
  assert.equal(response.status, 200);
  const rows = (await response.json()).records;
  const row = rows.find((item) => ['published', 'published_reviewed'].includes(item.validation_status) && item.source_hash);
  assert.ok(row);
  const blocked = [];
  try {
    sql('UPDATE ai_budget_policy SET enabled=0 WHERE id=1');
    for (const [path, body] of [
      ['advisor', { prompt: 'Jag soker en elbil for vardagen.', budget: 1200000, range: 100 }],
      ['compare', { variant_keys: [`${row.brand}|${row.model}|${row.variant_name}`] }],
    ]) {
      const result = await fetch(`${base}/api/${path}`, { method: 'POST', redirect: 'error', signal: AbortSignal.timeout(35000),
        headers: { 'content-type': 'application/json', origin: base }, body: JSON.stringify(body) });
      assert.equal(result.status, 200);
      const payload = await result.json();
      assert.equal(payload.mode, 'deterministic_fallback', 'Emergency stop did not prevent AI.');
      assert.equal(payload.ai_status, 'budget_limited', 'The deployed route must use the shared policy.');
      assert.ok(path === 'advisor' ? payload.shortlist.length > 0 : payload.compared.length > 0);
      blocked.push({ path, mode: payload.mode, ai_status: payload.ai_status });
    }
    const after = ledger();
    assert.equal(after.requests, before.requests, 'Disabled routes must not reserve or spend.');
    assert.equal(after.charged_micro, before.charged_micro);
    console.log(JSON.stringify({ remote_emergency_stop_ok: true, blocked, ledger_unchanged: true, provider_calls: 0 }));
  } finally {
    sql('UPDATE ai_budget_policy SET enabled=1 WHERE id=1');
    assert.equal(sql('SELECT enabled FROM ai_budget_policy WHERE id=1')[0].enabled, 1);
    console.log(JSON.stringify({ preview_policy_restored: true }));
  }
}
