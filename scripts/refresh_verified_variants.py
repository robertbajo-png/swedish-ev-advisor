"""Bounded official-source refresh. Default is local extraction, never publication."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from audit_catalog_sources import ROOT, SourceFetcher, allowed_url
from supabase_client import SupabaseRestClient
from variant_refresh import FACT_FIELDS, RefreshError, extract_polestar, parse_document, refresh_errors

CATALOG = ROOT / 'public/data/public_ev_variants.json'
REPORT = ROOT / 'data/review/variant_refresh_report.json'
QUARANTINE = ROOT / 'data/review/variant_refresh_quarantine.json'
LOCAL = ROOT / 'data/local/release-data/refresh'
ADAPTER = 'polestar_table_v1'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def prepare_group(expected, fetcher):
    urls = {row['source_url'] for row in expected}
    if len(urls) != 1:
        raise RefreshError('ambiguous_source_group')
    url = urls.pop()
    fetched = fetcher.fetch(url, {'Polestar'})
    if fetched['status'] != 'reachable':
        raise RefreshError(fetched['status'])
    checked = datetime.now(timezone.utc).isoformat()
    source = {'brand': 'Polestar', 'model': expected[0]['model'], 'url': url,
              'source_type': 'manufacturer_specs_page', 'source_authority': 'manufacturer',
              'source_validation': 'reachable_official_model_source', 'content_hash': fetched['content_hash'],
              'final_url': fetched['final_url'], 'fetched_at': checked}
    document = fetched['document']
    drafts = extract_polestar(document, source, expected)
    by_name = {row['variant_name']: row for row in expected}
    for row in drafts:
        row['validation_errors'] = refresh_errors(row, source, document, by_name[row['variant_name']])
        if row['validation_errors']:
            raise RefreshError('field_validation_failed:' + ','.join(row['validation_errors']))
        row['validation_status'] = 'validated'
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL / (source['content_hash'] + '.txt')).write_text(fetched['text'], encoding='utf-8')
    return source, drafts, document


def publish_group(client, source, drafts, document, publish=False):
    saved_sources = client.select('manufacturer_sources', '*', {'url': 'eq.' + source['url']})
    if len(saved_sources) != 1:
        raise RefreshError('existing_source_required')
    original = saved_sources[0]
    if (original['brand'], original['model']) != (source['brand'], source['model']):
        raise RefreshError('source_identity_mismatch')
    existing = client.select('canonical_model_variants', '*', {'canonical_model_id': 'eq.' + original['canonical_model_id']})
    by_name = {row['variant_name']: row for row in existing}
    if len(by_name) != len(existing):
        raise RefreshError('ambiguous_canonical_variant')
    records, targets = [], []
    batch_id = hashlib.sha256(json.dumps({'source': source, 'drafts': drafts}, sort_keys=True).encode()).hexdigest()
    for draft in drafts:
        previous = by_name.get(draft['variant_name'])
        if not previous or previous['validation_status'] != 'published':
            raise RefreshError('existing_published_variant_required')
        errors = refresh_errors(draft, source, document, {**previous, 'brand': source['brand'], 'model': source['model']})
        if errors:
            raise RefreshError('remote_fact_conflict:' + ','.join(errors))
        payload = {**draft['extraction_payload'], 'fetch': source, 'refresh_batch_id': batch_id,
                   'previous_canonical': {key: previous.get(key) for key in (*FACT_FIELDS, 'source_hash', 'source_quote', 'source_id')}}
        records.append({**draft, 'canonical_model_id': previous['canonical_model_id'], 'source_id': original['id'], 'extraction_payload': payload})
        targets.append({'id': previous['id'], 'expected_updated_at': previous['updated_at'],
                        'expected_hash': previous['source_hash'], 'variant_name': previous['variant_name']})
    staged = client.upsert('extracted_variant_drafts', records, 'source_url,variant_name')
    draft_ids = {row['variant_name']: row['id'] for row in staged}
    if len(draft_ids) != len(drafts):
        raise RefreshError('incomplete_staging_response')
    for target in targets:
        target['draft_id'] = draft_ids[target.pop('variant_name')]
    packet = {'batch_id': batch_id, 'adapter': ADAPTER, 'source_id': original['id'],
              'source_hash': source['content_hash'], 'expected_source_hash': original['content_hash'],
              'expected_source_updated_at': original['updated_at'], 'fetched_at': source['fetched_at'],
              'final_url': source['final_url'], 'targets': targets}
    save(LOCAL / (batch_id + '.json'), {'packet': packet, 'source': source, 'drafts': records})
    if not publish:
        return {'status': 'staged', 'staged': len(staged), 'published': 0, 'batch_id': batch_id}
    try:
        result = client._request('POST', 'rpc/publish_variant_refresh', {'p_batch': packet})
    except RuntimeError as error:
        if 'PGRST202' in str(error):
            raise RefreshError('migration_010_required_staged_only') from None
        raise RefreshError('publication_rejected_no_partial_source_update') from None
    if result.get('published') != len(drafts) or result.get('source_verified') is not True:
        raise RefreshError('unexpected_publication_response')
    return {'status': 'published', 'staged': len(staged), 'batch_id': batch_id, **result}


def discover_toyota(fetcher):
    url = 'https://www.toyota.se/bilar/bz4x'
    fetched = fetcher.fetch(url, {'Toyota'})
    if fetched['status'] != 'reachable':
        return {'discovery_url': url, 'status': fetched['status'], 'candidates': []}
    return {'discovery_url': url, 'status': 'discovered_not_verified', 'content_hash': fetched['content_hash'],
            'candidates': toyota_document_candidates(fetched['document'], fetched['final_url'], fetched['content_hash']), 'published': 0}


def toyota_document_candidates(document, origin, source_hash):
    links = {}
    for link in document.nodes('a'):
        target = urljoin(origin, link.attrs.get('href', ''))
        try:
            parsed = urlsplit(target)
            port = parsed.port
        except ValueError:
            continue
        label = link.text()
        if parsed.scheme != 'https' or parsed.username or parsed.password or port not in (None, 443):
            continue
        approved = allowed_url(target, {'Toyota'})
        linked_asset = parsed.hostname == 'pdf.toyotasverigebroschyr.com' and parsed.path == '/price-list/toyota-bz4x'
        if ('bz4x' in parsed.path.lower() and 'touring' not in parsed.path.lower()
                and ('.pdf' in parsed.path.lower() or label.casefold() in ('prislista', 'broschyr'))
                and (approved or linked_asset)):
            links[target] = {'url': target, 'source_type': 'price_list_pdf' if 'pris' in (target + label).lower() or '/price-list/' in parsed.path else 'technical_pdf',
                             'source_validation': 'needs_discovery', 'host_approved': approved,
                             'discovered_from': origin, 'discovery_source_hash': source_hash, 'link_label': label}
    return list(links.values())


def merge_quarantine(previous, outcomes):
    pending = {(row['brand'], row['model']): row for row in previous}
    for row in outcomes:
        key = (row['brand'], row['model'])
        if row['status'] == 'published':
            pending.pop(key, None)
        elif row['status'] == 'quarantined':
            pending[key] = row
    return list(pending.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--stage', action='store_true')
    mode.add_argument('--publish', action='store_true')
    parser.add_argument('--discover-toyota', action='store_true')
    parser.add_argument('--model', choices=['2', '4', 'all'], default='all')
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    if catalog.get('source') != 'supabase_public_ev_variants':
        raise RefreshError('canonical_snapshot_required')
    fetcher = SourceFetcher(document_parser=parse_document)
    client = SupabaseRestClient() if args.stage or args.publish else None
    outcomes, all_drafts = [], []
    publication_failed = False
    for model in (['2', '4'] if args.model == 'all' else [args.model]):
        expected = [row for row in catalog['records'] if row['brand'] == 'Polestar' and row['model'] == model]
        if not expected:
            continue
        outcome = {'brand': 'Polestar', 'model': model, 'variants': len(expected), 'published': 0}
        try:
            source, drafts, document = prepare_group(expected, fetcher)
            all_drafts += drafts
            outcome.update(source_url=source['url'], content_hash=source['content_hash'], validated=len(drafts))
            outcome.update(publish_group(client, source, drafts, document, args.publish) if client
                           else {'status': 'validated_local_only'})
        except RefreshError as error:
            outcome.update(status='quarantined', reason=str(error))
            publication_failed |= bool(args.publish and model == '2')
        except Exception:
            outcome.update(status='quarantined', reason='source_or_storage_error_details_not_logged')
            publication_failed |= bool(args.publish and model == '2')
        outcomes.append(outcome)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'catalog_sha256': catalog['catalog_sha256'],
              'mode': 'publish' if args.publish else 'stage' if args.stage else 'dry_run', 'groups': outcomes,
              'validated': sum(row.get('validated', 0) for row in outcomes),
              'published': sum(row.get('published', 0) for row in outcomes), 'openai_calls': 0}
    if args.discover_toyota:
        report['toyota'] = discover_toyota(fetcher)
    previous_quarantine = json.loads(QUARANTINE.read_text(encoding='utf-8')) if QUARANTINE.exists() else []
    pending = merge_quarantine(previous_quarantine, outcomes)
    save(QUARANTINE, pending)
    report['quarantined_variants'] = sum(row['variants'] for row in pending)
    save(REPORT, report)
    save(LOCAL / 'drafts.json', all_drafts)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if publication_failed:
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Variant refresh stopped safely; provider bodies and credentials are not logged.', file=sys.stderr)
        sys.exit(1)
