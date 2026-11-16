"""Explicit synthetic/local demonstration; no network, AI, public export or release."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import sys
from unittest.mock import patch

from news_factual_notices import prepare_price_notices, stage_factual_notices, REVIEW, RECIPE
from news_store import NewsStore

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'data/local'


def build(directory):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(PRIVATE.resolve()):
        raise ValueError('factual_notice_demo_must_remain_private')
    if directory.exists():
        raise FileExistsError('do_not_overwrite_existing_demo')
    sys.path.insert(0, str(ROOT / 'tests'))
    from test_news_factual_notices import capture, NOW
    files = ['public/data/public_ev_variants.json', 'public/data/news_articles.json', 'public/sitemap.xml']
    def hashes():
        return {file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest() for file in files}
    before = hashes()
    held = []
    prepared = prepare_price_notices(capture(), NOW, held=held)
    directory.mkdir(parents=True)
    with patch('socket.socket.connect', side_effect=AssertionError('No network in synthetic demo')), \
         patch('news_ai.NewsAi.__call__', side_effect=AssertionError('No paid AI in synthetic demo')), \
         patch.object(NewsStore, 'publish', side_effect=AssertionError('No publishing in synthetic demo')), \
         patch.object(NewsStore, 'publish_notice', side_effect=AssertionError('No publishing in synthetic demo')), \
         closing(NewsStore(directory / 'private.sqlite', backend='sqlite')) as store:
        results = stage_factual_notices(store, prepared, NOW)
        again = stage_factual_notices(store, prepared, NOW)
        assert all(row['status'] == 'draft' and row['review']['passed'] for row in results + again)
        assert len(store.rows('news_articles')) == 3 and len(store.rows('news_items')) == 1
        assert not store.public_articles()
    assert hashes() == before, 'Public files changed'
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'fixture': True,
        'fixture_description': 'Synthetic saved-source demonstration, not a live fetch or publication proof',
        'source_fixture_time': NOW.isoformat(), 'recipe': RECIPE, 'method': REVIEW,
        'passed': True, 'notices': len(results), 'source_documents': 1, 'duplicates_after_replay': 0,
        'held_candidates': len(held), 'held': held,
        'provider_requests': 0, 'source_requests': 0, 'cost_usd': 0, 'published': 0,
        'public_files_unchanged': True, 'public_file_hashes': before,
        'results': results, 'articles': [p['article'] for p in prepared]}
    (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    parts = []
    for article in report['articles']:
        parts.append('<article><h2>' + escape(article['title']) + '</h2><p><strong>' + escape(article['intro'])
                     + '</strong></p>' + ''.join('<p>' + escape(p['text']) + '</p>' for p in article['paragraphs'])
                     + '<p><a href="' + escape(article['sources'][0]['url'], quote=True) + '">Kia Sverige</a></p></article>')
    html = '''<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Privat notisprov</title>
<style>body{margin:0;background:#f7f7f4;color:#171b1c;font:16px/1.6 system-ui,sans-serif}main{max-width:760px;margin:auto;padding:32px 20px}h1{font-size:30px;line-height:1.2}h2{font-size:22px;line-height:1.3}article{padding-block:24px;border-bottom:1px solid #d7dfdc}a{color:#245e5b}</style>
<main><h1>Privat notisprov</h1><p>Syntetiskt testunderlag. Inte en aktuell prisverifiering eller publicerade nyheter.</p>'''
    (directory / 'index.html').write_text(html + ''.join(parts) + '</main></html>', encoding='utf-8')
    return {key: report[key] for key in ('passed', 'fixture', 'notices', 'source_documents',
            'duplicates_after_replay', 'held_candidates', 'provider_requests', 'source_requests', 'published', 'public_files_unchanged')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output)))
