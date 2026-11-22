"""Build a private, replayable Renault 4 Swedish EV52 source review."""

import argparse
import hashlib
import io
import json
import math
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pdfplumber
from openpyxl import load_workbook
from pypdf import PdfReader

from audit_catalog_sources import ROOT, SourceFetcher
from import_mobility_sweden import parse_ranking_sheet
from manufacturer_embedded_data import unique_object
from variant_refresh import Node, RefreshError, one, parse_document

MODEL = 'https://www.renault.se/personbilar/elbilar/r4-e-tech-electric'
VERSIONS = MODEL + '/versioner-och-priser'
DIMENSIONS = MODEL + '/matt-och-dimensioner'
CHARGING = MODEL + '/laddning'
PRICE_LIST = ('https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/'
              'hedin/distribution-cars/renaultsesite/cardocuments/prislista-renault-4-e-tech-electric.pdf')
PRESS = ('https://renault.mynewsdesk.com/pressreleases/'
         'renault-4-e-tech-electric-nu-till-foersaeljning-i-sverige-3401914')
MARKET = ('https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/'
          'tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober')
WORKBOOK = ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
            'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
            'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx')
SOURCES = {'versions.html': VERSIONS, 'prices.pdf': PRICE_LIST, 'dimensions.html': DIMENSIONS,
           'charging.html': CHARGING, 'press.html': PRESS, 'market.html': MARKET, 'market.xlsx': WORKBOOK}
CONFIGURATOR = 'https://www.renault.se/bygg-din-bil'
STOCK_SOURCES = {
    'configurator.html': CONFIGURATOR,
    'techno-stock.html': 'https://rnautomotive.se/bilar/240062/pc-nc-renault-4-2026',
    'rn-dealer.html': 'https://rnautomotive.se/om-oss',
    'plein-sud-stock.html': 'https://hedinautomotive.se/bilar/kop-bil/260151/pc-nc-renault-4-e-tech-2027',
    'hedin-dealer.html': 'https://hedinautomotive.se/anlaggningar/hedin-automotive-halmstad',
}
CURRENT_STOCK_SOURCES = {
    **STOCK_SOURCES,
    'evolution-stock.html': 'https://rnautomotive.se/bilar/261900/pc-nc-renault-4-e-tech-2027',
    'skobes-stock.html': ('https://www.skobes.se/fordon/nykoping/417306cd-8059-550d-8b78-cd3863bdbb85/'
                          'renault-4-e-tech-techno-plein-sud-52kwh/'),
    'skobes-dealer.html': 'https://www.skobes.se/anlaggningar/nykoping/',
}
LEGACY_STOCK_SOURCES = {**SOURCES, **STOCK_SOURCES}
ALL_SOURCES = {**SOURCES, **CURRENT_STOCK_SOURCES}
EFFICIENCY_SOURCES = {
    **ALL_SOURCES,
    'finnvedens-techno.html': 'https://finnvedensbil.se/bil/renault-r4-e-tech-techno-52kwh-tcu98n/',
    'finnvedens-linkoping.html': 'https://finnvedensbil.se/linkoping/',
}
TECHNO_SOURCES = {
    **EFFICIENCY_SOURCES,
    'hedin-techno-18.html': 'https://hedinautomotive.se/bilar/kop-bil/258900/pc-nc-renault-4-e-tech-2026',
    'renault-sales-locator.html': 'https://www.renault.se/om-oss/aterforsaljare',
}
TRIMS = ('EVOLUTION', 'TECHNO', 'TECHNO PLEIN SUD')
CARD_LABELS = ('evolution EV52', 'techno', 'techno EV52 Plein Sud')
VERSION_IDS = ('cd7efc7a-2549-4f9f-aa73-7c0d3a70dbad', '63132d5d-7c23-44cc-9606-f9dd4c2e50e2',
               'e3d31004-ff9d-461b-9669-a4c807f31ad7')
AUTH_RN = 'RN Automotive AB \xe4r auktoriserad \xe5terf\xf6rs\xe4ljare och servicepartner'
AUTH_SKOBES = 'Vi \xe4r auktoriserad \xe5terf\xf6rs\xe4ljare av nya bilar fr\xe5n Volvo, Renault, Dacia, Maxus och Lynk & Co.'
RANGE = 'Homologerad r\xe4ckvidd WLTP - blandad k\xf6rning (km)'
PRELIMINARY = 'R\xc4CKVIDD & F\xd6RBRUKNING (PREL. DATA)'
LIMIT = 12_000_000


def clean(text):
    return ' '.join((text or '').split())


def evidence(key, raw, value, quote, **extra):
    return {'value': value, 'quote': quote, 'source_url': TECHNO_SOURCES[key],
            'source_hash': hashlib.sha256(raw).hexdigest(), **extra}


def shared_cells(table, rows, label):
    index = one((i for i, row in enumerate(rows) if row[0] == label), 'r4_exact_technical_row:' + label)
    headers = table.rows[0].cells
    merged = table.rows[index].cells[1:]
    value = rows[index][1]
    # Empty PDF cells are not carry-forwards: require a single box across all three trims.
    if (len(merged) != 3 or merged[0] is None or merged[1:] != [None, None] or not value
            or merged[0][0] != headers[1][0] or merged[0][2] != headers[3][2]):
        raise ValueError('r4_full_width_shared_technical_cell_required:' + label)
    return value


def price_list(raw):
    if not raw.startswith(b'%PDF-'):
        raise ValueError('r4_pdf_required')
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        if len(pdf.pages) != 3:
            raise ValueError('r4_pdf_layout_changed')
        cover, _, technical = pdf.pages
        cover_lines = [clean(line) for line in PdfReader(io.BytesIO(raw)).pages[0].extract_text().splitlines()]
        if not all(x in cover_lines for x in
                   ('RENAULT 4 E-TECH ELECTRIC', 'Rek. cirkaprislista G\xe4llande fr\xe5n 12 oktober 2026')):
            raise ValueError('r4_current_swedish_price_list_required')
        grid = one((t for t in cover.extract_tables() if len(t[0]) == 10 and t[0][0] == 'Modell'
                    and tuple(map(clean, t[0][7:])) == (*TRIMS[:2], TRIMS[2] + ' (CANVAS TOP)')),
                   'r4_exact_three_price_columns_required')
        row = one((r for r in grid[1:] if r[0] == '4 E-Tech electric'), 'r4_exact_bev_price_row_required')
        if row[:7] != ['4 E-Tech electric', '52', '150', '394-407', '0', '15,2-15,7', 'AC 11 kW + DC 100 kW']:
            raise ValueError('r4_current_price_row_identity_changed')
        if not all(re.fullmatch(r'[1-9]\d{2} \d{3} kr', value or '') for value in row[7:]):
            raise ValueError('r4_exact_cash_prices_required')
        if 'RN Nordic AB' not in clean(technical.extract_text()):
            raise ValueError('r4_swedish_importer_imprint_required')
        table = one((t for t in technical.find_tables() if t.extract()[0] == ['Teknisk specifikation', *TRIMS]),
                    'r4_exact_three_technical_columns_required')
        rows = table.extract()
        if not any(r[0] == PRELIMINARY for r in rows):
            raise ValueError('r4_wltp_status_changed_review_required')
        wltp = one((r[1:] for r in rows if r[0] == RANGE), 'r4_exact_wltp_reference_row_required')
        if len(wltp) != 3 or not all(re.fullmatch(r'[1-9]\d{2}', v or '') for v in wltp):
            raise ValueError('r4_separate_wltp_columns_required')

        fields = {
            'seats': ('Antal sittplatser', '5', 5),
            'battery_kwh': ('Kapacitet (kWh)', '52', 52),
            'ac_charge_kw': ('Inbyggd laddare', 'Anpassningsbar en-/trefas fr\xe5n 1 kW till 11 kW', 11),
            'dc_charge_kw': ('Snabbladdning upp till DC 100 kW (15-80%)', '30 min', 100),
            'tow_kg': ('Maxvikt f\xf6r bromsat/obromsat sl\xe4p (kg)', '750/750', 750),
            'boot_liters': ('Bagagerumsvolym (L)', '420 (VDA 339)', 420),
            'motor_kw_reference': ('Max. effekt kW (hk)', '110 (150)', 110),
            'tyre_reference': ('Referensf\xe4lgar (18")', '195/60 R18 96H', '195/60 R18 96H'),
        }
        hardware = {}
        for field, (label, expected, value) in fields.items():
            display = clean(shared_cells(table, rows, label))
            if display != expected:
                raise ValueError('r4_shared_field_changed:' + field)
            hardware[field] = evidence('prices.pdf', raw, value, f'{label} | {display}', page=3,
                                       scope='shared_across_three_electric_52_kwh_150_hp_trims')
        profiles = {}
        for trim, money, km in zip(TRIMS, row[7:], wltp, strict=True):
            profiles[trim] = {
                'price': evidence('prices.pdf', raw, int(money[:-3].replace(' ', '')),
                                  f'4 E-Tech electric 52 kWh 150 hk | {trim} | {money}',
                                  page=1, price_type='list_price', date='2026-10-12'),
                'preliminary_wltp_range': evidence('prices.pdf', raw, int(km), f'{PRELIMINARY} | {RANGE} | {trim} | {km}',
                                                   page=3, scope='preliminary_do_not_publish_as_certified'),
            }
        return profiles, hardware, evidence('prices.pdf', raw, [15.2, 15.7], row[5], page=1,
                                            scope='preliminary_model_interval_not_per_trim')


def verify_link(raw, base, target, label):
    if not any(urljoin(base, a.attrs.get('href', '')) == target and a.text() == label
               for a in parse_document(raw, 'text/html').nodes('a')):
        raise ValueError('r4_current_source_link_required:' + label)


def web_crosscheck(raw, profiles):
    verify_link(raw, VERSIONS, PRICE_LIST, 'prislista')
    doc = clean(parse_document(raw, 'text/html').text())
    bundle = one(re.finditer(r'G\xe4ller vid k\xf6p av nya Renault 4 t\.o\.m\. (\d{1,2}/\d{1,2} 20\d\d)\.', doc),
                 'r4_dated_website_price_terms_required')
    if 'rekommenderade priser inklusive moms' not in doc:
        raise ValueError('r4_cash_price_vat_required')
    expiry = datetime.strptime(bundle[1], '%d/%m %Y').date().isoformat()
    checks = {}
    for trim in TRIMS:
        label = trim.lower().replace(' plein sud', '') + ' EV52' + (' Plein Sud' if trim.endswith('PLEIN SUD') else '')
        match = one(re.finditer(rf'{re.escape(label)} ?: Smarta Bill\xe5n med Renault Finans:'
                               r'(?:(?!Restskulden|Smarta Bill\xe5n med Renault Finans:).){0,700}?'
                               r'Kontantpriset \xe4r (\d+) kr och du betalar en kontantinsats', doc),
                    'r4_exact_cash_price_required:' + trim)
        if int(match[1]) != profiles[trim]['price']['value']:
            raise ValueError('r4_website_cash_price_conflict:' + trim)
        checks[trim] = evidence('versions.html', raw, int(match[1]), f'{label} | Kontantpriset \xe4r {match[1]} kr',
                                scope='manufacturer_cash_price_not_finance_payment_or_independent_source',
                                website_offer_valid_until=expiry)
    return checks


def market_data(raw):
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        models, _ = parse_ranking_sheet(workbook['Elbil ranking'], MARKET)
        row = one((m for m in models if (m.brand_raw, m.model_raw, m.fuel_type_raw) == ('RENAULT', '4', 'EL')),
                  'r4_exact_market_alias_required')
        if row.needs_mapping or row.last_seen_month != '2026-10-01' or row.registrations_last_month <= 0:
            raise ValueError('r4_positive_october_market_row_required')
        return evidence('market.xlsx', raw, row.registrations_last_month, 'RENAULT | 4 | EL',
                        report_month=row.last_seen_month, registrations_ytd=row.registrations_ytd,
                        market_source_url=MARKET, scope='registrations_only')
    finally:
        workbook.close()


def next_page(raw, key):
    url = TECHNO_SOURCES[key]
    doc = parse_document(raw, 'text/html')
    state = json.loads(one((''.join(s.children) for s in doc.nodes('script')
                            if s.attrs.get('id') == '__NEXT_DATA__' and s.attrs.get('type') == 'application/json'),
                           'r4_unique_next_data_required'), object_pairs_hook=unique_object)
    if ([n.attrs.get('href') for n in doc.nodes('link') if n.attrs.get('rel') == 'canonical'] != [url]
            or state.get('locale') != 'sv-SE'
            or state.get('query') != {'path': urlsplit(url).path.strip('/').split('/')}):
        raise ValueError('r4_exact_swedish_source_route_required:' + key)
    return doc, state['props']['pageProps']


def manufacturer_version_cards(raw, profiles, price_list_dc):
    key = 'versions.html'
    _, props = next_page(raw, key)
    route = props['page']['layout']['sitecore']['route']
    navigation = one((c for c in route['placeholders']['headless-main']
                      if c.get('componentName') == 'SubNavigationGroup'), 'r4_exact_version_navigation_required')
    copies = []
    for page in navigation['fields']['Pages']:
        car = page['fields'].get('Car')
        if car is None:
            continue
        if car.get('id') != '8415daf9-b7fd-45b9-b492-fe9946c04cf4' or car.get('name') != 'RENAULT 4 E-TECH ELECTRIC':
            raise ValueError('r4_exact_swedish_car_content_required')
        versions = car['fields']['Versions']
        if tuple(x.get('id') for x in versions) != VERSION_IDS:
            raise ValueError('r4_exact_current_three_version_cards_required')
        copies.append([tuple(v['fields'][k]['value'] for k in ('VersionName', 'VersionSubtitle', 'EquipmentBlock'))
                       for v in versions])
    if not copies or any(copy != copies[0] for copy in copies):
        raise ValueError('r4_version_card_copies_disagree')
    result = {}
    for trim, label, (name, subtitle, equipment) in zip(TRIMS, CARD_LABELS, copies[0], strict=True):
        match = re.fullmatch(r'150 hk \| 52 kWh \| r\xe4ckvidd ([1-9]\d{2}) km', clean(subtitle))
        if name != label or not match:
            raise ValueError('r4_card_powertrain_or_trim_mismatch:' + trim)
        doc = parse_document(equipment.encode(), 'text/html')
        line = one((n.text() for n in doc.nodes('li') if 'AC 11 kW' in n.text() and 'DC' in n.text()),
                   'r4_card_charging_field_required:' + trim)
        dc = re.fullmatch(r'AC 11 kW ladd(?:d)?ning \+ DC (\d{2,3})(?: kW)?', clean(line))
        if not dc or not 20 <= int(dc[1]) <= 350:
            raise ValueError('r4_card_charging_field_changed:' + trim)
        km = int(match[1])
        dc_quote = evidence(key, raw, int(dc[1]), f'{label} | {line}', scope='manufacturer_version_equipment')
        charges = {'version_card': dc_quote, 'price_list': price_list_dc}
        result[trim] = {
            'range_reference': evidence(key, raw, km, f'{label} | {subtitle}',
                                        scope='advertised_exact_variant_range_not_explicitly_final_wltp'),
            'matches_preliminary_range': km == profiles[trim]['preliminary_wltp_range']['value'],
            'dc_observations': charges,
        }
        if dc_quote['value'] == price_list_dc['value']:
            result[trim]['agreed_dc_charge_kw'] = dc_quote
        else:
            result[trim]['held_dc_reason'] = 'swedish_ev52_price_list_and_version_equipment_disagree'
    return result


def configurator_reference(raw):
    key = 'configurator.html'
    _, props = next_page(raw, key)
    route = props['page']['layout']['sitecore']['route']
    component = one((c for c in route['placeholders']['headless-main'] if c.get('componentName') == 'NewCarConfigurator'),
                    'r4_unique_configurator_component_required')
    if component['fields']['CarCompany']['value'] != 'RenaultSE':
        raise ValueError('r4_swedish_configurator_car_company_required')
    models = props['componentProps'][component['uid']]['modelsData']['RenaultSE']['models']
    if not models or any(type(m.get('modelId')) is not int or not m.get('name') or not m.get('modelCode') for m in models):
        raise ValueError('r4_actual_configurator_model_list_required')
    names = [' '.join(m['name'].split()) for m in models]
    included = any(re.search(r'\b(?:renault\s*4|r4)\b', name, re.I) for name in names)
    return evidence(key, raw, included, 'RenaultSE.models | ' + ' | '.join(names),
                    scope='current configurator response only; not evidence of market availability')


def stock_reference(files, key, dealer_key, trim, profile, identity, dealer_name, dealer_proof, *, include_claims=False):
    raw = files[key]
    doc, props = next_page(raw, key)
    car = one((c['car'] for c in props['componentProps'].values() if isinstance(c, dict) and isinstance(c.get('car'), dict)),
              'r4_exact_primary_stock_vehicle_required')
    required = {**identity, 'car_brand': 'Renault', 'car_fuel': 'El', 'car_condition': 'Ny', 'car_mileage': 0,
                'car_is_factory_vehicle': False, 'car_price_currency': 'SEK', 'car_has_campaign_price': False,
                'car_drive': 'Framhjulsdrift'}
    if any(car.get(k) != v for k, v in required.items()):
        raise ValueError('r4_registered_stock_identity_changed:' + trim)
    dealer = parse_document(files[dealer_key], 'text/html')
    if (dealer_proof not in clean(dealer.text())
            or [n.attrs.get('href') for n in dealer.nodes('link') if n.attrs.get('rel') == 'canonical'] != [ALL_SOURCES[dealer_key]]):
        raise ValueError('r4_dealer_identity_or_authority_changed:' + trim)
    schema = one((data for n in doc.nodes('script') if n.attrs.get('type') == 'application/ld+json'
                  for data in (json.loads(''.join(n.children), object_pairs_hook=unique_object),)
                  if isinstance(data, dict) and data.get('@type') == ['Product', 'Car']),
                 'r4_exact_stock_car_schema_required')
    offer = schema['offers']
    if ((schema['brand']['name'], schema['model'], schema['vehicleModelDate'], offer['seller']['name'],
         offer['availability'], offer['priceCurrency'], offer['price'])
            != ('Renault', car['car_model'], car['car_year'], dealer_name, 'https://schema.org/InStock', 'SEK', car['car_price'])):
        raise ValueError('r4_structured_stock_offer_disagrees:' + trim)
    price = car['car_price']
    km = car.get('wltp_electric_range')
    consumption = car.get('wltp_electric_consumption')
    if (type(price) is not int or not 100_000 <= price <= 3_000_000 or car.get('car_retail_price') != price
            or type(km) is not int or not 50 <= km <= 1200
            or type(consumption) not in (int, float) or not math.isfinite(consumption)):
        raise ValueError('r4_stock_data_outside_review_limits:' + trim)
    issue = []
    if km != profile['preliminary_wltp_range']['value']:
        issue.append('range_differs_from_preliminary_manufacturer_trim')
    if not 5 <= consumption <= 60:
        issue.append('stock_consumption_unit_or_value_unclear')
    if offer.get('itemCondition') != 'https://schema.org/NewCondition':
        issue.append('new_condition_conflicts_with_offer_markup')
    result = {'trim': trim, 'stock_id': car['car_id'], 'dealer': dealer_name,
            'dealer_evidence': evidence(dealer_key, files[dealer_key], dealer_name, dealer_proof),
            'scope': 'individual listed vehicle; not a factory configuration or final variant WLTP',
            'identity': evidence(key, raw, car['car_version'], f"{car['car_model']} | {car['car_version']} | {car['car_year']}"),
            'model_year': evidence(key, raw, car['car_year'], f"car_year: {car['car_year']}"),
            'drivetrain': evidence(key, raw, 'FWD', 'car_drive: Framhjulsdrift'),
            'cash_offer': evidence(key, raw, price, f'Offer | {price} SEK', price_type='dealer_offer',
                                   matches_manufacturer_amount=price == profile['price']['value']),
            'wltp_range_observation': evidence(key, raw, km, f'wltp_electric_range: {km}'),
            'consumption_raw_observation': evidence(key, raw, consumption, f'wltp_electric_consumption: {consumption}'),
            'release_issues': issue}
    if include_claims:
        for item in car.get('car_equipment', ()):
            if not isinstance(item, str):
                continue
            match = re.fullmatch(r'R\xe4ckvidd WLTP: ([1-9]\d{2}) km', clean(item))
            charge = re.fullmatch(r'AC 11 kW ladd(?:d)?ning \+ DC (\d{2,3}) kW', clean(item))
            for field, found in (('equipment_wltp_reference', match), ('equipment_dc_reference', charge)):
                if found:
                    if field in result:
                        raise ValueError('r4_ambiguous_equipment_claim:' + trim)
                    result[field] = evidence(key, raw, int(found[1]), item, scope='individual_exact_stock_equipment')
        text = car.get('car_description') or ''
        prose = re.findall(r'R\xe4ckvidden uppges till ([1-9]\d{2}) kilometer enligt WLTP\.', text)
        if prose:
            result['description_wltp_reference'] = evidence(
                key, raw, int(one(prose, 'r4_ambiguous_prose_claim:' + trim)),
                'R\xe4ckvidden uppges till ' + prose[0] + ' kilometer enligt WLTP.',
                scope='stock_description_not_factory_spec')
        for field in ('equipment_wltp_reference', 'description_wltp_reference'):
            if field in result and result[field]['value'] != km:
                issue.append('stock_range_field_conflicts_with_' + field)
    return result


def stock_support(files, profiles, *, updated=False):
    verify_link(files['versions.html'], VERSIONS, CONFIGURATOR, 'bygg din bil')
    references = [
        stock_reference(files, 'techno-stock.html', 'rn-dealer.html', 'TECHNO', profiles['TECHNO'],
                        {'car_id': '240062', 'car_model': '4', 'car_year': 2026,
                         'car_version': 'Techno | 52kWh | Backkamera | Carplay |'}, 'RN Automotive Sp\xe5nga',
                        AUTH_RN, include_claims=updated),
        stock_reference(files, 'plein-sud-stock.html', 'hedin-dealer.html', 'TECHNO PLEIN SUD', profiles['TECHNO PLEIN SUD'],
                        {'car_id': '260151', 'car_model': '4 E-Tech', 'car_year': 2027, 'car_version': 'Plein Sud'},
                        'Hedin Automotive Halmstad', 'Som \xe5terf\xf6rs\xe4ljare f\xf6r Nissan, MG, Isuzu, RAM, Renault och Dacia',
                        include_claims=updated),
    ]
    if updated:
        references.insert(0, stock_reference(
            files, 'evolution-stock.html', 'rn-dealer.html', 'EVOLUTION', profiles['EVOLUTION'],
            {'car_id': '261900', 'car_model': '4 E-Tech', 'car_year': 2027,
             'car_version': 'ELECTRIC EVOLUTION EV52 // Vinterhjul fr. 199kr/m\xe5n'},
            'RN Automotive Tagene', AUTH_RN, include_claims=True))
    return {'swedish_configurator_has_r4': configurator_reference(files['configurator.html']), 'stock_observations': references}


def skobes_corroboration(files):
    key = 'skobes-stock.html'
    raw = files[key]
    doc = parse_document(raw, 'text/html')
    if [h.text() for h in doc.nodes('h1')] != ['Renault 4 E-Tech techno Plein Sud 52kWh']:
        raise ValueError('r4_skobes_exact_plein_sud_required')
    dealer = parse_document(files['skobes-dealer.html'], 'text/html')
    if ('Skobes Bil Nyk\xf6ping' not in clean(doc.text()) or 'Skobes Bil i Nyk\xf6ping' not in clean(dealer.text())
            or AUTH_SKOBES not in clean(dealer.text())):
        raise ValueError('r4_skobes_authorized_dealer_required')

    def read(tag, label):
        node = one((n for n in doc.nodes(tag) if n.text() == label), 'r4_skobes_exact_label_required:' + label)
        children = [n for n in node.parent.children if isinstance(n, Node)]
        if len(children) != 2 or children[0] is not node or children[1].tag != 'p':
            raise ValueError('r4_skobes_exact_value_required:' + label)
        return clean(children[1].text())

    if (read('p', 'Tillverkare'), read('p', 'Version'), read('p', 'Modell\xe5r'), read('h5', 'Motor')) != (
            'Renault', '52 kWh', '2027', '52 kWh (110 kW)'):
        raise ValueError('r4_skobes_exact_generation_required')
    km = read('h5', 'Elr\xe4ckvidd WLTP')
    use = read('h5', 'Elf\xf6rbrukning WLTP')
    drive = read('h5', 'Drivningstyp')
    range_match = re.fullmatch(r'([1-9]\d{2}) km', km)
    use_match = re.fullmatch(r'([1-5]\d[.,]\d) kWh/100\s?km', use)
    if not range_match or not use_match or drive != 'Framhjulsdrift':
        raise ValueError('r4_skobes_exact_wltp_units_required')
    return {
        'scope': 'independent_authorized_dealer_individual_2027_plein_sud_not_factory_spec',
        'dealer_evidence': evidence('skobes-dealer.html', files['skobes-dealer.html'], 'Skobes Bil Nyk\xf6ping', AUTH_SKOBES),
        'wltp_range_observation': evidence(key, raw, int(range_match[1]), 'Elr\xe4ckvidd WLTP | ' + km),
        'wltp_consumption_observation': evidence(key, raw, float(use_match[1].replace(',', '.')), 'Elf\xf6rbrukning WLTP | ' + use),
        'drivetrain': evidence(key, raw, 'FWD', 'Drivningstyp | ' + drive),
    }


def apply_current_review(files, result, profiles):
    price_list_dc = result['shared_technical_evidence'].pop('dc_charge_kw')
    cards = manufacturer_version_cards(files['versions.html'], profiles, price_list_dc)
    result['review_format'] = 2
    result['manufacturer_exact_version_cards'] = cards
    if 'evolution-stock.html' not in files:
        return
    references = result['configuration_and_stock_support']['stock_observations']
    for row in references:
        card = cards[row['trim']]
        if row.get('equipment_dc_reference', {}).get('value') == price_list_dc['value'] and 'held_dc_reason' in card:
            card['preferred_dc_for_review'] = {
                **price_list_dc, 'corroboration': row['equipment_dc_reference'],
                'reason': 'exact Swedish EV52 PDF and exact vehicle equipment agree; version card differs',
            }
        if (row.get('equipment_wltp_reference', {}).get('value') == card['range_reference']['value']
                and row['wltp_range_observation']['value'] != card['range_reference']['value']
                and card['matches_preliminary_range']):
            card['preferred_range_for_review'] = {
                **row['equipment_wltp_reference'], 'corroboration': card['range_reference'],
                'reason': 'exact Swedish equipment and manufacturer card agree; generic stock field differs',
            }
    result['independent_plein_sud_corroboration'] = skobes_corroboration(files)


def exact_rn_consumption(files, key, record):
    raw = files[key]
    _, props = next_page(raw, key)
    car = one((c['car'] for c in props['componentProps'].values() if isinstance(c, dict) and isinstance(c.get('car'), dict)),
              'r4_exact_consumption_car_required')
    if (car['car_id'], car['car_year']) != (record['stock_id'], record['model_year']['value']):
        raise ValueError('r4_consumption_car_identity_changed')
    raw_value = record['consumption_raw_observation']['value']
    display = clean(car.get('wltp_electric_consumption_text'))
    match = re.fullmatch(r'(\d{1,2}(?:[,.]\d)?) kWh/100\s?km', display)
    if type(raw_value) not in (int, float) or not 5 <= raw_value <= 60 or not match:
        raise ValueError('r4_exact_consumption_unit_required')
    precision = 1 if '.' not in match[1] and ',' not in match[1] else 10
    shown = float(match[1].replace(',', '.'))
    if shown != math.floor(raw_value * precision + 0.5) / precision:
        raise ValueError('r4_consumption_text_disagrees_with_number')
    return evidence(key, raw, raw_value, f'wltp_electric_consumption: {raw_value} | {display}',
                    scope='exact_dealer_car_wltp_value_with_explicit_display_unit')


def finnvedens_techno(files, expected_range, *, allow_range_only=False):
    key = 'finnvedens-techno.html'
    branch_key = 'finnvedens-linkoping.html'
    document, branch = (parse_document(files[name], 'text/html') for name in (key, branch_key))
    authority = ('Vi s\xe4ljer nya bilar fr\xe5n Volvo, Polestar, Lynk & Co, Renault och Dacia')
    if (authority not in clean(branch.text()) or '\xe4r auktoriserad verkstad f\xf6r samma m\xe4rken' not in clean(branch.text())
            or [h.text() for h in branch.nodes('h1')] != ['Link\xf6ping']):
        raise ValueError('r4_finnvedens_branch_authority_required')
    for doc, name in ((document, key), (branch, branch_key)):
        if [n.attrs.get('href') for n in doc.nodes('link') if n.attrs.get('rel') == 'canonical'] != [EFFICIENCY_SOURCES[name]]:
            raise ValueError('r4_finnvedens_exact_source_required')
    if ([h.text() for h in document.nodes('h1')] != ['R4 E-Tech techno 52kWh']
            or not any(n.attrs.get('class') == 'row gy-2' and clean(n.text()) == '2026 Ny El' for n in document.nodes('div'))):
        raise ValueError('r4_finnvedens_exact_techno_edition_required')

    def field(label, *, optional=False):
        values = set()
        for node in document.nodes('div'):
            children = [child for child in node.children if isinstance(child, Node)]
            if (node.attrs.get('class') == 'col-11 d-flex d-md-block justify-content-between'
                    and len(children) == 2 and (children[0].text() == label or children[0].attrs.get('title') == label)):
                values.add(clean(children[1].text()))
        if not values and optional:
            return None
        return one(values, 'r4_finnvedens_exact_field_required:' + label)

    registration = field('Registreringsnummer', optional=True)
    forms = [n for n in document.nodes('form') if n.attrs.get('id') == 'car-interest-form']
    if forms:
        form = one(forms, 'r4_finnvedens_exact_vehicle_form_required')
        if form.attrs.get('data-regnumber') != 'TCU98N':
            raise ValueError('r4_finnvedens_exact_vehicle_required')
    if registration is None:
        descriptions = [n for n in document.nodes('div')
                        if (n.attrs.get('id'), n.attrs.get('class')) == ('car-interest', 'car-interest car-loader')]
        description = one(descriptions, 'r4_finnvedens_exact_vehicle_description_required')
        words = [n.text() for n in description.nodes('strong')]
        if not forms or form not in description.nodes('form') or words != ['R4 E-Tech techno 52kWh', 'TCU98N']:
            raise ValueError('r4_finnvedens_exact_vehicle_required')
        registration = form.attrs['data-regnumber']
    if registration != 'TCU98N':
        raise ValueError('r4_finnvedens_exact_vehicle_required')
    km = field('Elr\xe4ckvidd')
    combined_label = 'Elf\xf6rbrukning (blandad k\xf6rning)'
    use = field(combined_label, optional=allow_range_only)
    if use is None:
        consumption_label = 'Elf\xf6rbrukning...'
        use = field(consumption_label)
    else:
        consumption_label = combined_label
    use_match = re.fullmatch(r'([1-5]\d[,.]\d) kWh/100\s?km', use)
    if km != f'{expected_range} km' or not use_match:
        raise ValueError('r4_finnvedens_exact_efficiency_scope_changed')
    consumption_field = 'combined_consumption' if consumption_label == combined_label else 'unqualified_consumption_observation'
    return {'range': evidence(key, files[key], expected_range, f'Elr\xe4ckvidd | {km}'),
            consumption_field: evidence(key, files[key], float(use_match[1].replace(',', '.')), f'{consumption_label} | {use}'),
            'branch': evidence(branch_key, files[branch_key], 'Finnvedens Bil Link\xf6ping', authority),
            'scope': 'same Swedish Techno EV52 stock edition; page does not identify final factory WLTP'}


def apply_efficiency_review(files, result):
    records = {r['trim']: r for r in result['configuration_and_stock_support']['stock_observations']}
    cards = result['manufacturer_exact_version_cards']
    evolution, techno = (exact_rn_consumption(files, key, records[trim]) for key, trim in
                         (('evolution-stock.html', 'EVOLUTION'), ('techno-stock.html', 'TECHNO')))
    independent = finnvedens_techno(files, cards['TECHNO']['range_reference']['value'],
                                   allow_range_only=files.keys() == TECHNO_SOURCES.keys())
    observation = independent.get('combined_consumption') or independent['unqualified_consumption_observation']
    if observation['value'] != techno['value']:
        raise ValueError('r4_techno_consumption_sources_disagree')
    result['review_format'] = 3
    result['private_efficiency_review'] = {
        'EVOLUTION': {'combined_consumption': evolution, 'range': cards['EVOLUTION']['preferred_range_for_review'],
                      'scope': 'exact MY27 dealer evidence with matching Swedish manufacturer range; not final factory WLTP'},
        'TECHNO': {'combined_consumption': techno, 'corroboration': independent,
                   'range_alternative': records['TECHNO']['wltp_range_observation'],
                   'scope': 'exact 2026 dealer evidence; competing range figures retained'},
        'TECHNO PLEIN SUD': {'combined_consumption': result['independent_plein_sud_corroboration']['wltp_consumption_observation'],
                             'scope': 'MY27 canvas roof only; dealer and manufacturer ranges still disagree'},
    }


def techno_selection(files, result):
    key, locator = 'hedin-techno-18.html', 'renault-sales-locator.html'
    raw = files[key]
    doc, props = next_page(raw, key)
    _, authority_props = next_page(files[locator], locator)

    def outlets(value):
        if isinstance(value, dict):
            if value.get('dealerId') == '75225550':
                yield value
            for child in value.values():
                yield from outlets(child)
        elif isinstance(value, list):
            for child in value:
                yield from outlets(child)

    outlet = one(outlets(authority_props['componentProps']), 'r4_unique_techno_sales_outlet_required')
    street = 'Garnisonsgatan 5'
    if ((outlet.get('name'), outlet.get('streetAddress'), outlet.get('markerType')) !=
            ('Hedin Automotive Helsingborg', street, 'sales')
            or outlet.get('services', {}).get('RenaultPassengerCarSales') != 'True'):
        raise ValueError('r4_techno_sales_appointment_changed')
    appointment = evidence(locator, files[locator], outlet['name'],
                           f"{outlet['name']} | 75225550 | {street} | RenaultPassengerCarSales: True")

    car = one((c['car'] for c in props['componentProps'].values() if isinstance(c, dict) and isinstance(c.get('car'), dict)),
              'r4_techno_primary_stock_vehicle_required')
    identity = {'car_id': '258900', 'car_brand': 'Renault', 'car_model': '4 E-Tech', 'car_fuel': 'El',
                'car_year': 2026, 'car_version': 'R4 E-TECH TECHNO EV52', 'car_drive': 'Framhjulsdrift',
                'battery_size': 52, 'car_site_id': 'bce650651b22d99090829863b24bcb40', 'car_site_city': 'Helsingborg'}
    wheels = '18" aluminiumf\xe4lgar'
    if (any(car.get(field) != value for field, value in identity.items()) or wheels not in car.get('car_equipment', ())
            or not any(n.attrs.get('href') == '/anlaggningar/hedin-automotive-helsingborg-ostra' for n in doc.nodes('a'))
            or street not in doc.text()):
        raise ValueError('r4_techno_18_inch_stock_scope_changed')

    km = car.get('wltp_electric_range')
    use = car.get('wltp_electric_consumption')
    card = result['manufacturer_exact_version_cards']['TECHNO']
    prior = result['private_efficiency_review']['TECHNO']
    independent = prior['corroboration']
    supporting_use = independent.get('combined_consumption') or independent['unqualified_consumption_observation']
    if (type(km) is not int or km != card['range_reference']['value'] or km != independent['range']['value']
            or not card['matches_preliminary_range'] or clean(car.get('wltp_electric_range_text')) != f'{km} km'
            or use != prior['combined_consumption']['value'] or use != supporting_use['value']):
        raise ValueError('r4_techno_scope_or_efficiency_approval_required')
    consumption = exact_rn_consumption(files, key, {'stock_id': car['car_id'], 'model_year': {'value': 2026},
                                                  'consumption_raw_observation': {'value': use}})
    profile = result['swedish_current_ev52_versions']['TECHNO']
    if profile['price']['value'] != result['manufacturer_price_crosschecks']['TECHNO']['value']:
        raise ValueError('r4_techno_swedish_recommended_price_changed')
    hardware = result['shared_technical_evidence']
    return {'status': 'private_techno_candidate', 'model_year': 2026, 'edition': identity['car_version'],
            'manufacturer_version_id': VERSION_IDS[1], 'stock_authorization': appointment,
            'wheel_evidence': evidence(key, raw, 18, wheels), 'price': profile['price'],
            'fields': {**{field: hardware[field] for field in ('battery_kwh', 'ac_charge_kw', 'boot_liters', 'tow_kg', 'seats')},
                       'dc_charge_kw': card['agreed_dc_charge_kw'],
                       'wltp_range_km': evidence(key, raw, km, f'wltp_electric_range: {km} | {km} km',
                                                 scope='exact Swedish MY26 dealer vehicle, not factory homologation'),
                       'wltp_consumption_kwh_100km': consumption,
                       'drivetrain': evidence(key, raw, 'FWD', 'car_drive: Framhjulsdrift')},
            'range_alternative': prior['range_alternative'],
            'selection_reason': 'Exact 18-inch Techno EV52 dealer WLTP agrees with the manufacturer card and Finnvedens Bil; '
                                'the other dealer car remains a conflicting individual observation.', 'publication_approved': False}


def review(files, *, historical=False):
    stock_sources = LEGACY_STOCK_SOURCES if historical else ALL_SOURCES
    permitted = (SOURCES.keys(), stock_sources.keys()) + (() if historical else (EFFICIENCY_SOURCES.keys(), TECHNO_SOURCES.keys()))
    if files.keys() not in permitted or any(not 0 < len(body) <= LIMIT for body in files.values()):
        raise ValueError('r4_complete_registered_capture_required')
    profiles, hardware, consumption = price_list(files['prices.pdf'])
    prices = web_crosscheck(files['versions.html'], profiles)
    verify_link(files['market.html'], MARKET, WORKBOOK, 'M\xe5nadsrapport Nyregistreringar okt 2026.xlsx')
    for key, headings, quotes in (
        ('dimensions.html', ['m\xe5tt och dimensioner'], ['Renault 4:s bagageutrymme p\xe5 420 l', 'fem passagerare']),
        ('charging.html', ['Renault 4 E-Tech electric'], ['inbyggda 11 kW-laddaren', 'Laddar upp till 100 kW vid en DC snabbladdstation']),
    ):
        doc = parse_document(files[key], 'text/html')
        if [h.text() for h in doc.nodes('h1')] != headings or not all(q in doc.text() for q in quotes):
            raise ValueError('r4_official_model_specs_changed:' + key)
    press = parse_document(files['press.html'], 'text/html')
    body = 'Renault 4 \xe4r tillbaka \u2013 som helelektrisk crossover'
    if body not in press.text():
        raise ValueError('r4_importer_electric_crossover_required')
    result = {'model_key': 'renault|4', 'status': 'review_complete_held', 'publication_approved': False, 'database_writes': 0,
            'sources': {key: {'url': TECHNO_SOURCES[key], 'sha256': hashlib.sha256(raw).hexdigest()} for key, raw in files.items()},
            'swedish_current_ev52_versions': profiles, 'manufacturer_price_crosschecks': prices,
            'shared_technical_evidence': hardware, 'preliminary_consumption_reference': consumption,
            'body': evidence('press.html', files['press.html'], 'crossover', body, scope='production_renault_4_e_tech_electric'),
            'market_index': market_data(files['market.xlsx']),
            'held': ['exact final Swedish combined range and consumption by variant',
                     'confirmed driven axles for current variants and independent price evidence',
                     'approved model photo with image identity and usage rights']}
    if 'configurator.html' in files:
        result['configuration_and_stock_support'] = stock_support(files, profiles, updated=not historical)
    if not historical:
        apply_current_review(files, result, profiles)
    if files.keys() in (EFFICIENCY_SOURCES.keys(), TECHNO_SOURCES.keys()):
        apply_efficiency_review(files, result)
    if files.keys() == TECHNO_SOURCES.keys():
        result['review_format'] = 4
        result['techno_candidate'] = techno_selection(files, result)
    return result


def pair_review(report, files, fetched):
    from renault_4_evolution_candidate import SOURCE_URLS, candidate

    if files.keys() != TECHNO_SOURCES.keys() or fetched.keys() != files.keys():
        raise ValueError('r4_pair_requires_all_sources_from_one_capture')
    now = datetime.fromisoformat(report['captured_at'])
    if any(not 0 <= (now - datetime.fromisoformat(at)).total_seconds() <= 900 for at in fetched.values()):
        raise ValueError('r4_pair_capture_window_exceeded')
    keys = {name: 'renault-sales-locator.html' if name == 'locator.html' else name for name in SOURCE_URLS}
    for key, name in keys.items():
        if SOURCE_URLS[key] != TECHNO_SOURCES[name]:
            raise ValueError('r4_pair_source_identity_changed')
    return {**report, 'review_format': 5, 'fetched_at': fetched,
            'evolution_candidate': candidate({key: files[name] for key, name in keys.items()},
                                             {key: fetched[name] for key, name in keys.items()}, now)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    support = parser.add_mutually_exclusive_group()
    support.add_argument('--with-stock-support', action='store_true', help='Capture exact Swedish stock references and dealer authority')
    support.add_argument('--with-efficiency-review', action='store_true', help='Include scoped exact-car consumption evidence')
    support.add_argument('--with-techno-selection', action='store_true', help='Compare the exact Swedish MY26 Techno 18-inch vehicle')
    support.add_argument('--with-pair-selection', action='store_true', help='Capture both exact grades in the same private source window')
    parser.add_argument('--emit-pair', action='store_true', help='Emit the checked paired receipt after replaying the raw files')
    args = parser.parse_args()
    if (args.with_stock_support or args.with_efficiency_review or args.with_techno_selection or args.with_pair_selection) and not args.capture:
        parser.error('Source options require --capture')
    if args.emit_pair and not args.replay:
        parser.error('--emit-pair requires --replay')
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    if root != ROOT.resolve() / 'data/local/release-data' or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', s, re.I) for s in root.parts):
        raise ValueError('r4_private_release_directory_required')
    if args.capture:
        sources = TECHNO_SOURCES if args.with_techno_selection or args.with_pair_selection else (
            EFFICIENCY_SOURCES if args.with_efficiency_review else ALL_SOURCES if args.with_stock_support else SOURCES)
        fetcher = SourceFetcher(timeout=25, max_bytes=LIMIT, document_parser=lambda body, _: body,
                                text_parser=lambda *_: '', url_policy=lambda url, _: url in sources.values())
        files, fetched = {}, {}
        for name, url in sources.items():
            result = fetcher.fetch(url, {'Renault'})
            if (result['status'], result.get('http_status'), result.get('final_url')) != ('reachable', 200, url):
                raise ValueError('r4_unavailable_source:' + url)
            files[name] = result['document']
            fetched[name] = datetime.now(timezone.utc).isoformat()
        folder = Path(tempfile.mkdtemp(prefix='renault-4-review-', dir=root))
        for name, raw in files.items():
            (folder / name).write_bytes(raw)
        try:
            report = review(files)
            report['captured_at'] = datetime.now(timezone.utc).isoformat()
            if args.with_pair_selection:
                report = pair_review(report, files, fetched)
        except (ValueError, RefreshError) as error:
            (folder / 'held.json').write_text(json.dumps({
                'status': 'held', 'reason': str(error), 'publication_approved': False,
                'fetched_at': fetched,
                'sources': {name: {'url': sources[name], 'sha256': hashlib.sha256(raw).hexdigest()}
                            for name, raw in files.items()},
            }, indent=2) + '\n', encoding='utf-8')
            raise SystemExit(f'Renault 4 source checks held: {error}. Private evidence: {folder}') from error
        (folder / 'review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    else:
        folder = args.replay.resolve(strict=True)
        if folder != args.replay.absolute() or folder.parent != root or not re.fullmatch(r'renault-4-review-[a-z0-9_]+', folder.name):
            raise ValueError('r4_private_capture_required')

        def read(name):
            path = folder / name
            if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_size > LIMIT:
                raise ValueError('r4_regular_capture_file_required')
            return path.read_bytes()

        saved = json.loads(read('review.json'), object_pairs_hook=unique_object)
        historical = 'review_format' not in saved
        sources = (TECHNO_SOURCES if saved.get('review_format') in (4, 5) else EFFICIENCY_SOURCES if saved.get('review_format') == 3 else
                   (LEGACY_STOCK_SOURCES if historical else ALL_SOURCES) if (folder / 'configurator.html').exists() else SOURCES)
        files = {name: read(name) for name in sources}
        report = review(files, historical=historical)
        report['captured_at'] = saved['captured_at']
        if saved.get('review_format') == 5:
            report = pair_review(report, files, saved['fetched_at'])
        if report != saved:
            raise ValueError('r4_capture_or_review_changed')
    if args.emit_pair:
        if report.get('review_format') != 5:
            raise ValueError('r4_paired_capture_required')
        print(json.dumps(report))
        return
    print(json.dumps({'output': str(folder / 'review.json'), 'sources': len(sources), 'publication_approved': False}))


if __name__ == '__main__':
    main()
