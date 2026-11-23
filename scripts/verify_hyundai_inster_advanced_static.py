"""Verify the actual site generators against the reviewed private Inster catalog."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import generate_sitemap
import news_public
import prerender_static_routes
import vehicle_redirects
from verify_hyundai_ioniq9_static import SITE, live, verified_paths

SLUG = 'bilar/hyundai-inster-49-kwh-advanced-tech-17-tum-my27'
URL = f'{SITE}/{SLUG}'


def verify(output):
    release = Path(__file__).resolve().parents[1] / 'data/local/release-data'
    if (output.resolve(strict=True) != output or output.parent.parent != release or not output.name.startswith('ui-')
            or not output.parent.name.startswith('inster-advanced-local-')
            or any('onedrive' in part.casefold() for part in output.parts)):
        raise ValueError('Require an unlinked isolated Inster build')
    root, dist = output / 'source', output / 'dist'
    if any(p.resolve(strict=True) != p for p in (root, dist)):
        raise ValueError('Unexpected link in isolated build')
    ui = json.loads((output / 'ui-report.json').read_text(encoding='utf-8'))
    report = json.loads((output.parent / 'report.json').read_text(encoding='utf-8'))
    candidate = json.loads((root / 'public/data/public_ev_variants.json').read_text(encoding='utf-8'))
    if (ui['status'] != 'inster_private_ui_verified' or ui['production_writes'] or ui['publication_approved']
            or ui['catalog_sha256'] != report['candidate_sha256'] or not ui['comparison']
            or candidate['status'] != 'isolated_preview_only' or candidate['publication_approved']):
        raise ValueError('Require the tested private Inster candidate')
    copy = json.loads((output.parent / 'candidate-catalog.json').read_text(encoding='utf-8'))
    if candidate['records'] != copy['records'] or copy['catalog_sha256'] != report['candidate_sha256']:
        raise ValueError('Candidate changed after browser rehearsal')

    previous = verified_paths(live('/sitemap.xml'))
    news_bytes = live('/data/news_articles.json')
    news = json.loads(news_bytes)['records']
    article_paths = {SITE + '/nyheter/' + item['slug'] for item in news
                     if item.get('status', 'published') == 'published' and item['published_at']}
    if not article_paths or len(article_paths) != len(news) or article_paths != {
            path for path in previous if path.startswith(SITE + '/nyheter/')}:
        raise ValueError('The live news sitemap and export disagree')
    news_path = root / 'public/data/news_articles.json'
    news_path.write_bytes(news_bytes)

    for module in (generate_sitemap, news_public, prerender_static_routes, vehicle_redirects):
        module.ROOT = root
    generate_sitemap.SITE_URL = prerender_static_routes.SITE_URL = SITE
    if os.name == 'nt':
        dist = Path('\\\\?\\' + str(dist))
    prerender_static_routes.DIST = dist
    generate_sitemap.main()
    prerender_static_routes.main()
    actual = verified_paths((root / 'public/sitemap.xml').read_bytes())
    if URL in previous or actual != previous | {URL}:
        raise ValueError('Inster must be the only difference in the public sitemap')

    html = (dist / SLUG / 'index.html').read_text(encoding='utf-8')
    tag = re.search(r'<script type="application/ld\+json" data-prerender="page">(.*?)</script>', html, flags=re.S)
    if not tag or f'<link rel="canonical" href="{URL}"' not in html:
        raise ValueError('The new vehicle route is missing its canonical URL or structured data')
    data, = [node for node in json.loads(tag[1]) if node.get('@type') == 'Vehicle']
    names = {item['name']: item.get('value') for item in data['additionalProperty']}
    if 'offers' in data or names.get('Tillverkarens fr\u00e5npris') != '377900 SEK':
        raise ValueError('Inster starting price must not be presented as a fixed offer')
    if news_path.read_bytes() != news_bytes:
        raise ValueError('The rehearsal must preserve the public news export')
    proof = {'status': 'inster_static_preview_verified', 'added': URL, 'existing_urls': len(previous),
             'candidate_urls': len(actual), 'news_articles_preserved': len(article_paths),
             'public_news_sha256': hashlib.sha256(news_bytes).hexdigest(), 'catalog_sha256': ui['catalog_sha256'],
             'fixed_offer': False, 'production_writes': 0, 'publication_approved': False}
    with (output / 'seo-report.json').open('x', encoding='utf-8') as handle:
        json.dump(proof, handle)
    print(json.dumps(proof))


if __name__ == '__main__':
    verify(Path(os.path.abspath(sys.argv[1])))
