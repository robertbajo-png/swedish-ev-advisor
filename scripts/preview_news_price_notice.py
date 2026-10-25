"""Short price notice from an existing source snapshot. Offline and private only."""
import argparse
import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from news_notice_pipeline import prepare_notice, stage_notices
from news_notices import NOTICE_RECIPE
from news_store import NewsStore, artifact_hash
from refresh_verified_variants import save

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'data/local'
DEFAULT_MANIFEST = PRIVATE / 'release-data/news-short-breadth-private-2026-10-24/price/manifest.json'


def build(manifest_path, directory, now=None):
    now = now or datetime.now(timezone.utc)
    manifest_path, directory = Path(manifest_path).resolve(), Path(directory).resolve()
    if not directory.is_relative_to(PRIVATE.resolve()) or directory == PRIVATE.resolve():
        raise ValueError('price_preview_must_remain_private')
    if directory.exists():
        raise FileExistsError('price_preview_does_not_overwrite_existing_artifacts')
    raw = manifest_path.read_bytes()
    frozen = json.loads(raw)
    brief = frozen['brief']
    if brief.get('kind') != 'price':
        raise ValueError('price_preview_requires_price_source_snapshot')
    item, source = brief['item'], brief['source']
    article, review = prepare_notice(item, source, kind='price', now=now)
    if not review['passed']:
        raise ValueError('price_notice_rule_review_failed')
    fingerprints = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        for p in ('public/data/news_articles.json', 'public/sitemap.xml')}
    directory.mkdir(parents=True)
    with closing(NewsStore(directory / 'private.sqlite', backend='sqlite')) as store:
        store.put('news_items', item)
        staged = stage_notices(store, [source], {}, now=now, item_ids={item['id']})
        if (len(staged) != 1 or staged[0]['kind'] != 'price' or staged[0]['status'] != 'validated_draft'
                or store.public_articles()):
            raise ValueError('price_notice_private_staging_failed')
        stored = store.get('news_articles', staged[0]['article_id'])
        if stored['payload'] != article or stored['artifact_hash'] != artifact_hash(article):
            raise ValueError('price_notice_staged_artifact_changed')
    if any(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != digest for p, digest in fingerprints.items()):
        raise ValueError('price_notice_public_output_changed')
    if manifest_path.read_bytes() != raw:
        raise ValueError('price_notice_input_snapshot_changed')
    total = len(article['notice_facts']['fields']['prices']['entries'])
    report = {'preview_kind': 'offline_price_notice', 'recipe': NOTICE_RECIPE,
        'generated_at': now.isoformat(), 'offline': True, 'collector_requests': 0,
        'provider_requests': 0, 'ai_audit_performed': False, 'cost_usd': 0, 'published': 0,
        'historical_ai_result_reused': False, 'public_outputs_unchanged': True,
        'input_manifest_hash': hashlib.sha256(raw).hexdigest(), 'input_manifest_unchanged': True,
        'source_fetched_at': item['payload']['fetched_at'], 'source_published_at': item['payload']['published_at'],
        'source_hash': item['payload']['content_hash'], 'article_hash': artifact_hash(article),
        'source_price_rows': total, 'shown_price_rows': min(3, total),
        'article': article, 'review': review, 'private_staging': staged[0]}
    save(directory / 'report.json', report)
    (directory / 'index.html').write_text(render(report), encoding='utf-8')
    return {'passed': True, 'word_count': review['word_count'], 'review_method': review['method'],
        'provider_requests': 0, 'collector_requests': 0, 'published': 0, 'cost_usd': 0,
        'source_price_rows': total, 'shown_price_rows': min(3, total),
        'preview': str(directory / 'index.html'), 'report': str(directory / 'report.json')}


def render(report):
    article, review = report['article'], report['review']
    reference = article['sources'][0]
    body = ''.join('<p>' + escape(p['text']) + '</p>' for p in article['paragraphs'])
    return '''<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Privat prisnotis</title>
<style>body{margin:0;background:#f7f7f4;color:#171b1c;font:17px/1.7 system-ui}main{max-width:740px;margin:32px auto;padding:24px}
h1{font-size:30px;line-height:1.15}.intro{font-size:19px}.meta,footer{color:#566363;font-size:14px}a{color:#245e5b}
section{padding:24px 0;border-block:1px solid #e4e7e4}footer{margin-top:24px}</style>
<main><p class="meta">Privat offlineprov. Inget publicerat.</p><section><p class="meta">Rekommenderade cirkapriser · Sverige</p>
<h1>''' + escape(article['title']) + '</h1><p class="intro">' + escape(article['intro']) + '</p>' + body + '''
<p class="meta">Urval: ''' + str(report['shown_price_rows']) + ' av ' + str(report['source_price_rows']) + ''' prisrader.
Källa: <a href="''' + escape(reference['url'], quote=True) + '">' + escape(reference['publisher']) + '</a>, ' + escape(reference['published_at'][:10]) + '''.</p></section>
<footer><p>''' + str(review['word_count']) + ''' ord. Regelbaserad källkontroll godkänd, inte en AI-slutgranskning.
Ingen nätverkshämtning, inga betalda anrop och ingen publicering. Detta är inte ett godkännande av ett tidigare AI-prov.</p></footer></main></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--output', type=Path, default=PRIVATE / 'news-price-short-offline-2026-10-24')
    args = parser.parse_args()
    print(json.dumps(build(args.manifest, args.output), ensure_ascii=True, indent=2))
