import io
import json
import sys
import unittest
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ford_puma_gen_e_review import HARDWARE_SOURCES, MARKET_SOURCES, PRICE_HEADER, PRICE_LIST, market_index, review


def fixture():
    html = f"""
    <h1>Puma Gen-E</h1><p>Helt elektrisk</p>
    <a href="{PRICE_LIST}">Ladda ner prislista</a>
    <p>Energif&ouml;rbrukning 0.0 kWh/0 km</p><p>R&auml;ckvidd 0 km</p>
    <div><h3>Puma Gen-E</h3><p>Pris fr&aring;n 389 000 kr. FWD 168 hk
        Laddhastighet (10-80%) 26 min R&auml;ckvidd upp till 417 km</p></div>
    <div><h3>Puma Gen-E Premium</h3><p>Pris fr&aring;n 409 000 kr. FWD 168 hk
        Laddhastighet (10-80%) 26 min R&auml;ckvidd upp till 404 km</p></div>
    <div><h3>Rymlig interi&ouml;r</h3>
        <div>Med f&ouml;rvaringsutrymmena bak inklusive den extra Gigaboxen under golvet (totalt 523 liter)
             och frunken fram (upp till 43 liter) finns det gott om lastutrymme.</div></div>
    """
    prices = f"""
    Puma Gen-E Prislista 4 - 2026 MY27 inkl. 5-&aring;rs garanti*
    {PRICE_HEADER}
    Gen-E (46,8 kWh) 168 hk (124 kW) 417 13,0 360 kr 2 010 kr 397 000 kr 389 000 kr
    Gen-E Premium (46,8 kWh) 168 hk (124 kW) 404 13,7 360 kr 2 075 kr 414 000 kr 409 000 kr
    Tillvalspaket & Tillval
    Laddare med 200 kW
    Max r\u00e4ckvidd enligt Worldwide Harmonised
    Gen-E - Standardutrustning urval
    Upp till 100 kW DC-snabbladdning
    11 kW 3-fasladdare (Ombordladdare)
    Gen-E Premium - standardutrustning urval ut\u00f6ver Gen-E
    """
    return {'model.html': html.encode('ascii'), 'prices.pdf': b'%PDF-synthetic'}, prices


def ipaper(name, pages):
    return ('<script type="text/javascript">window.staticSettings =' + json.dumps({
        'url': '/' + HARDWARE_SOURCES[name].split('/', 3)[3], 'countryCode': 45, 'pageTexts': pages,
    }) + ';</script>').encode('ascii')


def hardware_fixture(*, dk_edit=None, se_edit=None):
    files, prices = fixture()
    prices += ' Dragkrok (avtagbar) 8 000 kr 8 000 kr'
    factsheet = '''
    FORD PUMA GEN-E LAUNCH SPECIFICATION HIGHLIGHTS 2 series Ford Puma Gen-E Ford Puma Gen-E Premium
    WEIGHTS: Ford Puma Gen-E Ford Puma Gen-E Premium
    Max. towable braked 12% gradient (kg) 15 750 750 Max. towable unbraked (kg) 11 750 750
    DIMENSIONS: Ford Puma Gen-E Ford Puma Gen-E Premium
    Luggage capacity 5-seat mode laden to roof (litres) 5 574 574
    Luggage capacity 5-seat mode laden to seat back height without load floor (litres) 5 523 523
    Frunk capacity (litres) 43 43
    '''
    prices_dk = '''
    FORD PUMA GEN-E Vejl. prisliste d. 12/10-2026 SUV
    Maks. Effekt Elektrisk R\u00e6kkevidde Maks. anh\u00e6ngerv\u00e6gt (med/uden bremser)
    Halv\u00e5rlig ejerafgift Vejl. udsalgspris Elbil Select Black Edition Premium
    124 kW/168 hk 124 kW/168 hk 124 kW/168 hk 419 km 405 km 404 km
    750 / 750 kg 750 / 750 kg 750 / 750 kg 460 kr.
    Priserne g\u00e6lder model\u00e5r 2027.00.
    Batterikapacitet (Netto) Maks. lade effekt (AC/DC) Lade tid (AC) (0-100%) Lade tid (DC) (10-80%)
    Select Elektrisk forbrug Black Edition Premium Puma Gen-E 46,8 kWh 11 / 100 kW 8 t. 24 min. 26 min.
    '''.replace('2027.00.', '2027.00 med forbehold.')
    dimensions_dk = '''
    FORD PUMA GEN-E TEKNISKE SPECIFIKATIONER UDVENDIGE DIMENSIONER
    Bagagerumsvolumen (uden bagagerumsbund), bag 2. s\u00e6der\u00e6kke til rygl\u00e6nskant, l.
    Bagagerumsvolumen (uden bagagerumsbund), bag 2. s\u00e6der\u00e6kke til tag, l.
    Bagagerumsvolumen (uden bagagerumsbund), bag 1. s\u00e6der\u00e6kke til tag, l. Gigabox, l. Frunk, l.
    SELECT BLACK EDITION 17/9-2026 PREMIUM For: Skive, Bag: Tromler
    523 574 1.283 145 43 1.000 / 983 1.127 965 / 957 786
    523 574 1.283 145 43 1.000 / - 1.127 965 / - 786
    523 574 1.283 145 43 1.000 / 983 1.127 965 / 957 786
    '''
    if dk_edit:
        doc, old, new = dk_edit
        if doc == 'prices':
            prices_dk = prices_dk.replace(old, new, 1)
        elif doc == 'dimensions':
            dimensions_dk = dimensions_dk.replace(old, new, 1)
    if se_edit:
        factsheet = factsheet.replace(*se_edit, 1)
    files.update({
        'ford-se-factsheet.pdf': b'%PDF-factsheet-fixture',
        'ford-dk-prices.html': ipaper('ford-dk-prices.html', [prices_dk, 'supplement']),
        'ford-dk-technical.html': ipaper('ford-dk-technical.html', ['other page'] * 5
                                         + [dimensions_dk, 'other page', 'other page']),
    })
    return files, {files['prices.pdf']: prices, files['ford-se-factsheet.pdf']: factsheet}.__getitem__


def market_fixture(model_names, period='oktober 2026', workbook_url=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Elbil ranking'
    sheet.cell(2, 8, 'Nyregistreringar ' + period)
    for index, name in enumerate(model_names, start=10):
        sheet.cell(index, 4, name)
        sheet.cell(index, 6, 37)
        sheet.cell(index, 13, 382)
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return {'market.html': f'<a href="{workbook_url or MARKET_SOURCES["market.xlsx"]}">XLSX</a>'.encode(),
            'market.xlsx': stream.getvalue()}


class FordPumaReviewTest(unittest.TestCase):
    def test_price_wltp_and_charging_joint_review_is_private(self):
        files, prices = fixture()
        result = review(files, price_text=lambda _: prices)
        self.assertEqual(['Gen-E', 'Gen-E Premium'], [variant['variant'] for variant in result['variants']])
        self.assertFalse(result['publication_approved'])
        self.assertEqual(0, result['production_writes'])
        for variant, expected in zip(result['variants'], [(397000, 389000, 417, 13.0), (414000, 409000, 404, 13.7)]):
            self.assertEqual(expected, (variant['list_price']['value'], variant['edition_price_reference']['value'],
                variant['facts']['wltp_range_km']['value'], variant['facts']['wltp_consumption_kwh_100km']['value']))
            facts = {key: evidence['value'] for key, evidence in variant['facts'].items()}
            self.assertEqual({k: v for k, v in facts.items() if not k.startswith('wltp')},
                             {'battery_kwh': 46.8, 'dc_charge_kw': 100, 'ac_charge_kw': 11,
                              'boot_liters': 523, 'drivetrain': 'FWD'})

    def test_rejects_wrong_year_old_battery_and_price_header(self):
        for old, new, reason in [('MY27', 'MY26.25', 'model_year_changed'), ('46,8', '43,0', 'two_rows_required'),
                                 ('Rek. Edition pris', 'Kampanjpris', 'price_columns')]:
            with self.subTest(old=old), self.assertRaisesRegex(ValueError, reason):
                files, prices = fixture()
                review(files, price_text=lambda _: prices.replace(old, new, 1))

    def test_rejects_mixed_trims_and_other_linked_pdf(self):
        for old, new, reason in [(b'404 km', b'417 km', 'wltp_conflict'),
                                 (b'409 000 kr', b'389 000 kr', 'wltp_conflict'),
                                 (PRICE_LIST.encode(), b'https://www.ford.se/other.pdf', 'price_link_changed'),
                                 (b'<h1>Puma Gen-E', b'<h1>Puma EcoBoost', 'electric_model_identity')]:
            with self.subTest(old=old), self.assertRaisesRegex(ValueError, reason):
                files, prices = fixture()
                files['model.html'] = files['model.html'].replace(old, new, 1)
                review(files, price_text=lambda _: prices)

    def test_cable_and_station_output_cannot_replace_vehicle_charging(self):
        for old, new, reason in [('11 kW 3-fasladdare (Ombordladdare)', '11 kW laddkabel', 'onboard_ac_required'),
                                 ('Upp till 100 kW DC-snabbladdning', '200 kW offentlig laddare', 'vehicle_dc_peak')]:
            with self.subTest(old=old), self.assertRaisesRegex(ValueError, reason):
                files, prices = fixture()
                review(files, price_text=lambda _: prices.replace(old, new, 1))

    def test_complete_hardware_packet_keeps_sweden_specific_rows(self):
        files, parse = hardware_fixture()
        result = review(files, price_text=parse)
        self.assertFalse(result['publication_approved'])
        self.assertEqual(0, result['production_writes'])
        self.assertEqual(5, len(result['sources']))
        self.assertEqual(['verify_bev_only_market_alias', 'finalize_photo_receipt', 'isolated_insertion_review'],
                         result['held'])
        for variant, expected in zip(result['variants'], [(397000, 417, 13.0), (414000, 404, 13.7)]):
            facts = variant['facts']
            self.assertEqual(9, len(facts))
            self.assertEqual(expected, (variant['list_price']['value'], facts['wltp_range_km']['value'],
                                        facts['wltp_consumption_kwh_100km']['value']))
            self.assertEqual((46.8, 523, 750, 5),
                             tuple(facts[k]['value'] for k in ('battery_kwh', 'boot_liters', 'tow_kg', 'seats')))
            self.assertIn('usable', facts['battery_kwh']['scope'])
            self.assertIn('seatback', facts['boot_liters']['scope'])
            self.assertIn('braked', facts['tow_kg']['scope'])
            for fact in facts.values():
                for evidence in [fact, *fact.get('corroboration', [])]:
                    self.assertTrue(evidence['source_quote'])
                    self.assertIn((evidence['source_url'], evidence['source_hash']),
                                  [(s['source_url'], s['source_hash']) for s in result['sources'].values()])

    def test_rejects_wrong_year_label_and_conflicting_braked_towing(self):
        for old, replacement, reason in [
            ('2027.00', '2026.75', 'my27_price_identity'),
            ('med/uden bremser', 'uden/med bremser', 'braked_tow_columns'),
            ('750 / 750', '650 / 750', 'braked_tow_conflict'),
            ('Select Black Edition Premium', 'Premium Black Edition Select', 'braked_tow_columns'),
            ('(Netto)', '(Brutto)', 'usable_battery_columns'),
            ('46,8 kWh', '46,0 kWh', 'battery_or_charging_conflict'),
        ]:
            with self.subTest(old=old), self.assertRaisesRegex(ValueError, reason):
                files, parse = hardware_fixture(dk_edit=('prices', old, replacement))
                review(files, price_text=parse)

    def test_rejects_roof_volume_wrong_seat_scope_and_partial_packet(self):
        files, parse = hardware_fixture(dk_edit=('dimensions', '523 574', '574 523'))
        with self.assertRaisesRegex(ValueError, 'dk_seats_up_cargo_conflict'):
            review(files, price_text=parse)
        files, parse = hardware_fixture(se_edit=('5-seat mode laden to seat back', '2-seat mode laden to seat back'))
        with self.assertRaisesRegex(ValueError, 'se_seats_up_cargo_conflict'):
            review(files, price_text=parse)
        del files['ford-dk-prices.html']
        with self.assertRaisesRegex(ValueError, 'review_source_set_changed'):
            review(files, price_text=parse)

    def test_requires_exact_puma_row_and_report_link(self):
        result = market_index(market_fixture(['FORD PUMA', 'FORD PUMA/OTHER']))
        self.assertEqual(('FORD', 'PUMA', 'EL', '2026-10-01', 37, 382),
                         tuple(result[k] for k in ('brand_raw', 'model_raw', 'fuel_type_raw', 'last_seen_month',
                                                   'registrations_last_month', 'registrations_ytd')))
        for files, reason in [
            (market_fixture(['FORD PUMA/OTHER']), 'exact_el_market_row'),
            (market_fixture(['FORD PUMA', 'FORD PUMA']), 'exact_el_market_row'),
            (market_fixture(['FORD PUMA'], 'september 2026'), 'exact_october_presence'),
            (market_fixture(['FORD PUMA'], workbook_url='https://example.com/unrelated.xlsx'), 'official_workbook_link'),
        ]:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                market_index(files)


if __name__ == '__main__':
    unittest.main()
