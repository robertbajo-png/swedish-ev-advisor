"""Fetch a price PDF only when the current official Swedish page links it."""
import argparse
import hashlib
import json
from urllib.parse import urljoin, urlsplit

from audit_catalog_sources import SourceFetcher
from collect_release_sources import capture, OUT
from variant_refresh import parse_document

PARENT = 'https://www.renault.se/personbilar/elbilar/r5-e-tech-electric/versioner-och-priser'
ASSET_HOST = 'edge.sitecorecloud.io'
PREFIX = '/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/renaultsesite/cardocuments/'


def collect():
    parent = SourceFetcher(document_parser=parse_document).fetch(PARENT, {'Renault'})
    if parent.get('status') != 'reachable' or parent.get('final_url') != PARENT:
        raise ValueError('fresh_official_page_required')
    links = {urljoin(PARENT, n.attrs['href']) for n in parent['document'].nodes('a')
             if n.attrs.get('href') and n.text().strip().casefold() == 'prislista'}
    if len(links) != 1:
        raise ValueError('unique_official_price_link_required')
    link = links.pop()
    parsed = urlsplit(link)
    if (parsed.scheme != 'https' or parsed.hostname != ASSET_HOST or not parsed.path.startswith(PREFIX)
            or not parsed.path.endswith('/prislista-renault-5-e-tech-electric.pdf')
            or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.query or parsed.fragment):
        raise ValueError('unapproved_document_target')
    result = capture(link, {'Renault'}, url_policy=lambda url, brands: url == link and brands == {'Renault'})
    result['discovered_from'] = PARENT
    result['discovery_source_hash'] = parent['content_hash']
    result['source_authority'] = 'importer'
    key = hashlib.sha256(link.encode()).hexdigest()[:16]
    (OUT / (key + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = collect()
    print(json.dumps({key: result.get(key) for key in ('status', 'final_url', 'content_hash', 'body_file', 'discovered_from')}))


if __name__ == '__main__':
    main()
