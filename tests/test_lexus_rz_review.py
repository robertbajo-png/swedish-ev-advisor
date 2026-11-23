import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from lexus_rz_review import (AC_EQUIPMENT, BODY_ID, CONFIG_API, CONFIG_ORIGIN, CONTENT, EDITIONS, FIELDS, GRID, MODEL, MODEL_ID,
                             PHOTO_LICENSE, PHOTO_PATH, PHOTO_TITLE, PRICE, SPECS, configuration_request, digest,
                             field_rows, photo_url, price_columns, request_bytes, review, technical_request)
from lexus_rz_nordic_crosscheck import (BRAKED_LABEL, CHARGING_SHEET, DC_LABEL, FACTORY_SHEET, NAMES, UNBRAKED_LABEL,
                                      charging_sheet_row, corroboration, factory_sheet_rows, factory_year_report,
                                      register, response_rows, shared_charging_report)

NOW = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)
PRICES = 'UTRUSTNINGSNIV\u00c5  RZ 350e  RZ 500e  RZ 550e\nSEK inkl. moms\nExecutive  599 000  662 000  -\nF SPORT  -  -  843 000\nTILLVAL'
PDF = b'%PDF-fixture'
NO_CHARGING_PAGE = '''NYE LEXUS R Z
  RZ 350e   RZ 500e   RZ 550e
  EXECUTIVE   LUXURY   EXECUTIVE   LUXURY   F SPORT
  EFFEKT     165 kW / 224 hk    280 kW / 380 hk    300 kW / 408 hk
  LADEHASTIGHET    150 kW    155 kW    150 kW    160 kW    150 kW
  TILHENGERVEKT    750 kg    750 kg    1500 kg   1500 kg   -
'''


def vehicle_data():
    cars, grades = [], []
    for edition, (price, distance, consumption) in zip(EDITIONS, [(599000, 567, '14,5'), (662000, 494, '16,8'),
                                                                 (843000, 460, '18')], strict=True):
        motor, grade_label, grade, engine_code, drive, type_code, suffix, car_id = edition
        label = f'RZ {motor} {drive} {grade_label.upper()}'
        facts = [distance, consumption, 77, 5, 586]
        specs = [{'id': category, 'items': [{'code': code, 'value': str(value), 'unit': unit, 'certification': cycle}]}
                 for value, (category, code, unit, cycle, _, _) in zip(facts, FIELDS.values(), strict=True)]
        specs.append({'id': 'trans', 'items': [{'code': 'Drive', 'value': drive}]})
        config = {'Country': 'se', 'Brand': 'lexus', 'Language': 'sv', 'ModelID': MODEL_ID, 'CarID': car_id,
                  'TotalPrice': price, 'PSLS': {'Suffix': {'Code': suffix, 'Katashiki': type_code,
                  'AvailableFromDate': '2026-11-01T00:00:00', 'AvailableToDate': '2999-12-31T00:00:00'}}}
        engine = {'etwCode': engine_code, 'wheeldrive': drive, 'seoIndex': True, 'fuel': 'electric', 'specs': specs,
                  'minPrice': {'listWithDiscount': price, 'netWithDiscount': price * 4 // 5,
                               'taxWithDiscount': price // 5, 'config': config}}
        cars.append({'id': car_id, 'name': label})
        grades.append({'code': grade, 'name': grade_label, 'bodyTypes': [{'code': 'ac4', 'name': 'SUV 5-d', 'engines': [engine]}]})
    return {'code': 'rz', 'name': 'RZ', 'certification': 'WLTP', '_date': NOW.isoformat(), 'grades': grades,
            'wheeldrives': [{'code': v, 'name': v} for v in ('FWD', 'AWD')], 'fuelTypes': [{'id': 'electric', 'name': 'El'}]}, cars


def model_html(grades, cars, *, market='se', price_url=PRICE):
    context = {'brand': 'lexus', 'country': market, 'locale': 'sv', 'page': CONTENT, 'runmode': 'publish', 'preview': False}
    powertrain = {'preload': {GRID + 'powertraincomparison': {'data': {'gradesData': grades}}}}
    visual = {'preload': {GRID + 'cargrid': {'data': {'visuals': {'models': [
        {'id': MODEL_ID, 'name': 'RZ', 'code': 'RZ', 'cars': cars}]}}}}}
    return (f'<html lang="sv"><link rel="canonical" href="{MODEL}"><h1>RZ</h1><a href="{price_url}">Prislista</a>'
            f'<script type="application/json" id="server-data-manifest">{json.dumps({"appContext": context})}</script>'
            f'<script type="application/json" id="payload-grade">{json.dumps(powertrain)}</script>'
            f'<script type="application/json" id="payload-grid">{json.dumps(visual)}</script></html>').encode()


def detail_html(*, wheel='18" standard', car_id=EDITIONS[0][-1], range_km=567, config_origin=CONFIG_ORIGIN, charger=None):
    tech = [{'internalCode': category.upper(), 'data': [{'internalCode': code, 'value': str(value),
             'unit': unit, 'certification': 2 if cycle else -1}]}
            for value, (category, code, unit, cycle, _, _) in zip((range_km, '14,5', 77, 5, 586), FIELDS.values(), strict=True)]
    state = {'commonSettings': {'brand': 'lexus', 'country': 'se', 'language': 'sv', 'component': 'car-config',
                                'resourcePath': config_origin, 'apiEndpoint': config_origin + '/v1/api'},
             'specs': {'techSpecs': tech, 'standardEquipment': [{'code': 'fd19fbd3', 'name': 'Dragvikt, max 750kg', 'standard': True}]},
             'car': {'id': car_id, 'name': 'RZ 350e FWD EXECUTIVE', 'certification': 2, 'model': {'id': MODEL_ID},
                     'grade': {'name': 'Executive'}, 'soldOut': False, 'price': {'cash': 599000, 'promotions': []},
                     'wheel': {'standard': True, 'price': {'cash': 0}, 'name': wheel}}}
    if charger is not None:
        state['specs']['standardEquipment'].append(charger)
    return (f'<html lang="sv"><link rel="canonical" href="{SPECS}"><div data-cpdqm="ignore" id="spec-data">'
            f'{escape(json.dumps(state))}</div></html>').encode()


def selected_configurations():
    packet = configuration_request(detail_html())
    responses = []
    for selection, (motor, grade, _, _, drive, _, _, car_id), price, inches in zip(
            packet['fetches'], EDITIONS, (599000, 662000, 843000), (18, 18, 20), strict=True):
        car = {'id': car_id, 'name': f'RZ {motor} {drive} {grade.upper()}', 'certification': 2,
               'model': {'id': MODEL_ID, 'configVersion': 'fixture', 'internalCode': 'rz'}, 'body': {'id': BODY_ID},
               'grade': {'name': grade}, 'soldOut': False, 'price': {'cash': price, 'promotions': []},
               'shortId': int(str(price)[:3]), 'colour': {'internalCode': '1L1', 'price': {'cash': 0}},
               'upholstery': {'internalCode': 'EA10', 'price': {'cash': 0}},
               'motorization': {'engine': {'category': {'code': 'BEV'}}},
               'wheel': {'standard': True, 'price': {'cash': 0}, 'name': f'{inches}" original'}}
        responses.append({**selection, 'result': {'errorLogs': [], 'fetchResult': {'car': car}}})
    return {'fetches': responses}


def selected_technical(spec_request):
    grades, _ = vehicle_data()
    responses = []
    for request, grade, towing in zip(spec_request['fetches'], grades['grades'],
                                      ('Dragvikt, max 750kg', 'Dragvikt, 1500 kg', None), strict=True):
        raw_specs = grade['bodyTypes'][0]['engines'][0]['specs'][:-1]
        technical = [{'internalCode': row['id'].upper(), 'data': [
            {**item, 'internalCode': item['code'], 'certification': 2 if item['certification'] == 'WLTP' else -1}
            for item in row['items']]} for row in raw_specs]
        equipment = [{'code': 'a4918819', 'name': AC_EQUIPMENT, 'standard': True}]
        if towing:
            equipment.append({'code': 'tow', 'name': towing, 'standard': True})
        responses.append({**request, 'result': {'reqLogs': [], 'fetchResult': {
            'techSpecs': technical, 'standardEquipment': equipment,
            'massValidationSpecs': {'error': None, 'exceedingKilogram': 0, 'successful': True}}}})
    return {'fetches': responses}


class LexusRZReviewTest(unittest.TestCase):
    def inspect(self, *args, details=None, configurations=None, technical=None, **kwargs):
        model = model_html(*args, **kwargs)
        with patch('lexus_rz_review.price_pdf', return_value=price_columns(PRICES)):
            return review(model, PDF, detail_html() if details is None else details, NOW, configurations, technical)

    def technical_fixture(self):
        configuration = request_bytes(selected_configurations())
        baseline = self.inspect(*vehicle_data(), configurations=configuration)
        packet = technical_request(configuration, detail_html(), baseline['variants'])
        return configuration, packet, selected_technical(packet)

    def test_technical_snapshot_binds_three_base_variants_and_only_fills_ac(self):
        configuration, packet, technical = self.technical_fixture()
        self.assertEqual([f['body']['car'] for f in packet['fetches']], [x[-1] for x in EDITIONS])
        for row in packet['fetches']:
            self.assertEqual(row['fetchType'], 'fetchCarConfigSpecs')
            for key in ('packs', 'serviceProducts', 'options', 'accessories'):
                self.assertEqual(row['body'][key], [])
        raw = request_bytes(technical)
        report = self.inspect(*vehicle_data(), configurations=configuration, technical=raw)
        self.assertFalse(report['publication_approved'])
        for row, tow in zip(report['variants'], (['Dragvikt, max 750kg'], ['Dragvikt, 1500 kg'], []), strict=True):
            fact = row['facts']['ac_charge_kw']
            self.assertEqual((fact['car_id'], fact['value'], fact['source_hash'], fact['request_hash']),
                             (row['car_id'], 22, digest(raw), digest(request_bytes(packet))))
            self.assertEqual(row['technical_configuration']['tow_limit_references'], tow)
            self.assertEqual(row['held'], ['model_year', 'dc_charge_kw', 'tow_kg'])
            self.assertNotIn('tow_kg', row['facts'])

    def test_technical_snapshot_rejects_another_car_missing_config_and_reordered_response(self):
        configuration, _, technical = self.technical_fixture()
        with self.assertRaisesRegex(ValueError, 'technical_specs_require_exact_configurations'):
            self.inspect(*vehicle_data(), technical=request_bytes(technical))
        technical['fetches'].reverse()
        with self.assertRaisesRegex(ValueError, 'technical_response_identity_mismatch'):
            self.inspect(*vehicle_data(), configurations=configuration, technical=request_bytes(technical))

    def test_technical_snapshot_rejects_invalid_mass_optional_charger_or_mismatched_wltp(self):
        configuration, _, technical = self.technical_fixture()
        for change, error in (
            (lambda d: d['massValidationSpecs'].update(successful=False), 'technical_configuration_validation_failed'),
            (lambda d: d['standardEquipment'][0].update(standard=False), 'technical_standard_ac_charger_changed'),
            (lambda d: d['techSpecs'][0]['data'][0].update(value='567'), 'technical_variant_conflict'),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                changed = copy.deepcopy(technical)
                change(changed['fetches'][1]['result']['fetchResult'])
                self.inspect(*vehicle_data(), configurations=configuration, technical=request_bytes(changed))

    def test_technical_request_requires_no_surcharge_factory_options(self):
        baseline = self.inspect(*vehicle_data())
        for key in ('colour', 'upholstery'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'technical_request_base_configuration_required'):
                selected = selected_configurations()
                selected['fetches'][0]['result']['fetchResult']['car'][key]['price']['cash'] = 5900
                technical_request(request_bytes(selected), detail_html(), baseline['variants'])

    def test_nordic_scope_binds_country_engine_and_exact_factory_suffix(self):
        selected, _, technical = self.technical_fixture()
        swedish = self.inspect(*vehicle_data(), configurations=selected, technical=request_bytes(technical))['variants']
        grades, _ = vehicle_data()
        grades['wheeldrives'] = [{'code': 'FWD', 'name': '4X2'}, {'code': 'AWD', 'name': '4X4'}]
        ids = [f'cafed00{i}-ecb0-4f9a-9206-88d853906100' for i in range(3)]
        for row, cid in zip(grades['grades'], ids, strict=True):
            engine = row['bodyTypes'][0]['engines'][0]
            engine['minPrice']['config'].update(Country='dk', Language='da', CarID=cid)
        raw = b'<html lang="da"><link rel="canonical" href="https://www.lexus.dk/nye-biler/rz"></html>'
        with patch('lexus_rz_nordic_crosscheck.published_components',
                   return_value={'powertraincomparison': {'gradesData': grades}}):
            self.assertEqual([row[-1] for row in register(raw, swedish, NOW)], ids)
            changed = grades['grades'][2]['bodyTypes'][0]['engines'][0]['minPrice']['config']['PSLS']['Suffix']
            changed['Code'] = 'OTHER'
            with self.assertRaisesRegex(ValueError, 'dk_factory_identity_differs'):
                register(raw, swedish, NOW)

    def test_nordic_both_brake_ratings_and_dc_are_scoped_corroboration(self):
        selected, _, technical = self.technical_fixture()
        swedish = self.inspect(*vehicle_data(), configurations=selected, technical=request_bytes(technical))['variants']
        for variant, braked, unbraked in zip(swedish, (750, 1500, 0), (750, 750, 0), strict=True):
            specs = [('BATCAP', '77 ', 'kWh', 'Bat', -1),
                     ('PERCOMBINED', str(variant['facts']['wltp_range_km']['value']), 'km', 'WLTP', 2),
                     ('ECCOMBINEDWHKM', str(round(variant['facts']['wltp_consumption_kwh_100km']['value'] * 10)), 'Wh/km', 'WLTP', 2),
                     ('TOWCAPBRK', str(braked), 'kg', BRAKED_LABEL, -1), ('TOWCAPNOBRK', str(unbraked), 'kg', UNBRAKED_LABEL, -1)]
            result = {'massValidationSpecs': {'error': None, 'exceedingKilogram': 0, 'successful': True},
                      'techSpecs': [{'data': [{'internalCode': code, 'value': value, 'unit': unit,
                                              'name': name, 'certification': cycle} for code, value, unit, name, cycle in specs]}],
                      'standardEquipment': [{'code': '6624963a', 'name': DC_LABEL, 'standard': True}]}
            found = corroboration(result, variant)
            self.assertEqual((found['dc_kw'], found['braked_kg'], found['unbraked_kg']), (150, braked, unbraked))
            self.assertEqual(found['se_maximum_present'], braked != 0)
            self.assertNotIn('tow_kg', variant['facts'])
            self.assertNotIn('dc_charge_kw', variant['facts'])
            for code, field, value, error in (
                ('PERCOMBINED', 'value', '1', 'dk_technical_identity_mismatch'),
                ('TOWCAPBRK', 'name', UNBRAKED_LABEL, 'dk_exact_label_and_unit_required'),
                ('TOWCAPNOBRK', 'value', '1500', 'dk_invalid_towing_capacity'),
            ):
                with self.subTest(code=code, variant=variant['variant']), self.assertRaisesRegex(ValueError, error):
                    changed = copy.deepcopy(result)
                    next(x for x in changed['techSpecs'][0]['data'] if x['internalCode'] == code)[field] = value
                    corroboration(changed, variant)

    def test_nordic_response_cannot_swap_configurations(self):
        _, packet, technical = self.technical_fixture()
        technical['fetches'].reverse()
        with self.assertRaisesRegex(ValueError, 'dk_response_does_not_match_request'):
            list(response_rows(request_bytes(technical), packet))

    def test_model_year_reference_never_borrows_from_different_trim_or_infers_suffix(self):
        page = '\n'.join((
            'LISTINO PREZZI                        RZ MC26', 'Del:             02/01/2026', 'In vigore da:    02/01/2026',
            'Codice Modello     Trazione     Katashiki     Versione     Prezzo di listino al pubblico',
            'RZ 350e 2WD MY26 EXE    FWD    XEBM20L-AWDCSW    RZ EXECUTIVE 2WD    1    2    3',
            'RZ 500e 4WD MY26 LUX    AWD    XEBM25L-AWDLSW    RZ LUXURY 4WD    1    2    3',
            'RZ 550e 4WD MY26 F-SPORT    AWD    XEBM25L-AWDSSW    RZ F-SPORT 4WD    1    2    3',
            'Optional', 'RZ 350e 2WD MY26 EXE    option-row',
        ))
        for changed in (page.replace('02/01/2026', '02/01/2025'), page.replace('MY26 F-SPORT', 'MY27 F-SPORT'),
                        page.replace('XEBM25L-AWDLSW', 'XEBM25L-AWDCSW'), page.replace('EXECUTIVE 2WD', 'LUXURY 2WD'),
                        page.replace('Optional', 'unknown table')):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'rz_it_'):
                factory_sheet_rows(changed)
        selected, _, technical = self.technical_fixture()
        swedish = self.inspect(*vehicle_data(), configurations=selected, technical=request_bytes(technical))
        nordic = {'captured_at': NOW.isoformat(), 'swedish_review_sha256': 'se',
                  'variants': [{**{k: v[k] for k in ('variant', 'type_code', 'suffix')}, 'se_car_id': v['car_id']}
                               for v in swedish['variants']]}
        with patch('lexus_rz_nordic_crosscheck.PdfReader') as reader:
            reader.return_value.pages = [None, reader.return_value] + [None] * 5
            reader.return_value.extract_text.return_value = page
            report = factory_year_report(PDF, swedish, nordic, 'dk', NOW)
            self.assertEqual([v['factory_year_reference'] for v in report['variants']], [2026, None, 2026])
            self.assertEqual([v['suffix'] for v in report['variants']], ['AB', 'PB', '0C'])
            self.assertEqual(report['source']['url'], FACTORY_SHEET)
            self.assertFalse(report['publication_approved'])
            self.assertNotIn('tow_kg', report['variants'][0])
            with self.assertRaisesRegex(ValueError, 'fresh_swedish_capture'):
                factory_year_report(PDF, swedish, nordic, 'dk', NOW + timedelta(days=2))
            nordic['variants'][2]['suffix'] = '0D'
            with self.assertRaisesRegex(ValueError, 'identity_conflict'):
                factory_year_report(PDF, swedish, nordic, 'dk', NOW)

    def test_norwegian_charging_requires_exact_motor_grade_and_kw_columns(self):
        self.assertEqual(charging_sheet_row(NO_CHARGING_PAGE)[0], (150, 150, 150))
        for changed in (NO_CHARGING_PAGE.replace('350e', '300e'),
                        NO_CHARGING_PAGE.replace('EXECUTIVE   LUXURY', 'LUXURY   EXECUTIVE', 1),
                        NO_CHARGING_PAGE.replace('280 kW', '230 kW'),
                        NO_CHARGING_PAGE.replace('150 kW', '150 kWh', 1),
                        NO_CHARGING_PAGE + 'LADEHASTIGHET 150 kW\n'):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                charging_sheet_row(changed)

    def test_shared_dc_report_requires_current_exact_agreement_and_keeps_towing_held(self):
        selected, _, technical = self.technical_fixture()
        swedish = self.inspect(*vehicle_data(), configurations=selected, technical=request_bytes(technical))
        dk_rows = [{**{k: v[k] for k in ('variant', 'type_code', 'suffix')}, 'se_car_id': v['car_id'],
                    'dc_kw': 150, 'dc_quote': DC_LABEL, 'braked_kg': 0} for v in swedish['variants']]
        nordic = {'captured_at': NOW.isoformat(), 'variants': dk_rows, 'swedish_review_sha256': 'se',
                  'sources': {NAMES[2]: {'url': 'dk', 'sha256': 'tech', 'request_sha256': 'request'}}}
        before = copy.deepcopy(swedish)
        with patch('lexus_rz_nordic_crosscheck.PdfReader') as reader:
            reader.return_value.pages = [None] * 5 + [reader.return_value]
            reader.return_value.extract_text.return_value = NO_CHARGING_PAGE
            result = shared_charging_report(PDF, swedish, nordic, 'nordic', NOW)
            self.assertEqual((result['corroboration']['url'], result['corroboration']['sha256'],
                              result['nordic_review_sha256']), (CHARGING_SHEET, digest(PDF), 'nordic'))
            self.assertFalse(result['publication_approved'])
            self.assertEqual(result['database_writes'], 0)
            self.assertEqual(swedish, before)
            for row in result['variants']:
                self.assertEqual(row['dc_charge_kw'], 150)
                self.assertEqual(row['still_held'], ['model_year', 'tow_kg'])
                self.assertNotIn('tow_kg', row)
            with self.assertRaisesRegex(ValueError, 'recent_se_and_dk'):
                shared_charging_report(PDF, swedish, nordic, 'nordic', NOW + timedelta(days=2))
            for key, value in (('suffix', 'other'), ('dc_kw', 160)):
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'hardware_or_identity_conflict'):
                    mismatch = copy.deepcopy(nordic)
                    mismatch['variants'][1][key] = value
                    shared_charging_report(PDF, swedish, mismatch, 'nordic', NOW)

    def test_exact_selected_configurations_confirm_only_standard_wheels_and_cash_price(self):
        raw = json.dumps(selected_configurations()).encode()
        report = self.inspect(*vehicle_data(), configurations=raw)
        self.assertEqual(report['sources']['selected-configurations.json']['source_hash'], digest(raw))
        for variant, wheel, price in zip(report['variants'], (18, 18, 20), (599000, 662000, 843000), strict=True):
            standard = variant['standard_configuration']
            self.assertEqual((standard['source_url'], standard['car_id'], standard['standard_wheels_inches'], standard['cash_sek']),
                             (CONFIG_API, variant['car_id'], wheel, price))
            self.assertEqual(standard['request_hash'], digest(request_bytes(configuration_request(detail_html()))))
            self.assertEqual(variant['held'], ['model_year', 'ac_charge_kw', 'dc_charge_kw', 'tow_kg'])
        self.assertFalse(report['publication_approved'])

    def test_configurator_rejects_untrusted_endpoint_or_reordered_response(self):
        payload = selected_configurations()
        with self.assertRaisesRegex(ValueError, 'exact_public_configurator_endpoint'):
            self.inspect(*vehicle_data(), details=detail_html(config_origin='https://www.lexus.no'),
                         configurations=json.dumps(payload).encode())
        payload['fetches'].reverse()
        with self.assertRaisesRegex(ValueError, 'response_identity_mismatch'):
            self.inspect(*vehicle_data(), configurations=json.dumps(payload).encode())

    def test_configurator_rejects_wrong_car_compared_price_promotions_and_optional_wheel(self):
        for path, value, error in ((('id',), EDITIONS[0][-1], 'swedish_price_and_engine'),
                                   (('body', 'id'), 'other', 'swedish_price_and_engine'),
                                   (('price', 'cash'), 599000, 'swedish_price_and_engine'),
                                   (('price', 'promotions'), ['offer'], 'swedish_price_and_engine'),
                                   (('wheel', 'standard'), False, 'standard_wheel_scope'),
                                   (('wheel', 'price', 'cash'), 1000, 'standard_wheel_scope'),
                                   (('wheel', 'name'), '20" accessory', 'standard_wheel_scope')):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, error):
                payload = selected_configurations()
                node = payload['fetches'][1]['result']['fetchResult']['car']
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = value
                self.inspect(*vehicle_data(), configurations=json.dumps(payload).encode())

    def test_exact_standard_ac_charger_only_fills_the_350e(self):
        charger = {'code': 'a4918819', 'name': '22kW (3-fas) AC-snabbladdare med Typ 2/Mennekes-kontakt', 'standard': True}
        raw = detail_html(charger=charger)
        report = self.inspect(*vehicle_data(), details=raw, configurations=json.dumps(selected_configurations()).encode())
        first, *rest = report['variants']
        fact = first['facts']['ac_charge_kw']
        self.assertEqual((fact['value'], fact['car_id'], fact['source_url'], fact['source_hash']),
                         (22, first['car_id'], SPECS, digest(raw)))
        self.assertNotIn('ac_charge_kw', first['held'])
        for variant in rest:
            self.assertIn('ac_charge_kw', variant['held'])
            self.assertNotIn('ac_charge_kw', variant['facts'])
        for wrong in ({**charger, 'name': '22 kW wallbox'}, {**charger, 'standard': False}):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, 'standard_ac_charger_changed'):
                self.inspect(*vehicle_data(), details=detail_html(charger=wrong))

    def test_exact_engine_prices_are_not_grade_minima_or_finance(self):
        grades, cars = vehicle_data()
        grades['grades'][1]['minPrice'] = {'listWithDiscount': 599000}
        report = self.inspect(grades, cars)
        self.assertFalse(report['publication_approved'])
        self.assertEqual(report['database_writes'], 0)
        self.assertEqual([(p['variant'], p['facts']['price_sek']['value'], p['facts']['wltp_range_km']['value'])
                          for p in report['variants']], [('350e Executive', 599000, 567),
                                                         ('500e Executive', 662000, 494), ('550e F SPORT', 843000, 460)])
        self.assertEqual([r['facts']['wltp_consumption_kwh_100km']['value'] for r in report['variants']], [14.5, 16.8, 18])
        self.assertIn('750kg', report['single_configuration']['tow_limit_reference'])
        self.assertEqual(len(report['single_configuration']['confirmed_technical_rows']), 5)
        self.assertNotIn('complete_wheel_scope', report['variants'][0]['held'])
        self.assertIn('complete_wheel_scope', report['variants'][1]['held'])
        for variant in report['variants']:
            self.assertEqual(variant['facts']['boot_liters']['value'], 586)
            self.assertEqual(variant['facts']['price_sek']['source_url'], PRICE)
            self.assertEqual(variant['facts']['price_sek']['corroboration']['car_id'], variant['car_id'])
            self.assertNotIn('tow_kg', variant['facts'])

    def test_rejects_mismatched_trim_inactive_car_stale_payload_and_price_conflicts(self):
        for key, value, error in (('CarID', EDITIONS[0][-1], 'exact_current_engine'),
                                  ('TotalPrice', 599000, 'cash_price_disagrees'), ('Country', 'no', 'exact_current_engine')):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, error):
                grades, cars = vehicle_data()
                grades['grades'][1]['bodyTypes'][0]['engines'][0]['minPrice']['config'][key] = value
                self.inspect(grades, cars)
        grades, cars = vehicle_data()
        grades['_date'] = '2026-09-01T15:00:00+00:00'
        with self.assertRaisesRegex(ValueError, 'current_manufacturer'):
            self.inspect(grades, cars)
        grades, cars = vehicle_data()
        with self.assertRaisesRegex(ValueError, 'market_or_publication_context'):
            self.inspect(grades, cars, market='dk')
        with self.assertRaisesRegex(ValueError, 'current_product_and_price_link'):
            self.inspect(grades, cars, price_url=PRICE.replace('260318', '251023'))
        with self.assertRaisesRegex(ValueError, 'standard_350e_wheels_changed'):
            self.inspect(grades, cars, details=detail_html(wheel='20" optional'))
        with self.assertRaisesRegex(ValueError, 'detail_does_not_match'):
            self.inspect(grades, cars, details=detail_html(car_id=EDITIONS[1][-1]))
        with self.assertRaisesRegex(ValueError, 'standard_configuration_technical_conflict'):
            self.inspect(grades, cars, details=detail_html(range_km=559))

    def test_requires_exact_pdf_columns_vat_and_non_empty_cash_cells(self):
        self.assertEqual(price_columns(PRICES)['500e'][0], 662000)
        for text in (PRICES.replace('RZ 350e  RZ 500e', 'RZ 500e  RZ 350e'),
                     PRICES.replace('inkl. moms', 'exkl. moms'), PRICES.replace('662 000', '-')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                price_columns(text)

    def test_rejects_generic_or_wrong_cycle_and_capacity_units(self):
        grades, _ = vehicle_data()
        engine = grades['grades'][0]['bodyTypes'][0]['engines'][0]
        for column, key, value in ((0, 'code', 'PERCOMBINEDMAX'), (0, 'certification', 'EPA'),
                                    (2, 'unit', 'Wh'), (4, 'value', '0')):
            modified = copy.deepcopy(engine)
            modified['specs'][column]['items'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                field_rows(modified)

    def test_photo_admits_only_reviewed_facelift_title_author_asset_and_license(self):
        meta = (f'<h1>{PHOTO_TITLE}</h1><table><tr><td id="fileinfotpl_aut">Author</td><td>Alexander Migl</td></tr></table>'
                f'<a href="{PHOTO_LICENSE}">Attribution-Share Alike 4.0 International</a>'
                f'<a href="{PHOTO_PATH}?utm_source=fixture">Original file</a>').encode()
        self.assertEqual(photo_url(meta), PHOTO_PATH)
        for before, after in ((b'550e', b'450e'), (b'Alexander Migl', b'Other Publisher'),
                              (b'by-sa/4.0', b'by-nc-sa/4.0'), (b'_IMG_5164.jpg?', b'_IMG_5155.jpg?')):
            with self.subTest(before=before), self.assertRaises(ValueError):
                photo_url(meta.replace(before, after))


if __name__ == '__main__':
    unittest.main()
