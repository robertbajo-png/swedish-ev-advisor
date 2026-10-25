"""Single-use owner-authorized hybrid writer/reviewer trial, never publication."""
import argparse
import hashlib
import json
import uuid
from contextlib import closing
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from news_ai import MODEL, SYSTEM, NewsAi, NewsBudgetBlocked, response_json
from news_engine import hydrate_item, models_for_news, registry
from news_http import Collector
from news_launch_hybrid import (HYBRID_POLICY, article_shape_errors, brief_errors,
    launch_brief, precheck_article, reviewer_call, review_errors, writer_call)
from news_notice_pipeline import notice_sources
from news_store import NewsStore, artifact_hash, now_iso, stable_id
from refresh_verified_variants import save
from smoke_news_engine import verified_context
from supabase_client import load_local_env
from trial_news_ab_r26 import surfaces

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-10-23'
TRIAL_ID = stable_id('private-hybrid-launch-live-v1:' + DATE)
DIRECTORY = ROOT / 'data/local/release-data/news-hybrid-live-2026-10-23'
MANIFEST = DIRECTORY / 'manifest.json'
REPORT = DIRECTORY / 'report.json'
DATABASE = DIRECTORY / 'private.sqlite'
CAP = 70000
ARTICLE_BYTES = 7000
SOURCE_ITEM = '8bd04eca-a817-59da-9177-2fa2b1c21878'
STAGES = {'ev_news_hybrid_launch_write': ('swedish_ev_article', 2500),
          'ev_news_hybrid_launch_review': ('ev_news_independent_audit', 2500)}


def authorize():
    if datetime.now(timezone.utc).date().isoformat() != DATE:
        raise NewsBudgetBlocked('hybrid_live_authorization_date_expired')


def code_hash():
    return artifact_hash({p: hashlib.sha256((ROOT / 'scripts' / p).read_bytes()).hexdigest()
        for p in ('trial_news_hybrid_launch.py', 'news_launch_hybrid.py', 'news_ai.py')})


def ledger(client):
    rows = client.select('news_ai_requests', columns=(
        'id,created_at,stage,model,charged_micro_usd,reserved_micro_usd,input_tokens,output_tokens,'
        'settled_at,budget_closed_at,provider_status'), filters={'limit': 1000})
    if len(rows) >= 1000 or any(type(r['charged_micro_usd']) is not int or r['charged_micro_usd'] < 0 for r in rows):
        raise NewsBudgetBlocked('hybrid_live_invalid_or_truncated_ledger')
    if any(not r['settled_at'] and not r['budget_closed_at'] or r['provider_status'] == 'accounting_anomaly' for r in rows):
        raise NewsBudgetBlocked('hybrid_live_unresolved_usage')
    return rows


def readiness(remote, enabled, maximum=0):
    authorize()
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    notice = remote.client.select('news_notice_release_config', filters={'id': 'eq.production'})[0]
    if (cfg['enabled'] is not enabled or cfg['publication_enabled'] or notice['enabled']
        or cfg['model'] != MODEL or cfg['daily_limit_micro_usd'] != 250000
        or cfg['monthly_limit_micro_usd'] != 5000000 or cfg['pricing_valid_until'] <= DATE):
        raise NewsBudgetBlocked('hybrid_live_configuration_mismatch')
    rows = ledger(remote.client)
    day = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE))
    month = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(DATE[:7]))
    if maximum > min(250000 - day, 5000000 - month, CAP):
        raise NewsBudgetBlocked('hybrid_live_whole_trial_exceeds_allowance')
    return {'daily_used_micro_usd': day, 'monthly_used_micro_usd': month,
            'available_micro_usd': min(250000 - day, 5000000 - month), 'unresolved': 0}


def production_surfaces(remote):
    return {**surfaces(remote), 'sitemap': hashlib.sha256((ROOT / 'public/sitemap.xml').read_bytes()).hexdigest()}


def payload(call):
    name, schema, prompt = call
    if name not in STAGES:
        raise NewsBudgetBlocked('hybrid_live_unapproved_stage')
    return {'model': MODEL, 'store': False, 'service_tier': 'default',
            'max_output_tokens': STAGES[name][1],
            'reasoning': {'effort': 'low' if name.endswith('_write') else 'none'},
            'input': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}],
            'text': {'format': {'type': 'json_schema', 'name': name, 'strict': True, 'schema': schema}}}


def request_bound(body):
    raw = json.dumps(body, ensure_ascii=False).encode()
    inp, out = len(raw) + 4096, body['max_output_tokens']
    if inp > 131072:
        raise NewsBudgetBlocked('hybrid_live_input_too_large')
    return {'input_bound': inp, 'output_bound': out, 'request_digest': hashlib.sha256(raw).hexdigest(),
            'maximum_micro_usd': (inp * 3 + out * 18 + 3) // 4}


def whole_trial_bound(brief):
    writer = request_bound(payload(writer_call(brief)))
    # Bound every possible schema-valid review, including seven paragraphs and five
    # citations per block. Twice the raw article bound covers nested JSON escaping.
    ids = sorted((f['id'] for f in brief['facts']), key=lambda s: len(s.encode()), reverse=True)[:5]
    stub = {'title': '', 'title_fact_ids': ids, 'intro': '', 'intro_fact_ids': ids,
            'paragraphs': [{'text': '', 'fact_ids': ids, 'kind': 'reporting', 'section': 'technology'} for _ in range(7)]}
    review = request_bound(payload(reviewer_call(stub, brief)))
    review['input_bound'] += 2 * ARTICLE_BYTES
    review['maximum_micro_usd'] = (review['input_bound'] * 3 + review['output_bound'] * 18 + 3) // 4
    if review['input_bound'] > 131072:
        raise NewsBudgetBlocked('hybrid_live_review_bound_too_large')
    return {'writer': writer['maximum_micro_usd'], 'review': review['maximum_micro_usd'],
            'total': writer['maximum_micro_usd'] + review['maximum_micro_usd']}


def receipt(remote, report):
    save(REPORT, report)
    remote.put('news_ingestion_runs', {'id': TRIAL_ID, 'payload': {
        k: v for k, v in report.items() if k not in ('article', 'review', 'baseline_ids')}})


def prepare(remote, collector=None):
    authorize()
    if REPORT.exists() or MANIFEST.exists() or DATABASE.exists() or remote.get('news_ingestion_runs', TRIAL_ID):
        raise NewsBudgetBlocked('hybrid_live_preparation_already_consumed')
    before = readiness(remote, False)
    sources = {s['id']: s for s in notice_sources(registry())}
    original = remote.get('news_items', SOURCE_ITEM)
    if not original or original['source_id'] != 'vw-sweden-press':
        raise NewsBudgetBlocked('hybrid_live_official_source_missing')
    isolated = {**original, 'cluster_id': None, 'status': 'collected', 'payload': {
        k: v for k, v in original['payload'].items() if k not in ('extraction', 'fact_quarantine', 'attempts')}}
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    with closing(NewsStore(DATABASE, backend='sqlite')) as local:
        fresh, _ = hydrate_item(local, isolated, sources, collector or Collector(tls_context=verified_context()))
        brief = launch_brief([fresh], [sources[fresh['source_id']]], models_for_news(remote))
    if brief_errors(brief) or not brief['article_eligible']:
        raise NewsBudgetBlocked('hybrid_live_fresh_brief_rejected')
    bounds = whole_trial_bound(brief)
    readiness(remote, False, bounds['total'])
    manifest = {'trial_id': TRIAL_ID, 'date': DATE, 'policy': HYBRID_POLICY, 'model': MODEL,
                'code_hash': code_hash(), 'brief': brief, 'bounds': bounds, 'cap_micro_usd': CAP,
                'max_requests': 2, 'publish': False, 'revisions': 0, 'created_at': now_iso()}
    save(MANIFEST, manifest)
    report = {'trial_id': TRIAL_ID, 'state': 'prepared', 'manifest_hash': artifact_hash(manifest),
              'budget_before': before, 'bounds': bounds, 'baseline_ids': [r['id'] for r in ledger(remote.client)],
              'baseline_surfaces': production_surfaces(remote), 'results': [], 'publish': False,
              'production_model_changed': False, 'shutdown_verified': False}
    receipt(remote, report)
    sql = f"""-- One private hybrid trial; no publication or budget increase.
begin;
do $$ begin
  if not exists(select 1 from public.news_ingestion_runs where id='{TRIAL_ID}'
    and payload->>'state'='prepared' and payload->>'manifest_hash'='{report['manifest_hash']}')
    or (now() at time zone 'UTC')::date <> date '{DATE}' then raise exception 'Trial marker/date mismatch'; end if;
  if not exists(select 1 from public.news_ai_config where id='production' and not enabled
    and not publication_enabled and model='{MODEL}' and daily_limit_micro_usd=250000
    and monthly_limit_micro_usd=5000000 and pricing_valid_until > date '{DATE}')
    or exists(select 1 from public.news_notice_release_config where enabled)
    or exists(select 1 from public.news_ai_requests where settled_at is null and budget_closed_at is null)
    then raise exception 'Paused configuration/ledger mismatch'; end if;
  if (select coalesce(sum(charged_micro_usd),0) from public.news_ai_requests
    where created_at >= date '{DATE}' at time zone 'UTC') + {bounds['total']} > 250000
    or (select coalesce(sum(charged_micro_usd),0) from public.news_ai_requests
    where created_at >= date '2026-10-01' at time zone 'UTC') + {bounds['total']} > 5000000
    then raise exception 'Insufficient ordinary budget'; end if;
  update public.news_ai_config set enabled=true where id='production';
end $$;
commit;
select enabled,publication_enabled,model,daily_limit_micro_usd,monthly_limit_micro_usd
from public.news_ai_config where id='production';
"""
    (DIRECTORY / 'owner-enable.sql').write_text(sql, encoding='utf-8')
    (DIRECTORY / 'owner-stop.sql').write_text("begin;\nupdate public.news_ai_config set enabled=false where id='production';\ncommit;\nselect enabled,publication_enabled,model,daily_limit_micro_usd,monthly_limit_micro_usd from public.news_ai_config where id='production';\nselect enabled from public.news_notice_release_config where id='production';\n", encoding='utf-8')
    return summary(report)


def paid_call(remote, report, call, transport=None):
    authorize()
    expected = list(STAGES)[len(report['results'])] if len(report['results']) < 2 else None
    if call[0] != expected:
        raise NewsBudgetBlocked('hybrid_live_stage_repeated_or_out_of_order')
    body = payload(call)
    contract = request_bound(body)
    budget_stage = STAGES[call[0]][0]
    amount = contract.pop('maximum_micro_usd')
    limit = report['bounds']['writer' if len(report['results']) == 0 else 'review']
    if amount > limit or sum(r['reserved_micro_usd'] for r in report['results']) + amount > CAP:
        raise NewsBudgetBlocked('hybrid_live_frozen_reservation_exceeded')
    readiness(remote, True, amount)
    current = ledger(remote.client)
    expected_ids = set(report['baseline_ids']) | {r['request_id'] for r in report['results']}
    if {r['id'] for r in current} != expected_ids or production_surfaces(remote) != report['baseline_surfaces']:
        raise NewsBudgetBlocked('hybrid_live_concurrent_work_or_production_changed')
    request_id = str(uuid.uuid4())
    reservation = remote.client._request('POST', 'rpc/reserve_news_ai', {
        'request_key': request_id, 'stage_key': budget_stage, 'model_key': MODEL, **contract})
    if reservation.get('allowed') is not True:
        raise NewsBudgetBlocked('hybrid_live_reservation_denied')
    row = {'request_id': request_id, 'hybrid_stage': call[0], 'budget_stage': budget_stage,
           'reserved_micro_usd': reservation['reserved_micro_usd'], 'state': 'dispatch_pending'}
    report['results'].append(row)
    receipt(remote, report)  # Durable proof before provider dispatch; unknown usage retains reservation.
    response = (transport or NewsAi.request)(body, request_id=request_id)
    row.update(state='usage_observed', response=response)
    receipt(remote, report)
    usage = response.get('usage') or {}
    if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('input_tokens', 'output_tokens')):
        raise NewsBudgetBlocked('hybrid_live_usage_unknown_reservation_retained')
    settled = remote.client._request('POST', 'rpc/settle_news_ai', {
        'request_key': request_id, 'used_input': usage['input_tokens'],
        'used_output': usage['output_tokens'], 'response_body': response})
    if settled.get('settled') is not True:
        raise NewsBudgetBlocked('hybrid_live_settlement_failed_reservation_retained')
    row.update(state='settled', charged_micro_usd=settled['charged_micro_usd'])
    receipt(remote, report)
    return response_json(response)


def render(report):
    article = report.get('article') or {}
    result = 'Godkänd i privat prov' if report.get('passed') else 'Underkänd eller ofullständig - privat karantän'
    body = '<h1>' + escape(article.get('title', 'Privat hybridprov')) + '</h1>'
    body += '<p class="intro">' + escape(article.get('intro', '')) + '</p>'
    body += ''.join('<p>' + escape(p['text']) + '</p>' for p in article.get('paragraphs', []))
    refs = json.loads(MANIFEST.read_text(encoding='utf-8'))['brief']['sources']
    body += '<h2>Källa</h2>' + ''.join('<p><a href="' + escape(s['item']['url'], quote=True) + '">' + escape(s['source']['name']) + '</a></p>' for s in refs)
    body += '<h2>Granskningsresultat</h2><pre>' + escape(json.dumps({k: report.get(k) for k in ('precheck', 'review_errors', 'error')}, ensure_ascii=False, indent=2)) + '</pre>'
    page = '<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Privat AI-hybridprov</title><style>body{margin:0;background:#f7f7f4;color:#171b1c;font:17px/1.7 system-ui}main{max-width:760px;margin:32px auto;padding:24px}h1{font-size:36px;line-height:1.15}.intro{font-size:20px}.label{padding:16px;border-left:4px solid #245e5b;background:#dceae6}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}a{color:#245e5b}</style><main><div class="label">Privat liveprov. Inget publicerat. ' + escape(result) + '.</div>' + body + '</main></html>'
    (DIRECTORY / 'index.html').write_text(page, encoding='utf-8')


def run(remote, transport=None):
    authorize()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    marker = remote.get('news_ingestion_runs', TRIAL_ID)
    if (report['state'] != 'prepared' or not marker or marker['payload'].get('state') != 'prepared'
        or artifact_hash(manifest) != report['manifest_hash'] or marker['payload']['manifest_hash'] != report['manifest_hash']
        or manifest['code_hash'] != code_hash() or manifest['bounds'] != whole_trial_bound(manifest['brief'])
        or manifest['trial_id'] != TRIAL_ID or manifest['model'] != MODEL or manifest['publish'] is not False
        or manifest['max_requests'] != 2 or manifest['revisions'] != 0 or manifest['cap_micro_usd'] != CAP
        or brief_errors(manifest['brief'])):
        raise NewsBudgetBlocked('hybrid_live_requires_unused_frozen_preparation')
    if (datetime.now(timezone.utc) - datetime.fromisoformat(manifest['created_at'])).total_seconds() > 7200:
        raise NewsBudgetBlocked('hybrid_live_preparation_expired')
    readiness(remote, True, report['bounds']['total'])
    report.update(state='running', started_at=now_iso())
    receipt(remote, report)
    try:
        brief = manifest['brief']
        article = paid_call(remote, report, writer_call(brief), transport)
        report['article'] = article
        report['precheck'] = precheck_article(article, brief)
        receipt(remote, report)
        if article_shape_errors(article) or len(json.dumps(article, ensure_ascii=False).encode()) > ARTICLE_BYTES:
            raise NewsBudgetBlocked('hybrid_live_article_not_reviewable_within_frozen_bound')
        # Review the exact raw final artifact even when deterministic editorial checks reject it.
        before = artifact_hash(article)
        review = paid_call(remote, report, reviewer_call(article, brief), transport)
        report['review'] = review
        report['review_errors'] = review_errors(review, article, brief)
        report['artifact_unchanged_during_review'] = before == artifact_hash(article)
        report['passed'] = (report['precheck']['passed'] and not report['review_errors']
                            and report['artifact_unchanged_during_review'])
        with closing(NewsStore(DATABASE, backend='sqlite')) as local:
            cluster_id = stable_id('private-hybrid-trial:' + TRIAL_ID)
            local.put('news_story_clusters', {'id': cluster_id, 'event_key': 'private:' + brief['event_key'], 'payload': {'trial_id': TRIAL_ID}})
            local.put('news_articles', {'id': TRIAL_ID, 'cluster_id': cluster_id,
                'slug': 'private-hybrid-' + TRIAL_ID, 'status': 'draft' if report['passed'] else 'quarantined',
                'published_at': None, 'payload': {'article': article, 'review': review,
                    'brief': brief, 'policy': HYBRID_POLICY, 'live_release_eligible': False}})
            if local.public_articles():
                raise NewsBudgetBlocked('hybrid_live_local_publication_forbidden')
    except Exception as exc:
        report.update(passed=False, error=type(exc).__name__ + ':' + str(exc)[:220])
    finally:
        report.update(state='completed', finished_at=now_iso(), owner_shutdown_required=True)
        receipt(remote, report)
        render(report)
    return summary(report)


def verify_stop(remote):
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    if report['state'] != 'completed':
        raise NewsBudgetBlocked('hybrid_live_trial_not_completed')
    report['budget_after'] = readiness(remote, False)
    rows = ledger(remote.client)
    new = [r for r in rows if r['id'] not in report['baseline_ids']]
    if ({r['id'] for r in new} != {r['request_id'] for r in report['results']}
        or any(not r['settled_at'] or r['provider_status'] != 'completed' for r in new)
        or sum(r['charged_micro_usd'] for r in new) > CAP):
        raise NewsBudgetBlocked('hybrid_live_usage_requires_reconciliation')
    report['usage'] = new
    report['charged_micro_usd'] = sum(r['charged_micro_usd'] for r in new)
    report['cost_usd'] = str(report['charged_micro_usd'] / 1000000)
    report['production_unchanged'] = production_surfaces(remote) == report['baseline_surfaces']
    if not report['production_unchanged']:
        raise NewsBudgetBlocked('hybrid_live_production_surface_changed')
    report.update(shutdown_verified=True, owner_shutdown_required=False)
    receipt(remote, report)
    return summary(report)


def summary(report):
    return {k: v for k, v in report.items() if k not in ('article', 'review', 'baseline_ids', 'baseline_surfaces', 'results')} | {
        'results': [{k: v for k, v in r.items() if k != 'response'} for r in report['results']]}


if __name__ == '__main__':
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'run', 'verify-stop'])
    args = parser.parse_args()
    with closing(NewsStore(backend='supabase')) as remote:
        result = {'prepare': prepare, 'run': run, 'verify-stop': verify_stop}[args.mode](remote)
        print(json.dumps(result, ensure_ascii=True, indent=2))
