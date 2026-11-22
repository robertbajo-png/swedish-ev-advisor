import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from hyundai_ioniq5_review import (BROCHURE, CapturedSources, ORDERING, ORDER_URLS, RA_WEBSITE, SCOPE, allow_source, brochure_facts, dc_facts,
                                  dealer_fact_cards, discover_downloads, ordering_identity, practicality, ra_n_line_identity,
                                  read_prices, verify_dealer_authorization)


ISSUE = date(2026, 11, 2)
TODAY = date(2026, 11, 20)
PRICE_URL = 'https://dmassets.hyundai.com/is/content/hyundaiautoever/Hyundai_Sverige_Prislista_20261102pdf'
SYNTHETIC_PRICES = '''Datum: 2026-11-02
Modell och version Elf\u00f6rbrukning* F\u00f6rbrukning* CO2* Rek. pris Privatleasing Businessleasing
kWh/10 km* l/10 km (g/km) (inkl. moms) (fr\u00e5n/m\u00e5n*) (fr\u00e5n/m\u00e5n*)
IONIQ 5
RWD 63kWh Essential 1,56 - 0 554 900 kr - -
RWD 84kWh Essential 1,60 - 0 594 900 kr 4 795 kr 2 620 kr
AWD 84kWh Essential 1,68 - 0 629 900 kr - -
RWD 84kWh Advanced 1,60 - 0 637 900 kr - -
AWD 84kWh Advanced 1,68 - 0 672 900 kr - -
RWD 84kWh N Line 1,72 - 0 654 900 kr - -
AWD 84kWh N Line 1,81 - 0 689 900 kr - -
M\u00f6jliga tillval: metalliclack 9 500 kr
IONIQ 5 N
AWD 84kWh N 2,12 - 0 843 900 kr - -
*G\u00e4ller blandad k\u00f6rning enligt WLTP
'''

BROCHURE_PAGE = '''Classification 2WD Standard 2WD Long Range AWD Long Range
Max. power (kW) 125 168 239
Capacity (kWh) 63.0 84.0 84.0
On-board charger (OBC) Max capacity (kW) 7 (1-phase)/10.5 (3-phase) 7 (1-phase)/10.5 (3-phase) 7 (1-phase)/10.5 (3-phase)
Charging time
Quick charge, up to 80% (350 kW) ~18 min ~18 min ~18 min
Electric range (WLTP)** combined (km) 440 19\u02dd tyres: 570/20\u02dd tyres: 530/
20\u02dd tyres N Line: 515
19\u02dd tyres: 546/20\u02dd tyres: 500/
20\u02dd tyres N Line: 495
Performance'''


class Ioniq5ReviewTests(unittest.TestCase):
    def test_downloads_must_link_exact_model_and_accepted_swedish_documents(self):
        def link(category, label, url):
            return (f"""<a data-js-item="download-list-link" data-js-tracking='"""
                    f"""{{"eventLabel":"{label}","eventCategory":"{category}"}}' href="{url}">PDF</a>""").encode()
        html = (link('Download - Prislista', 'IONIQ 5', PRICE_URL)
                + link('Download - IONIQ 5 Modellbroschyr', 'IONIQ 5', BROCHURE))
        self.assertEqual(discover_downloads(html), PRICE_URL)
        with self.assertRaises(ValueError):
            discover_downloads(html.replace(b'5"', b'5 N"'))
        self.assertFalse(allow_source(PRICE_URL + '?other=1', {'Hyundai'}))
        self.assertFalse(allow_source(PRICE_URL, {'Kia'}))

    def test_only_standard_grade_cash_prices_and_combined_units(self):
        rows = read_prices(SYNTHETIC_PRICES, ISSUE, TODAY)
        self.assertEqual(rows.keys(), SCOPE)
        self.assertEqual(rows['RWD', 84, 'Essential'][:2], (594900, 16.0))
        self.assertEqual(rows['AWD', 84, 'N Line'][:2], (689900, 18.1))

    def test_rejects_price_date_units_missing_and_duplicate_versions(self):
        bad = [SYNTHETIC_PRICES.replace('kWh/10 km', 'kWh/100 km'),
               SYNTHETIC_PRICES.replace('2026-11-02', '2026-11-03'),
               SYNTHETIC_PRICES.replace('AWD 84kWh N Line', 'AWD 84kWh Unknown'),
               SYNTHETIC_PRICES.replace('AWD 84kWh Advanced', 'AWD 84kWh Essential')]
        for fixture in bad:
            with self.subTest(fixture=fixture), self.assertRaises(ValueError):
                read_prices(fixture, ISSUE, TODAY)
        with self.assertRaises(ValueError):
            read_prices(SYNTHETIC_PRICES, ISSUE, date(2027, 5, 1))

    def test_dealer_check_uses_ordinary_price_and_exact_drivetrain(self):
        prices = read_prices(SYNTHETIC_PRICES, ISSUE, TODAY)
        cards = [f'{grade} {capacity} kWh \xb7 {"Bakhjulsdrift" if drive == "RWD" else "Fyrhjulsdrift"} ({drive}) '
                 f'Pris vid finansiering 488 312 kr Ord. pris {cash:,} kr Spara 66 588 kr'.replace(',', ' ')
                 for (drive, capacity, grade), (cash, *_rest) in prices.items()]
        self.assertEqual(dealer_fact_cards(cards, prices).keys(), SCOPE)
        for wrong in (cards[0].replace('554 900', '488 312'), cards[0].replace('RWD', 'AWD')):
            with self.assertRaises(ValueError):
                dealer_fact_cards([wrong, *cards[1:]], prices)

    def test_hyundai_locator_must_authorize_sales_on_exact_domain(self):
        fixture = {'id': 'C18AS20016', 'dealerId': 'C18AS20016', 'shortOutletName': 'Karmauto AB',
                   'webSite': 'https://karmauto.se/', 'onlyService': False,
                   'dealerProperties': [{'services': [{'serviceId': 'sales'}]}]}

        def html(item):
            data = json.dumps({'dealers': {'se': [item]}})
            return f"""<div data-js-module="dealer-locator" data-js-content='{data}'></div>""".encode()

        self.assertIn('sales', verify_dealer_authorization(html(fixture)))
        with self.assertRaises(ValueError):
            verify_dealer_authorization(html({**fixture, 'onlyService': True}))
        with self.assertRaises(ValueError):
            verify_dealer_authorization(html({**fixture, 'webSite': 'https://karmauto.example/'}))

    def test_swedish_ordering_id_binds_year_motor_and_literal_material(self):
        key = ('AWD', 84, 'Advanced')
        code = ORDERING[key][0]
        title = 'IONIQ 5 \xb7 AWD 84kWh Advanced MY27'
        component = json.dumps({'assetId': code, 'modelKey': 'IONIQ 5'}, separators=(',', ':'))
        frame = json.dumps([1, 'b:' + component])
        source = (f'<title>{title} | Hyundai Sverige</title><meta property="og:title" content="{title}">'
                  f'<script>self.__next_f.push({frame});</script>').encode()
        self.assertEqual(ordering_identity(source, key)['material_number'], code)
        self.assertNotIn(('RWD', 84, 'N Line'), ORDER_URLS)
        self.assertTrue(allow_source(ORDER_URLS[key], {'Hyundai'}))
        self.assertFalse(allow_source(ORDER_URLS[key].replace('private', 'corporate'), {'Hyundai'}))
        for wrong in [source.replace(b'MY27', b'MY26'), source.replace(b'AWD', b'RWD'),
                      source.replace(code.encode(), b'GIW5ZHZ7ZHH2GQ')]:
            with self.assertRaises(ValueError):
                ordering_identity(wrong, key)

    def test_offline_replay_checks_source_hash_before_parsing(self):
        with tempfile.TemporaryDirectory() as scratch:
            folder = Path(scratch).resolve()
            body = b'<p>Invented capture for byte integrity testing</p>'
            manifest = {}
            for n in range(1, 12):
                filename = f'source-{n}.html'
                (folder / filename).write_bytes(body)
                manifest[filename] = {'url': PRICE_URL.replace('20261102', f'202611{n:02d}'),
                                      'sha256': hashlib.sha256(body).hexdigest(), 'http_status': 200}
            captured = CapturedSources(folder, manifest)
            self.assertEqual(captured.fetch(PRICE_URL, {'Hyundai'})['document'], body)
            self.assertEqual(captured.fetch(BROCHURE, {'Hyundai'})['status'], 'not_captured')
            (folder / 'source-2.html').write_bytes(body + b' updated')
            with self.assertRaisesRegex(ValueError, 'hash_mismatch'):
                CapturedSources(folder, manifest)

    def test_rwd_n_line_uses_authorized_exact_year_without_leaking_stock_offer(self):
        outlet = {'id': 'C18AS20015', 'dealerId': 'C18AS20015', 'fullDealerName': 'Hyundai Haninge',
                  'shortOutletName': 'R A MOTOR AB', 'webSite': RA_WEBSITE, 'onlyService': False,
                  'dealerProperties': [{'services': [{'serviceId': 'sales'}]}]}
        data = json.dumps({'dealers': {'se': [outlet]}})
        locator = f"""<div data-js-module="dealer-locator" data-js-content='{data}'></div>""".encode()
        page = ('<h1>Hyundai Ioniq 5 84 kWh RWD N-Line *R\u00e4ntekampanj 2,99%</h1>'
                '<ul><li>\u00c5rsmodell 2027</li><li>Drivmedel El</li></ul>'
                '<dl><dt>Anl\u00e4ggning</dt><dd>Haninge</dd></dl><p>999 999 kr</p>').encode()
        self.assertEqual(ra_n_line_identity(page, locator), 'Hyundai Ioniq 5 84 kWh RWD N-Line | MY27 | Haninge')
        for wrong in [page.replace(b'2027', b'2026'), page.replace(b'RWD', b'AWD'),
                      page.replace(b'Haninge', b'Uppsala'), page.replace(b'Drivmedel El', b'Drivmedel Diesel')]:
            with self.assertRaises(ValueError):
                ra_n_line_identity(wrong, locator)
        with self.assertRaises(ValueError):
            ra_n_line_identity(page, locator.replace(b'"sales"', b'"service"'))

    def test_wheel_and_charging_evidence_is_scoped(self):
        rows, _, _ = brochure_facts(BROCHURE_PAGE)
        self.assertEqual(rows[1]['range_by_wheel'], {'19': 570, '20': 530, '20 N Line': 515})
        self.assertEqual(rows[2]['range_by_wheel']['20 N Line'], 495)
        self.assertTrue(all(row['ac_kw'] == 10.5 for row in rows))
        with self.assertRaises(ValueError):
            brochure_facts(BROCHURE_PAGE.replace('On-board charger', 'Charging station'))
        motor_keys = [('RWD', 63), ('RWD', 84), ('AWD', 84)]
        norway = ['2024 \u2013 63 kWt (Standard Range RWD) 440 km 195 kW',
                  '2024 \u2013 84 kWt (Long Range RWD) 570 km 260 kW',
                  '2024 \u2013 84 kWt (Long Range AWD) 546 km 260 kW']
        self.assertEqual(dc_facts(norway, dict(zip(motor_keys, rows)))['RWD', 63][0], 195)
        with self.assertRaises(ValueError):
            dc_facts([norway[0].replace('440', '450'), *norway[1:]], dict(zip(motor_keys, rows)))

    def test_towing_is_braked_cargo_is_seats_up_and_seats_are_exact(self):
        technical = ('Teknisk specifikation Motor V\u00e4xell\u00e5da 63kWh: RWD 170hk 84kWh: RWD 228hk/ AWD 325hk\n'
                     'Lastutrymme, uppf\u00e4llt/nedf\u00e4llt baks\u00e4te (VDA, liter) 520/1 580 Frunk\n'
                     'Max sl\u00e4pvagnsvikt (bromsad) (kg) 750 1600 Max sl\u00e4pvagnsvikt (obromsad)')
        family = 'IONIQ 5 Fra 465 375 kr Opptil 570 km 520 l \u2013 opptil 1 580 l + frunk 5 5 stjerner Opptil 1 600 kg Den komplette familiebilen'
        tow, cargo, seats = practicality(technical, [family])
        self.assertEqual((tow[1], tow[2], cargo[1], seats[2]), ('750', '1600', '520', '5'))
        with self.assertRaises(ValueError):
            practicality(technical.replace('bromsad', 'obromsad'), [family])
        with self.assertRaises(ValueError):
            practicality(technical, [family.replace('520 l', '530 l')])


if __name__ == '__main__':
    unittest.main()
