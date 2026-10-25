"""Recheck notice drafts; dry-run by default. Never invokes AI or exports public files."""
import argparse
import json
import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from news_notice_release import publication_config, review_notice_release
from news_notices import NOTICE_RECIPE, NOTICE_REVIEW
from news_store import NewsStore


def publish_notices(store, models, publish=False, max_items=3, article_ids=None, now=None):
    now = now or datetime.now(timezone.utc)
    config = publication_config(store)
    enabled = (config['enabled'] is True and config['publication_enabled'] is True
               and config['policy']==NOTICE_RECIPE and config['review_method']==NOTICE_REVIEW
               and type(config['daily_limit']) is int and 0 < config['daily_limit'] <= 5)
    rows = sorted(store.rows('news_articles'),key=lambda r:r['id'])
    reports = []
    for article in rows:
        if article_ids and article['id'] not in article_ids:
            continue
        if article['payload'].get('editorial_recipe')!=NOTICE_RECIPE or article['status']=='published':
            continue
        if len(reports)>=max(0,min(max_items,20)):
            break
        review = review_notice_release(store,article,models,now)
        row = {'article_id':article['id'], 'eligible':review['passed'], 'errors':review['errors'],
               'status':'ready' if review['passed'] else 'blocked_validation'}
        if review['passed']:
            row['would_publish'] = enabled
            if publish and enabled:
                try:
                    result = store.publish_notice(article['id'],article['artifact_hash'],article['payload'],
                                                  review['snapshot'],models=models,now=now)
                    row.update(status='published' if result['published'] else 'blocked_commit')
                except (ValueError, RuntimeError) as exc:
                    row.update(status='blocked_commit',errors=[str(exc)[:200]])
            elif publish:
                row['status']='blocked_disabled'
        reports.append(row)
    return {'dry_run':not publish, 'release_enabled':enabled, 'articles':reports,
            'published':sum(r['status']=='published' for r in reports),
            'provider_requests':0, 'cost_usd':0, 'public_export_written':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=['sqlite','supabase'],default=os.environ.get('NEWS_BACKEND','sqlite'))
    parser.add_argument('--db',type=Path)
    parser.add_argument('--publish',action='store_true',help='Requires separate owner-enabled release flags')
    parser.add_argument('--max-items',type=int,default=3)
    parser.add_argument('--article-id',action='append')
    args=parser.parse_args()
    if args.backend=='supabase':
        from supabase_client import load_local_env
        load_local_env()
    from news_engine import models_for_news
    with closing(NewsStore(args.db,args.backend)) as store:
        result=publish_notices(store,models_for_news(store),publish=args.publish,max_items=args.max_items,article_ids=args.article_id)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    main()
