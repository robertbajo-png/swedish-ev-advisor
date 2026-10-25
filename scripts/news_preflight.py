"""Read-only deployment diagnostics. Never prints credentials."""
import argparse
import json
import os
from urllib.parse import urlsplit
from datetime import datetime, timezone

from supabase_client import SupabaseRestClient, load_local_env
from news_model_policy import SUPPORTED_MODELS, selected_model


def run(remote=False, mode='publish'):
    load_local_env()
    url = os.environ.get("SUPABASE_URL", "")
    service = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    api = os.environ.get("OPENAI_API_KEY", "")
    report = {
        "supabase_host": urlsplit(url).hostname,
        "service_key_configured": bool(service and not service.startswith("your-")),
        "openai_key_configured": bool(api and not api.startswith("your-")),
        "migrations": ["007_news_engine.sql", "012_news_release_guardrails.sql", "013_news_unknown_usage_accounting.sql", "018_news_gpt6_sol.sql"],
        'mode': mode,
        "remote_checked": False, "errors": [], "warnings": [],
    }
    if not report["supabase_host"] or "your-project" in url:
        report["errors"].append("SUPABASE_URL_missing_or_placeholder")
    if not report["service_key_configured"]:
        report["errors"].append("SUPABASE_SERVICE_ROLE_KEY_missing")
    if mode != 'collect' and not report["openai_key_configured"]:
        report["errors"].append("OPENAI_API_KEY_missing")
    if mode != 'collect' and selected_model() not in SUPPORTED_MODELS:
        report['errors'].append('news_model_outside_pricing_contract')
    if remote and report["service_key_configured"] and report["supabase_host"]:
        try:
            client = SupabaseRestClient()
            for table in ("news_sources", "news_items", "news_articles", "public_news_articles", "news_quality_checks", "news_verification_requests", 'news_ai_requests'):
                client.select(table, filters={"limit": 1})
            report["remote_checked"] = True
            pending = client.select('news_ai_requests', columns='id,created_at,stage,charged_micro_usd', filters={
                'settled_at': 'is.null', 'budget_closed_at': 'is.null', 'order': 'created_at.asc', 'limit': 1})
            report['oldest_unsettled_request'] = pending[0] if pending else None
            if pending:
                report['warnings' if mode == 'collect' else 'errors'].append('news_unsettled_request_requires_reconciliation')
            closed = client.select('news_ai_requests', columns='id,created_at,stage,charged_micro_usd,budget_closed_at', filters={
                'budget_closed_at': 'not.is.null', 'order': 'budget_closed_at.desc', 'limit': 1})
            report['latest_conservative_budget_closure'] = closed[0] if closed else None
            if closed:
                report['warnings'].append('unknown_usage_full_reservation_still_counted')
            configs = client.select('news_ai_config', filters={'id': 'eq.production', 'limit': 1})
            if len(configs) != 1:
                report['errors'].append('news_budget_configuration_missing')
            else:
                cfg = configs[0]
                report['budget'] = {k: cfg[k] for k in ('enabled','publication_enabled','daily_limit_micro_usd',
                                   'monthly_limit_micro_usd','daily_article_limit','model','pricing_valid_until')}
                if mode != 'collect':
                    if not cfg['enabled']: report['errors'].append('news_budget_disabled')
                    if cfg['model'] not in SUPPORTED_MODELS: report['errors'].append('news_model_unpriced')
                    elif cfg['model'] != selected_model(): report['errors'].append('news_model_configuration_mismatch')
                    if cfg['pricing_valid_until'] <= datetime.now(timezone.utc).date().isoformat(): report['errors'].append('news_pricing_expired')
                    if not 0 < cfg['daily_limit_micro_usd'] <= 250000 or not 0 < cfg['monthly_limit_micro_usd'] <= 5000000:
                        report['errors'].append('news_budget_outside_owner_approval')
                if mode == 'publish' and not cfg['publication_enabled']: report['errors'].append('news_publication_disabled')
        except Exception as exc:
            report["errors"].append("news_schema_unavailable:" + type(exc).__name__)
    report["ready"] = report['remote_checked'] and not report["errors"]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", action="store_true")
    parser.add_argument('--mode', choices=['collect','editorial','publish'], default='publish')
    args = parser.parse_args()
    report = run(args.remote, args.mode)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ready"] else 1)
