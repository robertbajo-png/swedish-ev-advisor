"""Exact-variant price refresh; default fetches and prepares locally, without writes."""
import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from audit_catalog_sources import ROOT
from skoda_price_intake import URL, NAMES, extract_prices, fetch_price_source
from refresh_verified_variants import save
from supabase_client import SupabaseRestClient
from variant_refresh import RefreshError

ADAPTER = 'skoda_enyaq_price_private_v1'
SEPARATE_ADAPTER = 'skoda_enyaq_price_separate_proof_v2'
SEPARATE_CONTRACT = {'contract': SEPARATE_ADAPTER, 'publisher': 'publish_skoda_price_refresh_v2'}
PRICE_PROOF_FIELDS = ('price_source_url', 'price_source_hash', 'price_source_quote',
                      'price_source_name', 'price_verified_at', 'price_refresh_batch_id')
PRICE_FACT_FIELDS = ('price_sek', 'price_type', 'price_valid_until')
LOCAL = ROOT / 'data/local/release-data/price-refresh'


class PricePublicationUncertain(RefreshError):
    pass


def check_expected_prices(drafts, expected):
    actual = {row['variant_name']: {'price_sek': row['price_sek'], 'price_type': row['price_type'],
                                   'price_valid_until': row['price_valid_until']} for row in drafts}
    if len(actual) != len(drafts) or actual != expected:
        raise RefreshError('prices_changed_from_operator_approved_scope')


def uuid_value(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise RefreshError('invalid_canonical_identifier') from None


def separate_price_proof(row, draft, fetched):
    # Price-specific historical evidence, independently of the technical URL.
    if (row.get('price_source_url') != URL or row.get('price_source_name') != 'Skoda Sverige'
            or not re.fullmatch('[a-f0-9]{64}', row.get('price_source_hash') or '')
            or not re.fullmatch('[a-f0-9]{64}', row.get('price_refresh_batch_id') or '')
            or not isinstance(row.get('price_source_quote'), str) or not row['price_source_quote'].strip()
            or not all(row.get(field) is not None for field in PRICE_PROOF_FIELDS)):
        raise RefreshError('existing_exact_separate_price_proof_required')
    try:
        verified = datetime.fromisoformat(row['price_verified_at'])
        if verified.tzinfo is None or verified >= fetched:
            raise ValueError('nonfresh')
    except (ValueError, TypeError):
        raise RefreshError('existing_price_proof_timestamp_invalid') from None
    if any(row.get(field) != draft.get(field) for field in PRICE_FACT_FIELDS) or row.get('price_type') != 'campaign_price':
        raise RefreshError('separate_price_refresh_cannot_change_campaign_facts')
    return {field: row[field] for field in (*PRICE_PROOF_FIELDS, *PRICE_FACT_FIELDS)}


def prepare(source, text, original, previous, now=None, *, document_pages=None):
    now = now or datetime.now(timezone.utc)
    try:
        fetched = datetime.fromisoformat(source['fetched_at'])
        age = (now - fetched).total_seconds()
    except (KeyError, ValueError, TypeError):
        raise RefreshError('invalid_fetch_timestamp') from None
    if not -60 <= age <= 900:
        raise RefreshError('stale_price_fetch')
    if (source.get('status') != 'reachable' or source.get('http_status') != 200
            or 'pdf' not in source.get('content_type', '')):
        raise RefreshError('official_pdf_not_reachable')
    if ((original.get('url'), original.get('brand'), original.get('model'),
         original.get('country'), original.get('language')) != (URL, 'Skoda', 'Enyaq', 'SE', 'sv')
            or original.get('source_authority') not in (None, 'manufacturer', 'importer')
            or not re.fullmatch('[a-f0-9]{64}', original.get('content_hash') or '')
            or not original.get('updated_at')):
        raise RefreshError('existing_official_source_required')
    source_id = uuid_value(original.get('id'))
    model_id = uuid_value(original.get('canonical_model_id'))
    drafts = extract_prices(text, source, previous, now.date(), document_pages=document_pages)
    names = {row['variant_name']: row for row in previous}
    if len(names) != 4 or len({row.get('id') for row in previous}) != 4:
        raise RefreshError('duplicate_canonical_target')
    # Keep legacy same-technical-source publication unchanged; if any technical
    # source has moved, the entire group must possess complete exact price proof.
    adapter = ADAPTER if all(row.get('source_url') == URL for row in previous) else SEPARATE_ADAPTER
    records, targets = [], []
    for draft in drafts:
        old = names[draft['variant_name']]
        if (old.get('canonical_model_id') != model_id
                or old.get('validation_status') not in ('published', 'published_reviewed')
                or not old.get('updated_at') or not isinstance(old.get('source_url'), str)
                or not old['source_url'].startswith('https://')
                or not re.fullmatch('[a-f0-9]{64}', old.get('source_hash') or '')):
            raise RefreshError('existing_published_exact_variant_required')
        price = old.get('price_sek')
        if price is not None and (not isinstance(price, (int, float)) or isinstance(price, bool)
                                  or not math.isfinite(price) or price <= 0 or abs(draft['price_sek'] / price - 1) > 0.15):
            raise RefreshError('large_price_change_requires_quarantine')
        target = {'id': uuid_value(old.get('id')), 'draft_id': None,
                  'variant_name': old['variant_name'],
                  'expected_updated_at': old['updated_at'], 'expected_hash': old['source_hash']}
        if adapter == SEPARATE_ADAPTER:
            target.update(expected_technical_source_id=uuid_value(old.get('source_id')),
                          expected_technical_source_url=old['source_url'],
                          expected_price=separate_price_proof(old, draft, fetched))
        records.append({**draft, 'canonical_model_id': model_id, 'source_id': source_id,
                        'validation_status': 'validated', 'validation_errors': [],
                        'extraction_payload': {**draft['extraction_payload'], 'adapter': adapter, 'fetch': source}})
        targets.append(target)
    batch_id = hashlib.sha256(json.dumps({'source': source, 'drafts': records, 'targets': targets}, sort_keys=True).encode()).hexdigest()
    packet = {'adapter': adapter, 'batch_id': batch_id, 'source_id': source_id,
              'source_hash': source['content_hash'], 'expected_source_hash': original['content_hash'],
              'expected_source_updated_at': original['updated_at'], 'fetched_at': source['fetched_at'],
              'final_url': source['final_url'], 'targets': targets}
    return {'packet': packet, 'source': source, 'drafts': records, 'source_text': text,
            'ready_for_publication': False, 'staged': 0, 'published': 0,
            'requires_source_registry_alignment': original.get('source_authority') is None,
            'requires_separate_price_contract_v2': adapter == SEPARATE_ADAPTER,
            'specifications_reverified': False, 'openai_calls': 0}


def stage_or_publish(client, prepared, publish=False):
    if prepared.get('requires_source_registry_alignment'):
        raise RefreshError('source_registry_authority_missing_no_rows_staged')
    adapter = prepared['packet'].get('adapter')
    if adapter not in (ADAPTER, SEPARATE_ADAPTER):
        raise RefreshError('unknown_price_adapter_no_rows_staged')
    if adapter == SEPARATE_ADAPTER:
        try:
            contract = client._request('GET', 'rpc/skoda_price_refresh_contract_v2')
        except Exception:
            raise RefreshError('migration_028_required_no_rows_staged') from None
        if contract != SEPARATE_CONTRACT:
            raise RefreshError('migration_028_contract_mismatch_no_rows_staged')
    # Fail before staging on a deployment that lacks the per-price evidence contract.
    try:
        client.select('public_ev_variants', 'price_verified_at', {'limit': '1'})
    except RuntimeError:
        raise RefreshError('migration_020_required_no_rows_staged') from None
    rows = client.upsert('extracted_variant_drafts', prepared['drafts'], 'source_url,variant_name')
    by_name = {row['variant_name']: row['id'] for row in rows}
    if len(rows) != 4 or set(by_name) != set(NAMES.values()):
        raise RefreshError('incomplete_price_staging')
    packet = {**prepared['packet'], 'targets': []}
    for target in prepared['packet']['targets']:
        packet['targets'].append({key: value for key, value in
                                  {**target, 'draft_id': uuid_value(by_name[target['variant_name']])}.items()
                                  if key != 'variant_name'})
    if not publish:
        return {'staged': 4, 'published': 0, 'packet': packet, 'specifications_reverified': False}
    try:
        rpc = 'publish_skoda_price_refresh_v2' if adapter == SEPARATE_ADAPTER else 'publish_skoda_price_refresh'
        result = client._request('POST', 'rpc/' + rpc, {'p_batch': packet})
    except Exception:
        raise PricePublicationUncertain('publication_outcome_unknown_reconcile_saved_batch_before_retry') from None
    if (not isinstance(result, dict) or result.get('published') != 4 or result.get('price_verified') is not True
            or result.get('specifications_reverified') is not False):
        raise PricePublicationUncertain('unexpected_publication_response_reconcile_saved_batch_before_retry')
    return {'staged': 4, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--stage', action='store_true')
    mode.add_argument('--publish', action='store_true')
    parser.add_argument('--expected-prices', type=Path, help='Optional exact operator-approved price matrix; mismatch stops before staging')
    args = parser.parse_args()
    fetched = fetch_price_source()
    if fetched['status'] != 'reachable':
        raise RefreshError('official_source_' + fetched['status'])
    source = {key: fetched.get(key) for key in ('status', 'http_status', 'final_url', 'content_hash', 'text_hash', 'content_type')}
    source.update(url=URL, brand='Skoda', model='Enyaq', fetched_at=datetime.now(timezone.utc).isoformat())
    client = SupabaseRestClient()
    sources = client.select('manufacturer_sources', '*', {'url': 'eq.' + URL})
    if len(sources) != 1:
        raise RefreshError('unique_existing_source_required')
    previous = client.select('canonical_model_variants', '*', {'canonical_model_id': 'eq.' + sources[0]['canonical_model_id']})
    prepared = prepare(source, fetched['text'], sources[0], previous, document_pages=fetched['document'])
    if prepared['requires_separate_price_contract_v2'] and (args.stage or args.publish) and not args.expected_prices:
        raise RefreshError('exact_operator_price_matrix_required_no_rows_staged')
    if args.expected_prices:
        check_expected_prices(prepared['drafts'], json.loads(args.expected_prices.read_text(encoding='utf-8')))
    prepared['publication_requested'] = args.publish
    LOCAL.mkdir(parents=True, exist_ok=True)
    path = LOCAL / (prepared['packet']['batch_id'] + '.json')
    save(path, prepared)
    try:
        result = stage_or_publish(client, prepared, args.publish) if args.stage or args.publish else {'staged': 0, 'published': 0}
    except PricePublicationUncertain:
        prepared['publication_outcome'] = 'unknown_reconcile_before_retry'
        try:
            save(path, prepared)
        except OSError:
            pass  # Preserve the unknown RPC outcome even if receipt storage also fails.
        raise
    prepared['operation_result'] = result
    try:
        save(path, prepared)
    except OSError:
        if args.publish:
            raise PricePublicationUncertain('publication_response_received_but_receipt_failed_reconcile_saved_batch') from None
        raise
    print(json.dumps({'mode': 'publish' if args.publish else 'stage' if args.stage else 'dry_run',
                      'prepared_prices': len(prepared['drafts']), 'batch_id': prepared['packet']['batch_id'],
                      'prices': [{'variant': row['variant_name'], 'price_sek': row['price_sek'],
                                  'price_type': row['price_type'], 'price_valid_until': row['price_valid_until']}
                                 for row in prepared['drafts']],
                      'staged': result['staged'], 'published': result['published'],
                      'requires_source_registry_alignment': prepared['requires_source_registry_alignment'],
                      'requires_separate_price_contract_v2': prepared['requires_separate_price_contract_v2'],
                      'adapter': prepared['packet']['adapter'],
                      'remote_writes': bool(args.stage or args.publish), 'specifications_reverified': False,
                      'openai_calls': 0}, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        reason = str(error) if isinstance(error, RefreshError) else 'price_preparation_failed_details_not_logged'
        uncertain = isinstance(error, PricePublicationUncertain)
        print(json.dumps({'status': 'publication_outcome_unknown' if uncertain else 'quarantined',
                          'reason': reason, 'published': None if uncertain else 0, 'openai_calls': 0}))
        raise SystemExit(1)
