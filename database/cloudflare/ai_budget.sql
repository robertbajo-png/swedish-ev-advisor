-- Private Cloudflare D1 ledger. Do not apply to the canonical Postgres database.
CREATE TABLE IF NOT EXISTS ai_budget_policy (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  daily_limit_micro INTEGER NOT NULL CHECK (daily_limit_micro BETWEEN 0 AND 100000000),
  monthly_limit_micro INTEGER NOT NULL CHECK (monthly_limit_micro BETWEEN 0 AND 1000000000),
  client_per_minute INTEGER NOT NULL CHECK (client_per_minute BETWEEN 1 AND 10),
  client_per_day INTEGER NOT NULL CHECK (client_per_day BETWEEN 1 AND 100),
  pricing_version TEXT NOT NULL,
  pricing_review_until TEXT NOT NULL
);

INSERT INTO ai_budget_policy VALUES (
  1, 1, 1000000, 10000000, 5, 50,
  'gpt-5.4-mini-standard-2026-10-19', '2026-11-19'
) ON CONFLICT(id) DO NOTHING;

CREATE TABLE IF NOT EXISTS ai_budget_reservations (
  id TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  kind TEXT NOT NULL CHECK (kind IN ('advisor', 'compare')),
  client_hash TEXT NOT NULL,
  reserved_micro INTEGER NOT NULL CHECK (reserved_micro BETWEEN 1 AND 50000),
  charged_micro INTEGER NOT NULL CHECK (charged_micro BETWEEN 0 AND reserved_micro),
  settled INTEGER NOT NULL DEFAULT 0 CHECK (settled IN (0, 1))
);
CREATE INDEX IF NOT EXISTS ai_budget_created ON ai_budget_reservations(created_at);
CREATE INDEX IF NOT EXISTS ai_budget_client ON ai_budget_reservations(client_hash, created_at);
