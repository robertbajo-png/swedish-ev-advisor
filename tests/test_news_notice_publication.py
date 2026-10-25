"""Disposable notice publication/export tests. No remote writes or provider calls."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from news_engine import export_public
from news_notice_pipeline import stage_notices
from news_notice_release import notice_snapshot, review_notice_release, single_release_sql
from news_notices import NOTICE_RECIPE, notice_slug
from news_store import NewsStore
from publish_news_notices import publish_notices, main
from test_news_notices import source, MODEL, PRICES, STAT_TEXT, VW, ACEA, NOW


@contextmanager
def staged(kind='model', now=NOW):
    with tempfile.TemporaryDirectory() as directory, closing(NewsStore(Path(directory)/'test.sqlite')) as store:
        cfg=ACEA if kind=='statistics' else VW
        item=source(STAT_TEXT if kind=='statistics' else MODEL+PRICES if kind=='price' else MODEL,cfg)
        item['payload'].update(published_at=now.isoformat(),fetched_at=now.isoformat())
        store.put('news_items',item)
        report=stage_notices(store,[cfg],{},now=now)[0]
        if report['status']!='validated_draft': raise AssertionError(report)
        yield store,store.get('news_articles',report['article_id']),Path(directory)


def sql_fixtures():
    result=[]
    for kind in ['model','price','statistics']:
        with staged(kind,datetime.now(timezone.utc)) as (store,article,_):
            review=review_notice_release(store,article,{},datetime.now(timezone.utc))
            if not review['passed']: raise AssertionError(review)
            result.append({'kind':kind,'article':article,'snapshot':review['snapshot']})
    return result


def enable(store,limit=2):
    store.db.execute('update news_notice_release_config set enabled=1,publication_enabled=1,daily_limit=?',(limit,))
    store.db.commit()


def commit(store,article,review,now=NOW):
    return store.publish_notice(article['id'],article['artifact_hash'],article['payload'],review['snapshot'],models={},now=now)


class NoticePublicationTests(unittest.TestCase):
    def test_single_owner_release_requires_exact_passed_draft_and_no_persistent_activation(self):
        with staged() as (store, article, _):
            review = review_notice_release(store, article, {}, NOW)
            sql = single_release_sql(article, review, 0)
            self.assertIn('result:=public.publish_news_notice(', sql)
            self.assertEqual(sql.count('result:=public.publish_news_notice('), 1)
            self.assertIn('publication_enabled=false', sql.split('result:=')[1])
            self.assertIn('set enabled=false', sql.split('result:=')[1])
            self.assertNotIn('news_ai_config set enabled=true', sql)
            for change in ({'passed': False}, {'errors': ['failed']}, {'artifact_hash': 'stale'}, {'snapshot': None}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    single_release_sql(article, {**review, **change}, 0)
            for count in (-1, True, 0.5):
                with self.subTest(count=count), self.assertRaises(ValueError):
                    single_release_sql(article, review, count)
            article['payload']['intro'] = "Source's $single_notice_release$ marker"
            escaped = single_release_sql(article, review, 0)
            self.assertIn('do $single_notice_release_x$', escaped)
            self.assertIn("Source''s $single_notice_release$ marker", escaped)

    def test_three_templates_pass_fresh_release_review_with_ascii_routes(self):
        for kind in ['model','price','statistics']:
            with self.subTest(kind=kind),staged(kind) as (store,article,_):
                review=review_notice_release(store,article,{},NOW)
                self.assertTrue(review['passed'],review)
                self.assertRegex(article['slug'],r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
                self.assertEqual(notice_slug(article['payload']['title'],article['id']),article['slug'])

    def test_dry_run_is_read_only_even_with_both_flags_enabled_and_key_present(self):
        with staged() as (store,_,_):
            enable(store)
            before=[r for r in store.db.iterdump()]
            with patch.dict('os.environ',{'OPENAI_API_KEY':'never-use'}),patch('news_ai.NewsAi.request',side_effect=AssertionError('no paid calls')):
                result=publish_notices(store,{},now=NOW)
            self.assertTrue(result['dry_run']); self.assertTrue(result['release_enabled'])
            self.assertTrue(result['articles'][0]['would_publish']); self.assertEqual(result['published'],0)
            self.assertEqual(before,list(store.db.iterdump()))

    def test_both_flags_must_be_explicitly_enabled(self):
        with staged() as (store,article,_):
            review=review_notice_release(store,article,{},NOW)
            for notice,master in [(0,0),(1,0),(0,1)]:
                store.db.execute('update news_notice_release_config set enabled=?,publication_enabled=?',(notice,master));store.db.commit()
                with self.subTest(notice=notice,master=master),self.assertRaisesRegex(ValueError,'publication_disabled'):
                    commit(store,article,review)
                self.assertEqual(store.public_articles(),[])
                self.assertEqual(store.db.execute('select count(*) from news_notice_publications').fetchone()[0],0)

    def test_published_notice_exports_without_private_evidence_and_is_idempotent(self):
        for kind in ['model','price','statistics']:
            with self.subTest(kind=kind),staged(kind) as (store,article,directory):
                enable(store);review=review_notice_release(store,article,{},NOW)
                self.assertFalse(commit(store,article,review)['already_published'])
                self.assertTrue(commit(store,article,review,now=NOW+timedelta(days=20))['already_published'])
                export_public(store,directory/'private-export.json')
                rows=json.loads((directory/'private-export.json').read_text(encoding='utf-8'))['records']
                self.assertEqual(len(rows),1); row=rows[0]
                self.assertEqual(row['editorial_method'],'Automatisk faktanotis med källkontroll')
                self.assertIsNone(row['image']); self.assertEqual(row['title'],article['payload']['title'])
                for key in ('notice_facts','source_hash','title_fact_ids','intro_fact_ids','fact_ids','checked_at','reviewed_artifact_hash'):
                    self.assertNotIn('"'+key+'"',json.dumps(rows))
                self.assertEqual(set(row['sources'][0]),{'url','publisher','title','published_at','kind'})
                with self.assertRaisesRegex(ValueError,'immutable'):
                    store.put('news_articles',{**article,'payload':{**article['payload'],'title':'Changed'}})

    def test_tampered_text_is_blocked_even_with_three_passed_old_checks(self):
        with staged() as (store,article,_):
            changed=store.put('news_articles',{**article,'payload':{**article['payload'],'intro':'Den bästa bilen kostar 100 kronor.'}})
            for q in store.rows('news_quality_checks'):
                store.put('news_quality_checks',{**q,'id':q['id']+'forged','artifact_hash':changed['artifact_hash']})
            self.assertFalse(review_notice_release(store,changed,{},NOW)['passed'])

    def test_wrong_models_attribution_or_missing_checks_block_release(self):
        for target in ['news_quality_checks','news_article_sources']:
            with self.subTest(target=target),staged() as (store,article,_):
                store.db.execute('delete from '+target);store.db.commit()
                self.assertFalse(review_notice_release(store,article,{},NOW)['passed'])
        with staged() as (store,article,_):
            changed=store.put('news_articles',{**article,'payload':{**article['payload'],'related_models':[{'brand':'Tesla','model':'Model Y'}]}})
            self.assertFalse(review_notice_release(store,changed,{},NOW)['passed'])

    def test_stale_blocked_redirected_or_changed_source_is_rejected(self):
        changes=[{'access_status':'blocked'},{'content_hash':'changed'},{'final_url':'https://www.vwgroup.se/other/'},
                 {'fetched_at':(NOW-timedelta(days=2)).isoformat()}]
        for change in changes:
            with self.subTest(change=change),staged() as (store,article,_):
                item=store.rows('news_items')[0]
                store.put('news_items',{**item,'payload':{**item['payload'],**change}})
                self.assertFalse(review_notice_release(store,article,{},NOW)['passed'])

    def test_changed_source_snapshot_rolls_back_with_no_publication_receipt(self):
        with staged() as (store,article,_):
            enable(store); review=review_notice_release(store,article,{},NOW)
            item=store.rows('news_items')[0]
            store.put('news_items',{**item,'payload':{**item['payload'],'fetched_at':(NOW+timedelta(seconds=1)).isoformat()}})
            with self.assertRaisesRegex(ValueError,'source_snapshot_changed'): commit(store,article,review)
            self.assertEqual(store.public_articles(),[])
            self.assertEqual(store.db.execute('select count(*) from news_notice_publications').fetchone()[0],0)

    def test_changed_article_or_review_snapshot_is_rejected(self):
        with staged() as (store,article,_):
            enable(store); review=review_notice_release(store,article,{},NOW)
            with self.assertRaisesRegex(ValueError,'article_snapshot_changed'):
                store.publish_notice(article['id'],'stale',article['payload'],review['snapshot'],now=NOW)
            q=store.rows('news_quality_checks')[0]
            store.put('news_quality_checks',{**q,'payload':{**q['payload'],'checked_at':(NOW+timedelta(seconds=1)).isoformat()}})
            with self.assertRaisesRegex(ValueError,'source_snapshot_changed'): commit(store,article,review)

    def test_failed_or_wrong_policy_checks_are_never_promoted(self):
        for change in [{'policy_version':'news-editorial-2026-10-v2'},{'audit_performed':True},
                       {'source_hash':'a'*64},{'checked_at':(NOW-timedelta(days=2)).isoformat()},
                       {'errors':['failed_originality']}]:
            with self.subTest(change=change),staged() as (store,article,_):
                q=store.rows('news_quality_checks')[0]
                store.put('news_quality_checks',{**q,'payload':{**q['payload'],**change}})
                self.assertFalse(review_notice_release(store,article,{},NOW)['passed'])

    def test_daily_limit_counts_other_published_news_and_keeps_failed_draft_private(self):
        with staged() as (store,article,_):
            enable(store,1);review=review_notice_release(store,article,{},NOW);commit(store,article,review)
            item=source(STAT_TEXT,ACEA);store.put('news_items',item)
            report=stage_notices(store,[ACEA],{},now=NOW)[0]
            other=store.get('news_articles',report['article_id']); checked=review_notice_release(store,other,{},NOW)
            with self.assertRaisesRegex(ValueError,'daily_publication_limit'): commit(store,other,checked)
            self.assertEqual(len(store.public_articles()),1)
            self.assertEqual(store.db.execute('select count(*) from news_notice_publications').fetchone()[0],1)

    def test_cli_defaults_to_dry_run_and_uses_existing_publication_rpc_only_after_approval(self):
        with staged() as (store,article,directory):
            enable(store);store.close()
            with patch('sys.argv',['publish_news_notices.py','--db',str(directory/'test.sqlite')]),redirect_stdout(io.StringIO()):
                result=main()
            self.assertTrue(result['dry_run']);self.assertEqual(result['published'],0)
            # Context cleanup tolerates repeated close; a separate disposable adapter proves RPC routing.
            remote=Mock(spec=NewsStore);remote.backend='supabase';remote.client=Mock()
            NewsStore.publish_notice(remote,'id','digest',{'exact':'payload'},{'exact':'source'})
            remote.client._request.assert_called_once_with('POST','rpc/publish_news_notice',{
                'article_key':'id','expected_artifact_hash':'digest','expected_payload':{'exact':'payload'},'expected_source':{'exact':'source'}})


if __name__=='__main__': unittest.main()
