"""Prepare saved-source launch briefs or explicit synthetic offline previews. Never calls AI."""
import argparse
import copy
import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from news_editorial import blocks
from news_launch_hybrid import REVIEW_FLAGS, stage_offline_launch
from news_store import NewsStore, artifact_hash

ROOT = Path(__file__).resolve().parents[1]


def fixture_input(data):
    if data.get('fixture') is not True:
        raise ValueError('explicit_synthetic_fixture_required')
    source = {'id': 'vw-sweden-press', 'name': 'Volkswagen Group Sverige',
              'kind': 'primary', 'website': 'https://www.vwgroup.se'}
    url = source['website'] + '/nyheter--media/pressmeddelanden/2026/10/offline-fixture/'
    content = data['content']
    item = {'id': 'hybrid-offline-fixture', 'source_id': source['id'], 'url': url,
            'status': 'ready', 'cluster_id': None, 'payload': {
                'title': 'Nya Volkswagen ID. Cross - syntetisk testkälla', 'publisher': source['name'],
                'source_kind': 'primary', 'published_at': data['published_at'], 'fetched_at': data['published_at'],
                'final_url': url, 'access_status': 'accessible', 'content': content,
                'content_hash': hashlib.sha256(content.encode()).hexdigest()}}
    return [item], [source]


def fixture_article(data, brief):
    draft = copy.deepcopy(data['article'])
    ids = {f['metric']: f['id'] for f in brief['facts']}
    for key in ('title_fact_ids', 'intro_fact_ids'):
        draft[key] = [ids[i] for i in draft[key]]
    for p in draft['paragraphs']:
        p['fact_ids'] = [ids[i] for i in p['fact_ids']]
    return draft


def fixture_audit(article, brief):
    decision = {'supported': True, 'reason': 'Synthetic contract-test response, not an AI verdict.', 'unsupported_claims': []}
    return {'brief_hash': brief['brief_hash'], 'article_hash': artifact_hash(article),
            **{k: True for k in REVIEW_FLAGS},
            'facts': {f['id']: copy.deepcopy(decision) for f in brief['facts']},
            'blocks': {b['id']: copy.deepcopy(decision) for b in blocks(article)}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--input', type=Path, help='Saved JSON with items/sources; prepares facts only')
    inputs.add_argument('--fixture', type=Path, help='Explicit synthetic source + writer/review responses')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/local/news-hybrid-launch-preview')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'data/local').resolve()):
        raise ValueError('hybrid_preview_must_stay_in_private_local_directory')
    data = json.loads((args.fixture or args.input).read_text(encoding='utf-8-sig'))
    is_fixture = args.fixture is not None
    items, sources = fixture_input(data) if is_fixture else (data['items'], data['sources'])
    now = datetime.fromisoformat(data['published_at']) if is_fixture else datetime.now(timezone.utc)
    output.mkdir(parents=True, exist_ok=True)
    with closing(NewsStore(output / 'private.sqlite', backend='sqlite')) as store:
        writer = reviewer = None
        if is_fixture:
            from news_launch_hybrid import launch_brief
            brief = launch_brief(items, sources, now=now)
            article = fixture_article(data, brief)
            writer = lambda *_: copy.deepcopy(article)
            reviewer = lambda *_: fixture_audit(article, brief)
        result = stage_offline_launch(store, items, sources, writer, reviewer, now=now)
        result.update(offline_only=True, synthetic_fixture=is_fixture, paid_calls=0, cost_usd=0, public_export_written=False)
        (output / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        article = store.get('news_articles', result['article_id']) if result.get('article_id') else None
        payload = (article or {}).get('payload', {})
        content = '<h1>' + escape(payload.get('title', 'Faktaplan för modell och svensk lansering')) + '</h1>'
        if payload.get('intro'):
            content += '<p class="intro">' + escape(payload['intro']) + '</p>'
            content += ''.join('<p>' + escape(p['text']) + '</p>' for p in payload.get('paragraphs', []))
        else:
            content += '<ul>' + ''.join('<li>' + escape(f['statement']) + '</li>' for f in result.get('brief', {}).get('facts', [])) + '</ul>'
        label = 'Syntetiskt offlineprov - texten är en testfixtur, inte AI-genererad.' if is_fixture else 'Privat faktaplan från sparade källor.'
        page = '<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Privat hybridprov</title><style>body{margin:0;background:#f7f7f4;color:#171b1c;font:17px/1.7 system-ui}main{max-width:760px;margin:40px auto;padding:24px}h1{font-size:36px;line-height:1.15}p{margin:24px 0}.intro{font-size:20px}.label{border-left:4px solid #245e5b;padding:16px;background:#dceae6;font-size:15px}small{color:#697374}@media(max-width:600px){main{margin:0;padding:24px}h1{font-size:30px}}</style><main><div class="label">' + escape(label) + '<br>Inget publiceras. Ingen verklig oberoende AI-granskning har utförts.</div>' + content + '<hr><small>Status: ' + escape(result['status']) + '. 200-350 ord avser ingress och brödtext. Kostnad: 0 USD.</small></main></html>'
        (output / 'index.html').write_text(page, encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'brief'}, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    main()
