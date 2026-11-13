"""Collect an identified manufacturer press photo, with literal per-image media-use evidence."""
import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image, ImageOps
from audit_catalog_sources import ROOT, SourceFetcher
from variant_refresh import parse_document, one

PUBLISHERS = json.loads((ROOT / 'src/press-image-publishers.json').read_text(encoding='utf-8'))


def collect(publisher, model_key, url, output):
    policy = PUBLISHERS[publisher]
    parsed = urlsplit(url)
    if (model_key not in policy['model_keys'] or parsed.scheme + '://' + parsed.netloc != policy['origin']
            or not re.fullmatch(r'/images/[a-z0-9-]+-[0-9]+', parsed.path) or parsed.query or parsed.fragment):
        raise ValueError('unapproved_exact_pressroom_image_page')
    if policy.get('approved_image_paths') and parsed.path not in policy['approved_image_paths']:
        raise ValueError('unapproved_exact_model_photo')
    fetcher = SourceFetcher(document_parser=lambda body, _kind: body,
        url_policy=lambda target, _brands: target == url)
    response = fetcher.fetch(url, set())
    if response.get('status') != 'reachable' or response['final_url'] != url:
        raise ValueError('pressroom_page_' + response.get('status', 'unknown'))
    body = response['document']
    document = parse_document(body, 'text/html')
    text = document.text()
    for excerpt in (policy['permission_excerpt'], policy['condition_excerpt'], policy['license_label']):
        if excerpt not in text:
            raise ValueError('per_image_media_permission_not_found')
    heading = one(document.nodes('h1'), 'unique_image_title_required').text()
    model = model_key.split('|')[1]
    pattern = policy.get('model_title_pattern', r'(?<![a-z0-9])' + re.escape(model) + r'(?![a-z0-9])')
    if not re.search(pattern, heading, re.I):
        raise ValueError('exact_model_image_title_required')
    if model_key == 'skoda|enyaq' and re.search(r'coup|coupe', heading, re.I):
        raise ValueError('enyaq_coupe_is_a_different_body')
    links = [node.attrs.get('href') for node in document.nodes('a')
             if node.text() == policy['download_label'] and node.attrs.get('href', '').startswith(policy['asset_origin'] + '/')]
    asset_url = one(set(links), 'one_published_original_download_required')
    robot = SourceFetcher()
    if not robot.robots_allowed(asset_url):
        raise ValueError('press_asset_robots_unavailable_or_denied')
    with urlopen(Request(asset_url, headers={'User-Agent': 'Elbilsagenten/1.0 (kontakt@boleoai.se)'}), timeout=30) as asset:
        if urlsplit(asset.geturl()).netloc != urlsplit(policy['asset_origin']).netloc or asset.headers.get('tdm-reservation') == '1':
            raise ValueError('unexpected_image_redirect_or_reservation')
        original = asset.read(12000001)
    if len(original) > 12000000:
        raise ValueError('press_photo_too_large')
    with Image.open(io.BytesIO(original)) as opened:
        image = ImageOps.exif_transpose(opened).convert('RGB')
        original_width, original_height = image.size
        if original_width < 1500 or original_height < 700:
            raise ValueError('professional_resolution_required')
        # Mechanical web optimization only: preserve the entire photographic frame.
        image.thumbnail((1500, 1500), Image.Resampling.LANCZOS)
        encoded = io.BytesIO()
        image.save(encoded, 'JPEG', quality=90, optimize=True)
        width, height = image.size
    content = encoded.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    filename = model_key.replace('|', '-') + '-press-' + digest[:12] + '.jpg'
    output.mkdir(parents=True, exist_ok=True)
    (output / filename).write_bytes(content)
    (output / (response['content_hash'] + '.html')).write_bytes(body)
    record = dict(model_key=model_key, title=heading, source_url=url, evidence_url=url, license_url=url,
        license_id=policy['license_id'], evidence_quote=policy['permission_excerpt'] + ' | ' + policy['condition_excerpt'],
        publisher_id=publisher, asset_url=asset_url, original_url=asset_url,
        author=policy['publisher'], credit=policy['publisher'] + ' / pressbild',
        content_sha256=digest, source_content_sha256=hashlib.sha256(original).hexdigest(),
        metadata_sha256=response['content_hash'], review_filename=filename, width=width, height=height,
        original_width=original_width, original_height=original_height,
        full_frame=True, collected_at=datetime.now(timezone.utc).isoformat(), status='candidate_not_reviewed')
    path = output / (model + '-mynewsdesk-' + parsed.path.rsplit('-', 1)[1] + '.json')
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {key: record[key] for key in ('title', 'review_filename', 'width', 'height', 'status')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publisher', choices=sorted(PUBLISHERS), required=True)
    parser.add_argument('--model-key', required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/local/release-data/vehicle-quality-2026-11-12/photos')
    args = parser.parse_args()
    print(json.dumps(collect(args.publisher, args.model_key, args.url, args.output)))


if __name__ == '__main__':
    main()
