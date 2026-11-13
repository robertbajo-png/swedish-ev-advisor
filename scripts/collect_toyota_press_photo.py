"""Capture a current European bZ4X press photo for exact-model visual review."""
import argparse
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from PIL import Image

from audit_catalog_sources import SourceFetcher
from variant_refresh import one, parse_document

SOURCE = 'https://media.toyota.co.uk/images/bz4x-fwd-exterior-static-european-spec-2025/'
ASSET = 'https://media.toyota.co.uk/wp-content/uploads/sites/5/2025/12/2026_bZ4X-FWD_Deep-Blue-Metallic_Static_001-scaled.jpg'
NOTICE = 'Images are copyright free for editorial purposes only'


def collect(output):
    fetcher = SourceFetcher(document_parser=lambda body, _kind: body, url_policy=lambda url, brands: url == SOURCE and brands == {'Toyota'})
    response = fetcher.fetch(SOURCE, {'Toyota'})
    if response.get('status') != 'reachable' or response['final_url'] != SOURCE:
        raise ValueError('official_editorial_source_unavailable')
    document = parse_document(response['document'], 'text/html')
    title = one(document.nodes('h1'), 'exact_photo_gallery_required').text()
    if title != 'bZ4X FWD Exterior Static, European Spec (2025)' or NOTICE not in document.text():
        raise ValueError('current_facelift_or_editorial_permission_missing')
    link = one((a for a in document.nodes('a') if a.attrs.get('href') == ASSET), 'declared_full_frame_asset_required')
    if '2026_bZ4X FWD' not in link.attrs.get('title', '') or not fetcher.robots_allowed(ASSET):
        raise ValueError('photo_identity_or_access_failed')
    with urlopen(Request(ASSET, headers={'User-Agent': 'Elbilsagenten/1.0 (kontakt@boleoai.se)'}), timeout=30) as result:
        if result.geturl() != ASSET or result.headers.get('tdm-reservation') == '1':
            raise ValueError('asset_redirect_or_reservation')
        body = result.read(12000001)
    if len(body) > 12000000:
        raise ValueError('photo_too_large')
    with Image.open(io.BytesIO(body)) as image:
        width, height = image.size
        if image.format != 'JPEG' or width < 1920 or height < 1000:
            raise ValueError('professional_photo_resolution_required')
    digest = hashlib.sha256(body).hexdigest()
    filename = 'toyota-bz4x-press-' + digest[:12] + '.jpg'
    output.mkdir(parents=True, exist_ok=True)
    (output / filename).write_bytes(body)
    (output / 'toyota-gallery.html').write_bytes(response['document'])
    candidate = dict(model_key='toyota|bz4x', source_url=SOURCE, title=title, asset_url=ASSET, original_url=ASSET,
        evidence_url=SOURCE, evidence_quote=NOTICE, license_id='Toyota-editorial', license_url=SOURCE,
        author='Toyota (GB) PLC', credit='Toyota / Toyota Media', full_frame=True,
        content_sha256=digest, metadata_sha256=response['content_hash'], source_content_sha256=response['content_hash'],
        review_filename=filename, width=width, height=height, status='candidate_not_reviewed',
        collected_at=datetime.now(timezone.utc).isoformat())
    (output / 'toyota-candidate.json').write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: candidate[k] for k in ('review_filename','width','height','status')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    collect(parser.parse_args().output)
