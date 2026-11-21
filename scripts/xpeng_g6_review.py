"""Review the current Swedish XPENG G6 facelift without catalog writes."""

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
from manufacturer_embedded_data import ScriptData, unique_object
from variant_refresh import one, parse_document

CONFIG = 'https://store.xpeng.com/se/configurator/new_G6'
UK_CONFIG = 'https://store.xpeng.com/gb/configurator/New_G6R'
TECH = 'https://s-cdn.xpeng.com/commoncms/prod/2026-11-11/a6130a4e376b4711806b741f07b2f4ca.pdf'
LECAB = 'https://lecab.se/erbjudande/xpeng-g6-5/'
APPOINTMENT = 'https://news.cision.com/se/xpeng/r/xpeng-expanderar-och-oppnar-i-karlstad,c4032912'
PRESSROOM = 'https://www.mynewsdesk.com/se/xpeng-motors-sweden-ab/'
PRESS = PRESSROOM + 'pressreleases/nya-xpeng-g6-svenska-priser-och-foersaeljningsstart-3396446'
PHOTO = PRESSROOM + 'images/g6-launch-2025-exterior-urban-road-punkt-jpg-3287677'
MARKET = ('https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/'
          'tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober')
WORKBOOK = ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
            'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
            'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx')
SOURCES = {'config.html': CONFIG, 'uk.html': UK_CONFIG, 'specs.pdf': TECH, 'dealer.html': LECAB,
           'appointment.html': APPOINTMENT, 'press.html': PRESS, 'market.html': MARKET, 'market.xlsx': WORKBOOK}
TRIMS = {'RWD Standard Range': ('Standard Range', 185, 68.5, 382, 'RWD'),
         'RWD Long Range': ('Long Range', 218, 80.8, 451, 'RWD'),
         'AWD Performance': ('AWD Performance', 358, 80.8, 451, 'AWD')}
SWEDISH_WLTP_20 = {'RWD Standard Range': (470, 16.9), 'RWD Long Range': (525, 17.9), 'AWD Performance': (510, 18.4)}
VERSION_CODES = {'RWD Standard Range': ('2761', 'FFCB'), 'RWD Long Range': ('1881', 'FFAB'),
                 'AWD Performance': ('1886', 'FFBB')}
LIMIT = 12_000_000


def clean(text):
    return ' '.join(text.split())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def proof(key, raw, value, quote, **info):
    return {'value': value, 'source_url': SOURCES[key], 'source_hash': sha(raw), 'quote': quote, **info}


def exact_link(raw, base, destination):
    if not any(urljoin(base, n.attrs.get('href', '')) == destination for n in parse_document(raw, 'text/html').nodes('a')):
        raise ValueError('g6_expected_source_link_missing')


def classes(node, prefix):
    return any(name.startswith(prefix) for name in node.attrs.get('class', '').split())


def configured_versions(raw):
    doc = parse_document(raw, 'text/html')
    if 'BYGG DIN XPENG G6' not in {n.text() for n in doc.nodes('h2')}:
        raise ValueError('g6_swedish_configurator_heading_required')
    panel = one((n for n in doc.nodes('div') if classes(n, 'settingCard_content__')
                 and any(classes(c, 'detailCard_title__') and c.text() in TRIMS for c in n.nodes('span'))),
                'g6_visible_version_panel_required')
    result = {}
    for card in (n for n in panel.nodes('div') if classes(n, 'detailCard_detailCard__')):
        trim = one((n.text() for n in card.nodes('span') if classes(n, 'detailCard_title__')), 'g6_trim_title_required')
        if trim not in TRIMS or trim in result:
            raise ValueError('g6_unexpected_or_duplicate_trim')
        model_label, power, gross, peak, drive = TRIMS[trim]
        article = clean(one(card.nodes('article'), 'g6_exact_trim_specs_required').text())
        intro, marker, rest = article.partition(' Specifikationer: ')
        specs, exterior, equipment = rest.partition(' Exteri\xf6r: ')
        if (not marker or not exterior or not intro.startswith(f'NYA XPENG G6 {model_label} ')
                or (trim == 'RWD Standard Range' and 'mellanklass-SUV' not in intro)
                or 'All teknisk data \xe4r beroende av typgodk\xe4nnande' not in article):
            raise ValueError('g6_facelift_specs_and_wltp_caveat_required')
        rows = [clean(row) for row in specs.split('\xb7') if row.strip()]
        wheels = one((clean(line).split(' Interi', 1)[0] for line in equipment.split('\xb7')
                      if 'aluminiumf\xe4lgar' in line and clean(line).startswith(('18"', '20"'))),
                     'g6_exact_standard_wheel_required')
        if wheels != '20" aluminiumf\xe4lgar':
            raise ValueError('g6_swedish_20_inch_scope_required')

        def get(pattern):
            return one((m for row in rows if (m := re.fullmatch(pattern, row))), 'g6_exact_spec_required:' + pattern)

        def fact(match, value=None, **scope):
            return proof('config.html', raw, value if value is not None else float(match[1].replace(',', '.')),
                         match[0], trim=trim, **scope)

        motor = get(r'Max effekt: (\d+) kW \(\d+ hk\)')
        battery = get(r'Batterikapacitet \(Brutto\): (\d+,\d) kWh')
        dc = get(r'DC-laddning: upp till (\d+) kW \(10-80 % p\xe5 ca\. 12 min\)\*\*')
        axle = get(r'Motor: .+? \((bakhjulsdrift|fyrhjulsdrift)\)')
        tow = get(r'Dragvikt: (1\.500) kg')
        wltp = get(r'R\xe4ckvidd:? \(WLTP\): (\d+) km\*')
        consumption = get(r'Genomsnittlig f\xf6rbrukning \(WLTP\): (\d+,\d) kWh/100km')
        if (int(motor[1]), float(battery[1].replace(',', '.')), int(dc[1]),
                {'bakhjulsdrift': 'RWD', 'fyrhjulsdrift': 'AWD'}[axle[1]]) != (power, gross, peak, drive):
            raise ValueError('g6_facelift_power_battery_dc_or_drive_changed')
        if (int(wltp[1]), float(consumption[1].replace(',', '.'))) != SWEDISH_WLTP_20[trim]:
            raise ValueError('g6_swedish_20_inch_wltp_pair_changed')
        price = clean(one((n.text() for n in card.nodes('div') if classes(n, 'detailCard_priceValue__')),
                          'g6_price_inside_exact_variant_card_required'))
        if not re.fullmatch(r'[1-9]\d{2} \d{3} kr', price):
            raise ValueError('g6_unfinanced_configurator_price_required')
        result[trim] = {
            'wheels': proof('config.html', raw, 20, wheels, trim=trim),
            'motor': fact(motor, power),
            'price': proof('config.html', raw, int(price[:-3].replace(' ', '')), price, trim=trim,
                           market='SE', price_type='list_price', scope='configurator_base_cash_price'),
            'towing_reference': fact(tow, 1500, scope='swedish_configurator_not_explicitly_braked'),
            'facts': {
                'drivetrain': fact(axle, drive), 'battery_kwh': fact(battery, gross, capacity_basis='gross'),
                'ac_charge_kw': fact(get(r'AC-laddning: (11) kW \(3-fas\)'), 11),
                'dc_charge_kw': fact(dc, peak, scope='vehicle_peak_not_session_average'),
                'boot_liters': fact(get(r'Bagagerum: (571) liter / 1\.374 liter med nedf\xe4llt baks\xe4te'), 571,
                                    scope='rear_seats_up'),
                'wltp_range_km': fact(wltp, int(wltp[1]), wheels_inches=20, scope='SE_WLTP'),
                'wltp_consumption_kwh_100km': fact(consumption, wheels_inches=20, scope='SE_WLTP'),
            }}
    if result.keys() != TRIMS.keys():
        raise ValueError('g6_exact_three_sweden_variants_required')
    return result


def configured_identities(raw, variants):
    scripts = ScriptData()
    scripts.feed(raw.decode('utf-8'))
    if scripts.language != 'sv':
        raise ValueError('g6_swedish_configurator_language_required')
    states = []
    for script in scripts.scripts:
        if 'carVersionListData' not in script:
            continue
        frame = re.fullmatch(r'\s*self\.__next_f\.push\((.+)\);?\s*', script, re.S)
        if not frame:
            raise ValueError('g6_literal_version_state_required')
        pair = json.loads(frame[1], object_pairs_hook=unique_object)
        if not (isinstance(pair, list) and len(pair) == 2 and pair[0] == 1 and isinstance(pair[1], str)):
            raise ValueError('g6_literal_version_frame_required')
        for line in pair[1].splitlines():
            if 'carVersionListData' not in line:
                continue
            number, _, body = line.partition(':')
            if not re.fullmatch('[a-f0-9]+', number):
                raise ValueError('g6_version_frame_id_required')
            component = json.loads(body, object_pairs_hook=unique_object)
            states.append(component[1][3]['states'])
    state = one(states, 'g6_exact_configurator_state_required')
    if state.get('carSeriesCode') != 'new_G6' or len(state['carVersionListData']) != len(VERSION_CODES):
        raise ValueError('g6_exact_facelift_series_required')
    result = {}
    for item in state['carVersionListData']:
        trim = item.get('carVersionName')
        if (trim in result or VERSION_CODES.get(trim) != (item.get('id'), item.get('carVersionCode'))
                or (item.get('carSeriesId'), item.get('carSeriesCode'), item.get('carSeriesName'), item.get('powerType'))
                != ('731', 'F30bV', 'New G6', 'BEV') or item.get('carVersionAlias') != trim):
            raise ValueError('g6_exact_factory_version_required')
        if (type(item.get('msrpBeforeSubsidy')) is not int or type(item.get('msrpAfterSubsidy')) is not int
                or item['msrpBeforeSubsidy'] != item['msrpAfterSubsidy']
                or item['msrpBeforeSubsidy'] != variants[trim]['price']['value']):
            raise ValueError('g6_before_subsidy_visible_price_required')
        code = item['carVersionCode']
        result[trim] = proof('config.html', raw, 'F30bV$' + code,
                             f'New G6 | F30bV | {trim} | {code}', version_code=code,
                             series_code='F30bV', version_id=item['id'], power_type='BEV',
                             list_price_sek=item['msrpBeforeSubsidy'])
    return result


def seats_reference(raw):
    if not raw.startswith(b'%PDF-'):
        raise ValueError('g6_specification_pdf_required')
    pages = PdfReader(io.BytesIO(raw)).pages
    if len(pages) != 2:
        raise ValueError('g6_global_specification_layout_changed')
    lines = set(map(clean, pages[0].extract_text(extraction_mode='layout').splitlines()))
    if 'Drivetrain RWD RWD AW D' in lines:
        lines.add('Drivetrain RWD RWD AWD')
    required = {'XPENG G6 SPECIFICATIONS', 'Version RWD Standard Range RWD Long Range AWD Performance',
                'Drivetrain RWD RWD AWD', 'Power output (kW) 185 218 218+140',
                'Gross battery capacity (kWh) 68.5 80.8 80.8', 'DC Max charging power (kW) 382 451 451',
                'Number of Seats 5'}
    if not required <= lines:
        raise ValueError('g6_matching_facelift_seat_columns_required')
    return proof('specs.pdf', raw, 5, 'Number of Seats 5', page=1, scope='manufacturer_matching_facelift_seating_only')


def standard_braked_reference(raw):
    doc = parse_document(raw, 'text/html')
    options = {clean(n.text()).split(' XPILOT ASSIST', 1)[0] for n in doc.nodes('article')
               if n.text().startswith('The XPENG G6 RWD Standard Range is the rear-wheel-drive version')}
    specs = one(options, 'g6_uk_exact_standard_range_required')
    required = ('185 kW', 'Battery capacity (gross): 68.5 kWh LFP', 'Max DC charging power: 382 kW',
                'Gross vehicle weight: 2,535 kg', 'Braked towing capacity: Up to 1,500 kg',
                'Unbraked towing capacity: Up to 750 kg')
    if not all(label in specs for label in required):
        raise ValueError('g6_uk_variant_hardware_or_braked_towing_changed')
    return proof('uk.html', raw, 1500, required[-2], scope='matching_185_kw_68_5_kwh_2535_kg_hardware_braked_only')


def dealer_prices(raw, variants):
    body = clean(parse_document(raw, 'text/html').text())
    offer, mark, _ = body.partition(' Tillval vid privatleasing:')
    if not mark or not all(s in offer for s in ('XPENG G6 RWD Standard Range', 'NYA XPENG G6 Standard Range')):
        raise ValueError('g6_exact_dealer_offer_scope_required')
    checks = {}
    for trim in TRIMS:
        intro = (r'XPENG G6 RWD Standard Range Privatleasing Elbil Erbjudande Pris fr\. ' if trim == 'RWD Standard Range'
                 else re.escape(trim) + r': K\xf6ppris: ')
        match = one(re.finditer(intro + r'([1-9]\d{2} \d{3})\s?kr(?=\s+Privatleasing)', offer),
                    'g6_exact_dealer_cash_price_required:' + trim)
        amount = int(match[1].replace(' ', ''))
        if amount != variants[trim]['price']['value']:
            raise ValueError('g6_configurator_dealer_cash_price_conflict:' + trim)
        checks[trim] = proof('dealer.html', raw, amount, match[0], trim=trim,
                             scope='dealer_cash_corroboration_not_selected_list_price', authorization_url=APPOINTMENT)
    return checks


def dealer_appointment(raw):
    doc = parse_document(raw, 'text/html')
    quote = 'Tillsammans med Lecab, som fr\xe5n och med september blir \xe5terf\xf6rs\xe4ljare av XPENGs produkter'
    if ([n.text() for n in doc.nodes('h1')] != ['XPENG expanderar och \xf6ppnar i Karlstad']
            or quote not in clean(doc.text())):
        raise ValueError('g6_xpeng_swedish_lecab_appointment_required')
    return proof('appointment.html', raw, 'Lecab Bil Karlstad', quote, scope='xpeng_manufacturer_dealer_appointment')


def market_row(raw):
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        rows, _ = parse_ranking_sheet(workbook['Elbil ranking'], MARKET)
        row = one((r for r in rows if (r.brand_raw, r.model_raw, r.fuel_type_raw) == ('XPENG', 'G6', 'EL')),
                  'g6_exact_market_alias_required')
        if row.needs_mapping or row.last_seen_month != '2026-10-01' or row.registrations_last_month <= 0:
            raise ValueError('g6_positive_october_market_presence_required')
        return proof('market.xlsx', raw, row.registrations_last_month, 'XPENG | G6 | EL',
                     report_month=row.last_seen_month, registrations_ytd=row.registrations_ytd,
                     source_index=MARKET, scope='registrations_not_generation_or_variant_evidence')
    finally:
        workbook.close()


def review(files):
    if files.keys() != SOURCES.keys() or any(not 0 < len(raw) <= LIMIT for raw in files.values()):
        raise ValueError('g6_complete_registered_capture_required')
    variants = configured_versions(files['config.html'])
    appointment = dealer_appointment(files['appointment.html'])
    price_checks = dealer_prices(files['dealer.html'], variants)
    exact_link(files['press.html'], PRESS, PHOTO)
    exact_link(files['market.html'], MARKET, WORKBOOK)
    press = clean(parse_document(files['press.html'], 'text/html').text())
    tech_header = 'Tekniska data nya XPENG G6 Long Range (LR), Performance (P)'
    _, marker, spec = press.partition(tech_header)
    lr_awd_tow = 'dragvikt: 1500 kg bromsat, 750 kg obromsat'
    if not marker or not all(x in spec[:900] for x in ('Platser 5 sittplatser', lr_awd_tow, '218 kW RWD och 218+140 kW AWD')):
        raise ValueError('g6_swedish_launch_hardware_scope_required')
    seats = seats_reference(files['specs.pdf'])
    tow = standard_braked_reference(files['uk.html'])
    for trim, packet in variants.items():
        packet['dealer_price'] = {**price_checks[trim], 'authorization_hash': appointment['source_hash']}
        packet['facts']['seats'] = seats if trim == 'RWD Standard Range' else proof(
            'press.html', files['press.html'], 5, tech_header + ' | Platser 5 sittplatser')
        packet['facts']['tow_kg'] = tow if trim == 'RWD Standard Range' else proof(
            'press.html', files['press.html'], 1500, tech_header + ' | ' + lr_awd_tow, scope='braked')
    return {'status': 'private_variant_review_not_publication_approval', 'model_key': 'xpeng|g6',
            'market': 'SE', 'publication_approved': False, 'database_writes': 0,
            'sources': {name: {'url': url, 'sha256': sha(files[name])} for name, url in SOURCES.items()},
            'variants': variants, 'market_index': market_row(files['market.xlsx']),
            'dealer_appointment': appointment,
            'body': proof('config.html', files['config.html'], 'SUV', 'NYA XPENG G6 Standard Range \xe4r en rymlig mellanklass-SUV'),
            'photo_source': PHOTO,
            'remaining': ['bind exact photo proof to a model-specific publish preparation',
                          'prepare exact registered insertion adapter, isolated transaction and readback tests']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    parser.add_argument('--identities', action='store_true', help='Return manufacturer identities from a replayed packet')
    args = parser.parse_args()
    if args.identities and not args.replay:
        parser.error('--identities requires --replay')
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    if root != ROOT.resolve() / 'data/local/release-data' or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', s, re.I) for s in root.parts):
        raise ValueError('g6_private_release_directory_required')
    if args.capture:
        fetcher = SourceFetcher(timeout=25, max_bytes=LIMIT, document_parser=lambda body, _: body,
                                text_parser=lambda *_: '', url_policy=lambda url, _: url in SOURCES.values())
        files = {}
        for name, url in SOURCES.items():
            source = fetcher.fetch(url, {'Xpeng'})
            if (source['status'], source.get('http_status'), source.get('final_url')) != ('reachable', 200, url):
                raise ValueError('g6_unavailable_source:' + url)
            files[name] = source['document']
        report = review(files)
        report['captured_at'] = datetime.now(timezone.utc).isoformat()
        folder = Path(tempfile.mkdtemp(prefix='xpeng-g6-review-', dir=root))
        for name, raw in files.items():
            (folder / name).write_bytes(raw)
        (folder / 'review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    else:
        folder = args.replay.resolve(strict=True)
        if folder != args.replay.absolute() or folder.parent != root or not re.fullmatch(r'xpeng-g6-review-[a-z0-9_]+', folder.name):
            raise ValueError('g6_private_capture_required')

        def read(name):
            path = folder / name
            if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_size > LIMIT:
                raise ValueError('g6_regular_capture_file_required')
            return path.read_bytes()

        saved = json.loads(read('review.json'))
        report = review({name: read(name) for name in SOURCES})
        report['captured_at'] = saved['captured_at']
        if report != saved:
            raise ValueError('g6_capture_or_review_changed')
        if args.identities:
            print(json.dumps(configured_identities(read('config.html'), report['variants'])))
            return
    print(json.dumps({'output': str(folder / 'review.json'), 'sources': len(SOURCES),
                      'variants': len(report['variants']), 'publication_approved': False}))


if __name__ == '__main__':
    main()
