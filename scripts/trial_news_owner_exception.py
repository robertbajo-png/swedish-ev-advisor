"""Owner approved USD 0.10 extra for exactly one private r22 trial on 2026-10-22."""
import argparse
import json
from contextlib import closing
from datetime import datetime, timezone

import trial_news_matrix as matrix
import trial_news_length_r21 as r21
from news_ai import NewsBudgetBlocked
from news_store import NewsStore, stable_id
from supabase_client import load_local_env
from trial_news_review import TrialClient

AUTHORIZED_DATE = '2026-10-22'
TRIAL_ID = stable_id('private-news-owner-exception-r22:' + AUTHORIZED_DATE)
MAXIMUM = 100000


def configure():
    r21.configure()
    matrix.DATE = AUTHORIZED_DATE
    matrix.RECIPE = 'news-editorial-recipe-2026-10-r22'
    matrix.TRIAL_ID = TRIAL_ID
    matrix.MAX_MICRO_USD = MAXIMUM
    matrix.MAX_REQUESTS = 3
    matrix.MAX_REVISIONS = 0
    matrix.DATABASE = matrix.ROOT / ('data/local/news-owner-exception-r22-' + AUTHORIZED_DATE + '.sqlite')
    matrix.OUTPUT = matrix.ROOT / ('data/local/release-data/news-production/owner-exception-r22-' + AUTHORIZED_DATE + '.json')


def paused(remote, running):
    matrix.authorize()
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if (cfg['enabled'] or cfg['publication_enabled'] or cfg['daily_limit_micro_usd'] != 250000
            or cfg['monthly_limit_micro_usd'] != 5000000):
        raise NewsBudgetBlocked('private_exception_requires_unchanged_paused_production')
    if running:
        rows = remote.client.select('news_test_allowances', filters={'id': 'eq.' + TRIAL_ID})
        if (len(rows) != 1 or rows[0]['closed_at'] is not None or rows[0]['maximum_micro_usd'] != MAXIMUM
                or rows[0]['maximum_requests'] != 3
                or datetime.fromisoformat(rows[0]['expires_at']) <= datetime.now(timezone.utc)):
            raise NewsBudgetBlocked('private_exception_allowance_missing_closed_or_changed')


class ExceptionClient(TrialClient):
    def _request(self, method, path, body):
        matrix.authorize()
        if method != 'POST':
            raise NewsBudgetBlocked('private_exception_budget_rpcs_only')
        if path == 'rpc/reserve_news_ai':
            if body.get('stage_key') not in self.stages:
                raise NewsBudgetBlocked('private_exception_editorial_only')
            return self.client._request(method, 'rpc/reserve_news_test_ai', {'allowance_key': TRIAL_ID, **body})
        if path == 'rpc/settle_news_ai':
            row = self.client.select('news_ai_requests', columns='id', filters={
                'id': 'eq.' + body['request_key'], 'test_allowance_id': 'eq.' + TRIAL_ID})
            if len(row) != 1:
                raise NewsBudgetBlocked('private_exception_settlement_outside_scope')
            return self.client._request(method, path, body)
        raise NewsBudgetBlocked('private_exception_budget_rpcs_only')


def run(remote):
    try:
        return matrix.run(remote, switch_check=paused, client_factory=ExceptionClient)
    finally:
        closed = remote.client._request('POST', 'rpc/close_news_test_allowance', {'allowance_key': TRIAL_ID})
        if not isinstance(closed, dict) or closed.get('closed') is not True:
            raise NewsBudgetBlocked('private_exception_shutdown_not_verified')


def verify_stop(remote):
    rows = remote.client.select('news_test_allowances', filters={'id': 'eq.' + TRIAL_ID})
    if len(rows) != 1 or not rows[0]['closed_at']:
        raise NewsBudgetBlocked('private_exception_still_active')
    report = matrix.verify_stop(remote, switch_check=paused)
    saved = json.loads(matrix.OUTPUT.read_text(encoding='utf-8'))
    saved.update(test_allowance_closed=True, ordinary_ai_remained_disabled=True,
                 owner_approved_extra_micro_usd=MAXIMUM)
    matrix.receipt(remote, saved)
    return {**report, 'test_allowance_closed': True, 'ordinary_ai_remained_disabled': True}


if __name__ == '__main__':
    load_local_env()
    configure()
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--verify-stop', action='store_true')
    args = parser.parse_args()
    with closing(NewsStore(backend='supabase')) as remote:
        result = (matrix.prepare(remote, switch_check=paused) if args.prepare else
                  run(remote) if args.run else verify_stop(remote))
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(0 if args.prepare or args.verify_stop or result.get('passed') else 1)
