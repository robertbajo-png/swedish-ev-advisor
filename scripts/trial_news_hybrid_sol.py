"""Owner-authorized single private Sol writer/review trial. No activation or publishing."""
import argparse
import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone

import trial_news_hybrid_launch as base
from news_ai import NewsAi, NewsBudgetBlocked, response_json
from news_launch_hybrid import writer_call, reviewer_call
from news_model_policy import reservation_micro_usd
from news_store import NewsStore, artifact_hash, stable_id, now_iso
from supabase_client import load_local_env

DATE = '2026-10-23'
MODEL = 'gpt-6-sol'
TRIAL_ID = stable_id('private-hybrid-sol-owner-approved-v1:' + DATE)
CAP = 370000
ORIGINAL_PAYLOAD = base.payload
ORIGINAL_PREPARE = base.prepare
ORIGINAL_RUN = base.run
ORIGINAL_VERIFY = base.verify_stop


def authorize():
    if datetime.now(timezone.utc).date().isoformat()!=DATE:
        raise NewsBudgetBlocked('sol_trial_authorization_expired')


def code_hash():
    return artifact_hash({p:hashlib.sha256((base.ROOT/'scripts'/p).read_bytes()).hexdigest()
        for p in ('trial_news_hybrid_sol.py','trial_news_hybrid_launch.py','news_launch_hybrid.py','news_ai.py','news_model_policy.py')})


def payload(call):
    return {**ORIGINAL_PAYLOAD(call),'model':MODEL,'prompt_cache_options':{'mode':'explicit','ttl':'30m'}}


def request_bound(body):
    raw=json.dumps(body,ensure_ascii=False).encode()
    inp,out=len(raw)+4096,body['max_output_tokens']
    if inp>131072: raise NewsBudgetBlocked('sol_trial_input_too_large')
    return {'input_bound':inp,'output_bound':out,'request_digest':hashlib.sha256(raw).hexdigest(),
            'maximum_micro_usd':reservation_micro_usd(MODEL,inp,out)}


def whole_trial_bound(brief):
    writer=request_bound(payload(writer_call(brief)))
    ids=sorted((f['id'] for f in brief['facts']),key=lambda s:len(s.encode()),reverse=True)[:5]
    stub={'title':'','title_fact_ids':ids,'intro':'','intro_fact_ids':ids,
          'paragraphs':[{'text':'','fact_ids':ids,'kind':'reporting','section':'technology'} for _ in range(7)]}
    review=request_bound(payload(reviewer_call(stub,brief)))
    review['input_bound']+=2*base.ARTICLE_BYTES
    if review['input_bound']>131072: raise NewsBudgetBlocked('sol_trial_review_bound_too_large')
    maximum=reservation_micro_usd(MODEL,review['input_bound'],review['output_bound'])
    return {'writer':writer['maximum_micro_usd'],'review':maximum,'total':writer['maximum_micro_usd']+maximum}


def readiness(remote, enabled, maximum=0):
    authorize()
    cfg=remote.client.select('news_ai_config',filters={'id':'eq.production'})[0]
    notice=remote.client.select('news_notice_release_config',filters={'id':'eq.production'})[0]
    if (cfg['enabled'] or cfg['publication_enabled'] or notice['enabled'] or cfg['model']!=MODEL
        or cfg['daily_limit_micro_usd']!=250000 or cfg['monthly_limit_micro_usd']!=5000000
        or cfg['pricing_valid_until']<=DATE):
        raise NewsBudgetBlocked('sol_trial_requires_unchanged_paused_production')
    rows=base.ledger(remote.client)
    day=sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE))
    month=sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE[:7]))
    available=min(250000+CAP-day,5000000-month,CAP)
    if maximum>available: raise NewsBudgetBlocked('sol_trial_owner_or_monthly_allowance_exceeded')
    return {'daily_used_micro_usd':day,'monthly_used_micro_usd':month,'available_micro_usd':available,
            'ordinary_daily_limit_micro_usd':250000,'ordinary_monthly_limit_micro_usd':5000000,
            'one_trial_owner_cap_micro_usd':CAP,'unresolved':0}


def prepare(remote):
    result=ORIGINAL_PREPARE(remote)
    manifest=json.loads(base.MANIFEST.read_text(encoding='utf-8'))
    report=json.loads(base.REPORT.read_text(encoding='utf-8'))
    writer=request_bound(payload(writer_call(manifest['brief'])))
    review_input=(manifest['bounds']['review']-25000)//5
    sql=f"""-- Owner approved <=USD0.37 TOTAL for ONE private Sol trial; all switches stay OFF.
begin;
do $$ begin
  if (now() at time zone 'UTC')::date<>date '{DATE}' or not exists(select 1 from public.news_ingestion_runs
    where id='{TRIAL_ID}' and payload->>'state'='prepared' and payload->>'manifest_hash'='{report['manifest_hash']}')
    then raise exception 'Sol trial marker/date changed'; end if;
  if not exists(select 1 from public.news_ai_config where id='production' and not enabled and not publication_enabled
    and model='gpt-6-sol' and daily_limit_micro_usd=250000 and monthly_limit_micro_usd=5000000
    and pricing_valid_until>date '{DATE}') or exists(select 1 from public.news_notice_release_config where enabled)
    or exists(select 1 from public.news_ai_requests where (settled_at is null and budget_closed_at is null)
      or provider_status='accounting_anomaly') then raise exception 'Paused state/accounting changed'; end if;
  if exists(select 1 from public.news_sol_test_permits where id='{TRIAL_ID}') then raise exception 'Sol permit already issued'; end if;
  insert into public.news_sol_test_permits(id,issued_at,expires_at,maximum_micro_usd,manifest_hash,writer_hash,writer_input_bound,review_input_bound,approval_note)
  values('{TRIAL_ID}',now(),now()+interval '2 hours',{CAP},'{report['manifest_hash']}',
    '{writer['request_digest']}',{writer['input_bound']},{review_input},
    'Owner approved <=USD0.37 total for one private Sol writer and independent review, despite daily cap. Monthly cap unchanged; no publication.');
end $$;
commit;
select id,maximum_micro_usd,closed_at from public.news_sol_test_permits where id='{TRIAL_ID}';
"""
    (base.DIRECTORY/'owner-enable.sql').write_text(sql,encoding='utf-8')
    (base.DIRECTORY/'owner-stop.sql').write_text(f"select public.close_news_sol_test('{TRIAL_ID}');\n",encoding='utf-8')
    return result


def paid_call(remote, report, call, transport=None):
    authorize()
    expected=list(base.STAGES)[len(report['results'])] if len(report['results'])<2 else None
    if call[0]!=expected: raise NewsBudgetBlocked('sol_trial_stage_replayed_or_out_of_order')
    body=payload(call); contract=request_bound(body); amount=contract.pop('maximum_micro_usd')
    limit=report['bounds']['writer' if not report['results'] else 'review']
    if amount>limit or sum(r['reserved_micro_usd'] for r in report['results'])+amount>CAP:
        raise NewsBudgetBlocked('sol_trial_frozen_reservation_exceeded')
    readiness(remote,False,amount)
    expected_ids=set(report['baseline_ids'])|{r['request_id'] for r in report['results']}
    if ({r['id'] for r in base.ledger(remote.client)}!=expected_ids
        or base.production_surfaces(remote)!=report['baseline_surfaces']):
        raise NewsBudgetBlocked('sol_trial_concurrent_or_production_change')
    import uuid
    request_id=str(uuid.uuid4())
    reserved=remote.client._request('POST','rpc/reserve_news_sol_test_ai',{
        'permit_key':TRIAL_ID,'manifest_digest':report['manifest_hash'],'request_key':request_id,
        'stage_key':call[0],**contract})
    if reserved.get('allowed') is not True or reserved.get('reserved_micro_usd')!=amount:
        raise NewsBudgetBlocked('sol_trial_reservation_denied_or_wrong_tariff')
    row={'request_id':request_id,'hybrid_stage':call[0],'budget_stage':call[0],
         'reserved_micro_usd':amount,'state':'dispatch_pending'}
    report['results'].append(row)
    base.receipt(remote,report)
    response=(transport or NewsAi.request)(body,request_id=request_id)
    row.update(state='usage_observed',response=response)
    base.receipt(remote,report)
    usage=response.get('usage') or {}
    if any(type(usage.get(k)) is not int or usage[k]<0 for k in ('input_tokens','output_tokens')):
        raise NewsBudgetBlocked('sol_trial_usage_unknown_hold_retained')
    settled=remote.client._request('POST','rpc/settle_news_ai',{'request_key':request_id,
        'used_input':usage['input_tokens'],'used_output':usage['output_tokens'],'response_body':response})
    if settled.get('settled') is not True: raise NewsBudgetBlocked('sol_trial_settlement_failed_hold_retained')
    row.update(state='settled',charged_micro_usd=settled['charged_micro_usd'])
    base.receipt(remote,report)
    return response_json(response)


def verify_stop(remote):
    permits=remote.client.select('news_sol_test_permits',filters={'id':'eq.'+TRIAL_ID})
    if len(permits)!=1 or not permits[0]['closed_at']:
        raise NewsBudgetBlocked('sol_trial_permit_not_closed')
    result=ORIGINAL_VERIFY(remote)
    report=json.loads(base.REPORT.read_text(encoding='utf-8'))
    report.update(permit_closed=True,ordinary_ai_remained_disabled=True)
    base.receipt(remote,report)
    return base.summary(report)


def run(remote,transport=None):
    try:
        ORIGINAL_RUN(remote,transport)
    finally:
        closed=remote.client._request('POST','rpc/close_news_sol_test',{'permit_key':TRIAL_ID})
        if closed.get('closed') is not True: raise NewsBudgetBlocked('sol_trial_close_not_verified')
    return verify_stop(remote)


def configure(scope_probe=False):
    global TRIAL_ID
    TRIAL_ID=stable_id(('private-hybrid-sol-fact-scope-v2:' if scope_probe else
                        'private-hybrid-sol-owner-approved-v1:')+DATE)
    base.DATE=DATE; base.MODEL=MODEL; base.TRIAL_ID=TRIAL_ID; base.CAP=CAP
    name='news-hybrid-sol-scope-live-' if scope_probe else 'news-hybrid-sol-live-'
    base.DIRECTORY=base.ROOT/'data/local/release-data'/(name+DATE)
    base.ARTICLE_BYTES=6300 if scope_probe else 7000
    base.MANIFEST=base.DIRECTORY/'manifest.json'; base.REPORT=base.DIRECTORY/'report.json'
    base.DATABASE=base.DIRECTORY/'private.sqlite'
    base.authorize=authorize; base.code_hash=code_hash; base.readiness=readiness
    base.payload=payload; base.request_bound=request_bound; base.whole_trial_bound=whole_trial_bound; base.paid_call=paid_call


if __name__=='__main__':
    load_local_env()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','run','verify-stop'])
    parser.add_argument('--scope-probe',action='store_true',help='New owner-approved fact-scope probe; never reuse the closed first trial.')
    args=parser.parse_args()
    configure(args.scope_probe)
    with closing(NewsStore(backend='supabase')) as remote:
        print(json.dumps({'prepare':prepare,'run':run,'verify-stop':verify_stop}[args.mode](remote),ensure_ascii=True,indent=2))
