import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';

// Real SQLite and production SQL, with a controllable database clock. No network.
export function budgetFixture() {
  const db = new DatabaseSync(':memory:');
  let now = new Date('2026-10-19T12:00:00Z');
  db.function('unixepoch', { varargs: true }, (...args) => {
    const date = new Date(now);
    if (args.includes('start of month')) date.setUTCDate(1);
    if (args.includes('start of day') || args.includes('start of month')) date.setUTCHours(0, 0, 0, 0);
    return Math.floor(date.getTime() / 1000);
  });
  db.function('date', { varargs: true }, () => now.toISOString().slice(0, 10));
  db.exec(readFileSync(new URL('../../database/cloudflare/ai_budget.sql', import.meta.url), 'utf8'));
  const binding = {
    prepare(sql) {
      const statement = db.prepare(sql);
      const execute = (method, values) => statement[method](Object.fromEntries(values.map((value, index) => [String(index + 1), value])));
      return {
        bind(...values) { return { first: async () => execute('get', values) ?? null, run: async () => execute('run', values) }; },
        run: async () => statement.run(),
      };
    },
  };
  return {
    db, binding, setNow: (value) => { now = new Date(value); },
    env: { AI_ENABLED: 'true', AI_BUDGET_DB: binding, AI_BUDGET_SALT: 'fixture-only-budget-salt-at-least-32-chars' },
    rows: () => db.prepare('SELECT * FROM ai_budget_reservations').all(),
    total: () => db.prepare('SELECT COALESCE(SUM(charged_micro), 0) AS amount FROM ai_budget_reservations').get().amount,
  };
}
