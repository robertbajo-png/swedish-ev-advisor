"""Capture exact Swedish IONIQ 5 prices and wheel-scoped specs for private review."""

import argparse
import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urljoin

from openpyxl import load_workbook
from pypdf import PdfReader

from audit_catalog_sources import ROOT, SourceFetcher, source_text
from import_mobility_sweden import parse_ranking_sheet
from manufacturer_embedded_data import ScriptData, unique_object
from variant_refresh import one, parse_document


def document_date(url):
    match = re.fullmatch(
        r'https://dmassets\.hyundai\.com/is/content/hyundaiautoever/Hyundai_Sverige_Prislista_(20[0-9]{6})pdf', url)
    if not match:
        raise ValueError('unexpected_swedish_price_url')
    return datetime.strptime(match[1], '%Y%m%d').date()

SWEDEN = 'https://www.hyundai.com/se/sv/'
DOWNLOADS = SWEDEN + 'bilar/ioniq5/nedladdningar.html'
LOCATOR = SWEDEN + 'tjanster/online-tjanster/hitta-aterforsaljare.html'
DEALER = 'https://karmauto.se/ioniq-5'
RA_N_LINE = 'https://ramotor.se/lagerbilar/hyundai-ioniq-5-qnr278/'
RA_WEBSITE = 'https://ramotor.se/nya-bilar/hyundai/'
RWD_N_LINE_ID = 'MY27$RWD84-NLINE'
ASSETS = 'https://dmassets.hyundai.com/is/content/hyundaiautoever/'
BROCHURE = ASSETS + 'Nya_IONIQ_5_Modellbrochyr_202505_webpdf-AFpdf'
SWEDISH_TECH = ASSETS + 'Prislista_Nya_IONIQ5_202507pdf'
NORWAY = 'https://www.hyundai.com/no/no/bilguide/velge-elbil/kjope-brukt-elbil.html'
FAMILY = 'https://www.hyundai.com/no/no/bilguide/velge-elbil/elbil-familiebil.html'
MODEL = SWEDEN + 'bilar/ioniq5.html'
MARKET = ('https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/'
          'tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober')
WORKBOOK = ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
            'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
            'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx')
SCOPE = {(drive, capacity, grade) for drive, capacity in [('RWD', 63), ('RWD', 84), ('AWD', 84)]
         for grade in (['Essential'] if capacity == 63 else ['Essential', 'Advanced', 'N Line'])}
MOTOR_ORDER = [('RWD', 63), ('RWD', 84), ('AWD', 84)]
MONEY = r'[1-9]\d{0,2} \d{3}'
GRADE = r'Essential|Advanced|N Line'
ORDER_ORIGIN = 'https://lager.hyundai.se/model/IONIQ%205/'
ORDERING = {
    ('RWD', 63, 'Essential'): ('GIW5ZHZ7ZGG2L7', 'SAW'),
    ('RWD', 84, 'Essential'): ('GIW5ZHZ7ZGG2HC', 'A2B'),
    ('AWD', 84, 'Essential'): ('GIW5YCZ7ZGG2L8', 'SAW'),
    ('RWD', 84, 'Advanced'): ('GIW5ZHZ7ZHH2GQ', 'A2B'),
    ('AWD', 84, 'Advanced'): ('GIW5YCZ7ZHH2TP', 'SAW'),
    ('AWD', 84, 'N Line'): ('GIW5YCZ7ZMM325', 'R2P'),
}
ORDER_URLS = {key: f'{ORDER_ORIGIN}{code}?customer=private&ext={color}&int=NNB'
              for key, (code, color) in ORDERING.items()}
LIMIT = 32 * 1024 * 1024


def normalized(text):
    return ' '.join(text.split())


def discover_downloads(html):
    found = {}
    categories = {'Download - Prislista', 'Download - IONIQ 5 Modellbroschyr'}
    for node in parse_document(html, 'text/html').nodes('a'):
        if node.attrs.get('data-js-item') != 'download-list-link':
            continue
        try:
            metadata = json.loads(node.attrs.get('data-js-tracking', 'null'))
        except ValueError:
            continue
        if not isinstance(metadata, dict) or metadata.get('eventLabel') != 'IONIQ 5':
            continue
        category = metadata.get('eventCategory')
        if isinstance(category, str) and category in categories:
            found.setdefault(category, set()).add(node.attrs.get('href'))
    price = one(found.get('Download - Prislista', ()), 'unique_ioniq5_price_pdf_required')
    document_date(price or '')
    if found.get('Download - IONIQ 5 Modellbroschyr') != {BROCHURE}:
        raise ValueError('review_new_ioniq5_brochure_link')
    return price


def read_prices(text, issued, today):
    lines = [normalized(line) for line in text.splitlines() if line.strip()]
    if ({line for line in lines if line.startswith('Datum:')} != {f'Datum: {issued.isoformat()}'}
            or not 0 <= (today - issued).days <= 90):
        raise ValueError('current_matching_price_date_required')
    start = one((i for i, line in enumerate(lines) if line == 'IONIQ 5'), 'exact_ioniq5_price_section_required')
    header = 'Modell och version Elf\u00f6rbrukning* F\u00f6rbrukning* CO2* Rek. pris Privatleasing Businessleasing'
    headers = [i for i, line in enumerate(lines[:start]) if line == header]
    if not headers or lines[headers[-1] + 1] != 'kWh/10 km* l/10 km (g/km) (inkl. moms) (fr\u00e5n/m\u00e5n*) (fr\u00e5n/m\u00e5n*)':
        raise ValueError('cash_price_and_consumption_units_required')
    if not any(re.fullmatch(r'\*G\u00e4ller blandad k\u00f6rning enligt WLTP\.?', line) for line in lines):
        raise ValueError('combined_wltp_basis_required')
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('M\u00f6jliga tillval:')), len(lines))
    result = {}
    for line in lines[start + 1:end]:
        match = re.fullmatch(rf'(RWD|AWD) (63|84)\s*kWh ({GRADE}) (\d,\d{{2}}) - 0 ({MONEY}) kr'
                             rf' (?:-|{MONEY} kr) (?:-|{MONEY} kr)', line)
        if not match:
            raise ValueError('unknown_ioniq5_price_row_shape')
        drive, capacity, grade, consumption, price = match.groups()
        key = (drive, int(capacity), grade)
        cash = int(price.replace(' ', ''))
        kwh_per_100km = Decimal(consumption.replace(',', '.')) * 10
        if key not in SCOPE or key in result or not 100000 <= cash <= 3000000 or not 8 <= kwh_per_100km <= 45:
            raise ValueError('unknown_duplicate_or_invalid_ioniq5_price')
        result[key] = (cash, float(kwh_per_100km), line)
    if end == len(lines) or result.keys() != SCOPE:
        raise ValueError('incomplete_ioniq5_price_scope')
    return result


def dealer_fact_cards(cards, prices):
    pattern = rf'({GRADE}) (63|84) kWh \xb7 (Bakhjulsdrift|Fyrhjulsdrift) \((RWD|AWD)\) ' \
              rf'Pris vid finansiering {MONEY} kr Ord\. pris ({MONEY}) kr Spara {MONEY} kr'
    result = {}
    for card in cards:
        match = re.fullmatch(pattern, card)
        if not match:
            continue
        grade, capacity, description, drive, price = match.groups()
        key = (drive, int(capacity), grade)
        if (key not in prices or key in result or int(price.replace(' ', '')) != prices[key][0]
                or (description == 'Bakhjulsdrift') != (drive == 'RWD')):
            raise ValueError('ioniq5_dealer_ordinary_price_or_identity_conflict')
        result[key] = card
    if result.keys() != SCOPE:
        raise ValueError('incomplete_ioniq5_dealer_price_scope')
    return result


def verify_sales_outlet(raw, outlet_id, name, website):
    doc = parse_document(raw, 'text/html')
    listing = one((node.attrs['data-js-content'] for node in doc.nodes('div')
                   if node.attrs.get('data-js-module') == 'dealer-locator' and node.attrs.get('data-js-content')),
                  'unique_hyundai_dealer_locator_required')
    dataset = json.loads(listing, object_pairs_hook=unique_object)
    dealer = one((row for row in dataset['dealers']['se'] if row.get('id') == outlet_id),
                 'unique_hyundai_dealer_id_required')
    if (dealer.get('shortOutletName') != name or dealer.get('dealerId') != outlet_id
            or dealer.get('webSite') != website or dealer.get('onlyService') is not False
            or not any(s.get('serviceId') == 'sales'
                       for p in dealer['dealerProperties'] for s in p['services'])):
        raise ValueError('ioniq5_dealer_sales_authorization_required')
    return dealer


def verify_dealer_authorization(raw):
    verify_sales_outlet(raw, 'C18AS20016', 'Karmauto AB', 'https://karmauto.se/')
    return 'Karmauto AB | C18AS20016 | karmauto.se | sales'


def ra_n_line_identity(raw, locator):
    outlet = verify_sales_outlet(locator, 'C18AS20015', 'R A MOTOR AB', RA_WEBSITE)
    if outlet.get('fullDealerName') != 'Hyundai Haninge':
        raise ValueError('exact_hyundai_haninge_sales_outlet_required')
    doc = parse_document(raw, 'text/html')
    label = one((n.text() for n in doc.nodes('h1')), 'exact_ra_n_line_vehicle_heading_required')
    variant = 'Hyundai Ioniq 5 84 kWh RWD N-Line'
    if not re.fullmatch(re.escape(variant) + r'(?: \*R\u00e4ntekampanj \d,\d{2}%)?', label):
        raise ValueError('ra_n_line_rwd_identity_mismatch')
    details = [n.text() for n in doc.nodes('li')]
    if details.count('\u00c5rsmodell 2027') != 1 or details.count('Drivmedel El') != 1 or not any(
            text in {'Haninge', 'RA Motor Haninge'} for text in [n.text() for n in doc.nodes('dd')]):
        raise ValueError('ra_n_line_year_power_or_outlet_mismatch')
    return variant + ' | MY27 | Haninge'


def brochure_facts(page):
    text = normalized(page.replace('\u02dd', '"'))
    for line in ('Classification 2WD Standard 2WD Long Range AWD Long Range',
                 'Max. power (kW) 125 168 239', 'Capacity (kWh) 63.0 84.0 84.0'):
        if text.count(line) != 1:
            raise ValueError('ioniq5_brochure_powertrain_columns_changed')
    match = re.search(r'Electric range \(WLTP\)\*\* combined \(km\) (\d{3})'
                      r' 19" tyres: (\d{3})/20" tyres: (\d{3})/ 20" tyres N Line: (\d{3})'
                      r' 19" tyres: (\d{3})/20" tyres: (\d{3})/ 20" tyres N Line: (\d{3}) Performance', text)
    ac = re.search(r'On-board charger \(OBC\) Max capacity \(kW\) '
                   r'((?:[\d.]+ \(1-phase\)/[\d.]+ \(3-phase\) ){2}[\d.]+ \(1-phase\)/[\d.]+ \(3-phase\)) Charging time', text)
    if not match or not ac:
        raise ValueError('ioniq5_wheel_scoped_range_and_onboard_ac_required')
    wltp = list(map(int, match.groups()))
    power = [float(n) for n in re.findall(r'/([\d.]+) \(3-phase\)', ac[1])]
    if not all(50 <= n <= 1200 for n in wltp) or len(power) != 3 or not all(1 <= n <= 43 for n in power):
        raise ValueError('ioniq5_brochure_specs_out_of_bounds')
    return [
        {'range_by_wheel': {'19': wltp[0]}, 'ac_kw': power[0]},
        {'range_by_wheel': dict(zip(('19', '20', '20 N Line'), wltp[1:4])), 'ac_kw': power[1]},
        {'range_by_wheel': dict(zip(('19', '20', '20 N Line'), wltp[4:])), 'ac_kw': power[2]},
    ], match[0].removesuffix(' Performance'), ac[0].removesuffix(' Charging time')


def dc_facts(rows, motors):
    values = {}
    for motor, label in zip(motors, ('Standard Range RWD', 'Long Range RWD', 'Long Range AWD')):
        peak = one((re.fullmatch(rf'2024 [\u2013-] {motor[1]} kWt \({label}\) (\d{{3}}) km (\d{{3}}) kW', row)
                    for row in rows if row.startswith('2024') and label in row),
                   'exact_current_norwegian_powertrain_required')
        if not peak or int(peak[1]) != motors[motor]['range_by_wheel']['19'] or not 20 <= int(peak[2]) <= 600:
            raise ValueError('ioniq5_norwegian_hardware_match_failed')
        values[motor] = (int(peak[2]), peak[0])
    return values


def practicality(swedish_page, family_rows):
    text = normalized(swedish_page)
    if 'Teknisk specifikation Motor V\u00e4xell\u00e5da 63kWh: RWD 170hk 84kWh: RWD 228hk/ AWD 325hk' not in text:
        raise ValueError('ioniq5_swedish_technical_powertrain_scope_changed')
    tow = re.search(r'Max sl\u00e4pvagnsvikt \(bromsad\) \(kg\) (\d+) (\d+) Max sl\u00e4pvagnsvikt \(obromsad\)', text)
    boot = re.search(r'Lastutrymme, uppf\u00e4llt/nedf\u00e4llt baks\u00e4te \(VDA, liter\) (\d+)\/1 580 Frunk', text)
    family = one((re.fullmatch(rf'IONIQ 5 Fra {MONEY} kr Opptil 570 km (\d+) l \u2013 opptil 1 580 l \+ frunk (\d) '
                               r'5 stjerner Opptil 1 600 kg Den komplette familiebilen', row)
                  for row in family_rows if row.startswith('IONIQ 5 ')), 'exact_ioniq5_seating_row_required')
    if not tow or tow.groups() != ('750', '1600') or not boot or not family or boot[1] != family[1] or family[2] != '5':
        raise ValueError('ioniq5_current_practicality_corroboration_failed')
    return tow, boot, family


def exact_market_row(raw):
    book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        rows, _ = parse_ranking_sheet(book['Elbil ranking'], MARKET)
        row = one((r for r in rows if (r.brand_raw, r.model_raw, r.fuel_type_raw) == ('HYUNDAI', 'IONIQ 5', 'EL')),
                  'ioniq5_exact_market_alias_required')
        if row.needs_mapping or row.last_seen_month != '2026-10-01' or row.registrations_last_month <= 0:
            raise ValueError('ioniq5_positive_october_market_presence_required')
        return row
    finally:
        book.close()


def ordering_identity(raw, key):
    drive, capacity, grade = key
    code, _color = ORDERING[key]
    label = f'IONIQ 5 \xb7 {drive} {capacity}kWh {grade} MY27'
    doc = parse_document(raw, 'text/html')
    titles = [n.text() for n in doc.nodes('title')]
    og = [n.attrs.get('content') for n in doc.nodes('meta') if n.attrs.get('property') == 'og:title']
    if titles != [label + ' | Hyundai Sverige'] or og != [label]:
        raise ValueError('ioniq5_swedish_ordering_variant_or_model_year_mismatch')
    parser = ScriptData()
    parser.feed(raw.decode('utf-8'))
    tokens = []
    for script in parser.scripts:
        if 'assetId' not in script or 'modelKey' not in script:
            continue
        frame = re.fullmatch(r'\s*self\.__next_f\.push\((.+)\);?\s*', script, re.S)
        if not frame:
            continue
        pair = json.loads(frame[1], object_pairs_hook=unique_object)
        if isinstance(pair, list) and len(pair) == 2 and pair[0] == 1 and isinstance(pair[1], str):
            tokens.extend(re.findall(r'"assetId":"([A-Z0-9]{14})","modelKey":"([^"]+)"', pair[1]))
    if not tokens or set(tokens) != {(code, 'IONIQ 5')}:
        raise ValueError('ioniq5_swedish_ordering_material_number_mismatch')
    return {'material_number': code, 'model_year': 2027, 'quote': label,
            'scope': 'reference material for exact Swedish grade only; not price, availability or fitted options'}


def allow_source(url, brands):
    if brands != {'Hyundai'}:
        return False
    if url in {DOWNLOADS, LOCATOR, DEALER, BROCHURE, NORWAY, SWEDISH_TECH, FAMILY, MODEL, MARKET, WORKBOOK, RA_N_LINE}:
        return True
    if url in ORDER_URLS.values():
        return True
    try:
        document_date(url)
        return True
    except ValueError:
        return False


def fetch_text(body, content_type):
    if 'spreadsheetml.sheet' in content_type and body.startswith(b'PK\x03\x04'):
        return ''
    return source_text(body, content_type)


def capture(fetcher, now, with_identities=False, with_dealer_identity=False):
    sources = {}

    def get(url, name):
        source = fetcher.fetch(url, {'Hyundai'})
        if source['status'] != 'reachable' or source.get('final_url') != url or source.get('http_status') != 200:
            raise ValueError(f'ioniq5_source_held: {name}: {source["status"]}')
        sources[name] = (url, source)
        return source['document']

    url = discover_downloads(get(DOWNLOADS, 'downloads.html'))
    issued = document_date(url)
    require_pdf = get(url, 'swedish-price-list.pdf')
    if not require_pdf.startswith(b'%PDF-'):
        raise ValueError('ioniq5_price_pdf_required')
    prices = read_prices(sources['swedish-price-list.pdf'][1]['text'], issued, now.date())
    dealer = parse_document(get(DEALER, 'authorized-dealer.html'), 'text/html')
    locator_page = get(LOCATOR, 'dealer-locator.html')
    listing = verify_dealer_authorization(locator_page)
    dealer_rows = dealer_fact_cards([n.text() for n in dealer.nodes('article')], prices)
    brochure = get(BROCHURE, 'swedish-brochure.pdf')
    if not brochure.startswith(b'%PDF-'):
        raise ValueError('ioniq5_brochure_pdf_required')
    pages = PdfReader(io.BytesIO(brochure)).pages
    if len(pages) != 20:
        raise ValueError('ioniq5_brochure_page_count_changed')
    facts, wltp_quote, ac_quote = brochure_facts(pages[17].extract_text())
    motors = dict(zip(MOTOR_ORDER, facts))
    norway = parse_document(get(NORWAY, 'norwegian-dc-reference.html'), 'text/html')
    dc = dc_facts([n.text() for n in norway.nodes('tr')], motors)
    technical = get(SWEDISH_TECH, 'swedish-technical-archive.pdf')
    if not technical.startswith(b'%PDF-'):
        raise ValueError('ioniq5_archive_technical_pdf_required')
    tech_pages = PdfReader(io.BytesIO(technical)).pages
    if len(tech_pages) != 6:
        raise ValueError('ioniq5_technical_archive_page_count_changed')
    family = parse_document(get(FAMILY, 'norwegian-seats-reference.html'), 'text/html')
    towing, cargo, seats = practicality(tech_pages[5].extract_text(), [n.text() for n in family.nodes('tr')])
    model = parse_document(get(MODEL, 'swedish-model.html'), 'text/html')
    if 'all-electric CUV' not in model.text() and b'all-electric CUV' not in sources['swedish-model.html'][1]['document']:
        raise ValueError('ioniq5_swedish_crossover_scope_required')
    market = parse_document(get(MARKET, 'market.html'), 'text/html')
    if not any(urljoin(MARKET, n.attrs.get('href') or '') == WORKBOOK for n in market.nodes('a')):
        raise ValueError('ioniq5_official_october_workbook_link_required')
    market_row = exact_market_row(get(WORKBOOK, 'market.xlsx'))
    full_page = dealer.text()
    wheel_sections = (
        ('Essential Glidande mittkonsol', 'Advanced Bygger p\u00e5 Essential', '19” aluminiumf\u00e4lgar'),
        ('Advanced Bygger p\u00e5 Essential', 'Advanced m. 20 Alu Separat', '19” aluminiumf\u00e4lgar'),
        ('N Line Utvalda N Line-detaljer', 'Pris- och leasingvillkor', '20” Aluminiumf\u00e4lgar (N Line)'),
    )
    for heading, end, evidence in wheel_sections:
        if heading not in full_page or end not in full_page.split(heading, 1)[1] or evidence not in full_page.split(heading, 1)[1].split(end, 1)[0]:
            raise ValueError('ioniq5_swedish_base_wheel_scope_changed')

    def proof(name, value, quote, **scope):
        source_url, source = sources[name]
        return {'value': value, 'source_url': source_url, 'source_hash': source['content_hash'],
                'quote': quote, **scope}

    variants = []
    identity_holds = {}
    for (drive, capacity, grade), (price, consumption, quote) in prices.items():
        motor = (drive, capacity)
        wheels = '20 N Line' if grade == 'N Line' else '19'
        dc_kw, dc_quote = dc[motor]
        variant = {
            'variant': f'{capacity} kWh {drive} {grade}', 'standard_wheels': wheels,
            'evidence': {
                'price_sek': proof('swedish-price-list.pdf', price, quote, price_type='list_price',
                                   corroboration=proof('authorized-dealer.html', price, dealer_rows[(drive, capacity, grade)],
                                                       authorization=proof('dealer-locator.html', True, listing))),
                'wltp_consumption_kwh_100km': proof('swedish-price-list.pdf', consumption, quote),
                'wltp_range_km': proof('swedish-brochure.pdf', motors[motor]['range_by_wheel'][wheels], wltp_quote,
                                       wheel_scope=wheels, page=18),
                'battery_kwh': proof('swedish-brochure.pdf', capacity, 'Capacity (kWh) 63.0 84.0 84.0', page=18),
                'drivetrain': proof('swedish-price-list.pdf', drive, quote),
                'ac_charge_max_kw': proof('swedish-brochure.pdf', motors[motor]['ac_kw'], ac_quote, phases=3, page=18),
                'dc_charge_max_kw': proof('norwegian-dc-reference.html', dc_kw, dc_quote,
                                         scope='matching facelift battery, drivetrain and 19-inch WLTP; no foreign prices'),
                'tow_capacity_kg': proof('swedish-technical-archive.pdf', int(towing[1 if capacity == 63 else 2]),
                                         towing[0].removesuffix(' Max sl\u00e4pvagnsvikt (obromsad)'), page=6, braked=True),
                'cargo_liters': proof('swedish-technical-archive.pdf', int(cargo[1]), cargo[0].removesuffix(' Frunk'),
                                      page=6, seats_up=True, volume_standard='VDA'),
                'seats': proof('norwegian-seats-reference.html', int(seats[2]),
                               seats[0].split('570 km ', 1)[1].split(' 5 stjerner', 1)[0],
                               scope='same European facelift body; seats column'),
                'body_type': proof('swedish-model.html', 'SUV', 'IONIQ 5 | all-electric CUV', scope='crossover'),
            },
        }
        if with_identities:
            key = (drive, capacity, grade)
            order_url = ORDER_URLS.get(key)
            if order_url is None:
                if with_dealer_identity and key == ('RWD', 84, 'N Line'):
                    name = 'authorized-n-line-identity.html'
                    quote = ra_n_line_identity(get(RA_N_LINE, name), locator_page)
                    variant['identity_evidence'] = proof(name, RWD_N_LINE_ID, quote, model_year=2027,
                        kind='authorized_swedish_variant_identity', material_number=None,
                        scope='exact Swedish grade and model year only; no stock price, availability or equipment',
                        authorization=proof('dealer-locator.html', 'C18AS20015', 'R A MOTOR AB | Hyundai Haninge | sales'))
                else:
                    identity_holds[variant['variant']] = 'no_independent_swedish_material_number'
            else:
                name = 'ordering-' + ORDERING[key][0] + '.html'
                try:
                    identity = ordering_identity(get(order_url, name), key)
                    variant['identity_evidence'] = proof(name, identity['material_number'], identity['quote'],
                                                         model_year=identity['model_year'], scope=identity['scope'])
                except (ValueError, KeyError, TypeError) as error:
                    identity_holds[variant['variant']] = str(error)
        variants.append(variant)
    return issued, variants, sources, proof('market.xlsx', market_row.registrations_last_month, 'HYUNDAI | IONIQ 5 | EL',
        report_month=market_row.last_seen_month, registrations_ytd=market_row.registrations_ytd,
        scope='registrations_not_generation_or_variant_evidence'), identity_holds


def release_root():
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    if root != ROOT.resolve() / 'data/local/release-data' or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', x, re.I) for x in root.parts):
        raise ValueError('unexpected_evidence_directory')
    return root


def report_for(capture_result, now, with_identities):
    issue, variants, sources, market_index, identity_holds = capture_result
    receipts = {name: {'url': url, 'sha256': source['content_hash'], 'http_status': source['http_status']}
                for name, (url, source) in sources.items()}
    return {'status': 'private_source_review', 'model': 'Hyundai Ioniq 5', 'issued_on': issue.isoformat(),
            'captured_at': now.isoformat(), 'variants': variants, 'sources': receipts, 'market_index': market_index,
            'identity_holds': identity_holds,
            'holds': ['private_photo_receipt_binding', 'local_insert']
                     + (['independent_swedish_ordering_identity_check'] if not with_identities or identity_holds else []),
            'publication_approved': False, 'database_writes': 0, 'paid_calls': 0}


class CapturedSources:
    """Never reach the network when replaying a private source packet."""

    def __init__(self, folder, manifest):
        if not 11 <= len(manifest) <= 12 + len(ORDERING):
            raise ValueError('ioniq5_invalid_captured_source_count')
        self.rows = {}
        for name, evidence in manifest.items():
            path = folder / name
            url = evidence['url']
            if (path.parent != folder or path.name != name or not allow_source(url, {'Hyundai'})
                    or url in self.rows or evidence['http_status'] != 200 or path.is_symlink()
                    or path.resolve(strict=True) != path or not path.is_file() or not 0 < path.stat().st_size <= LIMIT):
                raise ValueError('ioniq5_invalid_captured_source')
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != evidence['sha256']:
                raise ValueError('ioniq5_captured_source_hash_mismatch')
            if path.suffix not in {'.pdf', '.html', '.xlsx'}:
                raise ValueError('ioniq5_capture_unexpected_document_type')
            # Only the price table needs full-document text. The other parsers read the verified raw bytes.
            text = source_text(raw, 'application/pdf') if name == 'swedish-price-list.pdf' else ''
            self.rows[url] = {'status': 'reachable', 'http_status': 200, 'final_url': url, 'document': raw,
                              'text': text, 'content_hash': digest}

    def fetch(self, url, brands):
        if not allow_source(url, brands):
            raise ValueError('ioniq5_replay_unapproved_url')
        return self.rows.get(url, {'status': 'not_captured'})


def replay(folder):
    path = folder.resolve(strict=True)
    if (path.parent != release_root() or path != folder.absolute()
            or not re.fullmatch(r'hyundai-ioniq5-review-[a-z0-9_]+', path.name)):
        raise ValueError('ioniq5_private_capture_directory_required')
    receipt = path / 'review.json'
    if receipt.resolve(strict=True) != receipt or not receipt.is_file() or not 0 < receipt.stat().st_size <= 512000:
        raise ValueError('ioniq5_bounded_regular_review_required')
    saved = json.loads(receipt.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    now = datetime.fromisoformat(saved['captured_at'])
    if now.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError('ioniq5_capture_timestamp_must_be_utc')
    with_identities = bool(saved['identity_holds']) or any('identity_evidence' in row for row in saved['variants'])
    fetcher = CapturedSources(path, saved['sources'])
    with_dealer_identity = 'authorized-n-line-identity.html' in saved['sources']
    actual = report_for(capture(fetcher, now, with_identities, with_dealer_identity), now, with_identities)
    if actual != saved:
        raise ValueError('ioniq5_captured_facts_scope_changed')
    return actual


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument('--with-identities', action='store_true', help='Check registered Swedish ordering reference pages')
    mode.add_argument('--with-dealer-identity', action='store_true',
                      help='Check all material pages and the authorized Swedish RWD N Line identity')
    mode.add_argument('--replay', type=Path, help='Check a captured source packet without reaching the network')
    args = cli.parse_args()
    if args.replay:
        folder = args.replay
        report = replay(folder)
    else:
        now = datetime.now(timezone.utc)
        identify = args.with_identities or args.with_dealer_identity
        built = capture(SourceFetcher(timeout=20, max_bytes=LIMIT,
            document_parser=lambda body, _kind: body, url_policy=allow_source, text_parser=fetch_text),
            now, identify, args.with_dealer_identity)
        report = report_for(built, now, identify)
        folder = Path(tempfile.mkdtemp(prefix='hyundai-ioniq5-review-', dir=release_root()))
        for name, (_url, source) in built[2].items():
            (folder / name).write_bytes(source['document'])
        (folder / 'review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    variants, identity_holds = report['variants'], report['identity_holds']
    print(json.dumps({'output': str(folder), 'checked_prices': len(variants),
                      'ordering_references': sum('identity_evidence' in row and row['identity_evidence'].get('material_number', True) is not None
                                                 for row in variants),
                      'authorized_variant_references': sum(row.get('identity_evidence', {}).get('kind') == 'authorized_swedish_variant_identity'
                                                            for row in variants),
                      'identity_holds': identity_holds, 'replayed_offline': args.replay is not None,
                      'publication_approved': False}))


if __name__ == '__main__':
    main()
