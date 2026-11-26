"""Freeze the exact maker-supplied web sizes on the local home-only candidate."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from audit_image_rights import ROOT, PRESS_PUBLISHERS, validate_home_publisher_web

def prepare(manifest, expected_sha, root=ROOT):
    root=Path(root)
    manifest=Path(manifest)
    raw=manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha:
        raise ValueError('publisher_web_manifest_changed')
    proof=json.loads(raw)
    if sorted(row['model_key'] for row in proof['records'])!=['bmw|i4','ford|explorer']:
        raise ValueError('home_featured_exact_pair_required')
    registry=json.loads((root/'src/home-featured-photos.json').read_text(encoding='utf8'))
    artifacts=[]
    for row in registry['assets']:
        policy=PRESS_PUBLISHERS[row['publisher_id']]
        pin=policy['publisher_web_display']
        name=Path(row['asset_url']).stem+'-1782.webp'
        source=manifest.parent/name
        if source.is_symlink():
            raise ValueError('home_featured_publisher_web_mismatch')
        row['publisher_display']={**pin,'url':'/media/responsive/'+name,'evidence_sha256':expected_sha}
        row['changes']='Tillverkarens egen webbstorlek visas i helbild. Ingen lokal beskärning, omkodning eller retusch.'
        validate_home_publisher_web(row,policy,proof,expected_sha,source.read_bytes())
        artifacts.append((source,row['publisher_display']['url']))
    if len(artifacts)!=2:
        raise ValueError('home_featured_exact_pair_required')
    return registry,artifacts

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--apply-local',action='store_true')
    args=parser.parse_args()
    registry,artifacts=prepare(args.manifest,args.sha256)
    if args.apply_local:
        for source,url in artifacts:
            target=ROOT/'public'/url.lstrip('/')
            if target.is_symlink() or (target.exists() and target.read_bytes()!=source.read_bytes()):
                raise ValueError('home_featured_publisher_web_mismatch')
        for source,url in artifacts:
            target=ROOT/'public'/url.lstrip('/')
            shutil.copyfile(source,target)
        (ROOT/'src/home-featured-photos.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        (ROOT/'data/review/home-featured-publisher-web-evidence.json').write_bytes(args.manifest.read_bytes())
    print(json.dumps({'local_candidate_prepared':args.apply_local,'assets':[url for _,url in artifacts],
                    'approval_asserted':False,'local_reencoding':False,'database_writes':0}))

if __name__=='__main__':
    main()
