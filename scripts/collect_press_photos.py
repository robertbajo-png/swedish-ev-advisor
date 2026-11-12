"""Download identified public pressroom photos for visual review, never auto-approve them."""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image
from audit_catalog_sources import ROOT, SourceFetcher

ORIGIN = 'https://media.polestar.com'
NOTICE = 'Content found in the Polestar media newsroom is intended for editorial use only and may not be used for any advertising or commercial purposes.'


def fetch(url, limit, robots):
    if not url.startswith(ORIGIN + '/') or not robots.robots_allowed(url):
        raise ValueError('pressroom_source_not_allowed')
    if '/api/' in url and os.name == 'nt':
        # This public endpoint returns its SPA shell to urllib on Windows. Use
        # the system HTTP client, which negotiates the actual public JSON route.
        if not re.fullmatch(re.escape(ORIGIN) + r'/api/gallery/[0-9]+\?lang=ww_WW', url):
            raise ValueError('unexpected_metadata_endpoint')
        command = "(Invoke-WebRequest -Uri $env:EV_PRESS_METADATA_URL -Headers @{Accept='application/json'} -ErrorAction Stop).Content"
        result = subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-Command', command],
            env={**os.environ, 'EV_PRESS_METADATA_URL': url}, capture_output=True, timeout=35)
        if result.returncode or len(result.stdout) > limit:
            raise ValueError('public_metadata_unavailable')
        json.loads(result.stdout.decode('utf-8-sig'))
        return result.stdout.decode('utf-8-sig').encode('utf-8')
    headers = {'User-Agent': 'Elbilsagenten/1.0 (kontakt@boleoai.se)',
               'Accept': 'application/json' if '/api/' in url else 'image/jpeg'}
    if '/api/' in url:
        headers['Content-Type'] = 'application/json'
    with urlopen(Request(url, headers=headers), timeout=25) as response:
        if response.geturl() != url or response.headers.get('tdm-reservation') == '1':
            raise ValueError('unexpected_pressroom_redirect_or_reservation')
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError('pressroom_file_too_large')
        return body


def collect(model, media_id, output, robots, size='small'):
    metadata_bytes = fetch(ORIGIN + '/api/gallery/' + str(media_id) + '?lang=ww_WW', 1000000, robots)
    item = json.loads(metadata_bytes)['data']
    if item['id'] != media_id or item['type'] != 'Image' or not re.match(r'^Polestar ' + re.escape(model) + r'(?:$| in | coupé$| MY26$)', item['title']):
        raise ValueError('exact_single_model_required')
    original_path = item['url']
    path = original_path
    if size == 'small':
        if 'small' not in [row['crop_size'] for row in item['options']['variants']]:
            raise ValueError('declared_web_image_missing')
        path = item['s3_url'].replace('{{variant}}', 'small')
    if not re.fullmatch(r'/assets/images/(?:original|small)/' + str(media_id) + r'-[a-zA-Z0-9._-]+\.jpe?g', path):
        raise ValueError('published_original_asset_required')
    body = fetch(ORIGIN + path, 12000000, robots)
    digest = hashlib.sha256(body).hexdigest()
    with Image.open(io.BytesIO(body)) as image:
        width, height = image.size
        if image.format != 'JPEG' or width < 1280 or height < 700:
            raise ValueError('professional_resolution_required')
    filename = 'polestar-' + model + '-press-' + digest[:12] + '.jpg'
    output.mkdir(parents=True, exist_ok=True)
    (output / filename).write_bytes(body)
    result = dict(model_key='polestar|' + model, source_url=ORIGIN + '/gallery/images/' + str(media_id),
        media_id=media_id, title=item['title'], asset_url=ORIGIN + path, original_url=ORIGIN + original_path,
        evidence_url=ORIGIN + '/copyright', evidence_quote=NOTICE,
        license_id='Polestar-editorial', license_url=ORIGIN + '/copyright',
        author='Polestar', credit='Polestar / Polestar Press',
        content_sha256=digest, review_filename=filename, width=width, height=height,
        metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(),
        published_at=item['published'], collected_at=datetime.now(timezone.utc).isoformat(),
        status='candidate_not_reviewed')
    (output / (str(media_id) + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {key: result[key] for key in ('media_id', 'title', 'review_filename', 'width', 'height', 'status')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=('2', '4'), required=True)
    parser.add_argument('--id', type=int, action='append', required=True)
    parser.add_argument('--size', choices=('small', 'original'), default='small')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/local/release-data/vehicle-quality-2026-11-12/photos')
    args = parser.parse_args()
    if not 1 <= len(args.id) <= 10:
        raise ValueError('bounded_photo_review_required')
    robots = SourceFetcher()
    for media_id in args.id:
        print(json.dumps(collect(args.model, media_id, args.output, robots, args.size)), flush=True)


if __name__ == '__main__':
    main()
