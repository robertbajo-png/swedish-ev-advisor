"""Freeze ONE separately reviewed factual notice for an explicit owner release."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import tempfile

from news_factual_notices import RECIPE,REVIEW,review_factual_notice,stage_factual_notices
from news_store import NewsStore

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'data/local'
TABLES=('news_sources','news_story_clusters','news_items','news_articles','news_article_sources','news_quality_checks')


def make_manifest(prepared, *, now=None, fixture=False):
    now=now or datetime.now(timezone.utc)
    review=review_factual_notice(prepared,now)
    if not review['passed'] or prepared['article']['notice_facts']['fact']['type']!='swedish_list_price':
        raise ValueError('single_notice_requires_exact_passed_price_review')
    PRIVATE.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=PRIVATE) as folder,closing(NewsStore(Path(folder)/'notice.sqlite')) as store:
        result=stage_factual_notices(store,[prepared],now)
        if len(result)!=1 or result[0]['status']!='draft' or store.public_articles():
            raise ValueError('single_notice_private_staging_failed')
        rows={table:store.rows(table) for table in TABLES}
    return {'recipe':RECIPE,'review_method':REVIEW,'fixture':fixture,'prepared_at':now.isoformat(),
            'review':review,'article_id':result[0]['article_id'],'tables':rows,
            'provider_requests':0,'publications':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(PRIVATE.resolve()):
        raise ValueError('release_manifest_must_remain_private')
    if args.output.exists():raise FileExistsError('release_manifest_already_exists')
    prepared=json.loads(args.prepared.read_text(encoding='utf-8'))
    manifest=make_manifest(prepared)
    raw=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(raw)
    print(json.dumps({'article_id':manifest['article_id'],'title':prepared['article']['title'],
        'file_sha256':hashlib.sha256(raw).hexdigest(),'review_passed':True,'provider_requests':0,'publications':0}))
