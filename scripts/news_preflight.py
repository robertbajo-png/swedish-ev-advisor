"""Read-only deployment diagnostics. Never prints credentials."""
import argparse
import json
import os
from urllib.parse import urlsplit

from supabase_client import SupabaseRestClient, load_local_env


def run(remote=False):
    load_local_env()
    url = os.environ.get("SUPABASE_URL", "")
    service = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    api = os.environ.get("OPENAI_API_KEY", "")
    report = {
        "supabase_host": urlsplit(url).hostname,
        "service_key_configured": bool(service and not service.startswith("your-")),
        "openai_key_configured": bool(api and not api.startswith("your-")),
        "migration": "database/migrations/007_news_engine.sql",
        "remote_checked": False, "errors": [],
    }
    if not report["supabase_host"] or "your-project" in url:
        report["errors"].append("SUPABASE_URL_missing_or_placeholder")
    if not report["service_key_configured"]:
        report["errors"].append("SUPABASE_SERVICE_ROLE_KEY_missing")
    if not report["openai_key_configured"]:
        report["errors"].append("OPENAI_API_KEY_missing")
    if remote and report["service_key_configured"] and report["supabase_host"]:
        try:
            client = SupabaseRestClient()
            for table in ("news_sources", "news_items", "news_articles", "public_news_articles", "news_quality_checks", "news_verification_requests"):
                client.select(table, filters={"limit": 1})
            report["remote_checked"] = True
        except Exception as exc:
            report["errors"].append("news_schema_unavailable:" + type(exc).__name__)
    report["ready"] = not report["errors"]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", action="store_true")
    args = parser.parse_args()
    report = run(args.remote)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ready"] else 1)
