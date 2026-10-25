"""Private, price-only Enyaq intake. No canonical writes or publisher path."""
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


def extract_prices(text, source, expected, today=None):
    today = today or datetime.now(timezone.utc).date()
    if (source.get('url'), source.get('final_url'), source.get('brand'), source.get('model')) != (URL, URL, 'Skoda', 'Enyaq'):
        raise RefreshError('unapproved_exact_price_source')
    if not re.fullmatch('[a-f0-9]{64}', source.get('content_hash', '')):
        raise RefreshError('source_hash_required')
    if {row['variant_name'] for row in expected} != set(NAMES.values()) or len(expected) != 4:
        raise RefreshError('exact_solid_edition_group_required')
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    title = next((line for line in lines if normalized(line) == normalized('Škoda Enyaq Solid Edition')), None)
    if not title:
        raise RefreshError('edition_changed')
    if 'selection sportline rs' not in normalized(text):
        raise RefreshError('price_columns_changed')
    expiry_matches = list(re.finditer(r'g\s*äller\s+tom\s+(\d{4}-\d{2}-\d{2})', text, re.I))
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
    if 'erbjudandet är begränsat' not in normalized(text):
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
        row.update(brand='Skoda', model='Enyaq', variant_name=variant,
                   price_sek=price, price_type='campaign_price', price_valid_until=expiry,
                   source_url=URL, source_hash=source['content_hash'],
                   source_quote=title + ' | ' + quote + ' | ' + expiry_quote,
                   extraction_confidence=0.99, validation_status='extracted',
                   extraction_payload={'adapter': 'skoda_enyaq_price_private_v1',
                                       'field_evidence': {'price_sek': proof,
                                                          'price_type': {**proof, 'quote': 'Erbjudandet är begränsat'},
                                                          'price_valid_until': {**proof, 'quote': expiry_quote}},
                                       'unimported_fields': 'Estimated WLTP and all technical specifications'})
        rows.append(row)
    return rows


def main():
    catalog = json.loads((ROOT / 'public/data/public_ev_variants.json').read_text(encoding='utf-8'))
    expected = [row for row in catalog['records'] if (row['brand'], row['model']) == ('Skoda', 'Enyaq')]
    fetched = SourceFetcher().fetch(URL, {'Skoda'})
    if fetched['status'] != 'reachable' or 'pdf' not in fetched.get('content_type', ''):
        raise RefreshError('official_pdf_not_reachable')
    source = {'url': URL, 'final_url': fetched['final_url'], 'brand': 'Skoda', 'model': 'Enyaq',
              'content_hash': fetched['content_hash'], 'fetched_at': datetime.now(timezone.utc).isoformat()}
    drafts = extract_prices(fetched['text'], source, expected)
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
