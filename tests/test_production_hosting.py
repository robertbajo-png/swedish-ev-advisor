import pathlib
import sqlite3
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProductionHostingTests(unittest.TestCase):
    def test_separate_target_and_disabled_ai(self):
        config = tomllib.loads((ROOT / "wrangler.production.toml").read_text())
        preview = tomllib.loads((ROOT / "wrangler.toml").read_text())
        self.assertEqual(config["name"], "elbilsagenten")
        old_id = preview["env"]["preview"]["d1_databases"][0]["database_id"]
        for target in (config, config["env"]["preview"]):
            self.assertEqual(target["vars"]["AI_ENABLED"], "false")
            self.assertEqual(target["vars"]["VEHICLE_DATA_MODE"], "snapshot")
            binding, = target["d1_databases"]
            self.assertEqual(binding["binding"], "AI_BUDGET_DB")
            self.assertEqual(binding["database_name"], "elbilsagenten-ai-budget-production")
            self.assertNotEqual(binding["database_id"], old_id)
            self.assertNotIn("OPENAI_API_KEY", target["vars"])
            self.assertNotIn("AI_BUDGET_SALT", target["vars"])

    def test_disabled_bootstrap_is_idempotent_and_preserves_costs(self):
        sql = (ROOT / "database/cloudflare/ai_budget_production.sql").read_text()
        with sqlite3.connect(":memory:") as db:
            db.executescript(sql)
            self.assertEqual(db.execute(
                "SELECT enabled,daily_limit_micro,monthly_limit_micro FROM ai_budget_policy"
            ).fetchone(), (0, 1000000, 10000000))
            db.execute("UPDATE ai_budget_policy SET daily_limit_micro=500000")
            db.execute("INSERT INTO ai_budget_reservations "
                       "(id,kind,client_hash,reserved_micro,charged_micro,settled) "
                       "VALUES ('test-only','advisor','expired',20000,20000,0)")
            before = db.execute("SELECT * FROM ai_budget_reservations").fetchall()
            db.executescript(sql)
            self.assertEqual(db.execute(
                "SELECT enabled,daily_limit_micro FROM ai_budget_policy"
            ).fetchone(), (0, 500000))
            self.assertEqual(db.execute("SELECT * FROM ai_budget_reservations").fetchall(), before)

    def test_table_contract_matches_existing_ledger(self):
        schemas = []
        for name in ("ai_budget.sql", "ai_budget_production.sql"):
            with sqlite3.connect(":memory:") as db:
                db.executescript((ROOT / "database/cloudflare" / name).read_text())
                schemas.append([db.execute(f"PRAGMA table_info({table})").fetchall()
                                for table in ("ai_budget_policy", "ai_budget_reservations")])
        self.assertEqual(schemas[0], schemas[1])


if __name__ == "__main__":
    unittest.main()
