import copy
import hashlib
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from audit_catalog_sources import allowed_url
from build_source_queue import official_source_for
from volkswagen_id_buzz_preflight import (MODEL_URL, TECHNICAL_URL, capture, read_charging_sheet, read_short_technical,
                                        read_short_versions, read_swedish_dc_claim, source_allowed)
from volkswagen_id_buzz_review import DEALER, TRIMS, build_review, read_dealer_offer, read_finnish_hardware


def card(name, price, motor, drive, range_km, tow, cargo=''):
    return (f'ID. Buzz {name} 5-sits \u2013 Sweden Olympic Edition '
            f'fr\u00e5n {price} kr inkl. moms Drivlina: {drive} L\u00e4ngd: 471 cm '
            f'Sittplatser: 5 (standard) eller 6 Batterikapacitet: 79 kWh (netto) '
            f'Maximal r\u00e4ckvidd: {range_km} km (WLTP, blandad k\u00f6rning) '
            f'Motor: {motor} kW / 999 hk Dragvikt: {tow} kg {cargo} '
            '7-sits \u2013 Sweden Olympic Edition fr\u00e5n 651 700 kr inkl. moms '
            'Maximal r\u00e4ckvidd: 499 km (WLTP, blandad k\u00f6rning) '
            'Bagageutrymme (5 sittplatser): 1 340 liter ')


TEXT = ('S\u00e4ljstarten av ID. Buzz modell\u00e5r 2027 ... Versioner '
        + card('Pro', '599 100', 210, 'Bakhjulsdrift', 448, '1 200')
        + card('Pro 4MOTION', '639 200', 250, '4MOTION fyrhjulsdrift', 413, '1 800',
               'Bagageutrymme (5 sittplatser): 1 133 liter')
        + 'ID. Buzz GTX 5-sits \u2013 Sweden Olympic Edition annat utf\u00f6rande. '
        + 'Bagageutrymmet i ID. Buzz har en volym p\u00e5 hela 1.123 liter (bakom andra s\u00e4tesraden). '
        + 'P\u00e5 snabbladdningsstationer (DC) kan ID. Buzz laddas med upp till 200 kW effekt '
          'med 86 kWh-batteriet och 185 kW effekt med 79 kWh-batteriet.')


TECHNICAL_TEXT = ('<b>Vikter</b> ID. Buzz Pro ID. Buzz Pro 4MOTION ID. Buzz GTX '
                  'Totalvikt Kort: 3.000 kg Tj\u00e4nstevikt Kort: 2 592 kg Maximal sl\u00e4pvagnslast '
                  'Kort: 1.200 kg (bromsad, vid 12 % stigning) L\u00e5ng: 1.000 kg (bromsad, vid 12 % stigning) 750 kg (obromsad) '
                  'Kort: 1.800 kg (bromsad, vid 12% stigning) L\u00e5ng: 1.600 kg (bromsad, vid 12% stigning) 750 kg (obromsad) '
                  'Kort: 1.900 kg (bromsad, vid 12% stigning) L\u00e5ng: 1.900 kg (bromsad, vid 12% stigning) 750 kg (obromsad) '
                  'Exteri\u00f6r och interi\u00f6r data. Axelavst\u00e5nd: 2 989 mm Bagageutrymme 1:a s\u00e4tesraden: 2 232 mm '
                  '2:a s\u00e4tesraden: 1 330 mm Bagageutrymme, bredd: 1 204 mm Bagageutrymme, volym: '
                  '1 123 liter (max) M\u00e5tt p\u00e5 korta versionen av ID. Buzz')


class FixtureFetcher:
    def __init__(self, **overrides):
        self.overrides = overrides

    def fetch(self, url, brands):
        assert source_allowed(url, brands)
        text = TEXT if url == MODEL_URL else TECHNICAL_TEXT
        return {'status': 'reachable', 'http_status': 200, 'content_type': 'text/html', 'final_url': url,
                'content_hash': 'a' * 64, 'text_hash': hashlib.sha256(text.encode()).hexdigest(),
                'text': text, **self.overrides}


class VolkswagenIdBuzzPreflightTest(unittest.TestCase):
    def test_exact_model_url_only(self):
        self.assertEqual(official_source_for('VW', 'ID. BUZZ')[0], MODEL_URL)
        for policy in (source_allowed, allowed_url):
            self.assertTrue(policy(MODEL_URL, {'Volkswagen'}))
            self.assertTrue(policy(TECHNICAL_URL, {'Volkswagen'}))
            for url in (MODEL_URL.replace('id-buzz', 'id-buzz-cargo'), MODEL_URL + '?x=1',
                        MODEL_URL.replace('volkswagen-transportbilar.se', 'volkswagen-transportbilar.se.example.com')):
                self.assertFalse(policy(url, {'Volkswagen'}))
            self.assertFalse(policy(MODEL_URL, {'Volvo'}))

    def test_isolates_short_versions_and_preserves_evidence(self):
        pro, awd = read_short_versions(TEXT)
        self.assertEqual((pro['trim'], awd['trim']), ('Pro', 'Pro 4MOTION'))
        self.assertEqual(pro['model_year'], 2027)
        self.assertEqual(pro['observations']['cash_from_sek']['value'], 599100)
        self.assertEqual(pro['observations']['combined_wltp_range_up_to_km']['value'], 448)
        self.assertEqual(awd['observations']['combined_wltp_range_up_to_km']['value'], 413)
        self.assertNotIn('cargo_five_seats_liters', pro['observations'])
        self.assertEqual(awd['observations']['cargo_five_seats_liters']['value'], 1133)
        self.assertEqual(awd['observations']['drivetrain']['value'], 'AWD')
        for variant in (pro, awd):
            for observation in variant['observations'].values():
                self.assertIn(observation['quote'], TEXT)

    def test_repeated_same_year_is_not_conflicting(self):
        self.assertEqual(len(read_short_versions('S\u00e4ljstarten av ID. Buzz modell\u00e5r 2027. ' + TEXT)), 2)
        with self.assertRaisesRegex(ValueError, 'model_year_required'):
            read_short_versions('S\u00e4ljstarten av ID. Buzz modell\u00e5r 2026. ' + TEXT)

    def test_refuses_changed_identity_duplicate_and_price_or_wltp_scope(self):
        variants = (
            TEXT.replace('2027', '2026'), TEXT + ' ' + TEXT,
            TEXT.replace('ID. Buzz Pro 5-sits', 'ID. Buzz Cargo Pro 5-sits'),
            TEXT.replace('79 kWh (netto)', '79 kWh (brutto)', 1),
            TEXT.replace('599 100 kr inkl. moms', '599 100 kr/m\u00e5n', 1),
            TEXT.replace('WLTP, blandad k\u00f6rning', 'WLTP, stadsk\u00f6rning', 1),
            TEXT.replace('L\u00e4ngd: 471 cm', 'L\u00e4ngd: 496 cm', 1),
            TEXT.replace('7-sits \u2013 Sweden Olympic Edition', 'long version', 1),
            TEXT.replace('Motor: 210 kW', 'Motor: 250 kW', 1),
        )
        for text in variants:
            with self.subTest(text=text[:135]), self.assertRaises(ValueError):
                read_short_versions(text)

    def test_captures_hashes_but_never_marks_publishable(self):
        report, texts = capture(FixtureFetcher())
        self.assertFalse(report['publication_approved'])
        self.assertEqual(report['status'], 'needs_review')
        self.assertEqual(report['variant_observation_source'], MODEL_URL)
        self.assertEqual(set(report['sources']), {MODEL_URL, TECHNICAL_URL})
        self.assertEqual(report['sources'][MODEL_URL]['text_hash'], hashlib.sha256(texts[MODEL_URL].encode()).hexdigest())
        self.assertEqual(report['technical_observation_source'], TECHNICAL_URL)
        self.assertEqual(report['swedish_dc_claim']['value'], 185)

    def test_binds_short_braked_weights_and_behind_second_row_cargo(self):
        technical = read_short_technical(TECHNICAL_TEXT, TEXT)
        towing = technical['braked_towing_12pct_kg']
        self.assertEqual({name: row['value'] for name, row in towing.items()}, {'Pro': 1200, 'Pro 4MOTION': 1800})
        self.assertEqual(technical['short_pro_cargo_row_two_liters']['value'], 1123)
        self.assertNotIn('750', towing['Pro']['quote'])
        self.assertIn('bakom andra', technical['short_pro_cargo_row_two_liters']['model_page_basis_quote'])

    def test_holds_reordered_drivetrains_wrong_gradient_wheelbase_and_cargo_basis(self):
        for text, model in (
            (TECHNICAL_TEXT.replace('Pro ID. Buzz Pro 4MOTION', 'Pro 4MOTION ID. Buzz Pro'), TEXT),
            (TECHNICAL_TEXT.replace('12 %', '8 %', 1), TEXT),
            (TECHNICAL_TEXT.replace('2 989 mm', '3 239 mm'), TEXT),
            (TECHNICAL_TEXT.replace('1 123 liter', '2 123 liter'), TEXT),
            (TECHNICAL_TEXT, TEXT.replace('bakom andra', 'bakom f\u00f6rsta')),
        ):
            with self.subTest(text=text[:78], model=model[-250:]), self.assertRaises(ValueError):
                read_short_technical(text, model)

    def test_holds_towing_conflict_between_swedish_sources(self):
        class ConflictFetcher(FixtureFetcher):
            def fetch(self, url, brands):
                data = super().fetch(url, brands)
                if url == TECHNICAL_URL:
                    data['text'] = data['text'].replace('1.200 kg', '1.800 kg')
                    data['text_hash'] = hashlib.sha256(data['text'].encode()).hexdigest()
                return data

        with self.assertRaisesRegex(ValueError, 'towing_sources_disagree: Pro'):
            capture(ConflictFetcher())

    def test_dc_claim_is_bound_to_the_small_battery_and_not_a_configured_limit(self):
        claim = read_swedish_dc_claim(TEXT)
        self.assertEqual((claim['battery_net_kwh'], claim['value'], claim['scope']),
                         (79, 185, 'swedish_battery_family_claim'))
        for replacement in ('185 kW effekt med 86 kWh-batteriet', '185 kW effekt med 79 kWh laddstation'):
            with self.assertRaisesRegex(ValueError, 'swedish_dc_battery_scope_required'):
                read_swedish_dc_claim(TEXT.replace('185 kW effekt med 79 kWh-batteriet', replacement))

    def test_refuses_unavailable_mismatched_or_unhashed_source(self):
        for kwargs in ({'status': 'http_error'}, {'status': 'machine_reservation'}, {'final_url': 'https://example.org'},
                       {'content_hash': 'unknown'}, {'text_hash': '0' * 64}, {'content_type': 'application/pdf'}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'uncaptured_source'):
                capture(FixtureFetcher(**kwargs))


CHARGING_TEXT = ('Mise \u00e0 jour au 21 octobre 2026\nAnn\u00e9e-mod\u00e8le 2027\f'
                 'Code mod\u00e8le Capacit\u00e9 Puissance Capacit\u00e9\nnette (kWh) (kW/ch) AC/DC (kW)\n'
                 'ID. Buzz Pro Court EBBR7R 79 210/286 11/183 6 20,0 443 58 250 EUR\n'
                 'ID. Buzz Pro 4Motion Court EBBR5R 79 250/340 11/183 5 21,2 411 61 300 EUR\n'
                 'ID. Buzz Pro Long EBJR7S 86 210/286 11/199 6 20,1 481 60 870 EUR')


class VolkswagenIdBuzzChargingTest(unittest.TestCase):
    def test_allows_only_shared_charging_hardware(self):
        report = read_charging_sheet(CHARGING_TEXT)
        self.assertFalse(report['publication_approved'])
        self.assertEqual(report['scope'], 'matching_model_code_hardware_only')
        self.assertEqual({r['model_code'] for r in report['variants']}, {'EBBR7R', 'EBBR5R'})
        for row in report['variants']:
            self.assertEqual((row['ac_charge_kw'], row['dc_charge_kw']), (11, 183))
            self.assertEqual(set(row), {'model_code', 'ac_charge_kw', 'dc_charge_kw', 'quote'})
            self.assertNotIn('EUR', row['quote'])
            self.assertNotIn('11/199', row['quote'])

    def test_holds_changed_column_year_short_body_motor_and_power(self):
        for changed in (CHARGING_TEXT.replace('AC/DC', 'DC/AC'), CHARGING_TEXT.replace('2027', '2026'),
                        CHARGING_TEXT.replace('21 octobre', '22 octobre'), CHARGING_TEXT.replace('EBBR5R', 'EBJR5W'),
                        CHARGING_TEXT.replace('4Motion Court', '4Motion Long'), CHARGING_TEXT.replace('79 210/286', '86 210/286'),
                        CHARGING_TEXT.replace('11/183', '11/185', 1), CHARGING_TEXT + '\n' + CHARGING_TEXT.splitlines()[4]):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                read_charging_sheet(changed)


DEALER_TEXT = ('ID. Buzz Pro Sweden Olympic Edition 5-sits pris fr\u00e5n 599 100 kr inkl. moms '
               'ID. Buzz Pro Sweden Olympic Edition 7-sits pris fr\u00e5n 638 100 kr inkl. moms '
               'ID. Buzz Pro 4MOTION Sweden Olympic Edition 5-sits pris fr\u00e5n 639 200 kr inkl. moms '
               'Erbjudandet g\u00e4ller tom 31/12 2026.')
AUTH_TEXT = ('M\u00f6ller Bil V\u00e4ster\u00e5s Ort: V\u00e4ster\u00e5s. Verksamhet: Auktoriserad '
             '\u00e5terf\u00f6rs\u00e4ljare och fullserviceverkstad f\u00f6r Volkswagen Transportbilar.')
FINNISH_TEXT = ('Pvm 18.6.2026 KOODI MALLI Istuinpaikka Lataus-teho CO2 netto/brutto kW Vapaa\n'
                'EBBR7R ID.Buzz PRO 210kW 79 kWh 5 19.5 210/286 79/84 kWh 450 184 0 54000\n'
                'PRO+\n'
                'EBBR7R ID.Buzz 210kW PRO+ 79 kWh 5 19.5 210/286 79/84 kWh 444 185 0 54100\n'
                'EBBR5R ID.Buzz 250kW PRO+ 79 kWh 4Motion 5 21 250/340 79/84 kWh 433 185 0 55100\n'
                'GTX\nMaahantuoja: K Auto Oy\fID.BUZZ PRO+\n11 kW AC-latausteho Vakiovaruste')


class VolkswagenIdBuzzPrivateReviewTest(unittest.TestCase):
    def test_only_named_authorized_unexpired_five_seat_prices(self):
        parsed = read_dealer_offer(DEALER_TEXT, AUTH_TEXT, date(2026, 11, 19))
        self.assertEqual(parsed['price_valid_until'], '2026-12-31')
        self.assertEqual([price['value'] for price in parsed['prices'].values()], [599100, 639200])
        for price, auth, asof in (
            (DEALER_TEXT, AUTH_TEXT, date(2027, 1, 1)),
            (DEALER_TEXT, AUTH_TEXT.replace('V\u00e4ster\u00e5s', 'Stockholm'), date(2026, 11, 19)),
            (DEALER_TEXT.replace('5-sits', '6-sits', 1), AUTH_TEXT, date(2026, 11, 19)),
            (DEALER_TEXT + DEALER_TEXT, AUTH_TEXT, date(2026, 11, 19)),
        ):
            with self.subTest(price=price, asof=asof), self.assertRaises(ValueError):
                read_dealer_offer(price, auth, asof)

    def test_finnish_importer_can_only_corroborate_charging(self):
        facts = read_finnish_hardware(FINNISH_TEXT)
        self.assertEqual([row['dc_charge_kw'] for row in facts.values()], [185, 185])
        self.assertEqual(set(facts['EBBR7R']), {'dc_charge_kw', 'ac_charge_kw', 'dc_quote', 'ac_quote'})
        self.assertNotIn('54100', facts['EBBR7R']['dc_quote'])
        for changed in (FINNISH_TEXT.replace('4Motion 5', '4Motion 7'), FINNISH_TEXT.replace('Lataus-teho', 'Other'),
                        FINNISH_TEXT.replace('11 kW AC', '22 kW AC'), FINNISH_TEXT.replace('PRO+\n', 'OTHER\n', 1)):
            with self.subTest(changed=changed[:80]), self.assertRaises(ValueError):
                read_finnish_hardware(changed)

    def test_private_join_chooses_selected_evidence_but_never_approves_publication(self):
        swedish, _ = capture(FixtureFetcher())
        french = read_charging_sheet(CHARGING_TEXT)
        dealer = read_dealer_offer(DEALER_TEXT, AUTH_TEXT, date(2026, 11, 19))
        finnish = read_finnish_hardware(FINNISH_TEXT)
        configs = [{'trim': trim, 'motor_id': code, 'model_year': 2027, 'seats': 5, 'wheelbase_mm': 2989,
                    'configuration_id': code + '$SYNTHETIC', 'summary': {'final_url': MODEL_URL,
                        'observations': {key: {'value': value, 'quote': 'synthetic evidence'} for key, value in (
                            ('configured_wltp_range_km', 460 - index * 10), ('configured_wltp_consumption_kwh_100km', 20 + index),
                            ('configured_cash_price_sek_including_vat', (599100, 639200)[index]), ('configured_braked_towing_kg', 1800))}}}
                   for index, (trim, code) in enumerate(TRIMS.items())]
        report = build_review(swedish, configs, french, finnish, dealer)
        self.assertFalse(report['publication_approved'])
        self.assertEqual(report['database_writes'], 0)
        for row in report['variants']:
            self.assertEqual(len(row['facts']), 9)
            self.assertEqual(row['price']['source_url'], DEALER)
            self.assertEqual(row['price']['price_type'], 'dealer_offer')
            self.assertEqual(row['facts']['dc_charge_kw']['value'], 185)
            self.assertEqual(row['facts']['dc_charge_kw']['alternative']['value'], 183)
        self.assertEqual(report['variants'][0]['facts']['tow_kg']['value'], 1200)
        self.assertEqual(report['variants'][0]['observed_configurator_tow']['value'], 1800)
        wrong_price = copy.deepcopy(dealer)
        wrong_price['prices']['Pro']['value'] -= 100
        with self.assertRaisesRegex(ValueError, 'dealer_cash_differs'):
            build_review(swedish, configs, french, finnish, wrong_price)
        finnish['EBBR5R']['dc_charge_kw'] = 183
        with self.assertRaisesRegex(ValueError, 'charging_sources_need_further_review'):
            build_review(swedish, configs, french, finnish, dealer)
