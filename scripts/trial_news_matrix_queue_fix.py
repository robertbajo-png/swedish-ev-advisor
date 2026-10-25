"""One queue-fix follow-up, allowed only after a verified zero-call matrix stop."""
import argparse
import json
from contextlib import closing
import trial_news_matrix as matrix
from news_ai import NewsBudgetBlocked
from news_store import NewsStore, stable_id
from supabase_client import load_local_env
from trial_news_review import ledger


def configure(remote, preparing=False):
    parent = remote.get('news_ingestion_runs', matrix.stable_id('private-news-matrix-r18:' + matrix.DATE))
    p = parent['payload'] if parent else {}
    if (p.get('state') != 'completed' or p.get('recipe') != matrix.RECIPE
            or not p.get('owner_shutdown_verified') or p.get('trial_usage') != []
            or p.get('new_charged_or_reserved_micro_usd') != 0
            or p.get('provider_stats', {}).get('provider_requests') != 0):
        raise NewsBudgetBlocked('queue_fix_requires_verified_zero_call_parent')
    matrix.assert_unchanged(remote, p)
    if preparing:
        matrix.switches(remote, False)
        baseline = set(json.loads(matrix.OUTPUT.read_text(encoding='utf-8'))['baseline_request_ids'])
        if any(row['id'] not in baseline for row in ledger(remote.client)):
            raise NewsBudgetBlocked('queue_fix_requires_unchanged_zero_cost_baseline')
    matrix.TRIAL_ID = stable_id('private-news-matrix-r18-queue-fix:' + matrix.DATE)
    matrix.DATABASE = matrix.DATABASE.with_name('news-matrix-r18-queue-fix-' + matrix.DATE + '.sqlite')
    matrix.OUTPUT = matrix.OUTPUT.with_name('matrix-r18-queue-fix-trial-' + matrix.DATE + '.json')


if __name__ == '__main__':
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--verify-stop', action='store_true')
    args = parser.parse_args()
    with closing(NewsStore(backend='supabase')) as remote:
        configure(remote, preparing=args.prepare)
        result = matrix.prepare(remote) if args.prepare else matrix.run(remote) if args.run else matrix.verify_stop(remote)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(0 if args.prepare or args.verify_stop or result.get('passed') else 1)
