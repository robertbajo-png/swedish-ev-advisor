"""Two audited AI formats and a deterministic price proof; owner activation is separate."""
import argparse
import copy
import hashlib
import json
import os
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import urljoin

from news_ai import NewsAi, NewsBudgetBlocked, response_json
from news_http import Collector, PageText
from news_notice_pipeline import prepare_notice
from news_notices import NOTICE_RECIPE, NOTICE_REVIEW
from news_short_articles import (RECIPE, SOURCES, LIMITS, ARTICLE_BYTES, AI_ARTICLE_KINDS, fetch_item, make_brief,
    writer_call, reviewer_call, precheck, review_check, pair_bound, official_url, stage, release)
from news_store import NewsStore, artifact_hash, now_iso, stable_id
from refresh_verified_variants import save
from smoke_news_engine import verified_context
from supabase_client import load_local_env
from trial_news_hybrid_launch import ledger

ROOT = Path(__file__).resolve().parents[1]
FORMAT_POLICY = 'news-mixed-release-2026-10-v1'
AI_KINDS = AI_ARTICLE_KINDS
DIRECTORY = ROOT / 'data/local/release-data/news-mixed-rollout'
VW_URL = 'https://www.vwgroup.se/nyheter--media/pressmeddelanden/2026/10/nya-volkswagen-id.-cross-kan-nu-bestallas-med-ett-batteri-pa-37-kwh/'
CASES = [('model', 'vw-sweden-press', VW_URL), ('price', 'vw-sweden-press', VW_URL),
         ('battery', 'firefly-china-press', 'https://www.firefly.com.cn/news/20261023001')]


def code_hash():
    return artifact_hash({name: (ROOT / 'scripts' / name).read_text(encoding='utf-8').replace('\r\n', '\n')
        for name in ('news_short_articles.py', 'run_short_news.py', 'news_ai.py',
                     'news_notice_pipeline.py', 'news_notice_facts.py', 'news_notices.py', 'news_notice_validation.py')})


@contextmanager
def worker_lock():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    with (DIRECTORY / 'worker.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def budget(remote, required=0):
    now = datetime.now(timezone.utc)
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    rows = ledger(remote.client)
    day = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(now.date().isoformat()))
    month = sum(r['charged_micro_usd'] for r in rows if r['created_at'].startswith(now.strftime('%Y-%m')))
    left = max(0, min(cfg['daily_limit_micro_usd'] - day, cfg['monthly_limit_micro_usd'] - month))
    valid = (cfg['model'] == 'gpt-6-sol' and cfg['daily_limit_micro_usd'] == 250000
             and cfg['monthly_limit_micro_usd'] == 5000000 and cfg['daily_article_limit'] == 1
             and cfg['pricing_valid_until'] > now.date().isoformat())
    return {'allowed': valid and cfg['enabled'] and left > 0 and required <= left,
        'remaining_micro_usd': left, 'day_spent_micro_usd': day, 'month_spent_micro_usd': month,
        'publication_enabled': cfg['publication_enabled'], 'config_valid': valid,
        'retry_after': (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()}


def state_id():
    return stable_id(FORMAT_POLICY + ':' + code_hash())


def load_state(remote):
    row = remote.get('news_ingestion_runs', state_id())
    return row['payload'] if row else {'recipe': RECIPE, 'format_policy': FORMAT_POLICY,
        'code_hash': code_hash(), 'cases': {}, 'passed': False}


def checkpoint(remote, state):
    save(DIRECTORY / 'report.json', state)
    remote.put('news_ingestion_runs', {'id': state_id(), 'payload': state})


def request_evidence(remote, ids):
    if len(ids) != 2 or len(set(ids)) != 2:
        return None
    rows = remote.client.select('news_ai_requests', filters={'id': 'in.(' + ','.join(ids) + ')'})
    by_id = {r['id']: r for r in rows}
    if len(by_id) != 2:
        return None
    ordered = [by_id[i] for i in ids]
    if ([r['stage'] for r in ordered] != ['swedish_ev_article', 'ev_news_independent_audit']
            or any(r['model'] != 'gpt-6-sol' or not r['settled_at'] or r['provider_status'] != 'completed' for r in ordered)):
        return None
    return ordered


def matrix_valid(remote, state):
    try:
        if (state.get('recipe') != RECIPE or state.get('format_policy') != FORMAT_POLICY
                or state.get('code_hash') != code_hash() or set(state.get('cases', {})) != {'model', 'price', 'battery'}):
            return False
        all_ids = []
        for kind, case in state['cases'].items():
            if case.get('state') != 'passed':
                return False
            checked_at = datetime.fromisoformat(case['finished_at'])
            if kind == 'price':
                if (case.get('format') != 'price_notice' or case.get('ai_audit_performed') is not False
                        or case.get('request_ids') != []):
                    return False
                article, review = prepare_notice(case['item'], case['source'], kind='price', now=checked_at)
                if (case['article'] != article or case['review'] != review or not review['passed']
                        or article['editorial_recipe'] != NOTICE_RECIPE or review['method'] != NOTICE_REVIEW):
                    return False
                continue
            if case.get('format') != 'ai_article' or case['brief']['kind'] != kind:
                return False
            if not precheck(case['article'], case['brief'], checked_at)['passed'] or review_check(case['review'], case['article'], case['brief']):
                return False
            rows = request_evidence(remote, case['request_ids'])
            if not rows or response_json(rows[0]['response_payload']) != case['article'] or response_json(rows[1]['response_payload']) != case['review']:
                return False
            all_ids.extend(case['request_ids'])
        return len(set(all_ids)) == 4
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def price_proof(item, source, now=None):
    now = now or datetime.now(timezone.utc)
    article, review = prepare_notice(item, source, kind='price', now=now)
    return {'format': 'price_notice', 'state': 'passed' if review['passed'] else 'failed',
        'item': copy.deepcopy(item), 'source': copy.deepcopy(source), 'article': article, 'review': review,
        'ai_audit_performed': False, 'request_ids': [], 'cost_micro_usd': 0, 'finished_at': now.isoformat()}


def verify_private_proofs(remote, model_directory, battery_directory, price_manifest, now=None):
    """Recheck frozen real outputs and a source-only price snapshot. No writes or paid calls."""
    now = now or datetime.now(timezone.utc)
    state = {'recipe': RECIPE, 'format_policy': FORMAT_POLICY, 'code_hash': code_hash(),
        'cases': {}, 'passed': False, 'release_authorized': False, 'paid_calls': 0, 'published': 0}
    for kind, directory in [('model', model_directory), ('battery', battery_directory)]:
        directory = Path(directory)
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        report = json.loads((directory / 'report.json').read_text(encoding='utf-8'))
        if (report.get('state') != 'completed' or report.get('quality_passed') is not True
                or report.get('shutdown_verified') is not True or report.get('publication') is not False
                or artifact_hash(manifest) != report.get('manifest_hash') or manifest['brief']['kind'] != kind):
            raise ValueError('mixed_proof_requires_unchanged_successful_private_trial:' + kind)
        state['cases'][kind] = {'format': 'ai_article', 'state': 'passed',
            **{k: copy.deepcopy(report[k]) for k in ('article', 'review', 'request_ids', 'finished_at')},
            'brief': copy.deepcopy(manifest['brief']),
            'origin': {'trial_id': report['trial_id'], 'manifest_hash': report['manifest_hash'],
                       'trial_code_hash': manifest['code_hash'], 'report_hash': artifact_hash(report)}}
    # The failed AI price result is never loaded: only the original source facts.
    raw = json.loads(Path(price_manifest).read_text(encoding='utf-8'))
    if raw['brief']['kind'] != 'price':
        raise ValueError('mixed_price_source_snapshot_required')
    state['cases']['price'] = price_proof(raw['brief']['item'], raw['brief']['source'], now)
    state['passed'] = matrix_valid(remote, state)
    if not state['passed']:
        raise ValueError('short_mixed_format_proofs_required')
    return state


def register_verified_proofs(remote, path):
    """Explicit private registration, never activation or replacement of a failed run."""
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    if remote.get('news_ingestion_runs', state_id()):
        raise ValueError('mixed_format_gate_already_exists_do_not_replace')
    if not matrix_valid(remote, state):
        raise ValueError('short_mixed_format_proofs_required')
    state['passed'] = True
    state['release_authorized'] = False
    checkpoint(remote, state)
    return state


def render_case(kind, case):
    if not case.get('article'):
        return
    a = case['article']
    body = '<h1>' + escape(a['title']) + '</h1><p class="intro">' + escape(a['intro']) + '</p>'
    body += ''.join('<p>' + escape(p['text']) + '</p>' for p in a['paragraphs'])
    item = case['item'] if case.get('format') == 'price_notice' else case['brief']['item']
    body += '<p><a href="' + escape(item['url'], quote=True) + '">Originalkälla</a></p>'
    body += '<pre>' + escape(json.dumps({'precheck': case.get('precheck'), 'review_errors': case.get('review_errors')}, ensure_ascii=False, indent=2)) + '</pre>'
    label = 'Privat regelbaserad prisnotis. Ingen AI-granskning.' if case.get('format') == 'price_notice' else 'Privat AI-artikel.'
    page = '<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Privat kortartikelprov</title><style>body{margin:0;background:#f7f7f4;color:#171b1c;font:17px/1.7 system-ui}main{max-width:740px;margin:32px auto;padding:24px}h1{font-size:34px;line-height:1.15}.intro{font-size:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}a{color:#245e5b}</style><main><p>' + label + ' Inget publicerat. Status: ' + escape(case['state']) + '</p>' + body + '</main></html>'
    path = DIRECTORY / kind / 'index.html'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding='utf-8')


def prepare(remote, collector):
    state = load_state(remote)
    for kind, source_id, url in CASES:
        if kind in state['cases']:
            continue
        item = fetch_item(source_id, url, collector)
        state['cases'][kind] = ({'state': 'prepared', 'format': 'price_notice', 'item': item, 'source': SOURCES[source_id]}
            if kind == 'price' else {'state': 'prepared', 'format': 'ai_article', 'brief': make_brief(item, kind)})
    checkpoint(remote, state)
    return state


def run_matrix(remote, collector):
    state = prepare(remote, collector)
    if any(c['state'] in ('running', 'failed') for c in state['cases'].values()):
        return {'status': 'blocked_failed_or_interrupted_case', 'passed': False}
    ai = None
    for kind, source_id, url in CASES:
        case = state['cases'][kind]
        if case['state'] == 'passed':
            continue
        if kind == 'price':
            try:
                state['cases'][kind] = price_proof(fetch_item(source_id, url, collector), SOURCES[source_id])
                render_case(kind, state['cases'][kind])
            except (ValueError, KeyError, TypeError) as exc:
                state['cases'][kind] = {'format': 'price_notice', 'state': 'failed',
                    'error': type(exc).__name__ + ':' + str(exc)[:160]}
            checkpoint(remote, state)
            if state['cases'][kind]['state'] != 'passed':
                return {'status': 'failed', 'published': 0, 'failed_format': kind}
            continue
        if ai is None:
            ai = NewsAi(remote.client, model='gpt-6-sol', cache_enabled=False, output_limits=LIMITS)
        # Refresh pending sources after a budget wait; do not relabel an old fetch.
        case['brief'] = make_brief(fetch_item(source_id, url, collector), kind)
        check = budget(remote, pair_bound(ai, case['brief']))
        if not check['allowed']:
            state['budget'] = check
            checkpoint(remote, state)
            return {'status': 'deferred_budget_or_disabled', 'passed_cases': [k for k, c in state['cases'].items() if c['state'] == 'passed'], 'budget': check}
        before = {r['id'] for r in ledger(remote.client)}
        case.update(state='running', started_at=now_iso(), request_ids=[])
        checkpoint(remote, state)
        try:
            case['article'] = ai(*writer_call(case['brief']))
            case['precheck'] = precheck(case['article'], case['brief'])
            checkpoint(remote, state)
            if len(json.dumps(case['article'], ensure_ascii=False).encode()) > ARTICLE_BYTES:
                raise ValueError('short_article_exceeds_reserved_review_bound')
            case['review'] = ai(*reviewer_call(case['article'], case['brief']))
            case['review_errors'] = review_check(case['review'], case['article'], case['brief'])
            new = [r for r in ledger(remote.client) if r['id'] not in before]
            new.sort(key=lambda r: r['created_at'])
            case['request_ids'] = [r['id'] for r in new]
            proof = request_evidence(remote, case['request_ids'])
            case['cost_micro_usd'] = sum(r['charged_micro_usd'] for r in new)
            case['state'] = 'passed' if proof and case['precheck']['passed'] and not case['review_errors'] else 'failed'
            with closing(NewsStore(DIRECTORY / kind / 'private.sqlite')) as local:
                stage(local, case['brief'], case['article'], case['review'], request_ids=case['request_ids'])
        except Exception as exc:
            case.update(state='failed', error=type(exc).__name__ + ':' + str(exc)[:160])
        case['finished_at'] = now_iso()
        render_case(kind, case)
        checkpoint(remote, state)
        if case['state'] == 'failed':
            return {'status': 'failed', 'cases': {k: c['state'] for k, c in state['cases'].items()},
                'cost_micro_usd': sum(c.get('cost_micro_usd', 0) for c in state['cases'].values()), 'published': 0}
    state['passed'] = matrix_valid(remote, state)
    checkpoint(remote, state)
    return {'status': 'passed' if state['passed'] else 'failed', 'cases': {k: c['state'] for k, c in state['cases'].items()},
        'cost_micro_usd': sum(c.get('cost_micro_usd', 0) for c in state['cases'].values()), 'published': 0}


def release_from_matrix(remote, collector):
    state = load_state(remote)
    if not matrix_valid(remote, state):
        raise ValueError('short_mixed_format_proofs_required')
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if not cfg['publication_enabled'] or cfg['daily_article_limit'] != 1:
        return {'status': 'awaiting_owner_activation', 'published': 0}
    public = remote.public_articles()
    if any(a['published_at'][:10] == now_iso()[:10] for a in public):
        return {'status': 'daily_limit', 'published': 0}
    urls = {ref['url'] for a in public for ref in a.get('sources', [])}
    for kind in AI_KINDS:
        case = state['cases'][kind]
        brief = case['brief']
        if brief['item']['url'] in urls:
            continue
        fresh = fetch_item(brief['item']['source_id'], brief['item']['url'], collector)
        if any(fresh['payload'][key] != brief['item']['payload'][key]
               for key in ('content_hash', 'title', 'published_at', 'final_url')):
            return {'status': 'source_changed_requires_new_review', 'published': 0}
        row = stage(remote, brief, case['article'], case['review'], request_ids=case['request_ids'])
        result = release(remote, row['id'], True)
        from news_engine import export_public
        return {**result, 'published': 1, 'export': export_public(remote)}
    return {'status': 'no_unpublished_matrix_event', 'published': 0}


def daily(remote, collector):
    state = load_state(remote)
    if not matrix_valid(remote, state):
        return {'status': 'mixed_format_proofs_required', 'published': 0}
    cfg = remote.client.select('news_ai_config', filters={'id': 'eq.production'})[0]
    if not cfg['publication_enabled'] or cfg['daily_article_limit'] != 1:
        return {'status': 'awaiting_owner_activation', 'published': 0}
    public = remote.public_articles()
    if any(a['published_at'][:10] == now_iso()[:10] for a in public):
        return {'status': 'daily_limit', 'published': 0}
    # Reuse a fully reviewed, still-fresh private candidate before buying another story.
    first = release_from_matrix(remote, collector)
    if first.get('published') or first['status'] != 'no_unpublished_matrix_event':
        return first
    runs = remote.rows('news_ingestion_runs')
    if any(r['payload'].get('kind') == 'short_daily' and str(r['payload'].get('started_at', '')).startswith(now_iso()[:10]) for r in runs):
        return {'status': 'daily_attempt_limit', 'published': 0}
    public_urls = {ref['url'] for a in public for ref in a.get('sources', [])}
    sources = [('vw-sweden-press', 'https://www.vwgroup.se/nyheter--media/', 'model'),
               ('firefly-china-press', 'https://www.firefly.com.cn/news', 'battery')]
    skipped = []
    for source_id, index_url, kind in sources:
        _, _, html, final = collector.fetch(index_url, SOURCES[source_id], editorial=True)
        parser = PageText(); parser.feed(html)
        urls = list(dict.fromkeys(urljoin(final, link) for link in parser.links))
        urls = [url for url in urls if official_url(source_id, url) and url not in public_urls][:6]
        for url in urls:
            try:
                brief = make_brief(fetch_item(source_id, url, collector), kind)
            except (ValueError, KeyError) as exc:
                skipped.append({'url': url, 'reason': str(exc)[:120]})
                continue
            attempt_id = stable_id(RECIPE + ':daily:' + url + ':' + brief['item']['payload']['content_hash'])
            if remote.get('news_ingestion_runs', attempt_id):
                continue
            ai = NewsAi(remote.client, model='gpt-6-sol', cache_enabled=False, output_limits=LIMITS)
            allowance = budget(remote, pair_bound(ai, brief))
            if not allowance['allowed']:
                return {'status': 'deferred_budget_or_disabled', 'published': 0, 'budget': allowance}
            record = {'kind': 'short_daily', 'recipe': RECIPE, 'started_at': now_iso(), 'state': 'running', 'url': url}
            remote.put('news_ingestion_runs', {'id': attempt_id, 'payload': record})
            before = {r['id'] for r in ledger(remote.client)}
            try:
                article = ai(*writer_call(brief))
                if len(json.dumps(article, ensure_ascii=False).encode()) > ARTICLE_BYTES:
                    raise ValueError('short_article_exceeds_reserved_review_bound')
                audit = ai(*reviewer_call(article, brief))
                new = sorted((r for r in ledger(remote.client) if r['id'] not in before), key=lambda r: r['created_at'])
                ids = [r['id'] for r in new]
                if not request_evidence(remote, ids):
                    raise ValueError('short_provider_evidence_missing')
                row = stage(remote, brief, article, audit, request_ids=ids)
                record.update(state=row['status'], article_id=row['id'])
                if row['status'] != 'draft':
                    return {'status': 'quarantined', 'published': 0, 'article_id': row['id']}
                fresh = fetch_item(source_id, url, collector)
                if any(fresh['payload'][key] != brief['item']['payload'][key]
                       for key in ('content_hash', 'title', 'published_at', 'final_url')):
                    raise ValueError('short_source_changed_before_publication')
                result = release(remote, row['id'], True)
                record.update(state='published', published_at=now_iso())
                from news_engine import export_public
                return {**result, 'published': 1, 'export': export_public(remote)}
            except Exception as exc:
                record.update(state='failed', error=type(exc).__name__ + ':' + str(exc)[:160])
                return {'status': 'failed', 'published': 0, 'error': record['error']}
            finally:
                remote.put('news_ingestion_runs', {'id': attempt_id, 'payload': record})
    return {'status': 'no_eligible_new_source', 'published': 0, 'skipped': skipped}


def activation_sql(remote):
    state = load_state(remote)
    if not matrix_valid(remote, state):
        raise ValueError('short_mixed_format_proofs_required')
    return f"""-- Requires separate owner release approval; format validation does not activate publication.
begin;
do $$ begin
  if not exists(select 1 from public.news_ingestion_runs where id='{state_id()}'
    and payload->>'code_hash'='{code_hash()}' and payload->'passed'='true'::jsonb
    and payload->>'format_policy'='{FORMAT_POLICY}'
    and payload->'cases'->'model'->>'state'='passed'
    and payload->'cases'->'model'->>'format'='ai_article'
    and payload->'cases'->'price'->>'state'='passed'
    and payload->'cases'->'price'->>'format'='price_notice'
    and payload->'cases'->'price'->'ai_audit_performed'='false'::jsonb
    and payload->'cases'->'price'->'request_ids'='[]'::jsonb
    and payload->'cases'->'price'->'review'->>'method'='{NOTICE_REVIEW}'
    and payload->'cases'->'battery'->>'state'='passed'
    and payload->'cases'->'battery'->>'format'='ai_article') then raise exception 'Mixed-format proofs required'; end if;
  if not exists(select 1 from public.news_ai_config where id='production' and enabled
    and model='gpt-6-sol' and daily_limit_micro_usd=250000 and monthly_limit_micro_usd=5000000
    and daily_article_limit=1 and pricing_valid_until>(now() at time zone 'UTC')::date)
    or exists(select 1 from public.news_ai_requests where settled_at is null and budget_closed_at is null)
    then raise exception 'Budget/configuration/accounting changed'; end if;
  update public.news_ai_config set publication_enabled=true where id='production';
end $$;
commit;
select enabled,publication_enabled,daily_article_limit,model from public.news_ai_config where id='production';
"""


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'matrix', 'release', 'run', 'status', 'activation-sql', 'verify-proofs'])
    parser.add_argument('--model-proof', type=Path)
    parser.add_argument('--battery-proof', type=Path)
    parser.add_argument('--price-source-manifest', type=Path)
    parser.add_argument('--proof-report', type=Path, help='Explicit private registration with prepare; no AI or activation')
    args = parser.parse_args()
    with worker_lock(), closing(NewsStore(backend='supabase')) as remote:
        collector = Collector(tls_context=verified_context())
        if args.command == 'verify-proofs':
            if not all((args.model_proof, args.battery_proof, args.price_source_manifest)):
                parser.error('verify-proofs requires --model-proof, --battery-proof and --price-source-manifest')
            state = verify_private_proofs(remote, args.model_proof, args.battery_proof, args.price_source_manifest)
            path = DIRECTORY / 'verified-private-proofs.json'
            save(path, state)
            result = {'status': 'format_proofs_validated', 'format_policy': FORMAT_POLICY,
                'proofs_passed': True, 'release_authorized': False, 'remote_writes': 0,
                'paid_calls': 0, 'published': 0, 'report': str(path)}
        elif args.command == 'prepare':
            state = register_verified_proofs(remote, args.proof_report) if args.proof_report else prepare(remote, collector)
            result = {'status': 'prepared', 'cases': list(state['cases']), 'paid_calls': 0}
        elif args.command == 'matrix':
            result = run_matrix(remote, collector)
        elif args.command == 'release':
            result = release_from_matrix(remote, collector)
        elif args.command == 'run':
            result = daily(remote, collector)
        elif args.command == 'activation-sql':
            sql = activation_sql(remote)
            save_path = DIRECTORY / 'owner-activate-publication.sql'
            save_path.write_text(sql, encoding='utf-8')
            result = {'sql_file': str(save_path), 'executed': False}
        else:
            state = load_state(remote)
            result = {'budget': budget(remote), 'gate_id': state_id(), 'matrix_passed': matrix_valid(remote, state),
                'cases': {k: c['state'] for k, c in state['cases'].items()}}
        print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
