"""Single-use private writing/audit trial using valid frozen r20 model extraction."""
import argparse
import json
import sqlite3
from contextlib import closing

import trial_news_matrix as matrix
from news_ai import NewsBudgetBlocked
from news_editorial import validate_fact_extraction
from news_store import NewsStore, stable_id
from supabase_client import load_local_env

PARENT_ID = stable_id('private-news-matrix-r20:' + matrix.DATE)
PARENT_DATABASE = matrix.ROOT / ('data/local/news-matrix-r20-' + matrix.DATE + '.sqlite')


def model_input(remote):
    parent = remote.get('news_ingestion_runs', PARENT_ID)
    payload = parent['payload'] if parent else {}
    if (payload.get('state') != 'completed' or not payload.get('owner_shutdown_verified')
            or not payload.get('production_unchanged') or payload.get('recipe') != 'news-editorial-recipe-2026-10-r20'):
        raise NewsBudgetBlocked('r21_requires_stopped_r20')
    # Read-only access: earlier trial receipts, extraction and drafts are never reset.
    with closing(sqlite3.connect(PARENT_DATABASE.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('select * from news_items where id=?', (matrix.MODEL_ITEM,)).fetchone()
        if not row:
            raise ValueError('r21_missing_parent_source')
        item = dict(row)
        item['payload'] = json.loads(item['payload'])
    case = next((c for c in payload.get('cases', []) if c['id'] == item['id']), None)
    if (not case or item['payload']['content_hash'] != case['content_hash']
            or validate_fact_extraction(item['payload'].get('extraction', {}), item)):
        raise ValueError('r21_invalid_parent_extraction_or_source')
    return item


def configure():
    matrix.RECIPE = 'news-editorial-recipe-2026-10-r21'
    matrix.TRIAL_ID = stable_id('private-news-length-r21:' + matrix.DATE)
    matrix.DATABASE = matrix.ROOT / ('data/local/news-length-r21-' + matrix.DATE + '.sqlite')
    matrix.OUTPUT = matrix.ROOT / ('data/local/release-data/news-production/length-r21-trial-' + matrix.DATE + '.json')
    matrix.MAX_MICRO_USD = 40000
    matrix.MAX_REQUESTS = 3
    matrix.REEXTRACT_MODEL = False
    matrix.MODEL_INPUT = model_input
    matrix.INCLUDE_MARKET = False
    # Preserve enough shared allowance for exact-artifact review, not a paid rewrite loop.
    matrix.MAX_REVISIONS = 0


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
