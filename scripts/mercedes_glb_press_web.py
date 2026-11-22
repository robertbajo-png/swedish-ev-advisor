"""Capture publisher-supplied GLB web sizes without modifying any source image."""
import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

from PIL import Image, ImageChops, ImageStat
from audit_catalog_sources import ROOT, SourceFetcher
from variant_refresh import one, parse_document

PUBLISHER = 'mercedes-glb-se-private-review'
POLICY = json.loads((ROOT / 'src/press-image-publishers.json').read_text(encoding='utf-8'))[PUBLISHER]
PAGE = POLICY['origin'] + POLICY['approved_image_paths'][0]
PREFIX = 'mercedes-glb-press-web-'
STEM = 'mercedes-benz-glb-press-' + POLICY['approved_source_sha256'][:12]
LIMIT = 1_500_000


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def advertised(page):
    doc = parse_document(page, 'text/html')
    if not re.fullmatch(POLICY['model_title_pattern'], one(doc.nodes('h1'), 'require the GLB title').text()):
        raise ValueError('GLB press page title changed')
    if any(POLICY[k] not in doc.text() for k in ('permission_excerpt', 'condition_excerpt', 'license_label')):
        raise ValueError('GLB usage terms changed')
    if POLICY['approved_asset_url'] not in {node.attrs.get('href') for node in doc.nodes('a')
                                           if node.text() == POLICY['download_label']}:
        raise ValueError('GLB press original changed')
    image = one((n for n in doc.nodes('img') if 'panel__media-image' in n.attrs.get('class', '').split()),
                'exact GLB press image required')
    if (image.attrs.get('width'), image.attrs.get('height')) != ('5000', '3333'):
        raise ValueError('Original dimensions changed')
    links = [part.split() for part in re.split(r'(?<=w),\s+', image.attrs.get('srcset', ''))]
    if ([width for _, width in links] != ['746w', '1782w'] or image.attrs.get('src') != links[0][0]
            or not all(url.startswith(POLICY['asset_origin'] + '/image/upload/')
                       and url.rsplit('/', 1)[1] == POLICY['approved_asset_url'].rsplit('/', 1)[1] for url, _ in links)):
        raise ValueError('Expected two publisher links to the exact GLB photo')
    return {url: int(width[:-1]) for url, width in links}


def check_frames(original, assets, links):
    if digest(original) != POLICY['approved_source_sha256']:
        raise ValueError('Original hash changed')
    with Image.open(io.BytesIO(original), formats=['JPEG']) as image:
        if image.size != (5000, 3333) or image.getexif().get(274, 1) != 1:
            raise ValueError('Original geometry changed')
        reference = image.convert('RGB').resize((150, 100), Image.Resampling.LANCZOS)
    result = []
    for url, expected_width in links.items():
        raw = assets[url]
        with Image.open(io.BytesIO(raw), formats=['WEBP']) as image:
            width, height = image.size
            if width != expected_width or abs(height - round(width * 3333 / 5000)) > 1 or image.n_frames != 1:
                raise ValueError('Publisher size does not preserve original proportions')
            projected = image.convert('RGB').resize((150, 100), Image.Resampling.LANCZOS)
        diff = ImageChops.difference(reference, projected)
        error = max(max(ImageStat.Stat(diff.crop((x, y, x + 75, y + 50))).mean) for x in (0, 75) for y in (0, 50))
        if error >= 2:
            raise ValueError('Publisher image frame no longer matches the full original')
        result.append(dict(source_url=url, width=width, height=height, sha256=digest(raw),
                           file=f'{STEM}-{width}.webp', bytes=len(raw), max_quadrant_mean_delta=round(error, 3)))
    if POLICY.get('publisher_responsive_variants'):
        keys = ('source_url', 'width', 'height', 'sha256')
        if [{k: item[k] for k in keys} for item in result] != POLICY['publisher_responsive_variants']:
            raise ValueError('Reviewed publisher web bytes changed')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    args = parser.parse_args()
    root = ROOT.resolve() / 'data/local/release-data'
    if root != root.resolve(strict=True) or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', x, re.I) for x in root.parts):
        raise ValueError('Require the private local release root')

    def read(path, limit=LIMIT):
        if path != path.resolve(strict=True) or not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise ValueError('Invalid private image evidence')
        return path.read_bytes()

    original = read(root / 'mercedes-glb-press-2026-11-21-pinned' / (STEM + '.jpg'), 12_000_000)
    if args.replay:
        out = args.replay.absolute()
        if out.parent != root or out.resolve(strict=True) != out or not re.fullmatch(PREFIX + r'[0-9a-z_]+', out.name):
            raise ValueError('Require exact GLB press evidence directory')
        saved = json.loads(read(out / 'report.json', 30_000))
        page = read(out / 'image-page.html')
        links = advertised(page)
        fetched_at = saved['fetched_at']
        assets = {url: read(out / f'{STEM}-{width}.webp') for url, width in links.items()}
    else:
        allowed = {PAGE}
        fetcher = SourceFetcher(timeout=20, max_bytes=LIMIT, document_parser=lambda body, _: body,
                                text_parser=lambda *_: '', url_policy=lambda url, _: url in allowed)

        def fetch(url, kind):
            response = fetcher.fetch(url, {'Mercedes-Benz'})
            if (response.get('status'), response.get('http_status'), response.get('final_url'),
                    response.get('content_type', '').split(';')[0]) != ('reachable', 200, url, kind):
                raise ValueError(f'GLB media source not verified: {response["status"]}')
            return response['document']

        page = fetch(PAGE, 'text/html')
        links = advertised(page)
        allowed.update(links)
        assets = {url: fetch(url, 'image/webp') for url in links}
        fetched_at = datetime.now(timezone.utc).isoformat()
    result = dict(status='glb_publisher_sizes_private_review', publisher=PUBLISHER, original_sha256=digest(original),
                  fetched_at=fetched_at, page_sha256=digest(page), variants=check_frames(original, assets, links),
                  publication_approved=False)
    if args.replay:
        if result != saved:
            raise ValueError('Publisher web evidence changed')
    else:
        out = Path(mkdtemp(prefix=PREFIX, dir=root))
        (out / 'image-page.html').write_bytes(page)
        for variant in result['variants']:
            (out / variant['file']).write_bytes(assets[variant['source_url']])
        (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({**result, 'output': str(out)}))


if __name__ == '__main__':
    main()
