"""Owner-authorized 2026-10-23 private writer/audit trial; ordinary allowance only."""
import argparse
import json
from contextlib import closing

import trial_news_matrix as matrix
import trial_news_length_r21 as r21
from news_ai import MODEL, NewsBudgetBlocked
from news_editorial import market_qualified_facts, source_qualifier_facts
from news_fact_brief import neutral_facts, source_technical_facts
from news_store import NewsStore, now_iso, stable_id
from supabase_client import load_local_env
from trial_news_evidence_r22 import budget_probe

DATE = '2026-10-23'
RECIPE = 'news-editorial-recipe-2026-10-r24-offline-launch'
PARENT_DATE = '2026-10-22'
PARENT_ID = stable_id('private-news-matrix-r20:' + PARENT_DATE)
PARENT_DATABASE = matrix.ROOT / ('data/local/news-matrix-r20-' + PARENT_DATE + '.sqlite')


def model_input(remote):
    # Reuse only the validated source facts, never an old draft or its review.
    if r21.PARENT_ID != PARENT_ID or r21.PARENT_DATABASE != PARENT_DATABASE:
        raise NewsBudgetBlocked('r24_frozen_parent_configuration_changed')
    return r21.model_input(remote)


def configure():
    matrix.DATE = DATE
    matrix.RECIPE = RECIPE
    matrix.TRIAL_ID = stable_id('private-news-writing-r24:' + DATE)
    matrix.DATABASE = matrix.ROOT / ('data/local/news-writing-r24-' + DATE + '.sqlite')
    matrix.OUTPUT = matrix.ROOT / ('data/local/release-data/news-production/writing-r24-trial-' + DATE + '.json')
    matrix.MAX_MICRO_USD = 60000
    matrix.MAX_REQUESTS = 2
    matrix.REEXTRACT_MODEL = False
    matrix.MODEL_INPUT = model_input
    matrix.INCLUDE_MARKET = False
    matrix.MAX_REVISIONS = 0


def check_budget(remote):
    matrix.authorize()
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    matrix.switches(remote, cfg['enabled'])
    if cfg['model'] != MODEL or cfg['pricing_valid_until'] <= DATE:
        raise NewsBudgetBlocked('r24_model_or_pricing_contract_invalid')
    rows = remote.client.select('news_ai_requests', columns=(
        'id,created_at,charged_micro_usd,settled_at,budget_closed_at'), filters={'limit': 1000})
    if len(rows) >= 1000 or any(type(r['charged_micro_usd']) is not int or r['charged_micro_usd'] < 0 for r in rows):
        raise NewsBudgetBlocked('r24_invalid_or_truncated_ledger')
    item = model_input(remote)
    facts = [{**f, 'id': item['id'] + ':f' + str(n), 'item_id': item['id'],
              'publisher': item['payload']['publisher']} for n, f in enumerate(item['payload']['extraction']['facts'])]
    facts = market_qualified_facts(facts)
    facts = neutral_facts(facts + source_technical_facts(item, facts) + source_qualifier_facts(item))
    previous = matrix.ROOT / ('data/local/release-data/news-production/owner-exception-r22-' + PARENT_DATE + '.json')
    reference = json.loads(previous.read_text(encoding='utf-8'))
    if (reference.get('state') != 'completed' or not reference.get('owner_shutdown_verified')
            or not reference.get('test_allowance_closed') or len(reference.get('articles', [])) != 1):
        raise NewsBudgetBlocked('r24_requires_closed_sizing_reference')
    bounds = budget_probe(facts, reference['articles'][0]['payload'])
    daily = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE))
    monthly = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE[:7]))
    pending = any(not r['settled_at'] and not r['budget_closed_at'] for r in rows)
    remaining = min(cfg['daily_limit_micro_usd'] - daily, cfg['monthly_limit_micro_usd'] - monthly,
                    matrix.MAX_MICRO_USD)
    return {'kind': 'private_news_budget_preflight', 'at': now_iso(), 'trial_id': matrix.TRIAL_ID,
            'recipe': RECIPE, 'daily_used_micro_usd': daily, 'monthly_used_micro_usd': monthly,
            'available_micro_usd': max(0, remaining), 'request_reservations_micro_usd': bounds,
            'audit_sizing_reference_only': True, 'provider_requests': 0,
            'allowed': not pending and sum(bounds.values()) <= remaining,
            'unresolved_usage': pending, 'ai_enabled': cfg['enabled'],
            'publication_enabled': cfg['publication_enabled']}


if __name__ == '__main__':
    load_local_env()
    configure()
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-budget', action='store_true')
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--verify-stop', action='store_true')
    args = parser.parse_args()
    with closing(NewsStore(backend='supabase')) as remote:
        if not args.verify_stop:
            readiness = check_budget(remote)
            if args.check_budget or not readiness['allowed']:
                print(json.dumps(readiness, indent=2))
                raise SystemExit(0 if readiness['allowed'] else 2)
        result = matrix.prepare(remote) if args.prepare else matrix.run(remote) if args.run else matrix.verify_stop(remote)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(0 if args.prepare or args.verify_stop or result.get('passed') else 1)
