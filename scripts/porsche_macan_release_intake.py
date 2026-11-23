"""Bind exact Macan facts, Swedish market data and a private photo candidate."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import mkdtemp
from urllib.parse import urljoin

from audit_catalog_sources import SourceFetcher
from porsche_macan_market import replay as replay_market
from porsche_macan_review import PRIVATE, replay as replay_specs, sha
from variant_refresh import one, parse_document

KIT = 'https://newsroom.porsche.com/de/pressemappen/der-neue-porsche-macan.html'
GALLERY = 'https://newsroom.porsche.com/.rest/pnr/gallery/v1/17a8a130-6cff-4b35-ad2b-206bcf974a20?locale=de'
TERMS = 'https://newsroom.porsche.com/de/bilder-videos/porsche-newsroom-nutzungshinweise.html'
PHOTO = ('https://porschepictures.flowcenter.de/pmdb/thumbnail.cgi?'
         'id=297892&w=6000&h=4000&crop=0&public=1&cs=7d0ab59f301c0f19')
PHOTO_SHA = '3097c517e11eb8ba4be5db10dec3fcaf8467d1d4b3e09fe8646b6e278c5662f6'
GALLERY_TITLE = 'Porsche Macan - Media Drive Stuttgart'
ASSET_ID = 'pmdb:9458fb1b-7f83-4267-ba53-8d6321764b0a'
CAPTION = 'Macan, Media Drive Stuttgart, 2024, Porsche AG'
EDITORIAL_ONLY = ('ausschlie\u00dflich f\u00fcr redaktionelle Berichterstattung, nicht jedoch '
                  'f\u00fcr Werbung oder f\u00fcr andere gesch\u00e4ftliche Zwecke')
PHOTO_SOURCES = {
    'kit.html': (KIT, 'text/html'), 'gallery.json': (GALLERY, 'application/json'),
    'terms.html': (TERMS, 'text/html'), 'photo.jpg': (PHOTO, 'image/jpeg'),
}


def photo_identity(bodies):
    kit = parse_document(bodies['kit.html'], 'text/html')
    gallery = one((node for node in kit.nodes('ul') if node.attrs.get('data-title') == GALLERY_TITLE),
                  'require_exact_base_macan_gallery')
    if urljoin(KIT, gallery.attrs.get('data-gallery-url', '')) != GALLERY:
        raise ValueError('macan_base_gallery_link_changed')
    asset = one((item for item in json.loads(bodies['gallery.json']) if item.get('assetId') == ASSET_ID),
                'require_exact_base_macan_asset')
    if (asset.get('title'), asset.get('highResDownloadLink'), asset.get('extension'), asset.get('portrait')) != (
            CAPTION, PHOTO, 'JPG', False):
        raise ValueError('macan_photo_identity_changed')
    terms = parse_document(bodies['terms.html'], 'text/html').text()
    if EDITORIAL_ONLY not in terms or 'Angabe der jeweils ausgewiesenen Quelle' not in terms:
        raise ValueError('macan_media_terms_changed')
    if sha(bodies['photo.jpg']) != PHOTO_SHA:
        raise ValueError('macan_photo_bytes_changed')
    return {'status': 'verified_model_photo_private_only', 'asset_id': ASSET_ID, 'credit': 'Porsche AG',
            'caption': CAPTION, 'source_url': KIT, 'media_url': PHOTO, 'license_url': TERMS,
            'width': 6000, 'height': 4000, 'sha256': PHOTO_SHA, 'catalog_use_confirmed': False}


def capture_photo():
    if PRIVATE.resolve() != PRIVATE or any('onedrive' in p.lower() for p in PRIVATE.parts):
        raise ValueError('require_private_unlinked_evidence_directory')
    urls = {url for url, _ in PHOTO_SOURCES.values()}
    fetcher = SourceFetcher(timeout=18, max_bytes=4_000_000, document_parser=lambda body, *_: body,
                            text_parser=lambda *_: '',
                            url_policy=lambda url, brands: url in urls and brands == {'Porsche'})
    bodies, receipts = {}, {}
    for name, (url, media_type) in PHOTO_SOURCES.items():
        response = fetcher.fetch(url, {'Porsche'})
        if (response['status'], response.get('http_status'), response.get('final_url'),
                response.get('content_type', '').split(';')[0]) != ('reachable', 200, url, media_type):
            raise ValueError('macan_photo_source_unavailable:' + name)
        bodies[name] = response['document']
        receipts[name] = {'source_url': url, 'http_status': 200, 'content_hash': sha(bodies[name]),
                          'fetched_at': datetime.now(timezone.utc).isoformat()}
    report = {**photo_identity(bodies), 'sources': receipts}
    PRIVATE.mkdir(parents=True, exist_ok=True)
    folder = Path(mkdtemp(prefix='porsche-macan-photo-', dir=PRIVATE))
    for name, content in bodies.items():
        (folder / name).write_bytes(content)
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    return folder, report


def replay_photo(folder):
    resolved = folder.resolve(strict=True)
    if resolved != folder.absolute() or resolved.parent != PRIVATE or not resolved.name.startswith('porsche-macan-photo-'):
        raise ValueError('require_private_macan_photo_packet')
    paths = {name: resolved / name for name in (*PHOTO_SOURCES, 'report.json')}
    if any(path.resolve(strict=True) != path for path in paths.values()):
        raise ValueError('macan_photo_packet_links_not_allowed')
    report = json.loads(paths['report.json'].read_text(encoding='utf8'))
    receipts = report['sources']
    if set(receipts) != set(PHOTO_SOURCES):
        raise ValueError('unexpected_macan_photo_source_scope')
    bodies = {name: paths[name].read_bytes() for name in PHOTO_SOURCES}
    for name, (url, _) in PHOTO_SOURCES.items():
        r = receipts[name]
        if (r.get('source_url'), r.get('http_status'), r.get('content_hash')) != (url, 200, sha(bodies[name])):
            raise ValueError('macan_photo_evidence_changed:' + name)
    if report != {**photo_identity(bodies), 'sources': receipts}:
        raise ValueError('macan_photo_replay_changed')
    return report


def intake(specs, market, photo, now):
    evidence = dict(specs['evidence'], price_sek=specs['price_evidence'])
    values = dict(specs['facts'], price_sek=specs['price_sek'])
    field_evidence = {}
    for field, value in values.items():
        proof = evidence[field]
        receipt = specs['sources'][proof['source']]
        field_evidence[field] = {'value': value, 'quote': proof['snippet'], 'source_url': receipt['source_url'],
                                 'source_hash': receipt['content_hash'], 'fetched_at': receipt['fetched_at']}
    receipts = [r for group in (specs, market, photo) for r in group['sources'].values()]
    ages = [now - datetime.fromisoformat(r['fetched_at']) for r in receipts]
    return {
        'status': 'macan_release_intake_verified_private',
        'model': 'Porsche Macan', 'variant': 'Electric RWD MY27',
        'manufacturer_identity': 'SE|MY27|XABAA1|RWD|5|20',
        'price_type': specs['price_type'], 'price_valid_until': None,
        'field_evidence': field_evidence, 'qualifications': specs['qualifications'],
        'spec_sources': specs['sources'],
        'market_discovery': market['row'], 'market_sources': market['sources'], 'photo_candidate': photo,
        'all_sources_within_15_minutes': all(timedelta() <= age <= timedelta(minutes=15) for age in ages),
        'release_holds': ['photo_terms_do_not_confirm_catalog_use', 'scoped_insertion_not_rehearsed'],
        'publication_approved': False, 'production_writes': 0,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-photo', action='store_true')
    parser.add_argument('--specs', type=Path)
    parser.add_argument('--market', type=Path)
    parser.add_argument('--photo', type=Path)
    args = parser.parse_args()
    if args.capture_photo and not any((args.specs, args.market, args.photo)):
        folder, report = capture_photo()
        print(json.dumps({'folder': str(folder), **report}))
    elif not args.capture_photo and all((args.specs, args.market, args.photo)):
        report = intake(replay_specs(args.specs), replay_market(args.market), replay_photo(args.photo),
                        datetime.now(timezone.utc))
        print(json.dumps(report, indent=2))
    else:
        parser.error('Use --capture-photo or supply all of --specs, --market and --photo')
