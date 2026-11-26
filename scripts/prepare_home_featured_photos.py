"""Prepare exactly the two reviewed-source home editorial photographs locally.

This is a proposed code/data artifact, not an approval, canonical image sync,
production operation or legal opinion. The supplied manifest is the frozen
source evidence to inspect on the candidate branch.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from audit_image_rights import ROOT, PRESS_PUBLISHERS, rights_errors, image_lookup

def prepare(manifest, expected_sha, root=ROOT):
    manifest = Path(manifest)
    raw = manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('home_photo_source_manifest_changed')
    rows = json.loads(raw)
    if sorted(r['model_key'] for r in rows) != ['bmw|i4', 'ford|explorer']:
        raise ValueError('home_featured_exact_pair_required')
    result = []
    lookup = image_lookup(root)
    for row in rows:
        policy = PRESS_PUBLISHERS.get(row['publisher_id'], {})
        key = row['model_key']
        sha = row['content_sha256']
        if (policy.get('placement') != 'home_featured' or row.get('status') != 'candidate_not_independently_approved'
                or not re.fullmatch('[a-f0-9]{64}', sha)
                or row['review_filename'] != key.replace('|', '-') + '-press-' + sha[:12] + '.jpg'
                or row['title'] is None or not re.fullmatch(policy['model_title_pattern'], row['title'])
                or row['release_source_url'] != policy['official_link_evidence']
                or row['replaces_only_home_image'] != lookup.get(key)
                or row['replaces_only_home_image'] != policy['replaces_only_home_image']
                or [row['width'], row['height']] != policy['approved_original_dimensions']):
            raise ValueError('home_featured_exact_photo_scope_mismatch')
        original = manifest.parent / row['review_filename']
        content = original.read_bytes()
        if original.is_symlink() or hashlib.sha256(content).hexdigest() != sha or not content.startswith(b'\xff\xd8\xff'):
            raise ValueError('home_featured_original_bytes_changed')
        item = {k: row[k] for k in ('model_key','title','source_url','release_source_url','release_metadata_sha256','evidence_url','license_url','license_id','evidence_quote','publisher_id','author','credit','original_url','content_sha256','source_content_sha256','metadata_sha256','width','height','full_frame','usage_scope','photographer_evidence','replaces_only_home_image')}
        item.update(asset_url='/media/vehicles/'+original.name, downloaded_from=row['asset_url'], placement='home_featured',
                    status='documented', reviewed_at=datetime.fromisoformat(row['collected_at']).date().isoformat(),
                    source_manifest_sha256=expected_sha, changes='Originalfilen visas i helbild, utan beskärning eller retusch.',
                    model_image_notice='Pressbild. Utrustning kan skilja mellan versioner.',
                    prohibited_uses=['advertising','commercial_promotion','endorsement'])
        failures = rights_errors({'model_key':key,'asset_url':item['asset_url'],'surface':'home_featured'},item)
        if failures:
            raise ValueError('home_featured_rights_incomplete: '+','.join(failures))
        result.append((original,item))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--source-manifest-sha256',required=True)
    parser.add_argument('--apply-local',action='store_true')
    args=parser.parse_args()
    result=prepare(args.manifest,args.source_manifest_sha256)
    if args.apply_local:
        for path,item in result:
            target=ROOT/'public'/item['asset_url'].lstrip('/')
            if target.is_symlink() or (target.exists() and target.read_bytes()!=path.read_bytes()):
                raise ValueError('home_featured_asset_collision')
        for path,item in result:
            shutil.copyfile(path,ROOT/'public'/item['asset_url'].lstrip('/'))
        (ROOT/'src/home-featured-photos.json').write_text(json.dumps({'schema_version':1,'assets':[item for _,item in result]},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'source_manifest_sha256':args.source_manifest_sha256,'photos':[item['asset_url'] for _,item in result],'local_candidate_prepared':args.apply_local,'approval_asserted':False,'database_writes':0,'paid_calls':0}))

if __name__=='__main__':
    main()
