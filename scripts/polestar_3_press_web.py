"""Capture and replay the unchanged Polestar 3 web sizes served by its pressroom."""

import argparse
import hashlib
import io
import json
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from PIL import Image, ImageChops, ImageStat, IptcImagePlugin
from audit_catalog_sources import ROOT, SourceFetcher
from manufacturer_embedded_data import unique_object
from variant_refresh import one, parse_document

POLICY_ID = 'polestar-3-have-private-3332240'
POLICY = json.loads((ROOT / 'src/press-image-publishers.json').read_text(encoding='utf-8'))[POLICY_ID]
PAGE = POLICY['origin'] + POLICY['approved_image_paths'][0]
RELEASE = POLICY['official_link_evidence']
PREFIX = 'polestar-3-press-web-'
STEM = 'polestar-3-press-' + POLICY['approved_source_sha256'][:12]
SIZES = POLICY['publisher_responsive_variants']
DIMENSIONS = tuple(POLICY['approved_original_dimensions'])
SOURCES = {PAGE: 'image-page.html', RELEASE: 'launch-page.html',
           **{item['source_url']: f'{STEM}-{item["width"]}.webp' for item in SIZES}}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def verify_press_link(release, page):
    release = parse_document(release, 'text/html')
    heading = one(release.nodes('h1'), 'exact_800v_launch_title_required').text()
    if not re.search(r'Polestar 3 med 800 volt\b', heading) or PAGE not in {n.attrs.get('href') for n in release.nodes('a')}:
        raise ValueError('exact_800v_launch_link_required')
    doc = parse_document(page, 'text/html')
    if not re.fullmatch(POLICY['model_title_pattern'], one(doc.nodes('h1'), 'require_image_title').text()):
        raise ValueError('polestar_press_title_changed')
    for field in ('license_label', 'permission_excerpt', 'condition_excerpt'):
        if POLICY[field] not in doc.text():
            raise ValueError('polestar_press_terms_changed')
    if POLICY['approved_asset_url'] not in {n.attrs.get('href') for n in doc.nodes('a') if n.text() == POLICY['download_label']}:
        raise ValueError('polestar_press_original_link_changed')
    img = one((n for n in doc.nodes('img') if 'panel__media-image' in n.attrs.get('class', '').split()),
              'require_one_main_pressroom_image')
    expected = [(s['source_url'], f'{s["width"]}w') for s in SIZES]
    # The source URL itself uses comma-separated image transformations.
    advertised = [tuple(m.split()) for m in re.split(r'(?<=w),\s+', img.attrs.get('srcset', ''))]
    if ((img.attrs.get('width'), img.attrs.get('height')) != tuple(map(str, DIMENSIONS))
            or advertised != expected or img.attrs.get('src') != expected[0][0]):
        raise ValueError('publisher_responsive_links_changed')
    credit_labels = ('fotograf', 'photographer', 'billedkreditering', 'kreditering')
    if any(n.text().strip(':').casefold() in credit_labels for n in doc.nodes('dt')):
        raise ValueError('new_photographer_credit_needs_review')


def compare_frames(original, sizes):
    if sha(original) != POLICY['approved_source_sha256']:
        raise ValueError('reviewed_image_original_changed')
    with warnings.catch_warnings():
        # The known image is larger than Pillow's warning threshold; its bytes are pinned above.
        warnings.filterwarnings('ignore', category=Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(original), formats=['JPEG']) as image:
            if image.size != DIMENSIONS or image.getexif().get(274, 1) != 1:
                raise ValueError('require_reviewed_original_geometry')
            if (image.getexif().get(315) or (IptcImagePlugin.getiptcinfo(image) or {}).get((2, 80))
                    or any(kind == 'APP1' and payload.startswith(b'http') for kind, payload in image.applist)):
                raise ValueError('embedded_photographer_credit_needs_review')
            image.draft('RGB', (380, 285))
            reference = image.resize((160, 120), Image.Resampling.LANCZOS)
    result = []
    for info in SIZES:
        data = sizes[info['source_url']]
        if sha(data) != info['sha256']:
            raise ValueError('unreviewed_publisher_image_bytes')
        width, height = info['width'], info['height']
        with Image.open(io.BytesIO(data), formats=['WEBP']) as image:
            if image.size != (width, height) or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('publisher_image_dimensions_changed')
            small = image.convert('RGB').resize((160, 120), Image.Resampling.LANCZOS)
        diff = ImageChops.difference(small, reference)
        # Check every quadrant, including the edges, against the approved full frame.
        error = max(max(ImageStat.Stat(diff.crop((x, y, x + 80, y + 60))).mean)
                    for x in (0, 80) for y in (0, 60))
        if error > 2:
            raise ValueError('publisher_image_does_not_preserve_full_frame')
        result.append({**info, 'bytes': len(data), 'max_quadrant_mean_delta': round(error, 3),
                       'file': SOURCES[info['source_url']]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    args = parser.parse_args()
    root = ROOT.resolve() / 'data/local/release-data'
    if root.resolve(strict=True) != root or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', s, re.I) for s in root.parts):
        raise ValueError('require_private_local_release_root')

    def read(path, limit):
        if path.resolve(strict=True) != path or not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise ValueError('invalid_private_media_file')
        return path.read_bytes()

    original = read(root / 'polestar-3-image-review-3cyf4kup' / (STEM + '.jpg'), 12_000_000)
    if args.replay:
        folder = args.replay.absolute()
        if folder.parent != root or folder.resolve(strict=True) != folder or not re.fullmatch(PREFIX + '[0-9a-z_]+', folder.name):
            raise ValueError('require_exact_private_polestar_web_directory')
        saved = json.loads(read(folder / 'report.json', 50_000), object_pairs_hook=unique_object)
        fetched_at = saved['fetched_at']
        raw = {url: read(folder / name, 300_000) for url, name in SOURCES.items()}
    else:
        fetcher = SourceFetcher(timeout=15, max_bytes=300_000, document_parser=lambda body, _:body,
                                text_parser=lambda _body, _: '',
                                url_policy=lambda url, scope: scope == {'Polestar'} and url in SOURCES)
        raw = {}
        for url, name in SOURCES.items():
            response = fetcher.fetch(url, {'Polestar'})
            kind = 'text/html' if name.endswith('.html') else 'image/webp'
            if (response.get('status') != 'reachable' or response.get('http_status') != 200
                    or response.get('final_url') != url or response.get('content_type', '').split(';')[0] != kind):
                raise ValueError(f'image_source_not_verified: {response["status"]}: {url}')
            raw[url] = response['document']
        fetched_at = datetime.now(timezone.utc).isoformat()
    verify_press_link(raw[RELEASE], raw[PAGE])
    result = {'status': 'publisher_web_sizes_private_review', 'publisher_id': POLICY_ID,
              'model_key': 'polestar|3', 'publisher_credit': POLICY['publisher'],
              'photographer_supplied': False, 'original_sha256': sha(original),
              'fetched_at': fetched_at, 'sources': {u: {'http_status': 200, 'content_sha256': sha(b)} for u, b in raw.items()},
              'variants': compare_frames(original, raw), 'publication_approved': False}
    if args.replay:
        if result != saved:
            raise ValueError('press_web_receipt_changed')
    else:
        folder = Path(mkdtemp(prefix=PREFIX, dir=root))
        for url, name in SOURCES.items():
            (folder / name).write_bytes(raw[url])
        (folder / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({**result, 'output': str(folder)}))


if __name__ == '__main__':
    main()
