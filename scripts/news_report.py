"""Generate public-safe operational diagnostics without raw reporting or secrets."""
import argparse
import json
from collections import Counter
from news_engine import ROOT
from news_store import NewsStore, now_iso


def report(store):
    sources = []
    for row in store.rows("news_sources"):
        p = row["payload"]
        if not p.get("priority"):
            continue
        sources.append({"source": p["name"], "status": p.get("collection_status", "not_checked"),
                        "verified_feed": p.get("verified_feed"), "checked_at": p.get("checked_at"),
                        "errors": p.get("diagnostics", [])})
    return {"generated_at": now_iso(), "backend": store.backend, "sources": sources,
            "items": dict(Counter(r["status"] for r in store.rows("news_items"))),
            "articles": dict(Counter(r["status"] for r in store.rows("news_articles"))),
            "verification_requests": dict(Counter(r["status"] for r in store.rows("news_verification_requests")))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["sqlite", "supabase"], default="sqlite")
    args = parser.parse_args()
    store = NewsStore(backend=args.backend)
    try:
        result = report(store)
        (ROOT / "data/news/health_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()
