"""New owner-authorized r19 evaluation; no reuse/reset of earlier trial receipts."""
import argparse
import json
from contextlib import closing

import trial_news_matrix as matrix
from news_store import NewsStore, stable_id
from supabase_client import load_local_env


def configure():
    matrix.RECIPE = 'news-editorial-recipe-2026-10-r19'
    matrix.TRIAL_ID = stable_id('private-news-matrix-r19:' + matrix.DATE)
    matrix.DATABASE = matrix.ROOT / ('data/local/news-matrix-r19-' + matrix.DATE + '.sqlite')
    matrix.OUTPUT = matrix.ROOT / ('data/local/release-data/news-production/matrix-r19-trial-' + matrix.DATE + '.json')


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
        result = matrix.prepare(remote) if args.prepare else matrix.run(remote) if args.run else matrix.verify_stop(remote)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        raise SystemExit(0 if args.prepare or args.verify_stop or result.get('passed') else 1)
