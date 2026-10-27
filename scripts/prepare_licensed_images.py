"""Adopt an explicitly reviewed, hash-bound photo manifest. Offline and dry-run by default."""
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from audit_image_rights import LICENSES, rights_errors
from verify_public_images import normalize_image_key, public_records
from discover_licensed_images import canonical_license

ROOT = Path(__file__).resolve().parents[1]


def prepare(manifest_path, reviewed_hash, catalog_path, today=None):
    manifest_path = Path(manifest_path)
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reviewed_hash:
        raise ValueError('reviewed_manifest_changed')
    today = today or datetime.now(timezone.utc).date()
    rows = json.loads(raw)['models']
    expected = {normalize_image_key(r['brand']) + '|' + normalize_image_key(r['model'])
                for r in public_records(catalog_path)}
    assets, lookup, copies = [], {}, []
    for row in rows:
        key = row['model_key']
        if key not in expected or key in lookup:
            raise ValueError('unexpected_or_duplicate_model')
        if not row.get('license_eligible') or row.get('restrictions'):
            raise ValueError('image_requires_additional_rights_review')
        license_url = canonical_license(row.get('license_id'), row.get('license_url'))
        if not license_url:
            raise ValueError('license_uri_mismatch')
        source = urlsplit(row['source_url'])
        proof = urlsplit(row['evidence_url'])
        proof_query = parse_qs(proof.query)
        if (source.scheme != 'https' or source.hostname != 'commons.wikimedia.org'
                or not source.path.startswith('/wiki/File:') or source.username or source.password
                or proof.scheme != 'https' or proof.hostname != source.hostname
                or proof.path != '/w/index.php' or proof.username or proof.password
                or proof_query.get('title') != [row['title']]
                or proof_query.get('oldid') != [str(row['revision'])]):
            raise ValueError('revision_bound_commons_evidence_required')
        filename = row['review_filename']
        if not re.fullmatch(r'[a-z0-9-]+-[a-f0-9]{12}\.jpg', filename):
            raise ValueError('unsafe_review_filename')
        file = manifest_path.parent / 'review' / filename
        if file.is_symlink() or not file.is_file():
            raise ValueError('review_file_missing')
        content = file.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != row['content_sha256'] or not content.startswith(b'\xff\xd8\xff'):
            raise ValueError('reviewed_image_bytes_changed')
        url = '/media/vehicles/' + filename
        evidence = dict(model_key=key, asset_url=url, source_url=row['source_url'],
            evidence_url=row['evidence_url'], evidence_quote=row['license_statement'],
            license_id=row['license_id'], license_url=license_url, author=row['author'],
            credit=row['title'].removeprefix('File:') + ' — ' + row['author'] + ' / Wikimedia Commons',
            changes='Wikimedias förminskade bild. Bilden beskärs för visning; filen är oförändrad.',
            reviewed_at=today.isoformat(), status='documented', content_sha256=digest,
            original_url=row['original_url'], downloaded_from=row['asset_url'],
            model_image_notice='Modellbild. Utrustning och årsmodell kan skilja.',
            reviewed_manifest_sha256=reviewed_hash)
        if rights_errors({'model_key': key, 'asset_url': url}, evidence, today):
            raise ValueError('incomplete_image_evidence')
        assets.append(evidence)
        lookup[key] = url
        copies.append((file, filename))
    if set(lookup) != expected:
        raise ValueError('incomplete_model_coverage')
    return {'schema_version': 1, 'assets': assets}, lookup, copies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--reviewed-manifest-sha256', required=True)
    parser.add_argument('--apply', action='store_true', help='Copy reviewed photos and regenerate rights/lookup data, never the database')
    args = parser.parse_args()
    registry, lookup, copies = prepare(args.manifest, args.reviewed_manifest_sha256,
                                      ROOT / 'public/data/public_ev_variants.json')
    if args.apply:
        folder = ROOT / 'public/media/vehicles'
        folder.mkdir(parents=True, exist_ok=True)
        for source, filename in copies:
            shutil.copyfile(source, folder / filename)
        for name, payload in [('image-rights.json', registry), ('model-images.json', lookup)]:
            (ROOT / 'src' / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'reviewed_models': len(lookup), 'generated_files': len(copies) + 2 if args.apply else 0,
                      'database_writes': 0, 'paid_calls': 0, 'applied': args.apply}))


if __name__ == '__main__':
    main()
