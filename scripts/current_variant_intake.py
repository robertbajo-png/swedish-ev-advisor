"""Source-bound replacement profiles. No inherited specifications, AI or database writes."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from audit_catalog_sources import ROOT, SourceFetcher
from kia_price_intake import URL as KIA_URL, extract_rows
from variant_refresh import FACT_FIELDS, RefreshError, one, parse_document

POLICY = 'current_exact_variants_2026_10_v1'
POLESTAR_URL = 'https://www.polestar.com/se/polestar-4-models/polestar-4-coupe/specifications/'
RENAULT_PARENT = 'https://www.renault.se/personbilar/elbilar/r5-e-tech-electric/versioner-och-priser'
KIA_SCOPE = {
    'Ev3': ['EV3'], 'Ev4': ['EV4'], 'Ev5': ['EV5 AWD'], 'Ev9': ['EV9 RWD Standard Range'],
}


def profile(brand, model, name, source, price, quote, adapter):
    if not 100000 <= price <= 3000000:
        raise RefreshError('price_out_of_range')
    return {**{field: None for field in FACT_FIELDS}, 'brand': brand, 'model': model,
        'variant_name': name, 'price_sek': price, 'price_type': 'list_price',
        'source_url': source['final_url'], 'source_hash': source['content_hash'],
        'source_quote': quote, 'source_name': brand + ' Sverige', 'fetched_at': source['fetched_at'],
        'extraction_confidence': 0.99, 'source_authority': 'manufacturer',
        'extraction_payload': {'adapter': adapter, 'policy': POLICY,
            'field_evidence': {'price_sek': {'quote': quote, 'variant': name,
                'source_url': source['final_url'], 'source_hash': source['content_hash']}}}}


def extract_kia(document, source):
    rows = extract_rows(document, source)
    grouped = []
    for model, retired in KIA_SCOPE.items():
        prefix = model.upper() + ' '
        selected = [row for row in rows if row['row_label'].startswith(prefix)]
        if model == 'Ev5':
            selected = [row for row in selected if ' AWD ' in row['row_label']]
        if model == 'Ev9':
            selected = [row for row in selected if row['row_label'] == 'EV9 RWD 7-SITS']
        if not selected:
            raise RefreshError('missing_exact_model_versions')
        profiles = [profile('Kia', model, row['row_label'], source, row['price_sek'],
                            row['source_quote'], 'kia_sweden_exact_price_row_v1') for row in selected]
        grouped.append({'brand': 'Kia', 'model': model, 'retire': retired, 'profiles': profiles})
    return grouped


def extract_polestar4(document, source):
    if source['final_url'] != POLESTAR_URL:
        raise RefreshError('wrong_polestar_body_or_market')
    headings = ['Rear motor', 'Dual motor']
    table = one((table for table in document.nodes('table')
        if [n.text() for n in table.nodes('th')] == headings), 'exact_polestar_columns_required')
    matching = []
    for tr in table.nodes('tr'):
        cells = list(tr.nodes('td'))
        if not cells:
            continue
        if len(cells) != 2 or any(n.attrs.get(k, '1') != '1' for n in cells for k in ('colspan', 'rowspan')):
            raise RefreshError('changed_polestar_table_shape')
        if all([n.text() for n in cell.nodes('label')] == ['Pris från'] for cell in cells):
            matching.append(cells)
    cells = one(matching, 'unique_exact_polestar_price_required')
    profiles = []
    for name, cell in zip(headings, cells):
        text = cell.text()
        match = re.fullmatch(r'Pris från ([0-9 ]+) kr', text)
        if not match:
            raise RefreshError('conditional_polestar_price')
        profiles.append(profile('Polestar', '4', name, source, int(match[1].replace(' ', '')),
            name + ' | ' + text, 'polestar4_coupe_exact_price_v1'))
    return [{'brand': 'Polestar', 'model': '4',
        'retire': ['Long range Dual motor', 'Long range Single motor'], 'profiles': profiles}]


def extract_renault5(text, source):
    # The current importer PDF has two engine rows and three explicit trim columns.
    # Preliminary range/charging values elsewhere in the PDF are deliberately not imported.
    if source.get('discovered_from') != RENAULT_PARENT or not re.fullmatch('[a-f0-9]{64}', source.get('discovery_source_hash', '')):
        raise RefreshError('official_link_evidence_required')
    compact = re.sub(r'\s+', ' ', text)
    if not all(needle in compact for needle in ('Renault 5 E-Tech Electric', 'EVOLUTION TECHNO ICONIC FIVE',
            'Samtliga priser är rekommenderade cirkapriser.')):
        raise RefreshError('renault_price_document_identity_changed')
    # These are full, exact rows, not amounts from finance/service paragraphs.
    matches40 = re.findall(r'(?m)^5 E-Tech electric 40 120 311 0 14,6 AC 11 kW \+ DC 80 kW ([0-9]{3} [0-9]{3}) kr\s+-\s+-\s*$', text)
    matches52 = re.findall(r'(?m)^5 E-Tech electric 52 150 407-410 0 15,1-15,2 AC 11 kW \+ DC 100 kW\s+-\s+([0-9]{3} [0-9]{3}) kr\s+([0-9]{3} [0-9]{3}) kr\s*$', text)
    row40 = one(matches40, 'renault_exact_40_price_row_required')
    row52 = one(matches52, 'renault_exact_52_price_row_required')
    profiles = []
    for name, amount in zip(['evolution 40 kWh', 'techno 52 kWh', 'iconic five 52 kWh'], [row40, *row52]):
        profiles.append(profile('Renault', '5', name, source, int(amount.replace(' ', '')),
            'EVOLUTION TECHNO ICONIC FIVE | ' + name + ' | Rek. cirkapris ' + amount + ' kr',
            'renault5_linked_price_pdf_v1'))
        profiles[-1]['source_authority'] = 'importer'
        profiles[-1]['extraction_payload']['discovered_from'] = RENAULT_PARENT
        profiles[-1]['extraction_payload']['discovery_source_hash'] = source['discovery_source_hash']
    return [{'brand': 'Renault', 'model': '5', 'retire': ['evolution', 'evolution EV 40',
        'iconic five EV 52', 'roland garros EV52', 'techno EV52'], 'profiles': profiles}]


def capture_html(url, brand):
    result = SourceFetcher(document_parser=parse_document).fetch(url, {brand})
    if result.get('status') != 'reachable' or result.get('http_status') != 200:
        raise RefreshError('source_unavailable_' + result.get('status', 'unknown'))
    result['fetched_at'] = datetime.now(timezone.utc).isoformat()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/local/release-data/current-variants/intake.json')
    args = parser.parse_args()
    kia = capture_html(KIA_URL, 'Kia')
    groups = extract_kia(kia['document'], kia)
    polestar = capture_html(POLESTAR_URL, 'Polestar')
    groups.extend(extract_polestar4(polestar['document'], polestar))
    # This helper revalidates the current official parent link, the exact CDN URL,
    # robots/TDM access and raw PDF hash on every collection, including before apply.
    from collect_linked_price_document import collect
    renault = collect()
    if renault.get('status') != 'reachable':
        raise RefreshError('renault_linked_pdf_unavailable')
    groups.extend(extract_renault5(renault['text'], renault))
    payload = {'policy': POLICY, 'groups': groups, 'paid_calls': 0, 'database_writes': 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'groups': len(groups), 'profiles': sum(len(g['profiles']) for g in groups),
        'retire': sum(len(g['retire']) for g in groups), 'paid_calls': 0, 'database_writes': 0}))


if __name__ == '__main__':
    main()
