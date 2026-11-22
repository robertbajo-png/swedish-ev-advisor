"""Collect and replay private source evidence for the current Swedish XPENG G9."""

import argparse
import io
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from openpyxl import load_workbook

from audit_catalog_sources import ROOT, SourceFetcher
from import_mobility_sweden import parse_ranking_sheet
from manufacturer_embedded_data import ScriptData, unique_object
from variant_refresh import one, parse_document
from xpeng_g6_review import (APPOINTMENT as HISTORICAL_APPOINTMENT, LIMIT, MARKET, PRESSROOM, WORKBOOK,
                             classes, clean, dealer_appointment, exact_link, sha)

CONFIG = 'https://store.xpeng.com/se/configurator/new_G9'
DE = 'https://store.xpeng.com/de/configurator/new_G9'
TECH = 'https://s-cdn.xpeng.com/commoncms/prod/2026-11-06/1c654ffc82e9482998d66dd73529f8be.pdf'
PRESS = PRESSROOM + 'pressreleases/nya-xpeng-g9-svenska-priser-och-foersaeljningsstart-3396460'
PHOTO = PRESSROOM + 'images/nya-g9-1-punkt-jpeg-3270628'
DEALER = 'https://lecab.se/erbjudande/xpeng-g9/'
APPOINTMENT = 'https://www.xpeng.com/se/find-us'
SOURCES = {'config.html': CONFIG, 'german.html': DE, 'german.pdf': TECH,
           'press.html': PRESS, 'dealer.html': DEALER, 'appointment.json': APPOINTMENT,
           'market.html': MARKET, 'market.xlsx': WORKBOOK}
HISTORICAL_SOURCES = {**{key:url for key,url in SOURCES.items() if key != 'appointment.json'},
                      'appointment.html': HISTORICAL_APPOINTMENT}
STANDARD, LONG, AWD = 'RWD Standard Range', 'RWD Long Range', 'AWD Performance'
FACTORY = {STANDARD: 'EEAB', LONG: 'EEBB', AWD: 'EECB'}
TRIMS = {
    STANDARD: dict(price=719900, wheels=20, power=258, gross=79, dc=445, drive='RWD',
                   wltp=502, consumption=18.4, curb=2235, gvw=2730, launch_gross=80.3),
    AWD: dict(price=849900, wheels=21, power=423, gross=93.1, dc=525, drive='AWD',
              wltp=540, consumption=20.1, curb=2420, gvw=2910, launch_gross=94.6),
}


def proof(key, raw, value, quote, **scope):
    return {'value': value, 'source_url': SOURCES[key], 'source_hash': sha(raw), 'quote': quote, **scope}


def configurator_identities(raw, *, market):
    parser = ScriptData()
    parser.feed(raw.decode('utf-8'))
    if parser.language != {'SE': 'sv', 'DE': 'de'}[market]:
        raise ValueError('g9_wrong_configurator_language')
    states = []
    for script in parser.scripts:
        if 'carVersionListData' not in script:
            continue
        frame = one(re.finditer(r'\s*self\.__next_f\.push\((.+)\);?\s*', script, re.S),
                    'g9_literal_next_frame_required')
        item = json.loads(frame[1], object_pairs_hook=unique_object)
        if not (isinstance(item, list) and len(item) == 2 and item[0] == 1 and isinstance(item[1], str)):
            raise ValueError('g9_literal_version_chunk_required')
        for line in item[1].splitlines():
            if 'carVersionListData' in line:
                tag, _, data = line.partition(':')
                if not re.fullmatch(r'[0-9a-f]+', tag):
                    raise ValueError('g9_invalid_version_chunk')
                states.append(json.loads(data, object_pairs_hook=unique_object)[1][3]['states'])
    state = one(states, 'g9_unique_configurator_state_required')
    expected = TRIMS if market == 'SE' else FACTORY
    series = ('651', 'New G9') if market == 'SE' else ('631', 'G9')
    result = {}
    for item in state['carVersionListData']:
        trim = item.get('carVersionName')
        if (state['carSeriesCode'] != 'new_G9' or trim not in expected or trim in result
                or (item.get('carSeriesCode'), item.get('powerType'), item.get('carVersionCode')) != ('E38bV', 'BEV', FACTORY[trim])
                or (item.get('carSeriesId'), item.get('carSeriesName')) != series or item.get('carVersionAlias') != trim
                or not re.fullmatch(r'[0-9]+', item.get('id', ''))):
            raise ValueError('g9_exact_export_generation_or_trim_required')
        if market == 'SE':
            amount = TRIMS[trim]['price']
            if (item.get('msrpBeforeSubsidy'), item.get('msrpAfterSubsidy')) != (amount, amount):
                raise ValueError('g9_price_changed_or_depends_on_subsidy')
        result[trim] = proof('config.html' if market == 'SE' else 'german.html', raw, 'E38bV$' + FACTORY[trim],
                             f'E38bV | {trim} | {FACTORY[trim]}', market=market, version_id=item['id'])
    if result.keys() != expected.keys():
        raise ValueError('g9_expected_market_variants_required')
    return result


def swedish_cards(raw):
    doc = parse_document(raw, 'text/html')
    if [node.text() for node in doc.nodes('h2')] != ['BYGG DIN XPENG G9']:
        raise ValueError('g9_exact_swedish_configurator_required')
    panel = one((n for n in doc.nodes('div') if classes(n, 'settingCard_content__')
                 and any(classes(c, 'detailCard_title__') and c.text() in TRIMS for c in n.nodes('span'))),
                'g9_unique_swedish_variant_panel_required')
    result = {}
    for card in (n for n in panel.nodes('div') if classes(n, 'detailCard_detailCard__')):
        trim = one((n.text() for n in card.nodes('span') if classes(n, 'detailCard_title__')), 'g9_card_title_required')
        if trim not in TRIMS or trim in result:
            raise ValueError('g9_unexpected_swedish_variant_card')
        expected = TRIMS[trim]
        article = clean(one(card.nodes('article'), 'g9_variant_article_required').text())
        intro, marker, data = article.partition(' Viktiga specifikationer: ')
        specs, exterior, _ = data.partition(' Exteri\xf6r ')
        label = 'Standard Range' if trim == STANDARD else trim
        drive = 'bakhjulsdrivna' if trim == STANDARD else 'fyrhjulsdrivna'
        if not (marker and exterior and intro.startswith(f'NYA XPENG G9 {label} \xe4r den {drive} versionen')
                and '800 Volt Sepa 2.0' in specs and 'beroende av typgodk\xe4nnandet' in article):
            raise ValueError('g9_exact_facelift_configuration_required')

        def matched(text, pattern, value, **scope):
            match = one(re.finditer(pattern, text), 'g9_exact_variant_value_required:' + trim + ':' + pattern)
            return proof('config.html', raw, value, match[0], trim=trim, **scope)

        dec = lambda x: str(x).replace('.', ',')
        facts = {
            'wltp_range_km': matched(specs, rf'R\xe4ckvidd \(WLTP\): {expected["wltp"]} km\*',
                                     expected['wltp'], wheels_inches=expected['wheels'], scope='swedish_model_variant_wltp'),
            'wltp_consumption_kwh_100km': matched(specs, rf'Genomsnittlig f\xf6rbrukning \(WLTP\): {re.escape(dec(expected["consumption"]))} kWh/100km',
                                                 expected['consumption'], wheels_inches=expected['wheels']),
            'battery_kwh': matched(specs, rf'Batterikapacitet \(brutto\): {re.escape(dec(expected["gross"]))} kWh',
                                   expected['gross'], capacity_basis='gross'),
            'dc_charge_kw': matched(specs, rf'DC-laddning: upp till {expected["dc"]} kW', expected['dc'], scope='vehicle_peak'),
            'ac_charge_kw': matched(specs, r'AC-laddning: 11 kW \(3-fas\)', 11),
            'boot_liters': matched(article, r'Bagagevolym: 660 liter / 1\.576 liter med nedf\xe4llt baks\xe4te', 660,
                                    scope='rear_seats_up_without_frunk'),
            'drivetrain': proof('config.html', raw, expected['drive'], intro.split('.')[0]),
        }
        motor = matched(specs, rf'Max effekt: {expected["power"]} kW \(\d+ hk\)', expected['power'])
        weight = matched(specs, rf'Bruttovikt: {expected["gvw"] // 1000}\.{expected["gvw"] % 1000:03d} kg', expected['gvw'])
        wheels = matched(article, rf'{expected["wheels"]}" aluminiumf\xe4lgar', expected['wheels'])
        tow = matched(specs, r'Dragvikt: 1\.500 kg', 1500, scope='swedish_rating_without_braking_label')
        amount = clean(one((n.text() for n in card.nodes('div') if classes(n, 'detailCard_priceValue__')),
                           'g9_cash_price_in_variant_card_required'))
        if amount != f'{expected["price"]:,} kr'.replace(',', ' '):
            raise ValueError('g9_exact_unfinanced_base_price_required:' + trim)
        result[trim] = dict(facts=facts, tow_reference=tow, motor=motor, gross_vehicle_weight=weight, standard_wheels=wheels,
                            price=proof('config.html',raw,expected['price'],amount,market='SE',price_type='list_price',
                                        scope='manufacturer_base_cash_price',trim=trim))
    if result.keys() != TRIMS.keys():
        raise ValueError('g9_exact_two_swedish_versions_required')
    return result


def table_scope(table, widths_label):
    rows = table.extract()
    labels = [clean(row[0] or '') for row in rows]
    widths = table.rows[labels.index(widths_label)].cells[1:]
    if len(widths) != 3 or not all(widths):
        raise ValueError('g9_exact_three_german_columns_required')
    edges = [(c[0], c[2]) for c in widths]

    def row(label):
        index = one((i for i, item in enumerate(labels) if item == label), 'g9_missing_german_row:' + label)
        cells = [(clean(value), cell) for value, cell in zip(rows[index][1:], table.rows[index].cells[1:], strict=True)
                 if value is not None and cell is not None]
        return tuple(one((text for text, box in cells if box[0] <= left + 1 and box[2] >= right - 1),
                         'g9_german_cell_not_bound_to_variant:' + label) for left, right in edges)
    return row


def german_technical(raw):
    if not raw.startswith(b'%PDF-'):
        raise ValueError('g9_german_technical_pdf_required')
    with pdfplumber.open(io.BytesIO(raw)) as document:
        if len(document.pages) != 14:
            raise ValueError('g9_german_technical_layout_changed')
        header = 'RWD STANDARD RANGE RWD LONG RANGE AWD PERFORMANCE'
        if any(header not in map(clean, page.extract_text().splitlines()) for page in document.pages[1:3]):
            raise ValueError('g9_german_column_order_changed')
        chassis = table_scope(one(document.pages[1].find_tables(), 'g9_german_chassis_table_required'),
                              'Bruttomasse des Fahrzeugs (kg)')
        powertrain = table_scope(one(document.pages[2].find_tables(), 'g9_german_powertrain_table_required'),
                                  'Reichweite (WLTP) kombiniert (km)')
        rows = [(chassis, 'Bruttomasse des Fahrzeugs (kg)', ('2730', '2810', '2910')),
                (chassis, 'Anzahl Sitze', ('5',) * 3),
                (chassis, 'Anh\xe4ngelast gebremst / ungebremst (kg)', ('1500 / 750',) * 3),
                (chassis, 'Kofferraumvolumen nach VDA Norm (L)', ('660 / 1576 (bei umgeklappter R\xfccksitzbank)',) * 3),
                (powertrain, 'Antrieb', ('Heckantrieb', 'Heckantrieb', 'Allrad')),
                (powertrain, 'AC-Ladeleistung (kW)', ('11 (3-phasig)',) * 3),
                (powertrain, 'Batteriekapazit\xe4t brutto (kWh)', ('79', '93,1', '93,1')),
                (powertrain, 'Reichweite (WLTP) kombiniert (km)', ('502', '585', '540')),
                (powertrain, 'Energieverbrauch (WLTP) kombiniert (kWh/100 km)', ('18,4', '18,6', '20,1'))]
        for reader, label, expected in rows:
            actual = reader(label)
            if actual != expected:
                raise ValueError('g9_german_variant_scope_changed:' + label)
        limits = powertrain('DC-Schnellladeleistung (kW)')
        if (limits[0], limits[2]) != ('445', '525'):
            raise ValueError('g9_german_peak_charge_scope_changed')
    return proof('german.pdf', raw, 1500, 'Anh\xe4ngelast gebremst / ungebremst (kg) | 1500 / 750',
                 page=2, scope='braked_only_on_matched_factory_versions')


def launch_evidence(raw):
    doc = parse_document(raw, 'text/html')
    table = one(doc.nodes('table'), 'g9_swedish_generation_launch_table_required')
    pairs = [[clean(cell.text()) for cell in row.nodes('td')] for row in table.nodes('tr')]
    if not pairs or pairs[0] != ['Tekniska data nya XPENG G9', 'Standard Range', 'AWD Performance']:
        raise ValueError('g9_launch_trim_headers_changed')
    seats = one((row for row in pairs if row and row[0] == 'Antal platser'), 'g9_seats_required')
    if seats != ['Antal platser', '5']:
        raise ValueError('g9_launch_shared_seat_count_changed')
    battery = one((row for row in pairs if row and row[0] == 'Batterikapacitet, brutto (kWh)'), 'g9_launch_batteries_required')
    if battery[1:] != ['80,3', '94,6']:
        raise ValueError('g9_launch_battery_conflict_changed')
    ranges = one((row for row in pairs if row and row[0] == 'WLTP-r\xe4ckvidd (km)'), 'g9_launch_ranges_required')
    if ranges[1:] != ['502', '540']:
        raise ValueError('g9_launch_range_generation_mismatch')
    return proof('press.html', raw, 5, 'Antal platser | 5', scope='exact_swedish_two_trim_launch_table')


def dealer_prices(raw, variants, appointment_url=APPOINTMENT):
    doc = parse_document(raw, 'text/html')
    body = clean(doc.text())
    if ([n.text() for n in doc.nodes('h1')] != ['XPENG G9']
            or 'Nya XPENG G9 Standard Range' not in body
            or 'F\xf6rbrukning, blandad k\xf6rning (WLTP): 18,4 kWh/100 km' not in body):
        raise ValueError('g9_authorized_new_model_offer_required')
    patterns = {STANDARD: r'XPENG G9 RWD Standard Range Elbil Erbjudande Pris fr\. (\d{3} \d{3})\s?kr',
                AWD: r'AWD Performance: K\xf6ppris: (\d{3} \d{3})\s?kr'}
    result = {}
    for trim, pattern in patterns.items():
        match = one(re.finditer(pattern, body), 'g9_separate_cash_price_required:' + trim)
        price = int(match[1].replace(' ', ''))
        if price != variants[trim]['price']['value']:
            raise ValueError('g9_manufacturer_dealer_price_conflict:' + trim)
        result[trim] = proof('dealer.html', raw, price, match[0], authorization_url=appointment_url, scope='independent_cash_corroboration')
    return result


def locator_appointment(packet):
    snapshot = json.loads(packet, object_pairs_hook=unique_object)
    html = snapshot.get('rendered_html')
    if ((snapshot.get('final_url'), snapshot.get('http_status'), snapshot.get('body_kind'))
            != (APPOINTMENT, 200, 'rendered_official_outlet_card') or not isinstance(html, str) or not 0 < len(html) < 16000):
        raise ValueError('g9_exact_official_locator_receipt_required')
    doc = parse_document(html.encode('utf-8'), 'text/html')
    quote = 'XPENG Experience Center Sweden Karlstad Blockgatan 5, 653 41 Karlstad info@lecab.se'
    if quote not in clean(doc.text()):
        raise ValueError('g9_exact_karlstad_outlet_appointment_required')
    return proof('appointment.json', packet, 'Lecab Bil Karlstad', quote, scope='rendered_official_public_locator')


def market_row(raw):
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        rows, _ = parse_ranking_sheet(workbook['Elbil ranking'], MARKET)
        row = one((r for r in rows if (r.brand_raw, r.model_raw, r.fuel_type_raw) == ('XPENG', 'G9', 'EL')),
                  'g9_exact_market_alias_required')
        if row.needs_mapping or row.last_seen_month != '2026-10-01' or row.registrations_last_month <= 0:
            raise ValueError('g9_exact_october_market_presence_required')
        return proof('market.xlsx', raw, row.registrations_last_month, 'XPENG | G9 | EL',
                     registrations_ytd=row.registrations_ytd, report_month=row.last_seen_month,
                     scope='registrations_only_not_vehicle_specifications')
    finally:
        workbook.close()


def review(files, *, historical=False):
    registered = HISTORICAL_SOURCES if historical else SOURCES
    if files.keys() != registered.keys() or not all(0 < len(raw) <= LIMIT for raw in files.values()):
        raise ValueError('g9_full_pinned_source_packet_required')
    exact_link(files['press.html'], PRESS, PHOTO)
    exact_link(files['market.html'], MARKET, WORKBOOK)
    variants = swedish_cards(files['config.html'])
    se = configurator_identities(files['config.html'], market='SE')
    de = configurator_identities(files['german.html'], market='DE')
    seats = launch_evidence(files['press.html'])
    tow = german_technical(files['german.pdf'])
    appointment = dealer_appointment(files['appointment.html']) if historical else locator_appointment(files['appointment.json'])
    prices = dealer_prices(files['dealer.html'], variants, appointment['source_url'])
    for trim, variant in variants.items():
        if se[trim]['value'] != de[trim]['value'] or variant['tow_reference']['value'] != tow['value']:
            raise ValueError('g9_cross_market_hardware_mapping_conflict')
        variant.update(manufacturer_identity=se[trim], engineering_identity=de[trim],
                       dealer_price={**prices[trim], 'authorization_hash': appointment['source_hash']})
        variant['facts'].update(seats=seats, tow_kg={**tow, 'factory_version': se[trim]['value'],
                                                   'swedish_source': variant['tow_reference']})
        variant['battery_decision'] = proof('press.html', files['press.html'], TRIMS[trim]['launch_gross'],
                                            'Batterikapacitet, brutto (kWh) | 80,3 | 94,6',
                                            disposition='older_launch_value_replaced_by_current_exact_swedish_configurator')
    return {'status': 'private_g9_profile_review', 'model_key': 'xpeng|g9', 'market': 'SE',
            'sources': {name: dict(url=url, sha256=sha(files[name])) for name, url in registered.items()},
            'variants': variants, 'market_index': market_row(files['market.xlsx']), 'dealer_appointment': appointment,
            'photo_source': PHOTO, 'publication_approved': False, 'database_writes': 0, 'paid_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    args = parser.parse_args()
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    if root != ROOT.resolve() / 'data/local/release-data' or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', s, re.I) for s in root.parts):
        raise ValueError('g9_private_release_directory_required')
    if args.capture:
        fetcher = SourceFetcher(timeout=25, max_bytes=LIMIT, url_policy=lambda url, _: url in SOURCES.values(),
                                document_parser=lambda body, _: body, text_parser=lambda *_: '')
        files, fetched = {}, {}
        for name, url in SOURCES.items():
            if name == 'appointment.json':
                if not fetcher.robots_allowed(url):
                    raise ValueError('g9_official_locator_robots_unavailable_or_denied')
                raw = subprocess.check_output(['node','scripts/capture_xpeng_g9_locator.mjs'], cwd=ROOT, timeout=50)
                locator_appointment(raw)
                files[name], fetched[name] = raw, json.loads(raw)['fetched_at']
                continue
            response = fetcher.fetch(url, {'Xpeng'})
            if (response['status'], response.get('final_url'), response.get('http_status')) != ('reachable', url, 200):
                raise ValueError('g9_official_source_unavailable:' + name)
            files[name] = response['document']
            fetched[name] = datetime.now(timezone.utc).isoformat()
        folder = Path(tempfile.mkdtemp(prefix='xpeng-g9-review-', dir=root))
        for name, body in files.items():
            (folder / name).write_bytes(body)
        try:
            report = {**review(files), 'fetched_at': fetched}
        except ValueError as error:
            (folder / 'held.json').write_text(json.dumps(dict(fetched_at=fetched, reason=str(error), status='held')) + '\n')
            raise
        (folder / 'review.json').write_text(json.dumps(report,indent=2) + '\n', encoding='utf-8')
    else:
        folder = args.replay.resolve(strict=True)
        if folder != args.replay.absolute() or folder.parent != root or not re.fullmatch(r'xpeng-g9-review-[a-z0-9_]+', folder.name):
            raise ValueError('g9_private_capture_required')

        def read(name):
            path = folder / name
            if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_size > LIMIT:
                raise ValueError('g9_regular_capture_file_required')
            return path.read_bytes()

        saved = json.loads(read('review.json'),object_pairs_hook=unique_object)
        historical = 'appointment.html' in saved['sources']
        registered = HISTORICAL_SOURCES if historical else SOURCES
        report = {**review({name:read(name) for name in registered}, historical=historical), 'fetched_at':saved['fetched_at']}
        if saved != report:
            raise ValueError('g9_private_replay_mismatch')
    print(json.dumps(dict(output=str(folder/'review.json'), sources=len(SOURCES), variants=len(report['variants']),
                          core_fields=sum(len(packet['facts']) for packet in report['variants'].values()),
                          publication_approved=False)))


if __name__ == '__main__':
    main()
