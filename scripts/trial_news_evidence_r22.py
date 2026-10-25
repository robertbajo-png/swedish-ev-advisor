"""Single-use r22 evidence/prose trial. No publication or budget-limit increase."""
import argparse
import json
import sqlite3
from contextlib import closing

import trial_news_matrix as matrix
import trial_news_length_r21 as r21
from news_ai import NewsAi, NewsBudgetBlocked
from news_editorial import audit_article, generate_article, market_qualified_facts, source_qualifier_facts
from news_fact_brief import neutral_facts, source_technical_facts
from news_store import NewsStore, stable_id, now_iso
from refresh_verified_variants import save
from supabase_client import load_local_env


def model_input(remote):
    previous = remote.get('news_ingestion_runs', stable_id('private-news-length-r21:' + matrix.DATE))
    payload = previous['payload'] if previous else {}
    if (payload.get('state') != 'completed' or not payload.get('owner_shutdown_verified')
            or not payload.get('production_unchanged') or payload.get('recipe') != 'news-editorial-recipe-2026-10-r21'):
        raise NewsBudgetBlocked('r22_requires_stopped_r21')
    return r21.model_input(remote)


def configure():
    r21.configure()
    matrix.RECIPE = 'news-editorial-recipe-2026-10-r22'
    matrix.TRIAL_ID = stable_id('private-news-evidence-r22:' + matrix.DATE)
    matrix.DATABASE = matrix.ROOT / ('data/local/news-evidence-r22-' + matrix.DATE + '.sqlite')
    matrix.OUTPUT = matrix.ROOT / ('data/local/release-data/news-production/evidence-r22-trial-' + matrix.DATE + '.json')
    matrix.MAX_MICRO_USD = 24000
    matrix.MODEL_INPUT = model_input
    matrix.MAX_REVISIONS = 1


def budget_probe(facts, article):
    """Measure real request reservations locally; neither reserve nor contact OpenAI."""
    bounds = {}

    class ProbeClient:
        def select(self, *args, **kwargs):
            return []

        def _request(self, method, path, body):
            if method != 'POST' or path != 'rpc/reserve_news_ai':
                raise ValueError('r22_probe_unexpected_operation')
            bounds[body['stage_key']] = (3 * body['input_bound'] + 18 * body['output_bound'] + 3) // 4
            return {'allowed': False}

    def no_transport(*args, **kwargs):
        raise AssertionError('r22_budget_probe_cannot_call_provider')

    provider = NewsAi(ProbeClient(), transport=no_transport)
    for operation, args in [(generate_article, (facts,)), (audit_article, (article, facts))]:
        try:
            operation(*args, ai=provider)
        except NewsBudgetBlocked as exc:
            if str(exc) != 'news_budget_denied':
                raise
    if set(bounds) != {'swedish_ev_article', 'ev_news_independent_audit'} or provider.stats['provider_requests']:
        raise ValueError('r22_budget_probe_incomplete')
    return bounds


def check_budget(remote):
    matrix.authorize()
    item = model_input(remote)
    stopped = remote.get('news_ingestion_runs', stable_id('private-news-length-r21:' + matrix.DATE))
    matrix.assert_unchanged(remote, stopped['payload'])
    facts = [{**f, 'id': item['id'] + ':f' + str(n), 'item_id': item['id'],
              'publisher': item['payload']['publisher']} for n, f in enumerate(item['payload']['extraction']['facts'])]
    facts = market_qualified_facts(facts)
    facts = neutral_facts(facts + source_technical_facts(item, facts) + source_qualifier_facts(item))
    previous = matrix.ROOT / ('data/local/news-length-r21-' + matrix.DATE + '.sqlite')
    with closing(sqlite3.connect(previous.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('select payload from news_articles').fetchall()
        if len(row) != 1:
            raise ValueError('r22_requires_one_sizing_reference')
        article = json.loads(row[0][0])
    # The old article sizes the request only; it is NOT a new draft or a new review.
    bounds = budget_probe(facts, article)
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if cfg['publication_enabled'] or cfg['daily_limit_micro_usd'] != 250000 or cfg['monthly_limit_micro_usd'] != 5000000:
        raise NewsBudgetBlocked('r22_changed_switch_or_limit')
    day = matrix.DATE + 'T00:00:00+00:00'
    usage = remote.client.select('news_ai_requests', columns='charged_micro_usd', filters={'created_at': 'gte.' + day, 'limit': 1000})
    if len(usage) >= 1000 or any(type(row['charged_micro_usd']) is not int or row['charged_micro_usd'] < 0 for row in usage):
        raise NewsBudgetBlocked('r22_invalid_budget_snapshot')
    used = sum(row['charged_micro_usd'] for row in usage)
    unresolved = remote.client.select('news_ai_requests', columns='id', filters={
        'settled_at': 'is.null', 'budget_closed_at': 'is.null', 'limit': 1})
    remaining = max(0, cfg['daily_limit_micro_usd'] - used)
    allowed = not unresolved and max(bounds.values()) <= min(remaining, matrix.MAX_MICRO_USD)
    report = {'kind': 'private_news_budget_preflight', 'at': now_iso(), 'recipe': matrix.RECIPE,
              'trial_id': matrix.TRIAL_ID, 'daily_used_micro_usd': used, 'daily_remaining_micro_usd': remaining,
              'trial_cap_micro_usd': matrix.MAX_MICRO_USD, 'request_reservations_micro_usd': bounds,
              'probe_uses_previous_article_for_size_only': True, 'allowed': allowed,
              'live_trial_started': False, 'provider_requests': 0, 'charged_micro_usd': 0,
              'production_unchanged': True,
              'ai_enabled': cfg['enabled'], 'publication_enabled': cfg['publication_enabled'],
              'reason': None if allowed else 'complete_review_probe_exceeds_available_allowance_or_unresolved_usage'}
    save(matrix.ROOT / ('data/local/release-data/news-production/evidence-r22-budget-' + matrix.DATE + '.json'), report)
    return report


if __name__ == '__main__':
    load_local_env()
    configure()
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--verify-stop', action='store_true')
    mode.add_argument('--check-budget', action='store_true')
    args = parser.parse_args()
    with closing(NewsStore(backend='supabase')) as remote:
        if args.check_budget or args.run:
            readiness = check_budget(remote)
            if args.check_budget or not readiness['allowed']:
                print(json.dumps(readiness, ensure_ascii=True, indent=2))
                raise SystemExit(0 if readiness['allowed'] else 2)
        result = matrix.prepare(remote) if args.prepare else matrix.run(remote) if args.run else matrix.verify_stop(remote)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(0 if args.prepare or args.verify_stop or result.get('passed') else 1)
