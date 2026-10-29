import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { productionHandover } from './production_budget.mjs';
import { PRICING_VERSION } from '../functions/_shared/ai-budget.mjs';

const now = new Date('2026-10-29T06:45:00Z');
const snapshot = { day_utc: '2026-10-29', checked_at_utc: now.toISOString(),
  preview_enabled: 0, preview_unsettled: 0, production_enabled: 0, production_reservations: 0,
  today_micro: 1500, month_micro: 9507,
  pricing_version: PRICING_VERSION, pricing_review_until: '2026-11-19' };
const handover = productionHandover(snapshot, now);
assert.equal(handover.daily_limit_micro + snapshot.today_micro, 1000000);
assert.equal(handover.monthly_limit_micro + snapshot.month_micro, 10000000);
for (const patch of [{ preview_enabled: 1 }, { preview_unsettled: 1 }, { production_enabled: 1 },
  { production_reservations: 1 }, { today_micro: -1 }, { month_micro: 0 },
  { today_micro: 1.5 }, { month_micro: 10000000 }, { today_micro: 1000000 },
  { day_utc: '2026-10-28' }, { checked_at_utc: '2026-10-29T06:42:00Z' },
  { checked_at_utc: '2026-10-29T06:46:00Z' }, { pricing_version: 'unknown' },
  { pricing_review_until: 'invalid' }, { pricing_review_until: '2026-10-28' }]) {
  assert.throws(() => productionHandover({ ...snapshot, ...patch }, now));
}
const db = new DatabaseSync(':memory:');
db.exec(readFileSync(new URL('../database/cloudflare/ai_budget_production.sql', import.meta.url), 'utf8'));
let databaseDay = '2026-10-30';
db.function('date', { varargs: true }, () => databaseDay);
assert.equal(db.prepare(handover.sql).all().length, 0, 'UTC rollover invalidates prepared activation');
databaseDay = '2026-10-29';
assert.equal(db.prepare(handover.sql).all().length, 1);
assert.equal(db.prepare(handover.sql).all().length, 0, 'Cannot replay an activated handover');
assert.equal(db.prepare('SELECT COUNT(*) AS n FROM ai_budget_reservations').get().n, 0,
  'No fabricated provider receipts are inserted');
db.exec('UPDATE ai_budget_policy SET enabled=0');
db.exec(readFileSync(new URL('../database/cloudflare/ai_budget_production.sql', import.meta.url), 'utf8'));
assert.equal(db.prepare('SELECT monthly_limit_micro FROM ai_budget_policy').get().monthly_limit_micro, 9990493);
db.exec('UPDATE ai_budget_policy SET daily_limit_micro=1000000,monthly_limit_micro=10000000');
db.exec(`INSERT INTO ai_budget_reservations
  (id,kind,client_hash,reserved_micro,charged_micro,settled)
  VALUES ('offline-race-fixture','advisor','expired',20000,20000,0)`);
const before = db.prepare('SELECT * FROM ai_budget_reservations').all();
assert.equal(db.prepare(handover.sql).all().length, 0, 'Cannot activate over newly arrived receipts');
assert.deepEqual(db.prepare('SELECT * FROM ai_budget_reservations').all(), before);
db.close();
assert.throws(() => productionHandover({ ...snapshot, preview_unsettled: undefined }, now));
console.log(JSON.stringify({ production_handover_ok: true, rejected_cases: 16,
  replay_safe: true, fabricated_receipts: 0, network_calls: 0 }));
