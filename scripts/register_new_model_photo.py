"""Register a reviewed new-model press photo locally, never publish a car."""
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from audit_image_rights import ROOT, rights_errors, normalize_image_key


def prepare(candidate_path, reviewed_hash, root=ROOT):
    path = Path(candidate_path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reviewed_hash:
        raise ValueError('reviewed_candidate_changed')
    c = json.loads(raw)
    name = c['review_filename']
    if not re.fullmatch(r'[a-z0-9-]+-press-[a-f0-9]{12}\.jpg', name) or not name.startswith(c['model_key'].replace('|', '-').replace(' ', '-')+'-press-'):
        raise ValueError('exact_new_model_filename_required')
    source = path.parent/name
    if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != c['content_sha256']:
        raise ValueError('reviewed_photo_changed')
    evidence = {n: c[n] for n in ('model_key','source_url','evidence_url','evidence_quote','license_id','license_url',
        'author','credit','content_sha256','metadata_sha256','source_content_sha256','publisher_id','full_frame')}
    evidence.update(asset_url='/media/vehicles/'+name, downloaded_from=c['asset_url'], original_url=c['original_url'],
        status='documented', reviewed_at=datetime.now(timezone.utc).date().isoformat(), usage_scope='independent_vehicle_editorial',
        prohibited_uses=['advertising','commercial_promotion','endorsement'],
        changes='Hela bildutsnittet bevaras. Endast storlek och filformat har anpassats; ingen retusch.',
        model_image_notice='Pressbild. Utrustning kan skilja mellan versioner.', reviewed_candidate_sha256=reviewed_hash)
    if c.get('original_content_sha256'):
        if not re.fullmatch('[a-f0-9]{64}',c['original_content_sha256']):
            raise ValueError('original_photo_hash_required')
        evidence['original_content_sha256']=c['original_content_sha256']
    if rights_errors(evidence, evidence):
        raise ValueError('new_model_media_permission_required')
    registry = json.loads((root/'src/image-rights.json').read_text(encoding='utf8'))
    lookup = json.loads((root/'src/model-images.json').read_text(encoding='utf8'))
    existing = [r for r in registry['assets'] if r['model_key'] == c['model_key']]
    if existing or c['model_key'] in lookup:
        raise ValueError('existing_image_requires_separate_refresh')
    public = json.loads((root/'public/data/public_ev_variants.json').read_text(encoding='utf8'))['records']
    if any(normalize_image_key(r['brand'])+'|'+normalize_image_key(r['model']) == c['model_key'] for r in public):
        raise ValueError('existing_public_model_requires_separate_refresh')
    registry['assets'] = sorted(registry['assets']+[evidence], key=lambda r: r['model_key'])
    lookup[c['model_key']] = evidence['asset_url']
    return source, evidence, registry, lookup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--reviewed-sha256', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    source, evidence, registry, lookup = prepare(args.candidate, args.reviewed_sha256)
    if args.apply:
        shutil.copyfile(source, ROOT/'public'/evidence['asset_url'].lstrip('/'))
        for name, value in [('image-rights.json',registry),('model-images.json',lookup)]:
            (ROOT/'src'/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        path = ROOT/'src/image-presentation.json'
        presentation = json.loads(path.read_text(encoding='utf8'))
        presentation['models'][evidence['model_key']] = dict(asset_url=evidence['asset_url'],
            content_sha256=evidence['content_sha256'], status='approved', reviewed_at=evidence['reviewed_at'],
            object_position='50% 50%', object_fit='contain', style='manufacturer_press_photo')
        path.write_text(json.dumps(presentation, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(dict(model=evidence['model_key'], applied=args.apply, database_writes=0, paid_calls=0)))


if __name__ == '__main__':
    main()
