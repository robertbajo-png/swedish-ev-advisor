"""One private price/statistics breadth test, ordinary shared budget only."""
import argparse
import json
import re
from contextlib import closing

import trial_news_matrix as matrix
import trial_news_length_r21 as r21
from news_ai import MODEL, NewsBudgetBlocked
from news_editorial import market_qualified_facts
from news_store import NewsStore, stable_id, now_iso
from supabase_client import load_local_env

DATE = '2026-10-23'
RECIPE = 'news-editorial-recipe-2026-10-r25-power-options'


def configure():
    matrix.DATE = DATE
    matrix.RECIPE = RECIPE
    matrix.TRIAL_ID = stable_id('private-news-breadth-r25:' + DATE)
    matrix.DATABASE = matrix.ROOT / ('data/local/news-breadth-r25-' + DATE + '.sqlite')
    matrix.OUTPUT = matrix.ROOT / ('data/local/release-data/news-production/breadth-r25-trial-' + DATE + '.json')
    matrix.MAX_MICRO_USD = 100000
    matrix.MAX_REQUESTS = 6
    matrix.MAX_REVISIONS = 0
    matrix.REEXTRACT_MODEL = True
    matrix.MODEL_INPUT = r21.model_input
    matrix.INCLUDE_MARKET = True
    matrix.EXPECTED_CATEGORIES = {'priser', 'marknad'}


def check_budget(remote):
    matrix.authorize()
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    matrix.switches(remote, cfg['enabled'])
    if cfg['model'] != MODEL or cfg['pricing_valid_until'] <= DATE:
        raise NewsBudgetBlocked('r25_pricing_contract_invalid')
    rows = remote.client.select('news_ai_requests', columns=(
        'id,created_at,charged_micro_usd,settled_at,budget_closed_at'), filters={'limit': 1000})
    if len(rows) >= 1000 or any(type(r['charged_micro_usd']) is not int or r['charged_micro_usd'] < 0 for r in rows):
        raise NewsBudgetBlocked('r25_invalid_or_truncated_ledger')
    daily = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE))
    monthly = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE[:7]))
    pending = any(not r['settled_at'] and not r['budget_closed_at'] for r in rows)
    remaining = min(cfg['daily_limit_micro_usd'] - daily, cfg['monthly_limit_micro_usd'] - monthly)
    return {'at': now_iso(), 'trial_id': matrix.TRIAL_ID, 'recipe': RECIPE,
            'daily_used_micro_usd': daily, 'monthly_used_micro_usd': monthly,
            'maximum_micro_usd': matrix.MAX_MICRO_USD, 'maximum_requests': matrix.MAX_REQUESTS,
            'unresolved_usage': pending, 'allowed': not pending and remaining >= matrix.MAX_MICRO_USD,
            'provider_requests': 0, 'publication_enabled': cfg['publication_enabled']}


def coverage(report):
    evidence = [(article, check['payload'].get('fact_inventory', []))
                for article in report.get('articles', []) for check in article.get('checks', [])
                if check['kind'] == 'evidence' and check['artifact_hash'] == article['artifact_hash']]
    prices = [fact for article, facts in evidence if article['payload'].get('category') == 'priser'
              for fact in market_qualified_facts(facts)
              if re.search(r'\b(?:kronor|SEK|euros?|EUR)\b', fact['statement'], re.I)
              and re.search(r'\b(?:Sverige|Sweden|Swedish|Germany|Tyskland|EU)\b', fact['statement'] + ' ' + fact['evidence'], re.I)]
    stats = [fact for article, facts in evidence if article['payload'].get('category') == 'marknad'
             for fact in facts if fact.get('origin') == 'literal_statistical_field']
    return {'market_qualified_price_facts': len(prices), 'literal_statistical_facts': len(stats),
            'passed': bool(prices) and len(stats) >= 3}


def run(remote):
    matrix.run(remote)
    report = json.loads(matrix.OUTPUT.read_text(encoding='utf-8'))
    report['breadth_coverage'] = coverage(report)
    # Coverage can reject a nominally successful run, never approve a failed gate.
    report['passed'] = report['passed'] and report['breadth_coverage']['passed']
    matrix.receipt(remote, report)
    return {k: v for k, v in report.items() if k not in {'articles', 'baseline_request_ids'}}


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
        result = matrix.prepare(remote) if args.prepare else run(remote) if args.run else matrix.verify_stop(remote)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(0 if args.prepare or args.verify_stop or result.get('passed') else 1)
