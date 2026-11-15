"""Capture one explicitly permitted C-HR+ production press photo for review."""
import argparse
import hashlib
import io
import json
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from PIL import Image
from audit_catalog_sources import SourceFetcher
from variant_refresh import one,parse_document

SOURCE='https://media.toyota.co.uk/images/c-hr-design-exterior-static-2026-current/'
ASSET='https://media.toyota.co.uk/wp-content/uploads/sites/5/2026/03/2026_ToyotaCHR_Statics_014-scaled.jpg'
NOTICE='Images are copyright free for editorial purposes only'
TITLE='C-HR+ Design Exterior Static (2026 – Current)'


def collect(output):
    fetcher=SourceFetcher(timeout=30,document_parser=lambda body,kind:body,
        url_policy=lambda url,brands:url==SOURCE and brands=={'Toyota'})
    response=fetcher.fetch(SOURCE,{'Toyota'})
    if response['status']!='reachable' or response['final_url']!=SOURCE:
        raise ValueError('official_photo_source_unavailable')
    document=parse_document(response['document'],'text/html')
    if one(document.nodes('h1'),'one_gallery_title_required').text()!=TITLE or NOTICE not in document.text():
        raise ValueError('production_plus_model_and_permission_required')
    link=one((a for a in document.nodes('a') if a.attrs.get('href')==ASSET),'declared_photo_required')
    if link.attrs.get('title')!='2026_ToyotaCHR+_Statics_014' or not fetcher.robots_allowed(ASSET):
        raise ValueError('exact_plus_photo_or_access_failed')
    with urlopen(Request(ASSET,headers={'User-Agent':'Elbilsagenten/1.0 (kontakt@boleoai.se)'}),timeout=30) as r:
        if r.status!=200 or r.geturl()!=ASSET or r.headers.get('tdm-reservation')=='1':
            raise ValueError('photo_redirect_or_reservation')
        body=r.read(12000001)
    if len(body)>12000000:raise ValueError('photo_size_limit')
    with Image.open(io.BytesIO(body)) as photo:
        width,height=photo.size
        if photo.format!='JPEG' or width<1920 or height<1000:
            raise ValueError('professional_resolution_required')
        photo=photo.convert('RGB')
        photo.thumbnail((1500,1500))
        web=io.BytesIO();photo.save(web,format='JPEG',quality=90,optimize=True)
    content=web.getvalue();sha=hashlib.sha256(content).hexdigest()
    filename='toyota-c-hr-press-'+sha[:12]+'.jpg'
    output.mkdir(parents=True,exist_ok=True)
    (output/filename).write_bytes(content)
    (output/'source-original.jpg').write_bytes(body)
    (output/'toyota-gallery.html').write_bytes(response['document'])
    candidate=dict(model_key='toyota|c hr',source_url=SOURCE,title=TITLE,asset_url=ASSET,original_url=ASSET,
        evidence_url=SOURCE,evidence_quote=NOTICE,license_id='Toyota-editorial',license_url=SOURCE,
        author='Toyota (GB) PLC',credit='Toyota / Toyota Media',publisher_id='toyota-chr-plus-media',full_frame=True,
        content_sha256=sha,metadata_sha256=response['content_hash'],source_content_sha256=response['content_hash'],
        original_content_sha256=hashlib.sha256(body).hexdigest(),review_filename=filename,width=width,height=height,
        status='candidate_not_reviewed',collected_at=datetime.now(timezone.utc).isoformat())
    raw=(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n').encode()
    (output/'toyota-candidate.json').write_bytes(raw)
    print(json.dumps(dict(filename=filename,candidate_sha256=hashlib.sha256(raw).hexdigest(),width=width,height=height,status=candidate['status'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output)
