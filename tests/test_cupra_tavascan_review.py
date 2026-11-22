import copy
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from build_source_queue import official_source_for
from cupra_tavascan_review import (DIN_BIL_GAVLE, DRIVE_DEALER, DRIVE_ESKILSTUNA, DRIVE_GAVLE, DRIVE_HARDWARE,
                                  DRIVE_LINKOPING, DRIVE_NACKA, DRIVE_OFFER, DRIVE_WLTP_STOCK, ENERGY, INDEX, MODEL,
                                  PRICE, VZ_MY25, drive_base_profile, drive_equipment, drive_offer_reference, drive_stock, energy_rows,
                                  drive_wltp_importer_context, finnish_wltp_reference, gavle_drive_price,
                                  importer_stock_identity, italian_reference,
                                  read_market, review, source_proof, stock_prices, swedish_drive_support, verify_links, vz_my25_stock)


def price_fixture(year, start):
    stamp = f'PRISLISTA MODELL\u00c5R {year}, 15 SEPTEMBER 2026'
    return [
        'CUPRA TAVASCAN PRISLISTA', f'LAGERBILAR MODELL\u00c5R\u2013{year % 100}',
        f'Tavascan Drive 77 kWh 210 kW/286 hk 2WD {start}:\u2013',
        f'Tavascan VZ 77 kWh 250 kW/340 hk 4WD {start + 45000}:\u2013',
        f'Tavascan VZ Drive 77 kWh 250kW/340 hk 4WD {start + 65000}:\u2013',
        f'Tavascan VZ Adrenaline 77 kWh 250 kW/340 hk 4WD {start + 115000}:\u2013',
        f'Samtliga priser \u00e4r inklusive moms och avser lagerbilar av modell\u00e5r {year}.',
        'Dragkrok 14 900:\u2013', 'Privatleasing fr\u00e5n 3 999 kr/m\u00e5n',
    ], stamp


def market_workbook(name, count=11, month='oktober'):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Elbil ranking'
    ws['H2'] = f'Nyregistreringar {month} 2026'
    ws['D10'] = name
    ws['F10'] = count
    ws['M10'] = 52
    stream = io.BytesIO()
    wb.save(stream)
    wb.close()
    return stream.getvalue()


def drive_page(url, price=554900, schema_price=None):
    nacka = url == DRIVE_NACKA
    dealer = url == DRIVE_DEALER
    title = '77kWh 286hk/2026/DRIVE' if nacka else 'CUPRA 210 KW / 286 HK'
    outlet = 'Bilia Nacka Cupra' if nacka else 'M\u00f6ller Bil Eskilstuna'
    outlet_line = '' if dealer else f'\u00c5terf\u00f6rs\u00e4ljare: {outlet}'
    rows = ' '.join(f'{label} {display}' for label, display, _ in DRIVE_HARDWARE.values())
    code = 'EWB33D' if nacka else 'EZK46X'
    cash = f'{price:,}'.replace(',', ' ')
    schema = {'@type': 'Car', 'brand': {'name': 'CUPRA'}, 'model': 'Tavascan', 'vehicleModelDate': '2026',
              'itemCondition': 'https://schema.org/NewCondition', 'vehicleEngine': {'fuelType': 'El'},
              'driveWheelConfiguration': 'https://schema.org/FrontWheelDriveConfiguration',
              'offers': {'price': schema_price or price, 'priceCurrency': 'SEK', 'availability': 'https://schema.org/InStock'}}
    return (f'<p>Tillbaka</p><h1>CUPRA Tavascan</h1><p>{title} Ny Om bilen {outlet_line} Drivmedel El '
            f'V\u00e4xell\u00e5da Automat Miltal 0 Modell\u00e5r 2026 Registreringsnummer {code}</p>'
            '<p>Fabriksinformation Styrnummer Tavascan Drive Swedish Edition</p>'
            f'<p>{"Tekniska data" if dealer else "Teknisk data"} {rows} Sl\u00e4pvikt, obromsad 750 kg '
            f'Energideklaration d\u00e4ck Pris {cash} kr R\u00e4kna p\u00e5 bill\u00e5n Eskilstuna CUPRA</p>'
            + (f'<script type="application/ld+json">{json.dumps(schema)}</script>' if dealer else '')).encode()


def importer_page(*, stock_key='LYK12H', visible_year=2026, model_code='KR1BCD', edition='Drive', **changes):
    car = {'model': 'Tavascan', 'modelYear': 2026, 'modelCode': model_code, 'fuelType': 'El',
           'specialBrandCode': 'Q', 'wltpInformation': None, **changes}
    state = {'locale': 'se', 'page': '/[brandSlug]/[regNr]', 'query': {'brandSlug': 'cupra', 'regNr': stock_key},
             'props': {'pageProps': {'brand': 'cupra', 'car': car}}}
    hardware = ' '.join(f'{label} {display}' for label, display, _ in DRIVE_HARDWARE.values())
    return (f'<h1>CUPRA Tavascan</h1><p>Ny \xc5terf\xf6rs\xe4ljare: Cupra G\xe4vle Miltal 0 Modell\xe5r {visible_year} '
            f'Registreringsnummer {stock_key} Fabriksinformation Styrnummer Tavascan {edition} Swedish Edition '
            f'Teknisk data {hardware} Energideklaration d\xe4ck Pris 554 900 kr R\xe4kna p\xe5 bill\xe5n</p>'
            f'<script type="application/json" id="__NEXT_DATA__">{json.dumps(state)}</script>').encode()


def gavle_dealer(*, visible_price=554900, schema_price=554900, pictured_id='LYK12H'):
    schema = {'@type': 'Car', 'brand': {'name': 'CUPRA'}, 'model': 'Tavascan', 'vehicleModelDate': '2026',
              'itemCondition': 'https://schema.org/NewCondition', 'vehicleEngine': {'fuelType': 'El'},
              'driveWheelConfiguration': 'https://schema.org/RearWheelDriveConfiguration',
              'offers': {'price': schema_price, 'priceCurrency': 'SEK', 'availability': 'https://schema.org/InStock'}}
    return (f'<img alt="CUPRA Tavascan {pictured_id}"><h1>CUPRA Tavascan Endurance</h1><p>Din Bil / CUPRA G\xe4vle '
            f'Kontantpris {visible_price:,} kr Intresseanm\xe4lan Drivlina Bakhjulsdrift</p>'.replace(',', ' ')
            + f'<script type="application/ld+json">{json.dumps(schema)}</script>').encode()


class TavascanReviewTests(unittest.TestCase):
    def test_official_queue_and_link_scope(self):
        self.assertEqual(official_source_for('CUPRA', 'TAVASCAN'), (MODEL, 'verified_known_model_url'))
        html = (f'<a href="{PRICE[2026]}">Prislista modell&#229;r 26 (15 sep-26)</a>'
                f'<a href="{PRICE[2026]}"></a>').encode()
        link = ('Prislista modell\u00e5r 26 (15 sep-26)', PRICE[2026])
        verify_links(html, INDEX, [link])
        with self.assertRaises(ValueError):
            verify_links(html, INDEX, [('Prislista modell\u00e5r 25 (15 sep-26)', PRICE[2026])])
        with self.assertRaises(ValueError):
            verify_links(html, INDEX, [('Ladda ner', ENERGY)])

    def test_stock_prices_are_edition_specific_not_lease_accessory_or_previous_year(self):
        newer, stamp = price_fixture(2026, 554900)
        old, older_stamp = price_fixture(2025, 534900)
        current = stock_prices(newer, stamp, 2026)
        self.assertEqual(stock_prices(newer, stamp.replace('PRISLISTA', 'PRISLIST A'), 2026), current)
        previous = stock_prices(old, older_stamp, 2025)
        self.assertEqual([v['value'] for v in current.values()], [554900, 599900, 619900, 669900])
        self.assertEqual(previous['Drive']['value'], 534900)
        self.assertEqual(current['Drive']['drivetrain'], 'RWD')
        self.assertEqual(current['VZ Drive']['drivetrain'], 'AWD')
        self.assertEqual(current['VZ']['price_scope'], 'manufacturer_swedish_stock_price_list')
        self.assertNotIn('available_confirmed', current['Drive'])
        for rows, date in [(old, stamp), (newer, older_stamp), (newer + [newer[2]], stamp),
                           ([x.replace('210 kW/286 hk 2WD', '250 kW/340 hk 4WD') for x in newer], stamp),
                           ([x.replace('inklusive moms', 'exklusive moms') for x in newer], stamp)]:
            with self.subTest(rows=rows, date=date), self.assertRaises(ValueError):
                stock_prices(rows, date, 2026)

    def test_wltp_motor_interval_is_not_an_exact_trim_value(self):
        lines = ['OKTOBER 2026', 'm\u00e4tt enligt WLTP-standarden f\u00f6r fordonets grundversion',
                 'Tavascan 77 kWh Batteri 210 kW / 286 hk \u2013 16,0 0',
                 'Tavascan 77 kWh Batteri 250 kW / 340 hk \u2013 17,2\u201317,4 0']
        rows = energy_rows(lines)
        self.assertEqual((rows['210']['min_kwh_100km'], rows['210']['max_kwh_100km']), (16, 16))
        self.assertEqual((rows['250']['min_kwh_100km'], rows['250']['max_kwh_100km']), (17.2, 17.4))
        self.assertNotIn('VZ', rows)
        for changed in (lines[1:], [*lines[:3], lines[3].replace('17,4', '17,1')],
                        [*lines[:3], lines[3].replace('340 hk', '286 hk')]):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                energy_rows(changed)

    def test_market_workbook_requires_exact_positive_model_row_in_expected_month(self):
        found = read_market(market_workbook('CUPRA TAVASCAN'))
        self.assertEqual((found['raw_alias'], found['registrations_month']), ('CUPRA | TAVASCAN | EL', 11))
        for name, count, month in [('CUPRA TAVASCAN/TERRAMAR', 11, 'oktober'),
                                   ('CUPRA TAVASCAN', 0, 'oktober'), ('CUPRA TAVASCAN', 11, 'september')]:
            with self.subTest(name=name, count=count, month=month), self.assertRaises(ValueError):
                read_market(market_workbook(name, count, month))

    def test_drive_retains_individual_prices_and_conflicting_dealer_schema_separately(self):
        files = {'drive-nacka.html': drive_page(DRIVE_NACKA, 534900), 'drive-eskilstuna.html': drive_page(DRIVE_ESKILSTUNA),
                 'drive-dealer.html': drive_page(DRIVE_DEALER)}
        report = swedish_drive_support(files, {'value': 554900})
        self.assertTrue(report['dealer_offer_matches_current_my26_price_list'])
        self.assertEqual(report['dealer_link_evidence']['value'], 'M\u00f6ller Bil Eskilstuna')
        references = report['importer_stock_references']
        self.assertEqual([r['cash_offer']['value'] for r in references], [534900, 554900])
        self.assertTrue(all(r['cash_offer']['price_type'] == 'dealer_offer' for r in references))
        r = report['dealer_stock_reference']
        self.assertIn('FrontWheelDrive', r['dealer_schema_drive_reference'])
        self.assertEqual(r['fields']['tow_kg']['value'], 1000)
        self.assertEqual(r['fields']['dc_charge_kw']['value'], 135)
        self.assertNotIn('wltp_range_km', r['fields'])
        self.assertNotIn('drivetrain', r['fields'])
        self.assertFalse(swedish_drive_support(files, {'value': 534900})['dealer_offer_matches_current_my26_price_list'])

    def test_drive_rejects_mismatched_year_trim_played_power_and_tax_price(self):
        raw = drive_page(DRIVE_NACKA)
        for before, after in [('2026/DRIVE', '2027/DRIVE'), ('Styrnummer Tavascan Drive', 'Styrnummer Tavascan VZ Drive'),
                              ('Maximal Laddningseffekt DC 135 kW', 'Laddstation 135 kW'),
                              ('bromsad 12% 1000 kg', 'obromsad 1000 kg')]:
            with self.subTest(before=before), self.assertRaises(ValueError):
                drive_stock(raw.replace(before.encode(), after.encode()), DRIVE_NACKA)
        with self.assertRaisesRegex(ValueError, 'cash_schema_conflict'):
            drive_stock(drive_page(DRIVE_DEALER, schema_price=443920), DRIVE_DEALER)

    def test_stock_factory_code_and_year_are_independent_of_wltp_and_display_trim(self):
        result = importer_stock_identity(importer_page(), DRIVE_GAVLE, 'Drive', 2026, 'KR1BCD')
        self.assertEqual(result['model_code']['value'], 'KR1BCD')
        self.assertEqual(result['wltp_state'], 'no_wltp_payload')
        self.assertNotIn('wltp_range_km', result)
        new = importer_page(wltpInformation={'range': 550, 'consumption': 16})
        self.assertEqual(importer_stock_identity(new, DRIVE_GAVLE, 'Drive', 2026, 'KR1BCD')['wltp_state'],
                         'payload_requires_separate_review')
        for raw in (importer_page(stock_key='EWB33D'), importer_page(visible_year=2025), importer_page(edition='VZ Drive'),
                    importer_page(model_code='KR1CED'), importer_page(modelYear=2027), importer_page(fuelType='Bensin')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                importer_stock_identity(raw, DRIVE_GAVLE, 'Drive', 2026, 'KR1BCD')

    def test_wltp_importer_context_requires_the_live_unit_and_exact_edition_package(self):
        plate = 'MJB63M'
        url = DRIVE_WLTP_STOCK[plate]
        packages = [{'code': 'P80', 'text': 'Styrnummer Tavascan Drive Swedish Edition'},
                    {'code': 'PF0', 'text': 'DRIVE: Navigation'}, {'code': 'YC1', 'text': 'Drive Edition'}]
        input = {'regNumber': plate, 'comissionId': 2222026867556, 'used': False, 'mileage': 0,
                 'factoryEquipment': packages, 'driveType': 'Framhjulsdrift'}
        proof = drive_wltp_importer_context(importer_page(stock_key=plate, **input), url)
        self.assertEqual(proof['order'], '2222026867556')
        self.assertEqual(proof['importer_drive_type_reference'], 'Framhjulsdrift')
        delivery = drive_wltp_importer_context(importer_page(stock_key=plate, **(input | {'mileage': 1})), url)
        self.assertEqual(delivery['importer_mileage_reference'], 1)
        for change in ({'regNumber': 'UON91J'}, {'used': True}, {'mileage': 5}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'wltp_importer_edition_mismatch'):
                drive_wltp_importer_context(importer_page(stock_key=plate, **(input | change)), url)
        for invalid in (packages[1:], packages + packages[:1]):
            with self.assertRaisesRegex(ValueError, 'wltp_importer_package_required'):
                drive_wltp_importer_context(importer_page(stock_key=plate, **(input | {'factoryEquipment': invalid})), url)

    def test_gavle_is_same_stock_unit_and_not_a_second_model_or_list_price_source(self):
        report = gavle_drive_price(importer_page(), gavle_dealer(), {'value': 554900})
        self.assertEqual(report['cash_offer']['source_url'], DIN_BIL_GAVLE)
        self.assertEqual(report['cash_offer']['price_type'], 'dealer_offer')
        self.assertEqual(report['identity']['edition'], 'Drive')
        self.assertTrue(report['agrees_with_my26_stock_list'])
        for raw in (gavle_dealer(pictured_id='EWB33D'), gavle_dealer(visible_price=534900), gavle_dealer(schema_price=534900)):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'gavle_dealer_cash_or_identity_conflict'):
                gavle_drive_price(importer_page(), raw, {'value': 554900})
        with self.assertRaisesRegex(ValueError, 'gavle_dealer_cash_or_identity_conflict'):
            gavle_drive_price(importer_page(), gavle_dealer(), {'value': 534900})

    def test_drive_19_inch_rwd_stock_and_offer_do_not_turn_advertised_range_into_certified_wltp(self):
        equipment = ('<h1>CUPRA Tavascan</h1><p>CUPRA 210 KW / 286 HK Ny Drivmedel El V\u00e4xell\u00e5da Automat '
                     'Miltal 0 Modell\u00e5r 2026 Registreringsnummer DRX34F Styrnummer Tavascan Drive Swedish Edition '
                     'L\u00e4ttmetallf\u00e4lgar 19" Vulcano Ombordladdare Max 11 kW AC Bakhjulsdrift '
                     'D\u00e4ck 235/55 R19 fram och 255/50 R19 bak Teknisk data Report</p>')
        self.assertEqual(drive_equipment(equipment.encode())['drivetrain']['value'], 'RWD')
        for term, changed in [('2026', '2025'), ('R19', 'R20'), ('Bakhjulsdrift', 'Framhjulsdrift')]:
            with self.subTest(term=term), self.assertRaises(ValueError):
                drive_equipment(equipment.replace(term, changed).encode())
        offer = ('<h1>CUPRA Tavascan DRIVE 2WD</h1><p>Swedish Edition 77kWh (210kW) 100% EL '
                 'R\u00e4ckvidd upp till 550 km Privatleasa fr\u00e5n: 4.695 kr/m\u00e5n Editionpris: 554.900 kr '
                 'G\u00e4ller begr\u00e4nsat antal lagerbilar av modell\u00e5r 2026. 19" L\u00e4ttmetallf\u00e4lgar "VULCANO" '
                 'Br\u00e4nslef\u00f6rbrukning*** 15,3 kWh/100km blandad k\u00f6rning liter/100 km enligt WLTP</p>')
        proof = drive_offer_reference(offer.encode(), {'value': 554900})
        self.assertEqual(proof['advertised_upper_range_km']['value'], 550)
        self.assertEqual(proof['advertised_consumption']['value'], 15.3)
        self.assertFalse(proof['publication_approved'])
        self.assertNotIn('wltp_range_km', proof)
        with self.assertRaises(ValueError):
            drive_offer_reference((offer + '<p>Erbjudandet g\u00e4ller modell\u00e5r 2025.</p>').encode(), {'value': 554900})
        with self.assertRaises(ValueError):
            drive_offer_reference(offer.encode(), {'value': 534900})

    def test_vz_older_stock_cash_and_tow_are_not_my26_or_financing(self):
        source = VZ_MY25['vz-drive.html']
        raw = ('<h1>CUPRA Tavascan</h1><p>CUPRA VZ AWD 250 KW / 340 HK Ny Drivmedel El Miltal 0 '
               'Modell\u00e5r 2025 Registreringsnummer BGR07F Finanspris 497.470 kr Fabriksinformation '
               'Styrnummer Tavascan VZ Drive Swedish Edition Teknisk data Drivning 1-vxl Fyrhjulsdrift '
               'Batteristorlek (Netto) 77 kWh Batteristorlek (Brutto) 82 kWh Max. effekt 250 kW (340 hk) '
               'Sl\u00e4pvikt, bromsad 12% 1200 kg Bagageutrymmesvolym 540 l Energideklaration d\u00e4ck '
               'Pris 599 900 kr R\u00e4kna p\u00e5 bill\u00e5n</p>').encode()
        result = vz_my25_stock(raw, *source)
        self.assertEqual(result['model_year'], 2025)
        self.assertEqual(result['cash_offer']['value'], 599900)
        self.assertEqual(result['stock_references']['braked_towing_kg']['value'], 1200)
        self.assertNotIn('dc_charge_kw', result['stock_references'])
        for old, new in ((b'2025', b'2026'), (b'VZ Drive Swedish Edition', b'VZ Adrenaline Swedish Edition'),
                         (b'bromsad 12% 1200 kg', b'obromsad 1200 kg'), (b'599 900', b'4 900')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                vz_my25_stock(raw.replace(old, new), *source)

    def test_drive_base_profile_separates_wltp_consumption_from_an_advertised_range(self):
        energy = 'Br\u00e4nslef\u00f6rbrukning*** 15,3 kWh/100km'
        method = ('***Br\u00e4nsledeklaration och utsl\u00e4ppsv\u00e4rden \u00e4r uppm\u00e4tta i enlighet med g\u00e4llande lagstiftning '
                  'och g\u00e4ller bil i grundversion. De anges vid blandad k\u00f6rning liter/100 km enligt WLTP.')
        price = {'value': 554900}
        stock = [drive_stock(drive_page(url), url) for url in (DRIVE_NACKA, DRIVE_ESKILSTUNA)]
        wheel = source_proof(b'fixture', DRIVE_LINKOPING, 19, 'Vulcano')
        factory = [{'edition': 'Drive', 'model_year': 2026, 'model_code': {
            'value': 'KR1BCD', 'source_url': proof['source_url'], 'source_hash': proof['source_hash']}}
            for proof in [wheel, *(row['identity'] for row in stock)]]

        def evidence(raw):
            return {'drive_standard_wheel_and_offer_references': {
                        'equipment': {'model_year': 2026, 'wheel_inches': wheel, 'drivetrain': {'value': 'RWD'}},
                        'offer': {'model_year': 2026, 'wheel_inches': 19, 'manufacturer_cash_offer': price,
                                  'advertised_consumption': source_proof(raw, DRIVE_OFFER, 15.3, energy),
                                  'advertised_upper_range_km': source_proof(raw, DRIVE_OFFER, 550, 'R\u00e4ckvidd upp till 550 km')}},
                    'swedish_factory_stock_scope': {'existing_stock_identities': factory,
                        'independent_gavle_price_support': {'cash_offer': price, 'agrees_with_my26_stock_list': True}},
                    'swedish_my26_drive_stock_support': {'importer_stock_references': stock},
                    'my26_stock_price_references': {'Drive': price}, 'model_facts': {'seats': {'value': 5}},
                    'motor_wltp_references': {'210': {'min_kwh_100km': 16, 'max_kwh_100km': 16}}}

        valid = f'<p>{energy}</p><p>{method}</p>'.encode()
        profile = drive_base_profile(valid, evidence(valid))
        self.assertEqual(len(profile['technical_fields']), 8)
        self.assertEqual(profile['technical_fields']['wltp_consumption_kwh_100km']['value'], 15.3)
        self.assertEqual(profile['alternative_motor_level_consumption']['min_kwh_100km'], 16)
        self.assertEqual(profile['held'], ['wltp_range_km'])
        self.assertEqual(profile['advertised_max_range_only']['value'], 550)
        self.assertNotIn('wltp_range_km', profile['technical_fields'])
        self.assertFalse(profile['publication_approved'])
        for changed in (method.replace('grundversion', 'annan version'), method.replace('WLTP', 'NEDC'), method + ' ' + method):
            raw = f'<p>{energy}</p><p>{changed}</p>'.encode()
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'base_scope_wltp_footnote_required'):
                drive_base_profile(raw, evidence(raw))
        changed = copy.deepcopy(evidence(valid))
        changed['swedish_factory_stock_scope']['existing_stock_identities'][0]['model_year'] = 2025
        with self.assertRaisesRegex(ValueError, 'drive_factory_scope_mismatch'):
            drive_base_profile(valid, changed)
        changed = copy.deepcopy(evidence(valid))
        changed['swedish_my26_drive_stock_support']['importer_stock_references'][1]['fields']['tow_kg']['value'] = 1200
        with self.assertRaisesRegex(ValueError, 'technical_profile_conflict:tow_kg'):
            drive_base_profile(valid, changed)

    def test_italian_columns_are_market_scoped_and_charging_test_is_not_a_peak(self):
        cover = Mock()
        cover.extract_text.return_value = 'LISTINO - A.M. 2026 VALIDIT\u00c0: 04.11.2026 TAVASCAN'
        table = Mock()
        table.extract_text.return_value = '\n'.join([
            'Potenza massima (kW/CV) 140 / 190 210 / 286 250 / 340',
            'Capacit\u00e0 della batteria netta (kWh) 58 77 77', 'Capacit\u00e0 della batteria lorda (kWh) 61 82 82',
            'Tempi di ricarica in AC 11 kW 0-100% SoC (h) 6h 0 min 8h 0 min 8h 0 min',
            'Tempi di ricarica in DC 10-80% SoC (h) 26 min (105 kW) 29 min (135 kW) 29 min (135 kW)',
            'Massa rimorchiabile con freni 12% (kg) 1.000 1.000 1800',
            'Autonomia WLTP (km) 403 - 441 468 - 557 451 - 533',
            'Consumo di energia ciclo combinato WLTP Min-Max (kWh/100 km) 15,4 - 17,2 15,6 - 18,8 16,5 - 19,6',
            'Cerchi 19\u201d 20\u201d / 21\u201d 20\u201d / 21\u201d',
        ])
        with patch('cupra_tavascan_review.PdfReader', return_value=Mock(pages=[cover] + [None]*11 + [table, None])):
            proof = italian_reference(b'%PDF-italy')
            self.assertEqual(proof['market'], 'IT')
            self.assertEqual(proof['vz_braked_tow_reference_kg'], 1800)
            self.assertEqual(proof['vz_test_condition_dc_kw'], 135)
            self.assertNotIn('tow_kg', proof)
            self.assertNotIn('dc_charge_kw', proof)
            table.extract_text.return_value = table.extract_text.return_value.replace('61 82 82', '61 82 79')
            with self.assertRaisesRegex(ValueError, 'italian_technical_columns_changed'):
                italian_reference(b'%PDF-italy')

    def test_finnish_same_factory_code_has_different_wltp_for_distinct_equipment(self):
        table = Mock()
        table_text = ('Mallikoodi\nmv. 2025 B\nEU-yhd.\nkWh/100 km\nNETTO/BRUTTO\nmatka km**\n(WL TP)\n'
                      'TUR PW1 PF0 P80 YOS\nKR1B7D TUR KR1BCD TUR 210/286 1) 0 16.0 77/82 550 46 300 0 46 300 635 575\n'
                      'TIM PW2 P28 WED YOS\nKR1BCD TIM 210/286 1) 0 16.3 77/82 541 48 900 0 48 900 675 615\n'
                      'Hinnasto 2.3.2026\nK Auto Oy www.cupraofficial.fi')
        table.extract_text.return_value = table_text
        wheels = Mock()
        wheels.extract_text.return_value = ('19" kevytmetallivanteet Vulcano Machined (8J x 19), '
                                            '235/55 R19 renkaat edess\xe4, 255/50 R19 renkaat takana')
        with patch('cupra_tavascan_review.PdfReader', return_value=Mock(pages=[None, table, None, None, wheels, None, None, None])):
            proof = finnish_wltp_reference(b'%PDF-finland')
            self.assertEqual((proof['market'], proof['model_year_label'], proof['model_code']), ('FI', '2025 B', 'KR1BCD'))
            self.assertFalse(proof['publication_approved'])
            self.assertEqual([r['ev_range_km'] for r in proof['equipment_references'].values()], [550, 541])
            self.assertEqual([r['combined_kwh_100km'] for r in proof['equipment_references'].values()], [16, 16.3])
            self.assertNotIn('wltp_range_km', proof)
            self.assertNotIn('46 300', proof['equipment_references']['TUR']['quote'])
            for old, new in [('mv. 2025 B', 'mv. 2026'), ('WED', 'P80'), ('TUR 210/286', 'TUR 250/340'),
                             ('77/82 550', '77/82 9999'), ('Hinnasto 2.3.2026', 'Hinnasto 3.3.2026'),
                             ('48 900 0 48 900', 'KR1BCD TIM 48 900 0 48 900')]:
                with self.subTest(old=old), self.assertRaises(ValueError):
                    table.extract_text.return_value = table_text.replace(old, new)
                    finnish_wltp_reference(b'%PDF-finland')
            table.extract_text.return_value = table_text + '\nKR1BCD TIM'
            with self.assertRaisesRegex(ValueError, 'finnish_duplicate_equipment_code'):
                finnish_wltp_reference(b'%PDF-finland')
            table.extract_text.return_value = table_text
            wheels.extract_text.return_value = '20" Heckla'
            with self.assertRaisesRegex(ValueError, 'finnish_wheel_reference_changed'):
                finnish_wltp_reference(b'%PDF-finland')
        with self.assertRaisesRegex(ValueError, 'nordic_review_requires_exact_swedish_identity'):
            review({'finnish-tech.pdf': b'%PDF-finland'})


if __name__ == '__main__':
    unittest.main()
