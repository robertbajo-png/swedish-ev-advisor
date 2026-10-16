"""Shared persistent store contract: Supabase production, SQLite development/tests."""
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from supabase_client import SupabaseRestClient

TABLES = {
    "news_sources": [], "news_ingestion_runs": [],
    "news_story_clusters": ["event_key"],
    "news_items": ["source_id", "url", "cluster_id", "status"],
    "news_articles": ["cluster_id", "slug", "status", "artifact_hash", "published_at"],
    "news_article_sources": ["article_id", "item_id"],
    "news_vehicle_links": ["article_id", "canonical_model_id"],
    "news_quality_checks": ["article_id", "kind", "artifact_hash", "passed"],
    "news_verification_requests": ["article_id", "status"],
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def stable_id(value):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(value)))


def artifact_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class NewsStore:
    def __init__(self, path=None, backend="sqlite"):
        self.backend = backend
        if backend == "supabase":
            self.client = SupabaseRestClient()
            self.client.select("news_sources", filters={"limit": 1})
        else:
            path = Path(path or Path(__file__).resolve().parents[1] / "data/local/news.sqlite")
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path, timeout=30)
            self.db.row_factory = sqlite3.Row
            self.db.execute("pragma journal_mode=wal")
            for table, fields in TABLES.items():
                columns = ",".join(f'{f} text' for f in fields)
                self.db.execute(f"create table if not exists {table}(id text primary key,{columns + ',' if columns else ''}payload text not null,updated_at text not null)")
            for table, field in (("news_items", "url"), ("news_articles", "cluster_id"), ("news_articles", "slug"), ("news_story_clusters", "event_key")):
                self.db.execute(f"create unique index if not exists {table}_{field}_unique on {table}({field})")
            self.db.commit()

    def close(self):
        if self.backend == "sqlite":
            self.db.close()

    def rows(self, table):
        if table not in TABLES:
            raise ValueError("unknown_news_table")
        if self.backend == "supabase":
            result = []
            for offset in range(0, 100000, 500):
                page = self.client.select(table, filters={"order": "id.asc", "offset": offset, "limit": 500})
                result.extend(page)
                if len(page) < 500:
                    return result
            raise RuntimeError("news_pagination_limit")
        rows = [dict(r) for r in self.db.execute(f"select * from {table}")]
        for row in rows:
            row["payload"] = json.loads(row["payload"])
            if "passed" in row:
                row["passed"] = row["passed"] == "1"
        return rows

    def get(self, table, key):
        return next((r for r in self.rows(table) if r["id"] == key), None)

    def put(self, table, row):
        if table not in TABLES:
            raise ValueError("unknown_news_table")
        row = {**row, "updated_at": now_iso()}
        if table == "news_articles":
            old = self.get(table, row["id"])
            if old and old["status"] == "published":
                if old["payload"] != row["payload"]:
                    raise ValueError("published_article_immutable")
                return old
            row["artifact_hash"] = artifact_hash(row["payload"])
            if row.get("status") == "published":
                raise ValueError("use_transactional_publish")
        if self.backend == "supabase":
            return self.client.upsert(table, [row], "id")[0]
        fields = list(row)
        values = [json.dumps(row[f], ensure_ascii=False) if f == "payload" else str(int(row[f])) if isinstance(row[f], bool) else row[f] for f in fields]
        self.db.execute(f"insert into {table}({','.join(fields)}) values({','.join('?' for _ in fields)}) on conflict(id) do update set " + ",".join(f"{f}=excluded.{f}" for f in fields if f != "id"), values)
        self.db.commit()
        return self.get(table, row["id"])

    def publish(self, article_id, daily_limit=5):
        if self.backend == "supabase":
            return self.client._request("POST", "rpc/publish_news_article", {"article_key": article_id, "daily_limit": daily_limit})
        try:
            self.db.execute("begin immediate")
            article = self.get("news_articles", article_id)
            if article["status"] == "published":
                self.db.commit()
                return
            checks = self.rows("news_quality_checks")
            passed = {r["kind"] for r in checks if r["article_id"] == article_id and r["passed"] and r["artifact_hash"] == article["artifact_hash"]}
            if article["status"] != "draft" or passed != {"evidence", "editorial", "originality"}:
                raise ValueError("missing_or_stale_quality_gates")
            links = [r for r in self.rows("news_article_sources") if r["article_id"] == article_id]
            if not links or any(self.get("news_items", r["item_id"])["payload"].get("access_status") != "accessible" for r in links):
                raise ValueError("missing_accessible_source")
            day = now_iso()[:10]
            count = sum(r["status"] == "published" and str(r.get("published_at", "")).startswith(day) for r in self.rows("news_articles"))
            if count >= min(daily_limit, 5):
                raise ValueError("daily_limit")
            self.db.execute("update news_articles set status='published',published_at=? where id=?", (now_iso(), article_id))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def public_articles(self):
        rows = self.client.select("public_news_articles", filters={"order": "published_at.desc", "limit": 500}) if self.backend == "supabase" else [r for r in self.rows("news_articles") if r["status"] == "published"]
        return sorted(({**r["payload"], "id": r["id"], "slug": r["slug"], "published_at": r["published_at"]} for r in rows), key=lambda r: r["published_at"], reverse=True)
