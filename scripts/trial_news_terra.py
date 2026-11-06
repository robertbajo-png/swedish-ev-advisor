"""Private Terra writer/reviewer probe. No publication or production-model changes."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from news_ai import NewsAi, NewsBudgetBlocked, response_json
from news_budget_policy import budget
from news_http import Collector
from news_publisher_articles import (LIMITS, writer_call, reviewer_call, evidence_readiness,
    resolve_writer_output, precheck, check_review)
from news_publisher_sources import refresh_bundle, same_sources
from news_store import NewsStore, artifact_hash, now_iso
from smoke_news_engine import verified_context
from supabase_client import load_local_env

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gpt-6.1-terra'
CAP = 100000
PACKET_LIMIT = 4000


def payload(call):
    value = NewsAi(model=MODEL, output_limits=LIMITS).payload(*call)
    value['prompt_cache_options'] = {'mode': 'explicit', 'ttl': '30m'}
    return value


def request_contract(body):
    if (body.get('model') != MODEL or body.get('service_tier') != 'default'
            or body.get('store') is not False or body.get('max_output_tokens') not in (2000, 1300)):
        raise NewsBudgetBlocked('terra_payload_outside_contract')
    raw = json.dumps(body, ensure_ascii=False).encode()
    input_bound, output_bound = len(raw) + 4096, body['max_output_tokens']
    if input_bound > 131072:
        raise NewsBudgetBlocked('terra_input_too_large')
    return {'input_bound': input_bound, 'output_bound': output_bound,
            'request_digest': hashlib.sha256(raw).hexdigest(),
            'maximum_micro_usd': (input_bound * 5 + output_bound * 10 + 1) // 2}


def plan(bundle):
    material = evidence_readiness(bundle)
    if not material['ready']:
        raise NewsBudgetBlocked('terra_fresh_source_not_ready')
    writer = request_contract(payload(writer_call(bundle)))
    stub = {'extraction': {'facts': [{'id': 'f' + str(i)} for i in range(1, 7)]},
            'article': {'title': '', 'title_fact_ids': ['f1'], 'intro': '', 'intro_fact_ids': ['f1'],
                        'paragraphs': [{'text': '', 'fact_ids': ['f1'], 'kind': 'reporting'} for _ in range(3)]}}
    review = request_contract(payload(reviewer_call(bundle, stub)))
    # The frozen packet occurs once inside a JSON string; bound its escaped bytes too.
    review_input = review['input_bound'] + 2 * PACKET_LIMIT
    review_maximum = (review_input * 5 + 1300 * 10 + 1) // 2
    total = writer['maximum_micro_usd'] + review_maximum
    if review_input > 131072 or total > CAP:
        raise NewsBudgetBlocked('terra_pair_exceeds_private_cap')
    return {'writer': writer, 'review_input_bound': review_input,
            'review_maximum_micro_usd': review_maximum, 'total_micro_usd': total}


def prepare(remote, source_file, directory):
    manifest_file = directory / 'manifest.json'
    if manifest_file.exists() or (directory / 'report.json').exists():
        raise NewsBudgetBlocked('terra_test_already_prepared')
    source = json.loads(source_file.read_text(encoding='utf-8'))
    bundle = source['bundle']
    if artifact_hash(bundle) != source['bundle_hash']:
        raise NewsBudgetBlocked('terra_source_manifest_changed')
    limits = plan(bundle)
    if not budget(remote, CAP)['allowed']:
        raise NewsBudgetBlocked('terra_ordinary_budget_unavailable')
    manifest = {'permit_id': 'terra-' + str(uuid.uuid4()), 'prepared_at': now_iso(),
        'date': datetime.now(timezone.utc).date().isoformat(), 'model': MODEL, 'publish': False,
        'max_requests': 2, 'cap_micro_usd': CAP, 'bundle': bundle, 'bounds': limits,
        'code_hash': code_hash()}
    directory.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'prepared': True, 'manifest_hash': artifact_hash(manifest), 'permit_id': manifest['permit_id'],
            'bounds': limits, 'paid_calls': 0, 'published': 0}


def code_hash():
    names = ('trial_news_terra.py', 'news_ai.py', 'news_publisher_articles.py', 'news_publisher_sources.py',
             'news_publisher_selection.py', 'news_reporting_policy.py', 'news_coverage.py')
    return artifact_hash({name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest() for name in names})


def private_record(directory, report):
    (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with closing(NewsStore(directory / 'private.sqlite')) as local:
        local.put('news_ingestion_runs', {'id': report['permit_id'], 'payload': report})


def paid_call(remote, manifest, report, directory, call, transport=None):
    expected = ['swedish_ev_article', 'ev_news_independent_audit']
    if len(report['calls']) >= 2 or call[0] != expected[len(report['calls'])]:
        raise NewsBudgetBlocked('terra_stage_replay_or_order')
    body = payload(call)
    contract = request_contract(body)
    maximum = contract.pop('maximum_micro_usd')
    bound = manifest['bounds']['writer']['input_bound'] if not report['calls'] else manifest['bounds']['review_input_bound']
    if contract['input_bound'] > bound or sum(row['reserved_micro_usd'] for row in report['calls']) + maximum > CAP:
        raise NewsBudgetBlocked('terra_frozen_bounds_exceeded')
    request_id = str(uuid.uuid4())
    reserved = remote.client._request('POST', 'rpc/reserve_news_terra_test', {
        'permit_key': manifest['permit_id'], 'manifest_digest': artifact_hash(manifest),
        'request_key': request_id, 'stage_key': call[0], **contract})
    if reserved.get('allowed') is not True or reserved.get('reserved_micro_usd') != maximum:
        raise NewsBudgetBlocked('terra_budget_reservation_denied')
    row = {'request_id': request_id, 'stage': call[0], 'reserved_micro_usd': maximum, 'state': 'dispatch_pending'}
    report['calls'].append(row)
    private_record(directory, report)
    result = (transport or NewsAi.request)(body, request_id=request_id)
    row.update(state='response_received', response=result)
    private_record(directory, report)
    settled = remote.client._request('POST', 'rpc/settle_news_terra_test', {
        'request_key': request_id, 'response_body': result})
    if settled.get('settled') is not True:
        raise NewsBudgetBlocked('terra_settlement_failed_hold_retained')
    row.update(state='settled', charged_micro_usd=settled['charged_micro_usd'])
    private_record(directory, report)
    return response_json(result)


def run(remote, directory, collector=None, transport=None):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if ((directory / 'report.json').exists() or manifest['model'] != MODEL or manifest['publish'] is not False
            or manifest['date'] != datetime.now(timezone.utc).date().isoformat() or manifest['code_hash'] != code_hash()):
        raise NewsBudgetBlocked('terra_test_changed_expired_or_consumed')
    permits = remote.client.select('news_terra_test_permits', filters={'id': 'eq.' + manifest['permit_id']})
    if len(permits) != 1 or permits[0]['closed_at'] or permits[0]['manifest_hash'] != artifact_hash(manifest):
        raise NewsBudgetBlocked('terra_owner_permit_missing_or_closed')
    report = {'kind': 'private_terra_probe', 'permit_id': manifest['permit_id'], 'model': MODEL, 'started_at': now_iso(),
        'state': 'running', 'calls': [], 'published': 0, 'production_model_changed': False}
    private_record(directory, report)
    try:
        fresh = refresh_bundle(manifest['bundle'], collector or Collector(tls_context=verified_context()))
        if not same_sources(manifest['bundle'], fresh) or plan(fresh) != manifest['bounds']:
            raise NewsBudgetBlocked('terra_source_changed_before_test')
        output = paid_call(remote, manifest, report, directory, writer_call(fresh), transport)
        packet = resolve_writer_output(fresh, output)
        if len(json.dumps(packet, ensure_ascii=False).encode()) > PACKET_LIMIT:
            raise NewsBudgetBlocked('terra_packet_exceeds_private_review_bound')
        checked = precheck(fresh, packet)
        report.update(packet=packet, precheck=checked)
        if checked['passed']:
            review = paid_call(remote, manifest, report, directory, reviewer_call(fresh, packet), transport)
            errors = check_review(fresh, packet, review)
            report.update(review=review, independent_review_errors=errors,
                          state='passed_private' if not errors else 'quarantined')
        else:
            report['state'] = 'quarantined'
    except Exception as exc:
        reason = str(exc).split(':', 1)[0]
        report.update(state='blocked_or_failed', error=reason if reason.replace('_', '').isalnum() else 'terra_private_test_failed')
    finally:
        closed = remote.client._request('POST', 'rpc/close_news_terra_test', {'permit_key': manifest['permit_id']})
        report.update(permit_closed=closed.get('closed') is True, finished_at=now_iso())
        private_record(directory, report)
        if not report['permit_closed']:
            raise NewsBudgetBlocked('terra_test_close_not_verified')
    return {key: report[key] for key in ('model', 'state', 'published', 'permit_closed', 'precheck', 'independent_review_errors', 'error') if key in report} | {
        'paid_calls': len(report['calls']), 'charged_micro_usd': sum(row.get('charged_micro_usd', row['reserved_micro_usd']) for row in report['calls'])}


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--source-file', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    private = (ROOT / 'data/local').resolve()
    if private not in directory.parents:
        raise ValueError('terra_private_directory_required')
    with closing(NewsStore(backend='supabase')) as remote:
        result = prepare(remote, args.source_file, directory) if args.command == 'prepare' else run(remote, directory)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
