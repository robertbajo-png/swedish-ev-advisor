"""Adopt a visually reviewed exact-model press image; keep every other model unchanged."""
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from audit_image_rights import rights_errors
from verify_public_images import public_records, normalize_image_key

ROOT = Path(__file__).resolve().parents[1]


def prepare(path, reviewed_hash, root=ROOT):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != reviewed_hash:
        raise ValueError('reviewed_candidate_changed')
    candidate = json.loads(raw)
    expected_prefix = candidate.get('model_key', '').replace('|', '-').replace(' ', '-')
    if not re.fullmatch(r'(?:polestar-[24]|kia-ev[34569]|skoda-(?:elroq|enyaq)|toyota-bz4x|mazda-6e|renault-5|mercedes-benz-cla)-press-[a-f0-9]{12}\.jpg', candidate.get('review_filename', '')) or not candidate['review_filename'].startswith(expected_prefix + '-press-'):
        raise ValueError('unsafe_photo_filename')
    file = Path(path).parent / candidate['review_filename']
    content = file.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if file.is_symlink() or digest != candidate['content_sha256'] or not content.startswith(b'\xff\xd8\xff'):
        raise ValueError('reviewed_photo_changed')
    key = candidate['model_key']
    expected = {normalize_image_key(row['brand']) + '|' + normalize_image_key(row['model'])
                for row in public_records(root / 'public/data/public_ev_variants.json')}
    if key not in expected:
        raise ValueError('model_outside_public_scope')
    lookup = json.loads((root / 'src/model-images.json').read_text(encoding='utf-8'))
    registry = json.loads((root / 'src/image-rights.json').read_text(encoding='utf-8'))
    url = '/media/vehicles/' + file.name
    today = datetime.now(timezone.utc).date().isoformat()
    evidence = {name: candidate[name] for name in ('model_key', 'source_url', 'evidence_url', 'evidence_quote',
        'license_id', 'license_url', 'author', 'credit', 'content_sha256', 'metadata_sha256')}
    for name in ('publisher_id', 'full_frame', 'source_content_sha256'):
        if name in candidate:
            evidence[name] = candidate[name]
    evidence.update(asset_url=url, downloaded_from=candidate['asset_url'], original_url=candidate['original_url'],
        status='documented', reviewed_at=today, usage_scope='independent_vehicle_editorial',
        prohibited_uses=['advertising', 'commercial_promotion', 'endorsement'],
        changes='Originalfilen är oförändrad. Storlek och format anpassas för visning.',
        model_image_notice='Pressbild. Utrustning kan skilja mellan versioner.',
        reviewed_candidate_sha256=reviewed_hash)
    if candidate.get('full_frame'):
        evidence['changes'] = 'Hela bildutsnittet bevaras. Endast storlek och filformat har anpassats; ingen retusch.'
    if rights_errors({'model_key': key, 'asset_url': url}, evidence):
        raise ValueError('press_permission_evidence_incomplete')
    old = [row for row in registry['assets'] if row['model_key'] == key]
    if len(old) != 1:
        raise ValueError('unique_existing_model_image_required')
    registry['assets'] = sorted([row for row in registry['assets'] if row['model_key'] != key] + [evidence], key=lambda row: row['model_key'])
    lookup[key] = url
    return registry, lookup, file, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--reviewed-sha256', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    registry, lookup, source, evidence = prepare(args.candidate, args.reviewed_sha256)
    if args.apply:
        shutil.copyfile(source, ROOT / 'public' / evidence['asset_url'].lstrip('/'))
        for filename, data in [('image-rights.json', registry), ('model-images.json', lookup)]:
            (ROOT / 'src' / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path = ROOT / 'src/image-presentation.json'
        presentation = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema_version': 1, 'models': {}}
        presentation['models'][evidence['model_key']] = {'asset_url': evidence['asset_url'],
            'content_sha256': evidence['content_sha256'], 'status': 'approved', 'reviewed_at': evidence['reviewed_at'],
            'object_position': '50% 60%', 'object_fit': 'contain' if evidence.get('full_frame') else 'cover',
            'style': 'manufacturer_press_photo'}
        path.write_text(json.dumps(presentation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'model_key': evidence['model_key'], 'applied': args.apply, 'database_writes': 0, 'paid_calls': 0}))


if __name__ == '__main__':
    main()
