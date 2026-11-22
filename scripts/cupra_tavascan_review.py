"""Capture CUPRA Sweden Tavascan prices and motor facts for private review only."""

import argparse
import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from openpyxl import load_workbook
from pypdf import PdfReader

from audit_catalog_sources import ROOT, SourceFetcher
from import_mobility_sweden import parse_ranking_sheet
from manufacturer_embedded_data import stock_document, unique_object
from variant_refresh import one, parse_document

BASE = 'https://www.cupraofficial.se'
MODEL = BASE + '/bilar/tavascan'
INDEX = BASE + '/kopa/broschyrer-prislistor'
DOC = BASE + '/content/dam/countries/se/cupra-website/'
PRICE = {year: DOC + f'prislistor/tavascan/cupra-tavascan-modellar-{year % 100}.pdf' for year in (2025, 2026)}
ENERGY = DOC + 'broschyr/cupra-bransledeklaration-okt2026.pdf'
MARKET_INDEX = ('https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/'
                'tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober')
MARKET_WORKBOOK = ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
                   'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
                   'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx')
SOURCES = {'index.html': INDEX, 'model.html': MODEL, 'my25.pdf': PRICE[2025], 'my26.pdf': PRICE[2026],
           'energy.pdf': ENERGY, 'market.html': MARKET_INDEX, 'market.xlsx': MARKET_WORKBOOK}
DRIVE_NACKA = 'https://bilarilager.vwgroup.se/cupra/EWB33D'
DRIVE_ESKILSTUNA = 'https://bilarilager.vwgroup.se/cupra/EZK46X'
DRIVE_DEALER = 'https://mollerbil.se/bilar-i-lager/ezk46x'
DRIVE_SOURCES = {'drive-nacka.html': DRIVE_NACKA, 'drive-eskilstuna.html': DRIVE_ESKILSTUNA,
                 'drive-dealer.html': DRIVE_DEALER}
DRIVE_LINKOPING = 'https://lagerbilar.vwgroup.se/cupra/DRX34F'
DRIVE_OFFER = BASE + '/kopa/erbjudande/tavascan/privat/cupra-tavascan-77-kwh-2wd-286-hk'
ITALIAN_TECH = 'https://www.cupraofficial.it/content/dam/countries/it/cupra-website/listini/2026/11/listino-tavascan-112026.pdf'
VZ_MY25 = {
    'vz-base.html': ('https://bilarilager.vwgroup.se/cupra/HRB38A', 'VZ', 'Swedish edition VZ AWD 250 kW / 340 hk'),
    'vz-drive.html': ('https://bilarilager.vwgroup.se/cupra/BGR07F', 'VZ Drive', 'CUPRA VZ AWD 250 KW / 340 HK'),
    'vz-adrenaline.html': ('https://bilarilager.vwgroup.se/cupra/DNW03D', 'VZ Adrenaline', 'VZ ADRENALINE AWD 250 KW / 340 HK'),
}
YEAR_CHECK_SOURCES = {'drive-linkoping.html': DRIVE_LINKOPING, 'drive-offer.html': DRIVE_OFFER,
                      'italian-tech.pdf': ITALIAN_TECH, **{name: item[0] for name, item in VZ_MY25.items()}}
DRIVE_GAVLE = 'https://bilarilager.vwgroup.se/cupra/LYK12H'
DRIVE_WLTP_STOCK = {plate: f'https://bilarilager.vwgroup.se/cupra/{plate}' for plate in ('MJB63M', 'UON91J')}
DIN_BIL_GAVLE = 'https://dinbil.se/cupra/bilar-i-lager/alla-bilar-i-lager/lyk12h'
IDENTITY_SOURCES = {'drive-gavle.html': DRIVE_GAVLE, 'drive-gavle-dealer.html': DIN_BIL_GAVLE}
FINNISH_TECH = 'https://api.k-auto.fi/priceCatalog/api/PriceCatalog/13a524b6-bec6-4cf2-89a2-40e7b800614c'
NORDIC_SOURCES = {'finnish-tech.pdf': FINNISH_TECH}
DRIVE_HARDWARE = {'battery_kwh': ('Batteristorlek (Netto)', '77 kWh', 77),
                  'battery_gross_kwh_reference': ('Batteristorlek (Brutto)', '82 kWh', 82),
                  'ac_charge_kw': ('Maximal Laddningseffekt AC', '11 kW', 11),
                  'dc_charge_kw': ('Maximal Laddningseffekt DC', '135 kW', 135),
                  'motor_kw_reference': ('Maximal effekt elmotor', '210.00 kW', 210),
                  'tow_kg': ('Sl\u00e4pvikt, bromsad 12%', '1000 kg', 1000),
                  'boot_liters': ('Bagageutrymmesvolym', '540 l', 540)}
EDITIONS = {'Drive': (210, 286, '2WD', 'RWD'), 'VZ': (250, 340, '4WD', 'AWD'),
            'VZ Drive': (250, 340, '4WD', 'AWD'), 'VZ Adrenaline': (250, 340, '4WD', 'AWD')}
LIMIT = 10_000_000


def digest(body):
    return hashlib.sha256(body).hexdigest()


def normalize(text):
    return ' '.join(text.replace('\u00ad', '').split())


def pdf_page(body):
    if not body.startswith(b'%PDF-'):
        raise ValueError('tavascan_official_pdf_required')
    doc = PdfReader(io.BytesIO(body))
    if len(doc.pages) != 1:
        raise ValueError('tavascan_document_layout_changed')
    return doc.pages[0]


def stock_prices(lines, complete_text, year):
    stamp = f'PRISLISTA MODELL\u00c5R {year}, 15 SEPTEMBER 2026'
    scope = f'Samtliga priser \u00e4r inklusive moms och avser lagerbilar av modell\u00e5r {year}.'
    if ('CUPRA TAVASCAN PRISLISTA' not in lines or f'LAGERBILAR MODELL\u00c5R\u2013{year % 100}' not in lines
            or not any(s in complete_text for s in (stamp, stamp.replace('PRISLISTA', 'PRISLIST A')))
            or scope not in lines):
        raise ValueError('tavascan_exact_swedish_stock_list_date_vat_required')
    prefix = 'Tavascan '
    result = {}
    for line in lines:
        if not line.startswith(prefix) or not re.search(r'\b\d+\s*kWh\b', line):
            continue
        match = re.fullmatch(r'Tavascan (.+?) 77 kWh (\d+)\s*kW/(\d+) hk (2WD|4WD) ([\d ]+):[\u2013-]', line)
        if not match:
            raise ValueError('tavascan_exact_stock_edition_row_required')
        edition, power, hp, drive, money = match.groups()
        if edition not in EDITIONS or edition in result or EDITIONS[edition][:3] != (int(power), int(hp), drive):
            raise ValueError('tavascan_exact_edition_motor_drive_required')
        price = int(money.replace(' ', ''))
        if not 100_000 <= price <= 3_000_000:
            raise ValueError('tavascan_stock_price_out_of_range')
        result[edition] = {'value': price, 'source_quote': line, 'scope_quote': scope, 'source_date': '2026-09-15',
                           'price_valid_until': None, 'price_scope': 'manufacturer_swedish_stock_price_list',
                           'model_year': year, 'label': f'Tavascan {edition}', 'motor_kw': int(power),
                           'battery_label_kwh': 77, 'drivetrain': EDITIONS[edition][3]}
    if result.keys() != EDITIONS.keys():
        raise ValueError('tavascan_complete_exact_stock_price_rows_required')
    return result


def energy_rows(lines):
    content = ' '.join(lines)
    if not all(x in content for x in ('OKTOBER 2026', 'WLTP-standarden', 'fordonets grundversion')):
        raise ValueError('tavascan_current_swedish_wltp_declaration_required')
    result = {}
    for line in lines:
        if not line.startswith('Tavascan '):
            continue
        match = re.fullmatch(r'Tavascan 77 kWh Batteri (210|250) kW / (286|340) hk \u2013 (\d+,\d)(?:\u2013(\d+,\d))? 0', line)
        if not match or match[1] in result or int(match[2]) != {'210': 286, '250': 340}[match[1]]:
            raise ValueError('tavascan_exact_wltp_motor_row_required')
        low = float(match[3].replace(',', '.'))
        high = float((match[4] or match[3]).replace(',', '.'))
        if not 5 <= low <= high <= 60:
            raise ValueError('tavascan_wltp_consumption_out_of_range')
        result[match[1]] = {'min_kwh_100km': low, 'max_kwh_100km': high, 'source_quote': line,
                            'scope': 'Swedish WLTP basic configuration by motor, not by specific trim or wheels'}
    if result.keys() != {'210', '250'}:
        raise ValueError('tavascan_two_wltp_motor_rows_required')
    return result


def verify_links(html, base, expected):
    doc = parse_document(html, 'text/html')
    for label, url in expected:
        one((a for a in doc.nodes('a') if urljoin(base, a.attrs.get('href', '')) == url and a.text() == label),
            'tavascan_current_swedish_document_link_required')


def read_market(body):
    if not body.startswith(b'PK\x03\x04'):
        raise ValueError('tavascan_official_market_workbook_required')
    workbook = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        models, _ = parse_ranking_sheet(workbook['Elbil ranking'], MARKET_INDEX)
        row = one((r for r in models if (r.brand_raw, r.model_raw, r.fuel_type_raw) == ('CUPRA', 'TAVASCAN', 'EL')),
                  'tavascan_exact_market_alias_required')
        if row.needs_mapping or row.last_seen_month != '2026-10-01' or row.registrations_last_month <= 0:
            raise ValueError('tavascan_exact_positive_october_presence_required')
        return {'report_month': row.last_seen_month, 'raw_alias': 'CUPRA | TAVASCAN | EL',
                'registrations_month': row.registrations_last_month, 'registrations_ytd': row.registrations_ytd,
                'source_url': MARKET_INDEX, 'workbook_url': MARKET_WORKBOOK, 'source_hash': digest(body)}
    finally:
        workbook.close()


def drive_stock(raw, url):
    if url not in DRIVE_SOURCES.values():
        raise ValueError('tavascan_unapproved_stock_source')
    doc = parse_document(raw, 'text/html')
    if [n.text() for n in doc.nodes('h1')] != ['CUPRA Tavascan']:
        raise ValueError('tavascan_exact_drive_stock_heading_required')
    body = doc.text().partition('Tillbaka CUPRA Tavascan ')[2]
    header, marker, specs = body.partition('Tekniska data ' if url == DRIVE_DEALER else 'Teknisk data ')
    nacka = url == DRIVE_NACKA
    stock_key = 'EWB33D' if nacka else 'EZK46X'
    dealer = 'Bilia Nacka Cupra' if nacka else 'M\u00f6ller Bil Eskilstuna'
    motor_label = '77kWh 286hk/2026/DRIVE' if nacka else 'CUPRA 210 KW / 286 HK'
    factory_label = 'Styrnummer Tavascan Drive Swedish Edition'
    if (not marker or not header.startswith(motor_label + ' Ny ') or factory_label not in header
            or f'Drivmedel El V\u00e4xell\u00e5da Automat Miltal 0 Modell\u00e5r 2026 Registreringsnummer {stock_key}' not in header
            or (url != DRIVE_DEALER and f'\u00c5terf\u00f6rs\u00e4ljare: {dealer}' not in header)
            or (url == DRIVE_DEALER and 'Eskilstuna CUPRA' not in specs)):
        raise ValueError('tavascan_exact_my26_electric_drive_swedish_edition_required')

    def proof(value, quote):
        return {'value': value, 'source_quote': quote, 'source_url': url, 'source_hash': digest(raw)}

    technical, marker, rest = specs.partition('Energideklaration d\u00e4ck')
    if not marker:
        raise ValueError('tavascan_stock_technical_boundary_required')
    fields = {}
    for field, (label, display, value) in DRIVE_HARDWARE.items():
        quote = label + ' ' + display
        if technical.count(label) != 1 or not re.search(rf'(?<!\S){re.escape(quote)}(?!\S)', technical):
            raise ValueError('tavascan_stock_exact_technical_row_changed: ' + field)
        fields[field] = proof(value, quote)
    price = one(re.finditer(r'\bPris (\d{3} \d{3}) kr R\u00e4kna p\u00e5 bill\u00e5n\b', rest), 'tavascan_stock_cash_price_required')
    value = int(price[1].replace(' ', ''))
    if not 100_000 <= value <= 3_000_000:
        raise ValueError('tavascan_stock_price_out_of_range')
    result = {'variant': 'Tavascan Drive Swedish Edition', 'model_year': 2026, 'dealer': dealer,
              'scope': 'individual new Swedish car; not homologation for every wheel or a general list price',
              'identity': proof(motor_label, factory_label), 'fields': fields,
              'cash_offer': {**proof(value, price[0]), 'price_type': 'dealer_offer', 'price_valid_until': None}}
    if url == DRIVE_DEALER:
        car = one(stock_document(raw, 'text/html')['cars'], 'tavascan_unique_dealer_vehicle_schema_required')
        offer = car.get('offers', {})
        if ((car.get('brand', {}).get('name'), car.get('model'), str(car.get('vehicleModelDate')), car.get('itemCondition'),
             car.get('vehicleEngine', {}).get('fuelType'), offer.get('price'), offer.get('priceCurrency'), offer.get('availability'))
                != ('CUPRA', 'Tavascan', '2026', 'https://schema.org/NewCondition', 'El', value, 'SEK', 'https://schema.org/InStock')):
            raise ValueError('tavascan_dealer_car_or_cash_schema_conflict')
        result['dealer_schema_drive_reference'] = car.get('driveWheelConfiguration')
    else:
        result['importer_named_dealer'] = proof(dealer, f'\u00c5terf\u00f6rs\u00e4ljare: {dealer}')
    return result


def swedish_drive_support(files, my26_price):
    nacka, eskilstuna, dealer = (drive_stock(files[name], url) for name, url in DRIVE_SOURCES.items())
    if any(row['fields'][field]['value'] != proof['value'] for field, proof in nacka['fields'].items()
           for row in (eskilstuna, dealer)):
        raise ValueError('tavascan_drive_stock_hardware_conflict')
    if dealer['cash_offer']['value'] != eskilstuna['cash_offer']['value']:
        raise ValueError('tavascan_same_unit_stock_price_disagreement')
    return {'importer_stock_references': [nacka, eskilstuna], 'dealer_stock_reference': dealer,
            'dealer_link_evidence': eskilstuna['importer_named_dealer'],
            'dealer_offer_matches_current_my26_price_list': dealer['cash_offer']['value'] == my26_price['value'],
            'source_decision': 'Moller mirrors the Eskilstuna vehicle. Prefer manufacturer 2WD and rear motor evidence; do not use dealer schema drive or body.',
            'scope': 'private MY26 Drive technical and price corroboration; no WLTP or availability inferred'}


def source_proof(body, url, value, quote):
    return {'value': value, 'source_url': url, 'source_hash': digest(body), 'source_quote': quote}


def importer_stock_identity(raw, url, edition, year, model_code):
    if url not in (DRIVE_NACKA, DRIVE_ESKILSTUNA, DRIVE_LINKOPING, DRIVE_GAVLE,
                   *DRIVE_WLTP_STOCK.values(), *(item[0] for item in VZ_MY25.values())):
        raise ValueError('tavascan_exact_swedish_importer_source_required')
    stock_key = url.rsplit('/', 1)[-1]
    doc = parse_document(raw, 'text/html')
    if [h.text() for h in doc.nodes('h1')] != ['CUPRA Tavascan']:
        raise ValueError('tavascan_stock_identity_heading_mismatch')
    state = json.loads(one((''.join(n.children) for n in doc.nodes('script')
                            if n.attrs.get('id') == '__NEXT_DATA__' and n.attrs.get('type') == 'application/json'),
                           'tavascan_unique_importer_stock_state_required'), object_pairs_hook=unique_object)
    header, separator, _ = doc.text().partition('Teknisk data ')
    factory = f'Styrnummer Tavascan {edition} Swedish Edition'
    if (not separator or state.get('locale') != 'se' or state.get('page') != '/[brandSlug]/[regNr]'
            or state.get('query') != {'brandSlug': 'cupra', 'regNr': stock_key}
            or f'Modell\xe5r {year} Registreringsnummer {stock_key}' not in header
            or not re.search(re.escape(factory) + r'(?:\s|$)', header)):
        raise ValueError('tavascan_mixed_stock_model_year_or_edition')
    props = state['props']['pageProps']
    car = props['car']
    if (props.get('brand') != 'cupra' or (car.get('model'), car.get('modelYear'), car.get('modelCode'),
                                         car.get('fuelType'), car.get('specialBrandCode'))
            != ('Tavascan', year, model_code, 'El', 'Q')):
        raise ValueError('tavascan_importer_factory_code_or_identity_changed')
    if 'wltpInformation' not in car:
        raise ValueError('tavascan_importer_wltp_scope_changed')
    return {'edition': edition, 'model_year': year, 'stock_reference': stock_key,
            'model_code': source_proof(raw, url, model_code, f'car.modelCode: {model_code} | car.modelYear: {year}'),
            'edition_proof': source_proof(raw, url, edition, factory),
            'wltp_state': 'no_wltp_payload' if car['wltpInformation'] is None else 'payload_requires_separate_review',
            'scope': 'Swedish individual factory identity; code alone is not equipment or homologated WLTP'}


def drive_wltp_importer_context(raw, url):
    if url not in DRIVE_WLTP_STOCK.values():
        raise ValueError('tavascan_unregistered_wltp_stock_source')
    # Require the importer's actual Swedish-edition codes as well as the matching unit number.
    identity = importer_stock_identity(raw, url, 'Drive', 2026, 'KR1BCD')
    doc = parse_document(raw, 'text/html')
    state = json.loads(one((''.join(n.children) for n in doc.nodes('script')
                            if n.attrs.get('id') == '__NEXT_DATA__' and n.attrs.get('type') == 'application/json'),
                           'tavascan_unique_importer_stock_state_required'), object_pairs_hook=unique_object)
    car = state['props']['pageProps']['car']
    packages = {code: one((row.get('text') for row in car['factoryEquipment'] if row.get('code') == code),
                          'tavascan_drive_wltp_importer_package_required') for code in ('P80', 'PF0', 'YC1')}
    order = car.get('comissionId')
    mileage = car.get('mileage')
    if (car.get('regNumber') != identity['stock_reference'] or type(order) is not int or not re.fullmatch(r'\d{13}', str(order))
            or car.get('used') is not False or type(mileage) is not int or not 0 <= mileage <= 1
            or packages.get('P80') != 'Styrnummer Tavascan Drive Swedish Edition'
            or not str(packages.get('PF0', '')).startswith('DRIVE:') or not packages.get('YC1')):
        raise ValueError('tavascan_drive_wltp_importer_edition_mismatch')
    return {'identity': identity, 'order': str(order), 'equipment_codes': list(packages), 'importer_mileage_reference': mileage,
            'importer_drive_type_reference': car.get('driveType')}


def gavle_drive_price(importer_raw, dealer_raw, list_price):
    identity = importer_stock_identity(importer_raw, DRIVE_GAVLE, 'Drive', 2026, 'KR1BCD')
    distributor = parse_document(importer_raw, 'text/html').text()
    header, _, technical = distributor.partition('Teknisk data ')
    specs, marker, cash = technical.partition('Energideklaration d\xe4ck')
    dealer = parse_document(dealer_raw, 'text/html')
    dealer_text = dealer.text()
    price = one(re.finditer(r'\bPris (\d{3} \d{3}) kr R\xe4kna p\xe5 bill\xe5n\b', cash), 'tavascan_gavle_importer_cash_required')
    visible = one(re.finditer(r'\bKontantpris (\d{3} \d{3}) kr Intresseanm\xe4lan\b', dealer_text),
                  'tavascan_gavle_dealer_cash_required')
    number = int(price[1].replace(' ', ''))
    car = one(stock_document(dealer_raw, 'text/html')['cars'], 'tavascan_gavle_unique_dealer_schema_required')
    offer = car.get('offers', {})
    schema_identity = (car.get('brand', {}).get('name'), car.get('model'), str(car.get('vehicleModelDate')),
                       car.get('itemCondition'), car.get('vehicleEngine', {}).get('fuelType'),
                       car.get('driveWheelConfiguration'), offer.get('price'), offer.get('priceCurrency'))
    if (not marker or '\xc5terf\xf6rs\xe4ljare: Cupra G\xe4vle' not in header or 'Miltal 0' not in header
            or any(label + ' ' + display not in specs for label, display, _ in DRIVE_HARDWARE.values())
            or [h.text() for h in dealer.nodes('h1')] != ['CUPRA Tavascan Endurance']
            or 'Din Bil / CUPRA G\xe4vle' not in dealer_text or 'Drivlina Bakhjulsdrift' not in dealer_text
            or not any('LYK12H' in img.attrs.get('alt', '') for img in dealer.nodes('img'))
            or schema_identity != ('CUPRA', 'Tavascan', '2026', 'https://schema.org/NewCondition', 'El',
                                   'https://schema.org/RearWheelDriveConfiguration', number, 'SEK')
            or offer.get('availability') != 'https://schema.org/InStock'
            or int(visible[1].replace(' ', '')) != number or number != list_price['value']):
        raise ValueError('tavascan_gavle_dealer_cash_or_identity_conflict')
    return {'identity': identity,
            'importer_named_dealer': source_proof(importer_raw, DRIVE_GAVLE, 'CUPRA G\xe4vle', '\xc5terf\xf6rs\xe4ljare: Cupra G\xe4vle'),
            'cash_offer': {**source_proof(dealer_raw, DIN_BIL_GAVLE, number, visible[0]), 'price_type': 'dealer_offer'},
            'agrees_with_my26_stock_list': True,
            'scope': 'One additional Swedish car; dealer calls it Endurance, the importer binds exact Drive Swedish Edition'}


def drive_equipment(raw):
    doc = parse_document(raw, 'text/html')
    header, marker, _ = doc.text().partition('Teknisk data ')
    identity = 'Drivmedel El V\u00e4xell\u00e5da Automat Miltal 0 Modell\u00e5r 2026 Registreringsnummer DRX34F'
    required = ('CUPRA Tavascan CUPRA 210 KW / 286 HK Ny', identity,
                'Styrnummer Tavascan Drive Swedish Edition', 'L\u00e4ttmetallf\u00e4lgar 19" Vulcano')
    tires = 'D\u00e4ck 235/55 R19 fram och 255/50 R19 bak'
    drive = 'Ombordladdare Max 11 kW AC Bakhjulsdrift'
    if (not marker or [n.text() for n in doc.nodes('h1')] != ['CUPRA Tavascan']
            or not all(x in header for x in (*required, tires, drive))):
        raise ValueError('tavascan_exact_my26_drive_and_wheels_required')
    return {'model_year': 2026, 'drivetrain': source_proof(raw, DRIVE_LINKOPING, 'RWD', drive),
            'wheel_inches': source_proof(raw, DRIVE_LINKOPING, 19, tires),
            'identity': source_proof(raw, DRIVE_LINKOPING, 'Tavascan Drive Swedish Edition', identity)}


def drive_offer_reference(raw, model_list_price):
    doc = parse_document(raw, 'text/html')
    details = doc.text().partition('CUPRA Tavascan DRIVE 2WD Swedish Edition 77kWh (210kW) 100% EL ')[2]
    scope = 'G\u00e4ller begr\u00e4nsat antal lagerbilar av modell\u00e5r 2026.'
    if ([n.text() for n in doc.nodes('h1')] != ['CUPRA Tavascan DRIVE 2WD']
            or not details.startswith('R\u00e4ckvidd upp till ') or scope not in details
            or re.search(r'modell\u00e5r 20(?!26)\d{2}', details, re.I)
            or '19" L\u00e4ttmetallf\u00e4lgar "VULCANO"' not in details):
        raise ValueError('tavascan_drive_swedish_my26_offer_scope_required')
    price = one(re.finditer(r'Editionpris: (\d{3}\.\d{3}) kr', details), 'tavascan_drive_offer_price_required')
    distance = re.match(r'R\u00e4ckvidd upp till (\d{3}) km', details)
    consumption = one(re.finditer(r'Br\u00e4nslef\u00f6rbrukning\*\*\* (\d{2},\d) kWh/100km', details),
                      'tavascan_drive_offer_combined_consumption_required')
    if (int(price[1].replace('.', '')) != model_list_price['value'] or distance is None
            or not 5 <= float(consumption[1].replace(',', '.')) <= 60
            or 'blandad k\u00f6rning liter/100 km enligt WLTP' not in details):
        raise ValueError('tavascan_drive_offer_price_or_wltp_basis_conflict')
    return {'advertised_upper_range_km': source_proof(raw, DRIVE_OFFER, int(distance[1]), distance[0]),
            'advertised_consumption': source_proof(raw, DRIVE_OFFER, float(consumption[1].replace(',', '.')), consumption[0]),
            'manufacturer_cash_offer': source_proof(raw, DRIVE_OFFER, model_list_price['value'], price[0]),
            'scope_quote': scope, 'model_year': 2026, 'wheel_inches': 19, 'publication_approved': False}


def drive_base_profile(raw, report):
    references = report['drive_standard_wheel_and_offer_references']
    offer = references['offer']
    equipment = references['equipment']
    identity = report['swedish_factory_stock_scope']['existing_stock_identities']
    stock = report['swedish_my26_drive_stock_support']['importer_stock_references']
    price = report['my26_stock_price_references']['Drive']
    gavle = report['swedish_factory_stock_scope']['independent_gavle_price_support']
    if (offer['model_year'], offer['wheel_inches'], equipment['model_year'], equipment['wheel_inches']['value'],
            equipment['drivetrain']['value']) != (2026, 19, 2026, 19, 'RWD'):
        raise ValueError('tavascan_exact_base_drive_profile_scope_required')
    if (offer['manufacturer_cash_offer']['value'] != price['value']
            or gavle['cash_offer']['value'] != price['value'] or not gavle['agrees_with_my26_stock_list']):
        raise ValueError('tavascan_base_drive_profile_price_conflict')

    # The offer's range is a maximum. Only its starred energy row has a WLTP method and base-vehicle scope.
    text = parse_document(raw, 'text/html').text()
    method = ('***Br\u00e4nsledeklaration och utsl\u00e4ppsv\u00e4rden \u00e4r uppm\u00e4tta i enlighet med g\u00e4llande lagstiftning '
              'och g\u00e4ller bil i grundversion. De anges vid blandad k\u00f6rning liter/100 km enligt WLTP.')
    energy = offer['advertised_consumption']
    upper = offer['advertised_upper_range_km']
    if (text.count(method) != 1 or text.count(energy['source_quote']) != 1
            or text.index(method) < text.index(energy['source_quote'])
            or energy['source_hash'] != digest(raw) or upper['source_hash'] != digest(raw)
            or energy['source_url'] != DRIVE_OFFER or upper['source_url'] != DRIVE_OFFER):
        raise ValueError('tavascan_drive_base_scope_wltp_footnote_required')

    def factory(url, source_hash):
        found = one((row for row in identity if row['model_code']['source_url'] == url),
                    'tavascan_exact_drive_stock_factory_reference_required')
        if (found['edition'], found['model_year'], found['model_code']['value'], found['model_code']['source_hash']) != (
                'Drive', 2026, 'KR1BCD', source_hash):
            raise ValueError('tavascan_drive_factory_scope_mismatch')
        return found['model_code']

    wheel = equipment['wheel_inches']
    factory(wheel['source_url'], wheel['source_hash'])
    if [r['identity']['source_url'] for r in stock] != [DRIVE_NACKA, DRIVE_ESKILSTUNA]:
        raise ValueError('tavascan_exact_two_swedish_stock_sources_required')
    for row in stock:
        factory(row['identity']['source_url'], row['identity']['source_hash'])
    fields = {'drivetrain': equipment['drivetrain'], 'seats': report['model_facts']['seats'],
              'wltp_consumption_kwh_100km': {**energy,
                  'basis': 'official_swedish_my26_drive_base_combined_wltp',
                  'method_excerpt': 'grundversion; blandad k\u00f6rning enligt WLTP'}}
    for key in ('battery_kwh', 'ac_charge_kw', 'dc_charge_kw', 'tow_kg', 'boot_liters'):
        first, second = (row['fields'][key] for row in stock)
        if (first['value'] != second['value'] or any(p['source_url'] != row['identity']['source_url']
                or p['source_hash'] != row['identity']['source_hash'] for p, row in zip((first, second), stock, strict=True))):
            raise ValueError('tavascan_drive_stock_technical_profile_conflict:' + key)
        fields[key] = {**first, 'corroboration': second}
    return {'edition': 'Drive Swedish Edition', 'market': 'SE', 'model_year': 2026, 'model_code': 'KR1BCD',
            'standard_wheel_inches': wheel, 'technical_fields': fields, 'price': price,
            'separate_dealer_price_proof': gavle['cash_offer'], 'advertised_max_range_only': upper,
            'alternative_motor_level_consumption': report['motor_wltp_references']['210'],
            'decision': 'Use the exact Swedish MY26 19-inch base edition combined consumption, not the generic motor row.',
            'held': ['wltp_range_km'], 'publication_approved': False}


def vz_my25_stock(raw, url, edition, header_label):
    doc = parse_document(raw, 'text/html')
    header, marker, specs = doc.text().partition('Teknisk data ')
    code = url.rsplit('/', 1)[-1]
    edition_label = f'Styrnummer Tavascan {edition} Swedish Edition'
    if (not marker or [n.text() for n in doc.nodes('h1')] != ['CUPRA Tavascan']
            or 'CUPRA Tavascan ' + header_label + ' Ny ' not in header
            or edition_label not in header.partition('Fabriksinformation ')[2]
            or f'Miltal 0 Modell\u00e5r 2025 Registreringsnummer {code}' not in header
            or 'Drivmedel El' not in header):
        raise ValueError('tavascan_exact_vz_my25_edition_required')
    technical, marker, prices = specs.partition('Energideklaration d\u00e4ck')
    if not marker:
        raise ValueError('tavascan_vz_stock_technical_boundary_required')
    values = {'battery_net_kwh': (77, 'Batteristorlek (Netto) 77 kWh'),
              'battery_gross_kwh': (82, 'Batteristorlek (Brutto) 82 kWh'),
              'drive': ('AWD', 'Drivning 1-vxl Fyrhjulsdrift'), 'motor_kw': (250, 'Max. effekt 250 kW (340 hk)'),
              'braked_towing_kg': (1200, 'Sl\u00e4pvikt, bromsad 12% 1200 kg'), 'boot_liters': (540, 'Bagageutrymmesvolym 540 l')}
    if not all(re.search(rf'(?<!\S){re.escape(quote)}(?!\S)', technical) for _, quote in values.values()):
        raise ValueError('tavascan_vz_exact_technical_scope_changed')
    price = one(re.finditer(r'\bPris ([1-9]\d{2} \d{3}) kr (?:Privatleasing|R\u00e4kna p\u00e5 bill\u00e5n)\b', prices),
                'tavascan_vz_separate_cash_price_required')
    amount = int(price[1].replace(' ', ''))
    if amount > 3_000_000:
        raise ValueError('tavascan_vz_cash_price_out_of_range')
    return {'model_year': 2025, 'edition': edition, 'identity': source_proof(raw, url, edition, edition_label),
            'stock_references': {k: source_proof(raw, url, v, q) for k, (v, q) in values.items()},
            'cash_offer': {**source_proof(raw, url, amount, 'Pris ' + price[1] + ' kr'), 'price_type': 'dealer_offer'},
            'holds': ['different model year', 'no vehicle DC/AC peak or combined WLTP established here']}


def italian_reference(raw):
    if not raw.startswith(b'%PDF-'):
        raise ValueError('tavascan_italian_manufacturer_pdf_required')
    pages = PdfReader(io.BytesIO(raw)).pages
    if len(pages) != 14 or not all(x in normalize(pages[0].extract_text()) for x in ('A.M. 2026', '04.11.2026', 'TAVASCAN')):
        raise ValueError('tavascan_italian_my26_edition_required')
    rows = [normalize(s) for s in pages[12].extract_text(extraction_mode='layout').splitlines()]
    quotes = {'motor_columns': 'Potenza massima (kW/CV) 140 / 190 210 / 286 250 / 340',
              'battery_net': 'Capacit\u00e0 della batteria netta (kWh) 58 77 77',
              'battery_gross': 'Capacit\u00e0 della batteria lorda (kWh) 61 82 82',
              'ac_test': 'Tempi di ricarica in AC 11 kW 0-100% SoC (h) 6h 0 min 8h 0 min 8h 0 min',
              'dc_test': 'Tempi di ricarica in DC 10-80% SoC (h) 26 min (105 kW) 29 min (135 kW) 29 min (135 kW)',
              'braked_towing': 'Massa rimorchiabile con freni 12% (kg) 1.000 1.000 1800',
              'wltp_range': 'Autonomia WLTP (km) 403 - 441 468 - 557 451 - 533',
              'wltp_consumption': 'Consumo di energia ciclo combinato WLTP Min-Max (kWh/100 km) 15,4 - 17,2 15,6 - 18,8 16,5 - 19,6',
              'wheels': 'Cerchi 19\u201d 20\u201d / 21\u201d 20\u201d / 21\u201d'}
    if any(rows.count(quote) != 1 for quote in quotes.values()):
        raise ValueError('tavascan_italian_technical_columns_changed')
    return {'source_url': ITALIAN_TECH, 'source_hash': digest(raw), 'page': 13, 'market': 'IT',
            'edition_date': '2026-11-04', 'model_year': 2026, 'quotes': quotes,
            'scope': 'Italian motor/market comparison only; includes no Swedish variant facts',
            'vz_braked_tow_reference_kg': 1800, 'vz_test_condition_dc_kw': 135,
            'drive_wheel_reference_inches': [20, 21]}


def finnish_wltp_reference(raw):
    if not raw.startswith(b'%PDF-'):
        raise ValueError('tavascan_finnish_importer_pdf_required')
    pages = PdfReader(io.BytesIO(raw)).pages
    if len(pages) != 8:
        raise ValueError('tavascan_finnish_document_layout_changed')
    price_page = pages[1].extract_text()
    headers = ('Mallikoodi\nmv. 2025 B', 'EU-yhd.\nkWh/100 km', 'NETTO/BRUTTO',
               'matka km**\n(WL TP)', 'Hinnasto 2.3.2026', 'K Auto Oy', 'www.cupraofficial.fi')
    if any(price_page.count(header) != 1 for header in headers) or 'mv. 2026' in price_page:
        raise ValueError('tavascan_finnish_model_year_or_wltp_columns_changed')
    rows = normalize(price_page)
    trims = {}
    for package, (prefix, option_codes, label) in {
        'TUR': ('KR1B7D TUR ', 'TUR PW1 PF0 P80 YOS', 'Endurance Turn On'),
        'TIM': ('', 'TIM PW2 P28 WED YOS', 'Endurance Immersive Turn On'),
    }.items():
        match = one(re.finditer(rf'\b{option_codes} ({prefix}KR1BCD {package} 210/286 1\) 0 '
                                r'(\d{2}\.\d) 77/82 (\d{3})) (?=\d{2} \d{3} \d+ \d{2} \d{3}\b)', rows),
                    'tavascan_finnish_exact_equipment_wltp_row_required')
        if len(re.findall(rf'\bKR1BCD {package}\b', rows)) != 1:
            raise ValueError('tavascan_finnish_duplicate_equipment_code')
        consumption, distance = float(match[2]), int(match[3])
        if not (5 <= consumption <= 60 and 50 <= distance <= 1200):
            raise ValueError('tavascan_finnish_wltp_out_of_range')
        trims[package] = {'label': label, 'option_codes': option_codes, 'ev_range_km': distance,
                          'combined_kwh_100km': consumption, 'quote': match[1]}
    wheel = '19" kevytmetallivanteet Vulcano Machined (8J x 19), 235/55 R19 renkaat edess\xe4, 255/50 R19 renkaat takana'
    if pages[4].extract_text().splitlines().count(wheel) != 1:
        raise ValueError('tavascan_finnish_wheel_reference_changed')
    return {'source_url': FINNISH_TECH, 'source_hash': digest(raw), 'issued_date': '2026-03-02',
            'market': 'FI', 'model_code': 'KR1BCD', 'model_year_label': '2025 B', 'wltp_table_page': 2,
            'wheel_table_page': 5, 'wheel_reference_quote': wheel, 'equipment_references': trims,
            'scope': 'Finnish MY25 B comparison only; no figures are admitted for Swedish MY26.',
            'publication_approved': False}


def review(files, *, with_drive_profile=False):
    with_drive = bool(DRIVE_SOURCES.keys() & files.keys())
    expected = SOURCES | DRIVE_SOURCES if with_drive else SOURCES
    with_year_check = bool(YEAR_CHECK_SOURCES.keys() & files.keys())
    if with_year_check:
        expected = expected | YEAR_CHECK_SOURCES
    with_identities = bool(IDENTITY_SOURCES.keys() & files.keys())
    if with_identities:
        if not with_drive or not with_year_check:
            raise ValueError('tavascan_identity_review_requires_existing_stock_scope')
        expected = expected | IDENTITY_SOURCES
    with_nordic = bool(NORDIC_SOURCES.keys() & files.keys())
    if with_nordic:
        if not with_identities:
            raise ValueError('tavascan_nordic_review_requires_exact_swedish_identity')
        expected = expected | NORDIC_SOURCES
    if files.keys() != expected.keys() or any(not 0 < len(b) <= LIMIT for b in files.values()):
        raise ValueError('tavascan_complete_registered_capture_required')
    verify_links(files['index.html'], INDEX, [(f'Prislista modell\u00e5r {year % 100} (15 sep-26)', url) for year, url in PRICE.items()]
                 + [('Ladda ner', ENERGY)])
    verify_links(files['market.html'], MARKET_INDEX, [('M\u00e5nadsrapport Nyregistreringar okt 2026.xlsx', MARKET_WORKBOOK)])
    model = parse_document(files['model.html'], 'text/html')
    body = model.text()
    labels = ['100% ELEKTRISK SUV COUP\u00c9', 'Bagagerumsvolym 540 L', 'S\u00e4ten 5']
    if [n.text() for n in model.nodes('h1')] != ['CUPRA TAVASCAN'] or not all(label in body for label in labels):
        raise ValueError('tavascan_official_model_body_boot_seats_required')
    references = {}
    for year in PRICE:
        raw = files[f'my{year % 100}.pdf']
        page = pdf_page(raw)
        rows = stock_prices([normalize(s) for s in page.extract_text(extraction_mode='layout').splitlines()],
                            normalize(page.extract_text()), year)
        references[str(year)] = {key: {**value, 'source_url': PRICE[year], 'source_hash': digest(raw)}
                                 for key, value in rows.items()}
    raw = files['energy.pdf']
    energy = energy_rows([normalize(s) for s in pdf_page(raw).extract_text(extraction_mode='layout').splitlines()])
    report = {'status': 'review_complete_held', 'market': 'SE', 'model_key': 'cupra|tavascan',
            'publication_approved': False, 'database_writes': 0, 'market_index': read_market(files['market.xlsx']),
            'my26_stock_price_references': references['2026'], 'my25_stock_price_references': references['2025'],
            'model_facts': {field: {'value': value, 'source_quote': label, 'source_url': MODEL,
                                    'source_hash': digest(files['model.html'])} for field, value, label in
                            zip(('body_type', 'boot_liters', 'seats'), ('SUV', 540, 5), labels, strict=True)},
            'motor_wltp_references': {k: {**v, 'source_url': ENERGY, 'source_hash': digest(raw)} for k, v in energy.items()},
            'held': ['independent price check and current ordinary order or stock scope by edition',
                     'exact technical identity, battery net/gross and WLTP scope for each MY26 edition',
                     'exact onboard AC, vehicle peak DC, braked towing and reviewed production-model photo']}
    if with_drive:
        report['swedish_my26_drive_stock_support'] = swedish_drive_support(files, references['2026']['Drive'])
    if with_year_check:
        report['drive_standard_wheel_and_offer_references'] = {
            'equipment': drive_equipment(files['drive-linkoping.html']),
            'offer': drive_offer_reference(files['drive-offer.html'], references['2026']['Drive']),
            'scope_decision': 'Keep the advertised consumption separate from the dated Swedish motor declaration; no exact certified WLTP is selected.',
        }
        report['vz_cross_year_and_market_references'] = {
            'swedish_my25_stock': [vz_my25_stock(files[name], *identity) for name, identity in VZ_MY25.items()],
            'italian_my26_motor_data': italian_reference(files['italian-tech.pdf']),
            'scope_decision': 'Do not transfer the 1200 kg Swedish MY25 or 1800 kg Italian MY26 value to Swedish MY26. DC test power is not a vehicle maximum.',
        }
    if with_identities:
        drive = [(name, url, 'Drive', 2026, 'KR1BCD') for name, url in (
            ('drive-nacka.html', DRIVE_NACKA), ('drive-eskilstuna.html', DRIVE_ESKILSTUNA), ('drive-linkoping.html', DRIVE_LINKOPING))]
        vz = [(name, url, edition, 2025, 'KR1CED') for name, (url, edition, _) in VZ_MY25.items()]
        report['swedish_factory_stock_scope'] = {
            'existing_stock_identities': [importer_stock_identity(files[name], url, edition, year, code)
                                          for name, url, edition, year, code in (*drive, *vz)],
            'independent_gavle_price_support': gavle_drive_price(files['drive-gavle.html'], files['drive-gavle-dealer.html'],
                                                               references['2026']['Drive']),
            'exact_swedish_wltp_admitted': False,
        }
    if with_nordic:
        report['finnish_wltp_scope_crosscheck'] = finnish_wltp_reference(files['finnish-tech.pdf'])
    if with_drive_profile:
        if not with_identities:
            raise ValueError('tavascan_drive_profile_requires_exact_swedish_identity')
        report['private_my26_drive_profile'] = drive_base_profile(files['drive-offer.html'], report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    parser.add_argument('--with-swedish-drive-stock', action='store_true', help='Capture exact MY26 Drive stock technical evidence')
    parser.add_argument('--with-year-crosscheck', action='store_true', help='Capture Drive equipment and VZ year/market comparisons')
    parser.add_argument('--with-stock-identity', action='store_true', help='Also capture factory codes and a separate Swedish Drive cash offer')
    parser.add_argument('--with-nordic-crosscheck', action='store_true', help='Compare Finnish equipment-level WLTP without admitting it as Swedish data')
    parser.add_argument('--with-drive-profile', action='store_true', help='Build the private MY26 Drive technical review with a held range')
    args = parser.parse_args()
    if (args.with_swedish_drive_stock or args.with_year_crosscheck or args.with_stock_identity
            or args.with_nordic_crosscheck or args.with_drive_profile) and not args.capture:
        parser.error('evidence flags require --capture')
    if args.with_stock_identity and not (args.with_swedish_drive_stock and args.with_year_crosscheck):
        parser.error('--with-stock-identity requires both existing stock and year checks')
    if args.with_nordic_crosscheck and not args.with_stock_identity:
        parser.error('--with-nordic-crosscheck requires --with-stock-identity')
    if args.with_drive_profile and not args.with_stock_identity:
        parser.error('--with-drive-profile requires --with-stock-identity')
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    if root != ROOT.resolve() / 'data/local/release-data' or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', s, re.I) for s in root.parts):
        raise ValueError('tavascan_private_release_directory_required')
    if args.capture:
        sources = SOURCES | DRIVE_SOURCES if args.with_swedish_drive_stock else SOURCES
        if args.with_year_crosscheck:
            sources = sources | YEAR_CHECK_SOURCES
        if args.with_stock_identity:
            sources = sources | IDENTITY_SOURCES
        if args.with_nordic_crosscheck:
            sources = sources | NORDIC_SOURCES
        fetcher = SourceFetcher(timeout=25, max_bytes=LIMIT, document_parser=lambda body, _: body,
                                text_parser=lambda *_: '', url_policy=lambda url, _: url in sources.values())
        files = {}
        for name, url in sources.items():
            source = fetcher.fetch(url, {'Cupra'})
            if (source['status'], source.get('http_status'), source.get('final_url')) != ('reachable', 200, url):
                raise ValueError('tavascan_official_source_unavailable: ' + url)
            files[name] = source['document']
        report = review(files, with_drive_profile=args.with_drive_profile)
        report['captured_at'] = datetime.now(timezone.utc).isoformat()
        folder = Path(tempfile.mkdtemp(prefix='cupra-tavascan-review-', dir=root))
        for name, body in files.items():
            (folder / name).write_bytes(body)
        (folder / 'review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    else:
        folder = args.replay.resolve(strict=True)
        if (folder != args.replay.absolute() or folder.parent != root
                or not re.fullmatch(r'cupra-tavascan-review-[a-z0-9_]+', folder.name)):
            raise ValueError('tavascan_private_capture_required')

        def read(name):
            path = folder / name
            if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_size > LIMIT:
                raise ValueError('tavascan_regular_capture_file_required')
            return path.read_bytes()

        saved = json.loads(read('review.json'))
        optional = DRIVE_SOURCES | YEAR_CHECK_SOURCES | IDENTITY_SOURCES | NORDIC_SOURCES
        sources = SOURCES | {name: url for name, url in optional.items() if (folder / name).exists()}
        report = review({name: read(name) for name in sources}, with_drive_profile='private_my26_drive_profile' in saved)
        report['captured_at'] = saved['captured_at']
        if report != saved:
            raise ValueError('tavascan_capture_or_review_changed')
    print(json.dumps({'output': str(folder / 'review.json'), 'sources': len(sources), 'publication_approved': False}))


if __name__ == '__main__':
    main()
