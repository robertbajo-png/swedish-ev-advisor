"""Official fact-first news, then existing broad editorial review if no AI started."""
import argparse
from contextlib import closing
import json

import run_fact_first_news as official
import run_publisher_news as publisher
from news_http import Collector
from news_store import NewsStore
from run_short_news import worker_lock
from smoke_news_engine import verified_context
from supabase_client import load_local_env


def run(remote, collector, *, max_candidates=2, owner_day=None):
    # Both existing workers retain shared historical attempts, receipts and limits.
    result = official.daily(remote, collector, max_candidates, owner_day)
    if (result.get('status') != 'no_eligible_new_source' or type(result.get('published')) is not int
            or result['published'] != 0
            or type(result.get('ai_candidates_started')) is not int
            or result['ai_candidates_started'] != 0):
        return {**result, 'editorial_route': 'official_fact_first'}
    broad = publisher.daily(remote, collector, max_candidates=max_candidates, owner_day=owner_day)
    # The broad worker rechecks official candidates too; never double-count them.
    return {**broad, 'editorial_route': 'broad_article_review',
            'official_selection': {k: result[k] for k in ('status', 'held_candidates',
                'held_reasons', 'held_stages', 'selection_checked', 'ai_candidates_started') if k in result}}


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run',))
    parser.add_argument('--max-candidates', type=int, default=2)
    parser.add_argument('--owner-approved-day')
    args = parser.parse_args()
    publisher.approved_candidate_limit(args.max_candidates, args.owner_approved_day)
    with worker_lock(), closing(NewsStore(backend='supabase')) as remote:
        result = run(remote, Collector(tls_context=verified_context()),
                     max_candidates=args.max_candidates, owner_day=args.owner_approved_day)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if result.get('status') == 'failed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
