"""Private, price-only Enyaq intake. No canonical writes or publisher path."""
import hashlib
import io
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from audit_catalog_sources import ROOT, SourceFetcher, normalized
from variant_refresh import FACT_FIELDS, RefreshError

URL = 'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660'
NAMES = {'85': 'Solid Edition 85', '85x': 'Solid Edition 85x',
         '85x Sportline': 'Solid Edition 85x Sportline', 'RS': 'Solid Edition RS'}
PRICE_COLUMNS = {'85': (0, 2), '85x': (0, 2), '85x Sportline': (1, 0), 'RS': (2, 0)}


# The underlying SourceFetcher still validates the exact HTTPS source, robots,
# response, body size and full PDF SHA. Page boundaries are extracted from those
# same bytes, never from a separate URL or a caller-selected page.
def pdf_price_pages(body, content_type):
    if 'pdf' not in content_type:
        raise ValueError('price_source_not_pdf')
    from pypdf import PdfReader
    return [page.extract_text() or '' for page in PdfReader(io.BytesIO(body)).pages]


def fetch_price_source():
    return SourceFetcher(document_parser=pdf_price_pages).fetch(URL, {'Skoda'})


EXPIRY = re.compile(r'g\s*äller\s+tom\s+(\d{4}-\d{2}-\d{2})', re.I)
LIMITED = re.compile(r'erbjudandet är begränsat', re.I)


def page_bound_vehicle_offer(text, source, document_pages):
    """Only resolve a differing date for the recognized three-page layout.

    Page 1 is the vehicle price table. Page 2 is explicitly optional equipment
    and has its own footer; page 3 is standard equipment. A second vehicle
    table, a second date on page 1, a date outside the options footer, or an
    unbound/changed page structure still quarantines the entire document.
    """
    dates = {match.group(1) for match in EXPIRY.finditer(text)}
    if len(dates) <= 1:
        return text, None
    if (not isinstance(document_pages, list) or len(document_pages) != 3
            or any(not isinstance(p, str) or not p.strip() for p in document_pages)
            or '\n'.join(document_pages).strip() != text.strip()
            or hashlib.sha256(text.encode('utf-8')).hexdigest() != source.get('text_hash')):
        raise RefreshError('campaign_expiry_ambiguous')
    vehicle, options, standard = document_pages
    def lines(page):
        return [re.sub(r'\s+', ' ', l).strip() for l in page.splitlines() if l.strip()]
    def heading(page):
        return next((l for l in lines(page) if not re.fullmatch(r'\d+/\d+', l)), '')
    if (normalized(heading(options)) != 'tillvalsutrustning'
            or normalized(heading(standard)) != 'standardutrustning'):
        raise RefreshError('campaign_expiry_ambiguous')
    for equipment in (options, standard):
        if ('selection sportline rs' in normalized(equipment)
                or any(normalized(line) == normalized('Škoda Enyaq Solid Edition')
                       or re.match(r'^(?:85x Sportline|85x|85|RS) \d{3}\b', line)
                       or re.match(r'^Prislista\b', line, re.I) for line in lines(equipment))):
            raise RefreshError('campaign_expiry_ambiguous')
    vehicle_dates = {m.group(1) for m in EXPIRY.finditer(vehicle)}
    option_matches = list(EXPIRY.finditer(options))
    option_footer = '\n'.join(lines(options)[-3:])
    if (len(vehicle_dates) != 1 or not LIMITED.search(vehicle)
            or len(option_matches) != 1 or EXPIRY.search(standard)
            or not LIMITED.search(option_footer)
            or len(list(EXPIRY.finditer(option_footer))) != 1
            or option_matches[0].group(1) in vehicle_dates):
        raise RefreshError('campaign_expiry_ambiguous')
    context = {'source_page': 1, 'source_page_count': 3,
               'page_text_sha256': hashlib.sha256(vehicle.encode('utf-8')).hexdigest(),
               'separate_optional_equipment_page': 2,
               'optional_equipment_footer_expiry': option_matches[0].group(1)}
    return vehicle, context


def extract_prices(text, source, expected, today=None, *, document_pages=None):
    today = today or datetime.now(timezone.utc).date()
    if (source.get('url'), source.get('final_url'), source.get('brand'), source.get('model')) != (URL, URL, 'Skoda', 'Enyaq'):
        raise RefreshError('unapproved_exact_price_source')
    if not re.fullmatch('[a-f0-9]{64}', source.get('content_hash', '')):
        raise RefreshError('source_hash_required')
    if {row['variant_name'] for row in expected} != set(NAMES.values()) or len(expected) != 4:
        raise RefreshError('exact_solid_edition_group_required')
    text, page_context = page_bound_vehicle_offer(text, source, document_pages)
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    title = next((line for line in lines if normalized(line) == normalized('Škoda Enyaq Solid Edition')), None)
    if not title:
        raise RefreshError('edition_changed')
    if 'selection sportline rs' not in normalized(text):
        raise RefreshError('price_columns_changed')
    expiry_matches = list(EXPIRY.finditer(text))
    dates = {match.group(1) for match in expiry_matches}
    if len(dates) != 1:
        raise RefreshError('campaign_expiry_ambiguous')
    expiry = dates.pop()
    expiry_quote = expiry_matches[0].group(0)
    try:
        if date.fromisoformat(expiry) < today:
            raise RefreshError('campaign_expired')
    except ValueError:
        raise RefreshError('invalid_campaign_expiry') from None
    qualification = LIMITED.search(text)
    if not qualification:
        raise RefreshError('campaign_qualification_missing')
    # The source labels its range as estimated. This adapter imports prices only.
    rows = []
    for motor, variant in NAMES.items():
        pattern = re.compile(re.escape(motor) + r' \d{3} \d{3} \d{3} 0 ((?:[–−-] )*)(\d{3} \d{3}) kr((?: [–−-])*)')
        matches = [(line, pattern.fullmatch(line)) for line in lines if pattern.fullmatch(line)]
        if len(matches) != 1:
            raise RefreshError('ambiguous_or_changed_price_row:' + motor)
        quote, match = matches[0]
        if (len(match.group(1).split()), len(match.group(3).split())) != PRICE_COLUMNS[motor]:
            raise RefreshError('price_in_wrong_trim_column:' + motor)
        price = int(match.group(2).replace(' ', ''))
        if not 100000 <= price <= 3000000:
            raise RefreshError('price_out_of_bounds')
        row = {field: None for field in FACT_FIELDS}
        proof = {'source_url': URL, 'source_hash': source['content_hash'],
                 'quote': quote, 'scope': 'exact_variant_row', 'row_label': motor, 'edition': title}
        if page_context:
            proof.update(page_context)
        row.update(brand='Skoda', model='Enyaq', variant_name=variant,
                   price_sek=price, price_type='campaign_price', price_valid_until=expiry,
                   source_url=URL, source_hash=source['content_hash'],
                   source_quote=title + ' | ' + quote + ' | ' + qualification.group(0) + ' | ' + expiry_quote,
                   extraction_confidence=0.99, validation_status='extracted',
                   extraction_payload={'adapter': 'skoda_enyaq_price_private_v1',
                                       'field_evidence': {'price_sek': proof,
                                                          'price_type': {**proof, 'quote': qualification.group(0)},
                                                          'price_valid_until': {**proof, 'quote': expiry_quote}},
                                       'unimported_fields': 'Estimated WLTP and all technical specifications'})
        rows.append(row)
    return rows


def main():
    catalog = json.loads((ROOT / 'public/data/public_ev_variants.json').read_text(encoding='utf-8'))
    expected = [row for row in catalog['records'] if (row['brand'], row['model']) == ('Skoda', 'Enyaq')]
    fetched = fetch_price_source()
    if fetched['status'] != 'reachable' or 'pdf' not in fetched.get('content_type', ''):
        raise RefreshError('official_pdf_not_reachable')
    source = {'url': URL, 'final_url': fetched['final_url'], 'brand': 'Skoda', 'model': 'Enyaq',
              'content_hash': fetched['content_hash'], 'text_hash': fetched['text_hash'],
              'fetched_at': datetime.now(timezone.utc).isoformat()}
    drafts = extract_prices(fetched['text'], source, expected, document_pages=fetched['document'])
    directory = ROOT / 'data/local/release-data/skoda-price-intake'
    directory.mkdir(parents=True, exist_ok=True)
    packet = {'source': source, 'drafts': drafts, 'source_text': fetched['text'],
              'publications': 0, 'remote_writes': False,
              'held_reason': 'A separately tested transactional price-only publisher is required; estimated specifications were not verified'}
    (directory / (source['content_hash'] + '.json')).write_text(json.dumps(packet, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'private_price_drafts': len(drafts), 'source_hash': source['content_hash'],
                      'price_type': 'campaign_price', 'price_valid_until': drafts[0]['price_valid_until'],
                      'estimated_specifications_imported': 0, 'remote_writes': False,
                      'publications': 0, 'openai_calls': 0, 'held_reason': packet['held_reason']}))


if __name__ == '__main__':
    main()
