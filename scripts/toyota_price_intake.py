"""Official-linked Toyota price intake. Never writes canonical vehicle records."""
import argparse
import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from audit_catalog_sources import ROOT, SourceFetcher, normalized
from refresh_verified_variants import save, toyota_document_candidates
from supabase_client import SupabaseRestClient
from validate_extracted_variants import validate_draft
from variant_refresh import FACT_FIELDS, RefreshError, parse_document

MODEL_URL = 'https://www.toyota.se/bilar/bz4x'
PDF_URL = 'https://pdf.toyotasverigebroschyr.com/price-list/toyota-bz4x'
HTML_URL = MODEL_URL + '/specifications'
LOCAL = ROOT / 'data/local/release-data/toyota'
REPORT = ROOT / 'data/review/toyota_price_intake.json'


def exact_link_policy(candidate, official):
    if (official.get('status') != 'reachable' or official.get('final_url') != MODEL_URL
            or not re.fullmatch(r'[0-9a-f]{64}', official.get('content_hash', ''))
            or candidate.get('url') != PDF_URL or candidate.get('discovered_from') != MODEL_URL
            or candidate.get('discovery_source_hash') != official['content_hash']):
        raise RefreshError('fresh_official_link_required')
    links = toyota_document_candidates(official['document'], MODEL_URL, official['content_hash'])
    if candidate not in links:
        raise RefreshError('official_link_not_present')

    def allowed(url, brands):
        parsed = urlsplit(url)
        return brands == {'Toyota'} and url == PDF_URL and not parsed.query and not parsed.fragment
    return allowed


def parse_pdf(body, content_type):
    from pypdf import PdfReader
    if 'application/pdf' not in content_type or not body.startswith(b'%PDF-'):
        raise RefreshError('pdf_signature_and_type_required')
    reader = PdfReader(io.BytesIO(body), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 20:
        raise RefreshError('unsupported_pdf')
    for key, value in (reader.metadata or {}).items():
        if re.sub(r'[^a-z]', '', str(key).casefold()).endswith('tdmreservation') and str(value).strip() == '1':
            raise RefreshError('machine_reservation')
    metadata_stream = reader.trailer['/Root'].get('/Metadata')
    if metadata_stream:
        import xml.etree.ElementTree as ET
        metadata = metadata_stream.get_object().get_data()
        if len(metadata) > 512000 or b'<!DOCTYPE' in metadata.upper() or b'<!ENTITY' in metadata.upper():
            raise RefreshError('oversized_pdf_metadata')
        tree = ET.fromstring(metadata)
        for node in tree.iter():
            for key, value in [(node.tag, node.text or ''), *node.attrib.items()]:
                if 'tdm' in key.casefold() and key.rsplit('}', 1)[-1].casefold() in ('reservation', 'tdm-reservation') and value.strip() == '1':
                    raise RefreshError('machine_reservation')
    pages = [page.extract_text(extraction_mode='layout', layout_mode_space_vertically=False) or '' for page in reader.pages]
    if not all(page.strip() for page in pages):
        raise RefreshError('scanned_or_empty_page')
    return {'pages': pages, 'body': body}


def collect_document():
    official = SourceFetcher(document_parser=parse_document).fetch(MODEL_URL, {'Toyota'})
    if official['status'] != 'reachable':
        raise RefreshError('official_page_' + official['status'])
    links = toyota_document_candidates(official['document'], official['final_url'], official['content_hash'])
    candidates = [item for item in links if item['url'] == PDF_URL]
    if len(candidates) != 1:
        raise RefreshError('unique_current_price_document_required')
    candidate = candidates[0]
    fetched = SourceFetcher(timeout=8, document_parser=parse_pdf,
                            url_policy=exact_link_policy(candidate, official)).fetch(PDF_URL, {'Toyota'})
    if fetched['status'] != 'reachable':
        raise RefreshError('price_document_' + fetched['status'])
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL / (fetched['content_hash'] + '.pdf')).write_bytes(fetched['document']['body'])
    save(LOCAL / 'pages.json', fetched['document']['pages'])
    return candidate, fetched


def config_from_document(document):
    configs = []
    for node in document.nodes('div'):
        if not node.attrs.get('id', '').endswith('-data') or not node.text().startswith('{'):
            continue
        raw = ''.join(child for child in node.children if isinstance(child, str))
        data = json.loads(raw)
        if isinstance(data, dict) and 'carConfigMotorization' in data:
            configs.append(data)
    if len(configs) != 1:
        raise RefreshError('unique_manufacturer_configuration_required')
    data = configs[0]
    market = data.get('commonSettings', {})
    car = data.get('car', {})
    if ({key: market.get(key) for key in ('brand', 'country', 'language')}
            != {'brand': 'toyota', 'country': 'se', 'language': 'sv'}
            or normalized(car.get('model', {}).get('name')) != 'nya toyota bz4x'
            or car.get('initialized') is not True
            or data.get('carConfigMotorization', {}).get('initialized') is not True):
        raise RefreshError('wrong_market_model_or_uninitialized_configuration')
    return data


def pointer_value(data, pointer):
    value = data
    for key in pointer.lstrip('/').split('/'):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def numeric(raw):
    if isinstance(raw, bool) or not re.fullmatch(r'[0-9]+(?:[.,][0-9]+)?', str(raw)):
        raise RefreshError('interval_or_non_numeric_value')
    return float(str(raw).replace(',', '.'))


def extract_config(data, source):
    grade = data['car'].get('grade', {}).get('name')
    if not isinstance(grade, str) or not re.fullmatch(r'[A-Za-z0-9 +\-]{1,50}', grade):
        raise RefreshError('unsupported_grade_identity')
    variants = data['carConfigMotorization'].get('motorization', [])
    if not isinstance(variants, list) or not 1 <= len(variants) <= 12:
        raise RefreshError('motorization_scope_missing')
    selected = [variant for variant in variants if variant.get('carId') == data['car'].get('id')]
    if (len(selected) != 1 or selected[0].get('engine', {}).get('id') != data['car'].get('motorization', {}).get('engine', {}).get('id')
            or selected[0].get('wheeldrive', {}).get('name') != data['car'].get('motorization', {}).get('wheeldrive', {}).get('name')
            or selected[0].get('price', {}).get('cash') != data['car'].get('price', {}).get('cash')
            or not data['car']['model'].get('id') or not data['car']['model'].get('configVersion')):
        raise RefreshError('selected_car_scope_mismatch')
    rows, ids, names = [], set(), set()
    for index, variant in enumerate(variants):
        identity = variant.get('carId')
        engine = variant.get('engine', {})
        drive = variant.get('wheeldrive', {}).get('name')
        match = re.fullmatch(r'Elmotor ([0-9]+) hk, batteri ([0-9]+,[0-9]+) kWh', engine.get('name', ''))
        if (not re.fullmatch(r'[0-9a-f-]{36}', str(identity)) or identity in ids or not match
                or engine.get('category', {}).get('code') != 'BEV' or engine.get('internalFuelCode') != 'ELECTRIC'
                or engine.get('certification') != 2 or drive not in ('Framhjulsdrift', 'Fyrhjulsdrift')):
            raise RefreshError('unsupported_or_duplicate_variant_identity')
        ids.add(identity)
        power, battery = int(match[1]), float(match[2].replace(',', '.'))
        name = f"{grade} {'FWD' if drive == 'Framhjulsdrift' else 'AWD'} {battery:g} kWh {power} hk"
        if name in names:
            raise RefreshError('duplicate_exact_variant')
        names.add(name)
        base = f'/carConfigMotorization/motorization/{index}'
        row = {field: None for field in FACT_FIELDS}
        proof = {}

        def fact(field, path, value, conversion=None):
            raw = pointer_value(data, path)
            row[field] = value
            proof[field] = {'source_pointer': path, 'raw_value': raw,
                            'quote': json.dumps(raw, ensure_ascii=False, separators=(',', ':')),
                            'manufacturer_variant_id': identity, 'source_url': source['url'],
                            'source_hash': source['content_hash'], 'conversion': conversion}

        price = variant.get('price', {})
        cash = numeric(price.get('cash'))
        if numeric(price.get('exclVat')) * 1.25 != cash:
            raise RefreshError('swedish_vat_price_mismatch')
        if not cash.is_integer():
            raise RefreshError('invalid_cash_price')
        fact('price_sek', base + '/price/cash', int(cash))
        fact('battery_kwh', base + '/engine/name', battery, 'battery_from_exact_engine_label')
        fact('drivetrain', base + '/wheeldrive/name', 'FWD' if drive == 'Framhjulsdrift' else 'AWD', 'swedish_drive_to_code')
        # Unknown cash/list-price classification stays null, even if monthly offers exist.
        for field, code, unit, conversion in (
                ('wltp_range_km', 'PERCOMBINED', 'km', None),
                ('wltp_consumption_kwh_100km', 'ECCOMBINEDWLTP', 'Wh/km', 'Wh_per_km_to_kWh_per_100km')):
            specs = [(i, item) for i, item in enumerate(variant.get('specs', [])) if item.get('internalCode') == code]
            if len(specs) > 1:
                raise RefreshError('conflicting_variant_specs')
            if not specs:
                continue
            spec_index, spec = specs[0]
            if spec.get('unit') != unit or spec.get('certification') != 2:
                continue
            try:
                value = numeric(spec.get('value'))
            except RefreshError:
                continue
            if field == 'wltp_range_km' and not value.is_integer():
                continue
            if field == 'wltp_consumption_kwh_100km' and not value.is_integer():
                continue
            fact(field, f'{base}/specs/{spec_index}/value', int(value) if field == 'wltp_range_km' else value / 10, conversion)
        # Nonselected motorizations must never inherit the selected car's techSpecs.
        if identity == data['car'].get('id'):
            for group_index, group in enumerate(data.get('specs', {}).get('techSpecs', [])):
                for spec_index, spec in enumerate(group.get('data', [])):
                    config = {'TOWCAPBRK': ('tow_kg', 'kg'), 'NRSEAT': ('seats', 'säten')}.get(spec.get('internalCode'))
                    if config and spec.get('unit') == config[1]:
                        value = numeric(spec.get('value'))
                        if not value.is_integer() or config[0] in proof:
                            raise RefreshError('ambiguous_selected_car_spec')
                        fact(config[0], f'/specs/techSpecs/{group_index}/data/{spec_index}/value', int(value))
        row.update(brand='Toyota', model='bZ4X', variant_name=name, source_url=source['url'],
                   source_hash=source['content_hash'], source_quote=engine['name'] + ' | ' + grade + ' | ' + str(int(cash)) + ' SEK',
                   extraction_confidence=0.99, validation_status='needs_review',
                   extraction_payload={'adapter': 'toyota_embedded_config_v1', 'manufacturer_variant_id': identity,
                                       'manufacturer_model_id': data['car']['model'].get('id'),
                                       'model_config_version': data['car']['model'].get('configVersion'),
                                       'grade': grade, 'power_hp': power, 'field_evidence': proof},
                   validation_errors=['canonical_identity_mapping_required'])
        errors = validate_draft(row, {source['url']: source})
        if errors:
            raise RefreshError('hard_validation_failed:' + ','.join(errors))
        for field, evidence in proof.items():
            if pointer_value(data, evidence['source_pointer']) != evidence['raw_value']:
                raise RefreshError('evidence_pointer_mismatch')
        rows.append(row)
    return rows


def preserve_intake_state(report, previous):
    if 'pdf' not in report and 'pdf' in previous:
        report['pdf'] = previous['pdf']
    if report.get('staged', 0):
        report['last_successful_stage'] = {'fetched_at': report['checked_at'], 'content_hash': report['content_hash'],
                                           'rows': report['staged']}
    elif previous.get('last_successful_stage'):
        report['last_successful_stage'] = previous['last_successful_stage']
    return report


def legacy_mapping(existing, drafts):
    outcomes = []
    for old in existing:
        candidates = [row for row in drafts if row['drivetrain'] == old.get('drivetrain')]
        reason = 'legacy_battery_identity_missing' if old.get('battery_kwh') is None else 'generation_identity_not_proven'
        outcomes.append({'variant_name': old['variant_name'], 'status': 'needs_mapping', 'reason': reason,
                         'candidates': [row['variant_name'] for row in candidates], 'auto_update_allowed': False})
    return outcomes


def stage_private(client, source, rows):
    before = client.select('public_ev_variants', '*', {'brand': 'eq.Toyota'})
    models = client.select('canonical_models', '*', {'brand': 'eq.Toyota', 'model': 'eq.bZ4X'})
    if len(models) != 1 or models[0]['validation_status'] == 'rejected':
        raise RefreshError('one_existing_canonical_model_required')
    if any(row['source_url'] == HTML_URL for row in before):
        raise RefreshError('source_already_public_requires_atomic_publisher')
    stored = client.select('manufacturer_sources', '*', {'url': 'eq.' + HTML_URL})
    if any(item.get('verified_at') or item.get('extraction_status') in ('validated', 'published', 'published_reviewed')
           or item.get('canonical_model_id') != models[0]['id'] for item in stored):
        raise RefreshError('reviewed_source_must_not_be_overwritten')
    drafts = client.select('extracted_variant_drafts', '*', {'source_url': 'eq.' + HTML_URL})
    if any(item.get('validation_status') in ('validated', 'published', 'published_reviewed') for item in drafts):
        raise RefreshError('reviewed_draft_must_not_be_overwritten')
    sources = client.upsert('manufacturer_sources', [{
        'canonical_model_id': models[0]['id'], 'brand': 'Toyota', 'model': 'bZ4X',
        'url': HTML_URL, 'country': 'SE', 'language': 'sv', 'source_type': 'manufacturer_specs_page',
        'source_name': 'Toyota Sverige', 'source_authority': 'manufacturer',
        'source_validation': 'reachable_official_model_source', 'content_hash': source['content_hash'],
        'http_status': 200, 'final_url': HTML_URL, 'fetched_at': source['fetched_at'],
        'extraction_status': 'extracted', 'extraction_confidence': 0.99,
        'extracted_payload': {'adapter': 'toyota_embedded_config_v1', 'publication_allowed': False},
        'validation_errors': ['canonical_identity_mapping_required']}], 'url')
    if len(sources) != 1:
        raise RefreshError('incomplete_private_source_write')
    staged = client.upsert('extracted_variant_drafts', [dict(row, source_id=sources[0]['id'], canonical_model_id=models[0]['id'])
                                                       for row in rows], 'source_url,variant_name')
    if len(staged) != len(rows):
        raise RefreshError('incomplete_staging_response')
    after = client.select('public_ev_variants', '*', {'brand': 'eq.Toyota'})
    if sorted(before, key=lambda r: r['id']) != sorted(after, key=lambda r: r['id']):
        raise RefreshError('unexpected_public_catalog_change')
    return len(staged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', action='store_true')
    parser.add_argument('--check-pdf', action='store_true')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'public/data/public_ev_variants.json').read_text(encoding='utf-8'))
    if catalog.get('source') != 'supabase_public_ev_variants':
        raise RefreshError('canonical_snapshot_required')
    # SSR occasionally omits initialized data. One bounded retry is allowed,
    # but access denials/reservations are never retried around or bypassed.
    for attempt in range(2):
        fetched = SourceFetcher(document_parser=parse_document).fetch(HTML_URL, {'Toyota'})
        if fetched['status'] != 'reachable' or fetched['final_url'] != HTML_URL:
            raise RefreshError('specification_source_' + fetched['status'])
        try:
            data = config_from_document(fetched['document'])
            break
        except RefreshError as error:
            if str(error) != 'unique_manufacturer_configuration_required' or attempt:
                raise
    source = {'url': HTML_URL, 'brand': 'Toyota', 'model': 'bZ4X', 'source_authority': 'manufacturer',
              'source_type': 'manufacturer_specs_page', 'source_validation': 'reachable_official_model_source',
              'content_hash': fetched['content_hash'], 'fetched_at': datetime.now(timezone.utc).isoformat()}
    rows = extract_config(data, source)
    mapping = legacy_mapping([row for row in catalog['records'] if row['brand'] == 'Toyota'], rows)
    # Keep only the source subset needed to replay every JSON pointer. Never
    # archive unrelated embedded service configuration/tokens in review payloads.
    save(LOCAL / 'source-inputs.json', {'source': source, 'configuration': {
        'commonSettings': {key: data['commonSettings'][key] for key in ('brand', 'country', 'language')},
        'car': {key: data['car'][key] for key in ('id', 'model', 'grade', 'motorization', 'price', 'initialized')},
        'carConfigMotorization': {'initialized': True, 'motorization': [
            {key: item[key] for key in ('carId', 'engine', 'wheeldrive', 'price', 'specs')}
            for item in data['carConfigMotorization']['motorization']]},
        'specs': {'techSpecs': data.get('specs', {}).get('techSpecs', [])}}})
    save(LOCAL / 'drafts.json', rows)
    report = {'checked_at': source['fetched_at'], 'catalog_sha256': catalog['catalog_sha256'],
              'status': 'needs_mapping', 'source_url': HTML_URL, 'content_hash': source['content_hash'],
              'extracted': len(rows), 'candidates': [row['variant_name'] for row in rows], 'legacy_mapping': mapping,
              'staged': stage_private(SupabaseRestClient(), source, rows) if args.stage else 0,
              'published': 0, 'canonical_writes': False, 'remote_writes': args.stage, 'openai_calls': 0}
    if args.check_pdf:
        try:
            candidate, pdf = collect_document()
            report['pdf'] = {'status': 'collected_not_extracted', 'discovery': candidate, 'content_hash': pdf['content_hash'],
                             'pages': len(pdf['document']['pages']), 'published': 0}
        except RefreshError as error:
            report['pdf'] = {'status': 'quarantined', 'reason': str(error), 'published': 0}
    previous = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {}
    preserve_intake_state(report, previous)
    save(REPORT, report)
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        reason = str(error) if isinstance(error, RefreshError) else 'source_or_storage_error'
        report = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'published': 0, 'canonical_writes': False}
        report['last_attempt'] = {'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'quarantined', 'reason': reason}
        save(REPORT, report)
        print('Toyota intake stopped safely; no canonical writes were requested. ' + reason)
        raise SystemExit(1)
