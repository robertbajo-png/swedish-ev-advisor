"""Review the Swedish bZ4X Touring Active Tech FWD, without staging or publishing."""

import argparse
import hashlib
import io
import json
import re
import tempfile
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

import pdfplumber

from audit_catalog_sources import SourceFetcher
from import_mobility_sweden import parse_elbil_ranking
from manufacturer_embedded_data import unique_object
from toyota_chr_plus_intake import MARKET_URL
from variant_refresh import one, parse_document

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'https://www.toyota.se/bilar/bz4x-touring'
SPECS = MODEL + '/specifications'
BROCHURE = 'https://pdf.toyotasverigebroschyr.com/price-list/bz4x-touring'
SOURCES = {'model.html': MODEL, 'specifications.html': SPECS, 'brochure.pdf': BROCHURE,
           'market.xlsx': MARKET_URL}
MODEL_ID = '005b05cd-028a-4116-9df3-e6ee345cd7a8'
PRECISION = '6.HD'
GRADE_ID = '984d769f-e823-4e3a-b421-b8fbdbbff93b'
CAR_ID = '4dd8d99a-24a0-4de3-b84f-bb4c6fbf1526'
ENGINE_ID = '9b8f6669-46f0-452a-b598-ade4d30578b1'
ENGINE_NAME = 'Elmotor 224 hk, batteri 74,7 kWh'
CASH = 569_900
CHARGE = 'Ombordladdare 11 kW AC och kapacitet f\xf6r snabbladdning 150 kW DC'
FIELD_ROWS = (
    ('battery_kwh', 'AC95940B-E5CE', '74,7', 'kWh', 74.7),
    ('dc_charge_kw', '3EB2873F-D852', '150', 'kW', 150),
    ('tow_kg', 'TOWCAPBRK', '750', 'kg', 750),
    ('seats', 'NRSEAT', '5', 's\xe4ten', 5),
    ('boot_liters', 'VDALUCAPREARUP', '669', 'l', 669),
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def compact(text):
    return ' '.join(text.split())


def document(body, url):
    doc = parse_document(body, 'text/html')
    require([n.attrs.get('lang') for n in doc.nodes('html')] == ['sv']
            and [n.attrs.get('href') for n in doc.nodes('link') if n.attrs.get('rel') == 'canonical'] == [url],
            'touring_exact_swedish_document_required')
    return doc


def configuration(doc):
    candidates = []
    for node in doc.nodes('div'):
        if not node.attrs.get('id', '').endswith('-data') or not node.text().startswith('{'):
            continue
        data = json.loads(''.join(v for v in node.children if isinstance(v, str)), object_pairs_hook=unique_object)
        if 'carConfigMotorization' in data:
            candidates.append(data)
    return one(candidates, 'touring_exact_configuration_required')


def verify_configuration(c):
    market = {'brand': 'toyota', 'country': 'se', 'language': 'sv', 'component': 'car-config'}
    require(all(c['commonSettings'].get(k) == v for k, v in market.items()), 'touring_swedish_scope_required')
    car = c['car']
    model = car['model']
    require((model['id'], model['name'], model['defaultCar'], model['configVersion'], model['steering'],
             car['body']['name'], car['id'], car['grade']['id'], car['grade']['name'])
            == (MODEL_ID, 'Nya bZ4X Touring', CAR_ID, PRECISION, 'L', 'SUV Kombi', CAR_ID, GRADE_ID, 'Active Tech')
            and car['initialized'] is True and c['carConfigMotorization']['initialized'] is True,
            'touring_active_tech_fwd_identity_required')
    grade = one((g for g in c['grades']['items'] if g['id'] == GRADE_ID), 'touring_grade_required')
    require((grade['name'], grade['defaultCarId']) == ('Active Tech', CAR_ID), 'touring_default_grade_changed')
    motor = one((m for m in c['carConfigMotorization']['motorization'] if m['carId'] == CAR_ID),
                'touring_exact_bev_motor_required')
    for choice in (car['motorization'], motor):
        engine, drive = choice['engine'], choice['wheeldrive']
        require((engine['id'], engine['name'], engine['category']['code'], engine['internalFuelCode'],
                 drive['internalCode'], drive['name'])
                == (ENGINE_ID, ENGINE_NAME, 'BEV', 'ELECTRIC', '2WD', 'Framhjulsdrift'),
                'touring_exact_bev_motor_or_drive_changed')
    require(motor['engine'].get('certification') == 2, 'touring_motor_certification_required')
    for choice in (car, motor):
        price = choice['price']
        require(price['cash'] == CASH and price['exclVat'] * 1.25 == CASH and price['promotions'] == [],
                'touring_base_cash_not_configured_extra_or_monthly_required')
    result = {}
    for field, code, unit, shown, value in (
        ('wltp_range_km', 'PERCOMBINED', 'km', '591', 591),
        ('wltp_consumption_kwh_100km', 'ECCOMBINEDWLTP', 'Wh/km', '140', 14),
    ):
        row = one((x for x in motor['specs'] if x['internalCode'] == code), 'touring_exact_motor_spec_required')
        require((row['unit'], row['value'], row['certification']) == (unit, shown, 2), 'touring_final_wltp_required')
        result[field] = (value, f"{ENGINE_NAME} | {code}: {shown} {unit} | certification=2")
    tech = [row for group in c['specs']['techSpecs'] for row in group['data']]
    for field, code, shown, unit, value in (*FIELD_ROWS, ('tyre', 'TYRSIZE', '235/60R18', '', None)):
        row = one((x for x in tech if x['internalCode'] == code), 'touring_exact_technical_row_required:' + field)
        require((row['unit'], compact(row['value'])) == (unit, shown), 'touring_engineering_scope_changed:' + field)
        if value is not None:
            result[field] = (value, f"{row['name']}: {shown} {unit}")
    require(any(x['name'] == CHARGE and x['standard'] is True for x in c['specs']['standardEquipment']),
            'touring_standard_onboard_charger_required')
    return result | {'ac_charge_kw': (11, CHARGE), 'drivetrain': ('FWD', 'Framhjulsdrift | 2WD')}


def verify_brochure(raw, as_of):
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        require(len(pdf.pages) == 9, 'touring_brochure_shape_changed')
        title = compact(pdf.pages[0].extract_text() or '')
        grade = compact(pdf.pages[2].crop((0, 0, 225, pdf.pages[2].height)).extract_text() or '')
        tech = compact(pdf.pages[5].extract_text() or '')
        terms = compact(pdf.pages[8].extract_text() or '')
    cash = one(re.finditer(r'bZ4X Touring Active Tech Fr\xe5n: 569 900 kr Easy Bill\xe5n fr\xe5n: [\d ]+ kr/m\xe5n Elf\xf6rbrukning \(WLTP\): 14 kWh/100km', grade),
               'touring_exact_fwd_brochure_cash_required')[0]
    require('BZ4X TOURING PRISLISTA OCH BROSCHYR' in title.upper()
            and all(q in tech for q in (ENGINE_NAME + ' Elmotor 380 hk, batteri 74,7 kWh',
                                        'Dragvikt bromsat sl\xe4p (kg) 750 1500', 'Antal platser 5 5',
                                        'R\xe4ckvidd (WLTP) 591 km 479 - 528 km')),
            'touring_brochure_different_model_or_motor_table')
    dated = one(re.finditer(r'Uppdaterad: (\d{4}-\d{2}-\d{2}) \d{2}:\d{2}', terms),
                'touring_brochure_date_required')
    updated = date.fromisoformat(dated[1])
    require(0 <= (as_of - updated).days <= 7 and 'ca-pris fr\xe5n generalagent' in terms,
            'touring_current_general_agent_brochure_required')
    return updated.isoformat(), cash


def review(folder, as_of):
    raw = {name: (folder / name).read_bytes() for name in SOURCES}
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in raw.items()}
    model = document(raw['model.html'], MODEL)
    require(any(a.attrs.get('href') == BROCHURE for a in model.nodes('a'))
            and 'helelektriska, kombi' in model.text(), 'touring_exact_official_brochure_link_required')
    pack = verify_configuration(configuration(document(raw['specifications.html'], SPECS)))
    updated, quote = verify_brochure(raw['brochure.pdf'], as_of)
    rows, _ = parse_elbil_ranking(folder / 'market.xlsx', MARKET_URL)
    row = one((r for r in rows if (r.brand_raw, r.model_raw, r.fuel_type_raw) == ('TOYOTA', 'BZ4X TOURING', 'EL')),
              'touring_distinct_market_row_required')
    require(row.normalized_model == 'bz4x touring' and not row.needs_mapping
            and row.last_seen_month == '2026-10-01' and 0 < row.registrations_last_month <= row.registrations_ytd,
            'touring_market_source_scope_changed')

    def proof(name, value, snippet):
        return dict(value=value, source_url=SOURCES[name], source_hash=hashes[name], quote=snippet)

    return dict(status='private_touring_source_review', brand='Toyota', model='bZ4X Touring',
                variant='Active Tech FWD', factory_id=CAR_ID, body_type='Kombi', standard_wheel_inches=18,
                evidence={field: proof('specifications.html', value, snippet) for field, (value, snippet) in pack.items()},
                cash_from=dict(**proof('brochure.pdf', CASH, quote), page=3, price_type='manufacturer_from',
                               brochure_updated=updated),
                market=dict(row=asdict(row), source_url=MARKET_URL, source_hash=hashes['market.xlsx']),
                source_hashes=hashes, publication_approved=False, database_writes=0, paid_calls=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    parser.add_argument('--verified-report', action='store_true', help='Emit the replayed private packet as JSON')
    args = parser.parse_args()
    require(not args.verified_report or args.replay, 'touring_report_requires_verified_replay')
    local = ROOT / 'data/local/release-data'
    require(local.resolve(strict=True) == local and not any(
        re.fullmatch(r'onedrive(?:commercial|consumer)?', part, re.I) for part in local.parts), 'touring_local_scope_required')
    current = datetime.now(timezone.utc)
    if args.capture:
        folder = Path(tempfile.mkdtemp(prefix='toyota-touring-capture-', dir=local))
        fetcher = SourceFetcher(timeout=30, max_bytes=14_000_000, document_parser=lambda body, kind: body,
            url_policy=lambda url, brands: url in SOURCES.values(), text_parser=lambda body, kind: '')
        for name, url in SOURCES.items():
            source = fetcher.fetch(url, {'Toyota'} if name != 'market.xlsx' else set())
            require(source['status'] == 'reachable' and source['http_status'] == 200 and source['final_url'] == url,
                    'touring_exact_source_unavailable:' + name)
            (folder / name).write_bytes(source['document'])
        result = review(folder, current.date())
        result['fetched_at'] = current.isoformat()
        (folder / 'review.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    else:
        folder = args.replay.absolute()
        require(folder.resolve(strict=True) == folder and folder.parent == local, 'touring_private_source_packet_required')
        recorded = json.loads((folder / 'review.json').read_text(encoding='utf-8'))
        observed = datetime.fromisoformat(recorded['fetched_at'])
        result = review(folder, observed.date())
        require(result | {'fetched_at': recorded['fetched_at']} == recorded, 'touring_captured_source_or_proof_changed')
        if args.verified_report:
            print(json.dumps(recorded))
            return
    print(json.dumps(dict(folder=str(folder), status=result['status'], technical_fields=len(result['evidence']),
                          publication_approved=False, database_writes=0, replay=not args.capture)))


if __name__ == '__main__':
    main()
