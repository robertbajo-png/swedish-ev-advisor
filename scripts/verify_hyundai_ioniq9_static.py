"""Verify the real sitemap and metadata generators in the private UI build."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import generate_sitemap
import news_public
import prerender_static_routes
import vehicle_redirects


SITE = 'https://elbilsagenten.se'


def verified_paths(xml):
    return {node.text for node in ElementTree.fromstring(xml).iterfind('.//{*}loc')}


def live(path):
    # Use the same public HTTP client as the deployment verifier.
    return subprocess.check_output(['node', '--input-type=module', '-e', '''
      const response=await fetch(process.argv[1],{redirect:'error',signal:AbortSignal.timeout(20000)});
      if(response.status!==200)throw Error('Expected the exact public resource');
      const body=Buffer.from(await response.arrayBuffer());
      if(!body.length||body.length>2000000)throw Error('Unexpected public resource size');
      process.stdout.write(body);
    ''', SITE + path], timeout=25)


def news_digest(root):
    return hashlib.sha256((root / 'public/data/news_articles.json').read_bytes()).hexdigest()


def main(output):
    release = Path(__file__).resolve().parents[1] / 'data/local/release-data'
    output = output.resolve(strict=True)
    if (output.parent.parent != release or not output.name.startswith('ui-')
            or not output.parent.name.startswith('hyundai-ioniq9-local-')
            or any('onedrive' in part.lower() for part in output.parts)):
        raise ValueError('Require the isolated IONIQ 9 build')
    root = output / 'source'
    original = output.parent / 'main-source'
    dist = output / 'dist'
    for folder in (root, original, dist):
        if folder.resolve(strict=True) != folder:
            raise ValueError('Unexpected linked directory in isolated build')
    report = json.loads((output / 'ui-report.json').read_text(encoding='utf-8'))
    if report['status'] != 'ioniq9_private_ui_verified' or report['production_writes'] != 0:
        raise ValueError('Require an isolated browser receipt')
    candidate = json.loads((root / 'public/data/public_ev_variants.json').read_text(encoding='utf-8'))
    if candidate['status'] != 'isolated_preview_only' or candidate['publication_approved']:
        raise ValueError('Do not run static rehearsal against a production export')
    previous = verified_paths(live('/sitemap.xml'))
    live_news = live('/data/news_articles.json')
    articles = json.loads(live_news)['records']
    expected_articles = {SITE + '/nyheter/' + row['slug'] for row in articles
                         if row.get('status', 'published') == 'published' and row['published_at']}
    if len(expected_articles) != len(articles) or expected_articles != {
            path for path in previous if path.startswith(SITE + '/nyheter/')}:
        raise ValueError('Production news export differs from the deployed sitemap')
    (root / 'public/data/news_articles.json').write_bytes(live_news)
    for module in (generate_sitemap, news_public, prerender_static_routes, vehicle_redirects):
        module.ROOT = root
    generate_sitemap.SITE_URL = prerender_static_routes.SITE_URL = SITE
    if os.name == 'nt':
        dist = Path('\\\\?\\' + str(dist))
    prerender_static_routes.DIST = dist
    generate_sitemap.main()
    prerender_static_routes.main()
    actual = verified_paths((root / 'public/sitemap.xml').read_bytes())
    slug = 'bilar/hyundai-ioniq-9-advanced-awd-7-sits-my27'
    url = SITE + '/' + slug
    if actual != previous | {url} or url in previous:
        raise ValueError('Sitemap must keep all existing URLs and add only IONIQ 9')
    html = (dist / slug / 'index.html').read_text(encoding='utf-8')
    tag = re.search(r'<script type="application/ld\+json" data-prerender="page">(.*?)</script>', html, flags=re.S)
    if not tag or f'<link rel="canonical" href="{url}"' not in html:
        raise ValueError('New static route lacks canonical URL or structured data')
    data, = [node for node in json.loads(tag[1]) if node.get('@type') == 'Vehicle']
    if ('offers' in data or not any(item.get('name') == 'Tillverkarens fr\u00e5npris' and item.get('value') == '850900 SEK'
                                    for item in data['additionalProperty'])):
        raise ValueError('Static data must not advertise the manufacturer starting price as a fixed offer')
    if not expected_articles or news_digest(root) != hashlib.sha256(live_news).hexdigest():
        raise ValueError('Preserve all existing public news')
    proof = {'status': 'ioniq9_static_preview_verified', 'existing_urls': len(previous), 'candidate_urls': len(actual),
             'added': url, 'news_articles_preserved': len(expected_articles), 'catalog_sha256': report['catalog_sha256'],
             'fixed_offer': False, 'production_writes': 0, 'publication_approved': False}
    with (output / 'seo-report.json').open('x', encoding='utf-8') as handle:
        json.dump(proof, handle)
    print(json.dumps(proof))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
