"""Read-only notice deployment checks. No provider key, writes or publication."""
import argparse
import hashlib
import json
from datetime import datetime, timezone

from news_notices import NOTICE_RECIPE, NOTICE_REVIEW
from supabase_client import SupabaseRestClient
from news_model_policy import SUPPORTED_MODELS


def all_rows(client,table,columns='*'):
    result=[]
    for offset in range(0,100000,500):
        page=client.select(table,columns=columns,filters={'order':'id.asc','offset':offset,'limit':500})
        result.extend(page)
        if len(page)<500: return result
    raise ValueError('notice_preflight_pagination_limit')


def digest(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def run(remote=False,mode='paused',client=None):
    if mode not in ('paused','release'): raise ValueError('invalid_notice_preflight_mode')
    report={'at':datetime.now(timezone.utc).isoformat(),'mode':mode,'remote_checked':False,
            'schema_installed':False,'ready':False,'errors':[],'warnings':[],
            'provider_requests':0,'cost_usd':0,'writes':0,'public_export_written':False,
            'fingerprints':{}}
    if not remote:
        report['errors'].append('explicit_remote_read_check_required')
        return report
    try:
        client=client or SupabaseRestClient()
        configs=client.select('news_ai_config',columns='id,enabled,publication_enabled,model,daily_limit_micro_usd,monthly_limit_micro_usd,daily_article_limit',filters={'id':'eq.production'})
        if len(configs)!=1: raise ValueError('notice_global_configuration_missing')
        cfg=configs[0]
        report['global_config']=cfg
        if cfg['enabled'] is not False: report['errors'].append('paid_news_ai_must_remain_disabled')
        if cfg['model'] not in SUPPORTED_MODELS: report['errors'].append('production_model_changed')
        if cfg['daily_limit_micro_usd']!=250000 or cfg['monthly_limit_micro_usd']!=5000000:
            report['errors'].append('news_budget_caps_changed')
        for table in ('public_news_articles','public_ev_models','public_ev_variants'):
            rows=all_rows(client,table)
            report['fingerprints'][table]={'count':len(rows),'sha256':digest(rows)}
        ledger=all_rows(client,'news_ai_requests','id,charged_micro_usd,reserved_micro_usd,settled_at,budget_closed_at,provider_status')
        report['fingerprints']['news_ai_requests']={'count':len(ledger),'sha256':digest(ledger)}
        if any(not r['settled_at'] and not r['budget_closed_at'] for r in ledger):
            report['warnings'].append('unresolved_ai_usage_no_paid_work_authorized')
        if any(r['budget_closed_at'] for r in ledger):
            report['warnings'].append('old_unknown_maximum_cost_remains_in_ledger')
        report['remote_checked']=True
        try:
            notices=client.select('news_notice_release_config',filters={'id':'eq.production'})
            client.select('news_notice_publications',columns='article_id,artifact_hash,source_hash',filters={'limit':1})
            if len(notices)!=1: raise ValueError('notice_configuration_missing')
            notice=notices[0]
            report['notice_config']=notice
            report['schema_installed']=True
        except (RuntimeError,ValueError):
            report['errors'].append('migration_017_schema_unavailable_or_inaccessible')
            return report
        api=client._request('GET','')
        if not isinstance(api,dict) or not isinstance(api.get('paths',{}).get('/rpc/publish_news_notice',{}).get('post'),dict):
            report['errors'].append('notice_publication_rpc_not_visible_to_worker')
        if notice['policy']!=NOTICE_RECIPE or notice['review_method']!=NOTICE_REVIEW:
            report['errors'].append('notice_release_policy_changed')
        if (type(notice['daily_limit']) is not int or type(cfg['daily_article_limit']) is not int
                or not 0 < min(notice['daily_limit'],cfg['daily_article_limit']) <= 5):
            report['errors'].append('notice_daily_limit_invalid')
        expected=mode=='release'
        if cfg['publication_enabled'] is not expected:
            report['errors'].append('global_publication_must_be_'+('enabled' if expected else 'disabled'))
        if notice['enabled'] is not expected:
            report['errors'].append('notice_publication_must_be_'+('enabled' if expected else 'disabled'))
        report['ready']=not report['errors']
    except (RuntimeError,ValueError,KeyError,TypeError) as exc:
        # Do not echo HTTP bodies, URLs containing credentials or raw provider data.
        report['errors'].append('notice_preflight_read_failed:'+type(exc).__name__)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remote',action='store_true')
    parser.add_argument('--mode',choices=['paused','release'],default='paused')
    args=parser.parse_args()
    result=run(args.remote,args.mode)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['ready'] else 1)
