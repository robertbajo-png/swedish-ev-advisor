"""Owner-approved production budgets; historical trial contracts stay pinned."""
from datetime import date, datetime, timedelta, timezone

APPROVED_LIMITS = ((250000, 5000000), (500000, 10000000))


def approved_limits(config):
    values = tuple(config.get(k) for k in ('daily_limit_micro_usd', 'monthly_limit_micro_usd'))
    return all(type(v) is int for v in values) and values in APPROVED_LIMITS


def budget(remote, required=0):
    # Reuse the strict ledger only for runtime accounting, not config inspection.
    from trial_news_hybrid_launch import ledger
    now = datetime.now(timezone.utc)
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    rows = ledger(remote.client)
    day = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(now.date().isoformat()))
    month = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(now.strftime('%Y-%m')))
    try:
        pricing_current = date.fromisoformat(cfg['pricing_valid_until']) > now.date()
    except (KeyError, TypeError, ValueError):
        pricing_current = False
    valid = (approved_limits(cfg) and cfg.get('model') == 'gpt-6-sol'
             and type(cfg.get('daily_article_limit')) is int and cfg['daily_article_limit'] == 1
             and pricing_current)
    remaining = max(0, min(cfg['daily_limit_micro_usd'] - day, cfg['monthly_limit_micro_usd'] - month)) if valid else 0
    return {'allowed': valid and cfg.get('enabled') is True and type(required) is int
            and 0 <= required <= remaining and remaining > 0,
            'remaining_micro_usd': remaining, 'day_spent_micro_usd': day, 'month_spent_micro_usd': month,
            'publication_enabled': cfg.get('publication_enabled') is True, 'config_valid': valid,
            'retry_after': (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()}
