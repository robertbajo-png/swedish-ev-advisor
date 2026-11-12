"""Collect current Swedish Kia technical PDFs for exact-version extraction. No AI or writes to Postgres."""
import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

from audit_catalog_sources import ROOT, SourceFetcher
from variant_refresh import RefreshError

SOURCES = {
    'Ev3': 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev3/Faktablad-Kia-EV3.pdf',
    'Ev4': 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev4/kia-sweden-ev4-specification.pdf',
    'Ev5': 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev5/kia-sweden-ev5-specification.pdf',
    'Ev6': 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev6/kia-sweden-ev6-specification.pdf',
    'Ev9': 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev9/kia-sweden-ev9-gtline-specification.pdf',
}
ADAPTER = 'kia_sweden_technical_pdf_v1'
SCOPES = {
    'Ev3': {'EV3 FWD': ('sr_fwd', 17), 'EV3 FWD Long Range': ('lr_fwd', 17),
            'EV3 Plus FWD Long Range': ('lr_fwd', 17), 'EV3 GT Line FWD Long Range': ('lr_fwd', 19)},
    'Ev4': {'EV4 GT Line FWD Long Range': ('lr_fwd', 19), 'EV4 GT Line AWD Long Range': ('lr_awd', 19)},
    'Ev5': {'EV5 FWD': ('lr_fwd', 18), 'EV5 Plus AWD Long Range': ('lr_awd', 18),
            'EV5 GT Line AWD Long Range': ('lr_awd', 19), 'EV5 GT Line Panorama AWD Long Range': ('lr_awd', 19)},
    'Ev6': {'EV6 RWD': ('lr_rwd', 19), 'EV6 AWD': ('lr_awd', 19)},
    'Ev9': {'EV9 RWD 7-SITS': ('sr_rwd', 19), 'EV9 AWD': ('lr_awd', 19),
            'EV9 AWD GT Line 6-sits': ('lr_awd', 21), 'EV9 AWD GT Line 7-sits': ('lr_awd', 21)},
}


def line(text, pattern):
    matches = list(re.finditer('(?m)^' + pattern + '$', text))
    if len(matches) != 1:
        raise RefreshError('missing_or_ambiguous_technical_row')
    return matches[0]


def extract(payload, variant_name):
    model, source = payload['model'], payload['source']
    if (model not in SOURCES or source.get('final_url') != SOURCES[model]
            or source.get('http_status') != 200 or source.get('status') != 'reachable'
            or not re.fullmatch('[a-f0-9]{64}', source.get('content_hash', ''))):
        raise RefreshError('unverified_exact_swedish_source')
    if variant_name not in SCOPES[model]:
        raise RefreshError('exact_variant_not_supported_or_preliminary')
    scope, wheel = SCOPES[model][variant_name]
    pages = [page for page in payload['pages'] if 'Teknisk specifikation' in page['text']]
    if len(pages) != 1 or not 590 <= pages[0]['width'] <= 600 or not 835 <= pages[0]['height'] <= 850:
        raise RefreshError('technical_pdf_layout_changed')
    page = pages[0]
    text = page['text']
    heading = '\n'.join(text.splitlines()[:7])
    expected_headers = {'Ev3': 'FWD FWD/AWD', 'Ev4': 'FWD AWD', 'Ev5': 'FWD AWD',
                        'Ev6': 'RWD AWD', 'Ev9': 'RWD AWD'}
    if expected_headers[model] not in heading:
        raise RefreshError('technical_columns_changed')
    if re.search('preliminär|homologering', heading, re.I) and model != 'Ev3':
        raise RefreshError('preliminary_technical_data')
    # EV3's explicit AWD qualification does not apply to its FWD columns.
    if model == 'Ev3' and ('(AWD, Preliminär information i väntan på homologering)' not in heading or 'awd' in scope):
        raise RefreshError('ev3_preliminary_scope_changed')
    index = 0 if scope in ('sr_fwd', 'lr_fwd', 'lr_rwd', 'sr_rwd') else 1
    if model == 'Ev3':
        index = 0 if scope == 'sr_fwd' else 1
    evidence, facts = {}, {}

    def add(field, value, match, qualifier=None):
        facts[field] = value
        evidence[field] = dict(value=value, quote=match[0], page=page['page'],
            column_header=heading, technical_scope=scope, wheel_inches=wheel,
            variant_name=variant_name, source_url=source['final_url'], source_hash=source['content_hash'])
        if qualifier:
            evidence[field]['qualification'] = qualifier

    def values(field, pattern, converter=int, shared=False):
        match = line(text, pattern)
        groups = match.groups()
        if len(groups) != (1 if shared else 2):
            raise RefreshError('technical_cell_count_changed')
        value = groups[0] if shared else groups[index]
        add(field, converter(value.replace(' ', '').replace(',', '.')), match)

    values('battery_kwh', r'Batterikapacitet \(kWh\) ([0-9.]+)' + (r' ([0-9.]+)' if model in ('Ev3', 'Ev5', 'Ev9') else ''), float, model in ('Ev4', 'Ev6'))
    if model == 'Ev3':
        values('dc_charge_kw', r'DC snabbladdning max kW ([0-9]+) ([0-9]+)')
        match = line(text, r'Max räckvidd \(km\) enligt WLTP \(Upp till\) FWD ([0-9]+) \(17"\) ([0-9]+) \(17"\) & ([0-9]+) \(19"\)')
        add('wltp_range_km', int(match[1 if scope == 'sr_fwd' else 2 if wheel == 17 else 3]), match, 'WLTP, upp till; standardhjul för utrustningsnivån')
        match = line(text, r'BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv \(liter\) FWD ([0-9]+) / [0-9]+ / [0-9]+')
        add('boot_liters', int(match[1]), match)
        match = line(text, r'Max släpvagnsvikt, bromsat släp ([0-9]+) ([0-9 ]+) / [0-9]+')
        add('tow_kg', int(match[index + 1].replace(' ', '')), match)
    elif model in ('Ev4', 'Ev5'):
        values('dc_charge_kw', r'DC snabbladdning max kW ([0-9]+)', shared=True)
        if model == 'Ev4':
            values('wltp_range_km', r'Max räckvidd \(km\) enligt WLTP \(Upp till\) ([0-9]+) ([0-9]+)')
            values('boot_liters', r'BAGAGEUTRYMME Baksäte uppfällt / nedfällt ([0-9]+) / [0-9]+ ([0-9]+) / [0-9]+')
            values('wltp_consumption_kwh_100km', r'FÖRBRUKNING Blandad, kWh/100km enligt WLTP ([0-9.,]+) ([0-9.,]+)', float)
        else:
            match = line(text, r'Max räckvidd \(km\) enligt WLTP \(Upp till\): ' + ('FWD' if index == 0 else 'AWD') + r' ([0-9]+)km, \(([0-9]+)km GT Line\)')
            add('wltp_range_km', int(match[2 if 'GT Line' in variant_name else 1]), match, 'WLTP, upp till; GT Line separat från övriga nivåer')
            values('boot_liters', r'BAGAGEUTRYMME Baksäte uppfällt / Nedfällt / Frunk ([0-9]+) / [0-9 ]+ / [0-9]+', shared=True)
        values('tow_kg', r'Max släpvagnsvikt, bromsat släp ([0-9 ]+) ([0-9] [0-9]{3})')
    elif model == 'Ev6':
        values('dc_charge_kw', r'DC snabbladdning max ([0-9]+)kW', shared=True)
        values('wltp_range_km', r'Max räckvidd \(km\) enligt WLTP upp till ([0-9]+)\*\* upp till ([0-9]+)\*\*')
        values('boot_liters', r'BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv \(liter\) ([0-9]+) / [0-9]+ / [0-9]+ ([0-9]+) / [0-9]+ / [0-9]+')
        values('tow_kg', r'Max släpvagnsvikt \(obromsat / bromsat släp\) [0-9]+ / ([0-9]+) [0-9]+ / ([0-9]+)')
    else:
        values('dc_charge_kw', r'DC snabbladdning max ([0-9]+)kW', shared=True)
        match = line(text, r'Max räckvidd \(km\) enligt WLTP \(upp till\) upp till ([0-9]+)\* \* upp till ([0-9]+) \(19"\), ([0-9]+) \(21"\)\*\*')
        add('wltp_range_km', int(match[1 if index == 0 else 2 if wheel == 19 else 3]), match, 'WLTP, upp till; 19/21-tumshjul hålls isär')
        values('tow_kg', r'Max släpvagnsvikt \(obromsat / bromsat släp\) [0-9]+ / ([0-9]+) [0-9]+ / ([0-9 ]+)')
        if '6-sits' not in variant_name:
            match = line(text, r'BAGAGEUTRYMME 2-sits / 5-sits / 7-sits / under framhuv \(liter\) [0-9 ]+ / [0-9]+ / ([0-9]+) / [0-9]+')
            add('boot_liters', int(match[1]), match, 'Samtliga sju sittplatser i bruk')
        if 'GT Line' in variant_name:
            match = line(text, r'VIKTER \(kg\) Totalvikt \(7-sits / 6-sits\) [0-9 ]+ / [0-9 ]+')
            add('seats', 6 if '6-sits' in variant_name else 7, match, 'Exakt sittplatsversion i variantnamnet; 6/7-sits hålls isär')
    drive = scope.split('_')[1].upper()
    header_line = line(text, re.escape(expected_headers[model]))
    add('drivetrain', drive, header_line)
    ac = line(text, r'Bilens laddare \(On Board Charger\) \(kW\) ([0-9.]+)')
    # The existing AC database column is integer. Never round 10.5 to 10 or 11.
    held_fields = {'ac_charge_kw': {'value': float(ac[1]), 'reason': 'decimal_database_column_required', 'quote': ac[0]}}
    return dict(brand='Kia', model=model, variant_name=variant_name, facts=facts,
        field_evidence=evidence, held_fields=held_fields, extraction_confidence=0.99,
        adapter=ADAPTER, source=source)


def collect(model, fetcher, output):
    result = fetcher.fetch(SOURCES[model], {'Kia'})
    if result.get('status') != 'reachable':
        raise RefreshError('technical_source_' + result.get('status', 'unknown'))
    body = result.pop('document')
    if not body.startswith(b'%PDF') or result['final_url'] != SOURCES[model]:
        raise RefreshError('exact_swedish_pdf_required')
    digest = hashlib.sha256(body).hexdigest()
    if digest != result['content_hash']:
        raise RefreshError('source_bytes_changed')
    source = {key: result[key] for key in ('status', 'final_url', 'http_status', 'content_hash', 'content_type')}
    source['fetched_at'] = datetime.now(timezone.utc).isoformat()
    pages = []
    with pdfplumber.open(io.BytesIO(body)) as document:
        for index, page in enumerate(document.pages):
            pages.append({'page': index + 1, 'width': page.width, 'height': page.height,
                          'text': page.extract_text(layout=False) or '', 'words': page.extract_words()})
    if not any('Teknisk specifikation' in page['text'] for page in pages):
        raise RefreshError('technical_table_not_found')
    output.mkdir(parents=True, exist_ok=True)
    (output / (digest + '.pdf')).write_bytes(body)
    payload = {'brand': 'Kia', 'model': model, 'source': source, 'pages': pages,
               'database_writes': 0, 'paid_calls': 0}
    (output / (model.lower() + '-source.json')).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'model': model, 'source_hash': digest, 'pages': len(pages),
            'technical_pages': [page['page'] for page in pages if 'Teknisk specifikation' in page['text']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=sorted(SOURCES))
    parser.add_argument('--output', type=Path, default=ROOT / 'data/local/release-data/vehicle-quality-2026-11-12/kia')
    args = parser.parse_args()
    fetcher = SourceFetcher(document_parser=lambda body, _kind: body)
    drafts, held = [], []
    for model in [args.model] if args.model else SOURCES:
        try:
            result = collect(model, fetcher, args.output)
            payload = json.loads((args.output / (model.lower() + '-source.json')).read_text(encoding='utf-8'))
            for variant_name in SCOPES[model]:
                try:
                    drafts.append(extract(payload, variant_name))
                except RefreshError as error:
                    held.append({'model': model, 'variant_name': variant_name, 'reason': str(error)})
            print(json.dumps({**result, 'database_writes': 0, 'paid_calls': 0}), flush=True)
        except RefreshError as error:
            held.append({'model': model, 'reason': str(error)})
    intake = {'adapter': ADAPTER, 'drafts': drafts, 'held': held, 'database_writes': 0, 'paid_calls': 0}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'intake.json').write_text(json.dumps(intake, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'technical_drafts': len(drafts), 'held': held, 'database_writes': 0, 'paid_calls': 0}))


if __name__ == '__main__':
    main()
