"""Fresh-evidence gate for initial Toyota identities; canonical writes use one RPC."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone

from audit_catalog_sources import ROOT
from refresh_verified_variants import save
from supabase_client import SupabaseRestClient
from toyota_price_intake import HTML_URL, LOCAL, collect_configuration, extract_config, source_subset
from variant_refresh import FACT_FIELDS, RefreshError

REPORT = ROOT / 'data/review/toyota_publication_report.json'


def check_new_identity(client, source, data):
    try:
        fetched = datetime.fromisoformat(source['fetched_at'])
        age = (datetime.now(timezone.utc) - fetched).total_seconds()
    except (KeyError, ValueError, TypeError):
        raise RefreshError('fresh_source_evidence_required') from None
    if source.get('url') != HTML_URL or not re.fullmatch(r'[0-9a-f]{64}', source.get('content_hash', '')) or not -60 <= age <= 900:
        raise RefreshError('fresh_source_evidence_required')
    rows = extract_config(data, source)
    sources = client.select('manufacturer_sources', '*', {'url': 'eq.' + HTML_URL})
    if len(sources) != 1:
        raise RefreshError('one_previously_discovered_source_required')
    stored = sources[0]
    if any(stored.get(k) != v for k, v in {'brand': 'Toyota', 'model': 'bZ4X', 'country': 'SE', 'language': 'sv',
            'source_authority': 'manufacturer', 'source_validation': 'reachable_official_model_source', 'http_status': 200}.items()):
        raise RefreshError('unapproved_publication_source')
    models = client.select('canonical_models', '*', {'id': 'eq.' + stored['canonical_model_id']})
    if len(models) != 1 or models[0]['brand'] != 'Toyota' or models[0]['model'] != 'bZ4X' or models[0]['validation_status'] == 'rejected':
        raise RefreshError('canonical_model_mismatch')
    existing = client.select('canonical_model_variants', '*', {'canonical_model_id': 'eq.' + stored['canonical_model_id']})
    matched = []
    for row in rows:
        identity = row['extraction_payload']['manufacturer_variant_id']
        collisions = [old for old in existing if old.get('manufacturer_variant_id') == identity or old['variant_name'] == row['variant_name']]
        if collisions:
            if (len(collisions) != 1 or collisions[0].get('manufacturer_variant_id') != identity
                    or collisions[0]['variant_name'] != row['variant_name'] or collisions[0]['validation_status'] != 'published'
                    or collisions[0].get('source_id') != stored['id'] or collisions[0].get('source_url') != HTML_URL
                    or collisions[0].get('manufacturer_model_id') != row['extraction_payload']['manufacturer_model_id']
                    or collisions[0].get('manufacturer_config_version') != row['extraction_payload']['model_config_version']
                    or collisions[0].get('source_hash') != row['source_hash']
                    or any(collisions[0].get(k) != row.get(k) for k in FACT_FIELDS)):
                raise RefreshError('existing_identity_requires_separate_refresh')
            matched.append(collisions[0]['id'])
    if matched:
        if len(matched) != len(rows):
            raise RefreshError('partial_existing_group_requires_refresh')
        return stored, rows, matched
    if any(old.get('source_id') == stored['id'] or old.get('source_url') == HTML_URL for old in existing):
        raise RefreshError('public_source_requires_complete_refresh')
    return stored, rows, []


def prepare_packet(client, source, data, write=False):
    stored, rows, existing = check_new_identity(client, source, data)
    if existing:
        return {'status': 'already_public', 'canonical_variant_ids': existing, 'inserted': 0}, None
    staged = client.select('extracted_variant_drafts', '*', {'source_url': 'eq.' + HTML_URL})
    by_name = {row['variant_name']: row for row in staged}
    targets = []
    for index, row in enumerate(rows):
        old = by_name.get(row['variant_name'])
        if not old or old.get('source_id') != stored['id'] or old.get('canonical_model_id') != stored['canonical_model_id']:
            raise RefreshError('previous_private_intake_required')
        payload = old.get('extraction_payload') or {}
        if (old['validation_status'] not in ('needs_review', 'validated')
                or payload.get('adapter') != 'toyota_embedded_config_v1'
                or payload.get('manufacturer_variant_id') != row['extraction_payload']['manufacturer_variant_id']
                or (old['validation_status'] == 'needs_review' and old.get('validation_errors') != ['canonical_identity_mapping_required'])
                or (old['validation_status'] == 'validated' and payload.get('publication_intent') != 'new_identity_only')):
            raise RefreshError('unresolved_or_reviewed_draft_requires_review')
        for field in ('price_sek', 'wltp_range_km'):
            if old.get(field) and row.get(field) and abs(row[field] / old[field] - 1) > 0.15:
                raise RefreshError('large_staging_change_requires_review')
        row['validation_status'] = 'validated'
        row['validation_errors'] = []
        row['extraction_payload'].update(source_configuration=source_subset(data), publication_intent='new_identity_only',
            motorization_pointer=f'/carConfigMotorization/motorization/{index}', fetched_at=source['fetched_at'])
        if write:
            changes = {**row, 'updated_at': datetime.now(timezone.utc).isoformat()}
            updated = client._request('PATCH', 'extracted_variant_drafts', changes,
                query={'id': 'eq.' + old['id'], 'updated_at': 'eq.' + old['updated_at'], 'validation_status': 'eq.' + old['validation_status']},
                prefer='return=representation')
            if len(updated or []) != 1:
                raise RefreshError('concurrent_private_draft_change')
            old = updated[0]
        targets.append({'draft_id': old['id'], 'expected_updated_at': old['updated_at']})
    packet = {'adapter': 'toyota_embedded_config_v1', 'source_id': stored['id'],
              'expected_source_hash': stored.get('content_hash'), 'expected_source_updated_at': stored['updated_at'],
              'source_hash': source['content_hash'], 'fetched_at': source['fetched_at'], 'final_url': HTML_URL, 'targets': targets}
    packet['batch_id'] = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
    if write:
        save(LOCAL / 'publication-batch.json', {'packet': packet, 'source': source})
    return {'status': 'prepared' if write else 'validated_local_only', 'validated': len(rows), 'inserted': 0,
            'candidate_names': [row['variant_name'] for row in rows]}, packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    source, data = collect_configuration()
    client = SupabaseRestClient()
    result, packet = prepare_packet(client, source, data, write=args.prepare or args.publish)
    if args.publish and packet:
        try:
            published = client._request('POST', 'rpc/publish_new_toyota_variants', {'p_batch': packet})
        except RuntimeError as error:
            raise RefreshError('migration_011_required' if 'PGRST202' in str(error) else 'atomic_publication_rejected') from None
        if published.get('inserted') != result['validated'] and published.get('already_applied') is not True:
            raise RefreshError('unexpected_publication_response')
        result.update(status='published', **published)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'source_url': HTML_URL,
              'source_hash': source['content_hash'], 'mode': 'publish' if args.publish else 'prepare' if args.prepare else 'dry_run',
              **result, 'canonical_write_requested': bool(args.publish and packet), 'openai_calls': 0}
    save(REPORT, report)
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        reason = str(error) if isinstance(error, RefreshError) else 'source_or_storage_error'
        previous = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'inserted': 0}
        previous['last_attempt'] = {'status': 'quarantined', 'reason': reason, 'checked_at': datetime.now(timezone.utc).isoformat()}
        save(REPORT, previous)
        print('Toyota publication stopped safely: ' + reason)
        raise SystemExit(1)
