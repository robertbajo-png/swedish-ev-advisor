import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from openpyxl import Workbook
from polestar_3_review import MARKET_SOURCES, SOURCES, review, review_market
from prerender_static_routes import public_variant_routes


def fixture():
    return {name: body.encode('ascii') for name, body in {
        'overview.html': '<h1>Polestar 3</h1><h2>Ja, det &auml;r en SUV. Med k&auml;nslan av en sportbil.</h2>',
        'configuration.html': '''
        <h1>Polestar 3 Performance</h1><p>22-tums Performance-f&auml;lgar</p>
        <script>
        {queryKey:["configuration-rules",$R[1]={pno3:"359",modelYear:"2027",locale:"se",x:0}],
        title:"Performance",shortTitle:"Performance",description:"Performance wheels",slug:"performance",pnoType:"engine",pnoCode:"DA",
        preview:"359 - 2027 - DA - Engine - 22-inch Performance wheels",
        from:$R[2]={code:"XPFWHE",pnoType:"options"},to:$R[3]=[$R[4]={code:"DA",pnoType:"engine"}],onlyAvailableWith:!0}
        </script>
        ''',
        'specs.html': '''
        <title>Polestar 3 - Tekniska specifikationer | Polestar Sverige</title>
        <table><tr><th>Dual motor</th><th>Performance</th></tr>
        <tr><td>Pris 924 000 kr</td><td>Pris 999 000 kr</td></tr>
        <tr><td>Effekt&sup1; 400 kW/544 hk</td><td>Effekt&sup1; 500 kW / 680 hk</td></tr>
        <tr><td>Drivlina Fyrhjulsdrift</td><td>Drivlina Fyrhjulsdrift</td></tr>
        <tr><td>R&auml;ckvidd (WLTP)&sup2; 647 km</td><td>R&auml;ckvidd (WLTP)&sup2; 601 km</td></tr>
        <tr><td>Energikonsumtion (WLTP)&sup2; 19,0 - 23,1 kWh/100 km</td>
            <td>Energikonsumtion (WLTP)&sup2; 20,5 - 23,1 kWh/100 km</td></tr>
        <tr><td>Dragkraft Upp till 2 200 kg</td><td>Dragkraft Upp till 2 200 kg</td></tr></table>
        <dl><div><dt>Batteri</dt><dd>800 V Litiumjonbatteri 106 kWh kapacitet, 16 moduler</dd></div>
        <div><dt>Laddkapacitet</dt><dd>Upp till 350 kW (800 V) Upp till 120 kW (400 V)</dd></div>
        <div><dt>Hemma- eller publik laddning (0-100%)</dt><dd>10 timmar (11 kW AC)&sup1;</dd></div>
        <div><dt>Volym (s&auml;ten uppf&auml;llda)</dt><dd>484 liter upp till ryggst&ouml;den, inklusive 90 liter under golvet
        597 liter upp till innertaket, inklusive 90 liter under golvet</dd></div></dl>
        ''',
        'wltp.html': '''
        <p>Polestar 3 - 2027</p><h1>Bilens certifierade v&auml;rden f&ouml;r r&auml;ckvidd och elf&ouml;rbrukning</h1>
        <table>
        <tr><td><img src="range"></td><td>Certifierat v&auml;rde f&ouml;r bilens potentiella r&auml;ckvidd (km)</td></tr>
        <tr><td><img src="consumption"></td><td>Certifierat v&auml;rde f&ouml;r bilens elf&ouml;rbrukning (kWh/100 km)</td></tr>
        <tr><td><img src="city"></td><td>Stads- och f&ouml;rortsk&ouml;rning.</td></tr>
        <tr><td><img src="combined"></td><td>Medelv&auml;rde &ouml;ver alla fyra k&ouml;rcykelfaser.</td></tr>
        <tr><td><img src="low"></td><td>L&aring;gt v&auml;rde.</td></tr>
        <tr><td><img src="high"></td><td>H&ouml;gt v&auml;rde.</td></tr>
        </table><table><caption>Performance</caption>
        <tr><td></td><td colspan="2"><img src="range"></td><td><img src="consumption"></td></tr>
        <tr><td><img src="city"></td><td><img src="combined"></td></tr>
        <tr><td><img src="low"></td><td>742</td><td>601</td><td>20,5</td></tr>
        <tr><td><img src="high"></td><td>649</td><td>524</td><td>23,1</td></tr>
        </table>
        ''',
        'tow.html': '''
        <p>Polestar 3 - 2027</p><section><h2>Bromsad sl&auml;pvagn</h2><table>
        <tr><td>Max. sl&auml;pvagnsvikt</td><td>2 200 kg</td></tr></table></section>
        <section><h2>Obromsad sl&auml;pvagn</h2><table>
        <tr><td>Max. sl&auml;pvagnsvikt</td><td>750 kg</td></tr></table></section>
        ''',
        'seats.html': '''
        <p>Polestar 3 - 2027</p><h1>&Ouml;versiktstabell &ouml;ver l&auml;mpliga placeringar av barnskydd</h1>
        <table><tr><th>S&auml;tesplats 1</th><th>1</th><th>2 (med inaktiverad krockkudde, endast bak&aring;tv&auml;nda barnskydd)</th>
        <th>2 (med aktiverad krockkudde, endast fram&aring;tv&auml;nda barnskydd)</th><th>3</th><th>4</th><th>5</th></tr></table>
        ''',
    }.items()}


class Polestar3ReviewTest(unittest.TestCase):
    def test_static_route_includes_certified_interval_instead_of_city_or_single_number(self):
        row = {'brand': 'Polestar', 'model': '3', 'variant_name': 'Performance', 'validation_status': 'published',
               'price_sek': 999000, 'price_type': 'list_price', 'wltp_range_km': 601, 'source_url': SOURCES['specs.html'],
               'source_quote': SOURCES['wltp.html'] + ' | Performance | 742 | 601 | 20,5 | 649 | 524 | 23,1'}
        route, = public_variant_routes([row])
        self.assertIn('524\u2013601 km', route['description'])
        self.assertNotIn('742', route['description'])
        vehicle, = (schema for schema in route['json_ld'] if schema['@type'] == 'Vehicle')
        props = {prop['name']: prop['value'] for prop in vehicle['additionalProperty']}
        self.assertEqual('524\u2013601 km', props['WLTP-r\u00e4ckvidd'])

    def test_market_evidence_requires_exact_october_workbook_and_bev_identity(self):
        def market(label='POLESTAR 3', month='oktober 2026', use_link=True):
            book = Workbook()
            sheet = book.active
            sheet.title = 'Elbil ranking'
            sheet.cell(2, 8, 'Nyregistreringar ' + month)
            for col, value in ((4, label), (6, 15), (13, 390)):
                sheet.cell(10, col, value)
            stream = io.BytesIO()
            book.save(stream)
            book.close()
            link = MARKET_SOURCES['market.xlsx'] if use_link else 'https://example.com/not-the-workbook.xlsx'
            return {'market.html': f'<a href="{link}">Report</a>'.encode(), 'market.xlsx': stream.getvalue()}

        self.assertEqual(15, review_market(market())['row']['registrations_last_month'])
        for candidate in (market('POLESTAR 4'), market(month='september 2026'), market(use_link=False)):
            with self.assertRaises(ValueError):
                review_market(candidate)

    def test_exact_performance_sources_are_complete_but_held(self):
        result = review(fixture())
        self.assertEqual({n: item['value'] for n, item in result['facts'].items()}, {
            'wltp_range_km': 601, 'wltp_consumption_kwh_100km': 20.5, 'battery_kwh': 106,
            'dc_charge_kw': 350, 'ac_charge_kw': 11, 'boot_liters': 484, 'tow_kg': 2200,
            'seats': 5, 'drivetrain': 'AWD',
        })
        self.assertEqual(999000, result['price']['value'])
        self.assertEqual(SOURCES['wltp.html'], result['facts']['wltp_range_km']['source_url'])
        self.assertEqual(result['sources']['seats.html']['source_hash'], result['facts']['seats']['source_hash'])
        self.assertEqual(2027, result['market_configuration_model_year'])
        self.assertEqual('359/DA/XPFWHE', result['configuration']['value'])
        self.assertFalse(result['configuration']['configuration_price_returned'])
        self.assertFalse(result['publication_approved'])
        self.assertEqual(0, result['database_writes'])

    def test_exact_model_scope_failures(self):
        for name, old, new, error in (
            ('configuration.html', b'<h1>Polestar 3 Performance', b'<h1>Polestar 3 Dual motor', 'heading_changed'),
            ('configuration.html', b'22-tums', b'20-tums', 'wheel_scope_changed'),
            ('configuration.html', b'pnoCode:"DA"', b'pnoCode:"DE"', 'swedish_my27_engine_rule_changed'),
            ('configuration.html', b'modelYear:"2027"', b'modelYear:"2026"', 'swedish_my27_engine_rule_changed'),
            ('configuration.html', b'onlyAvailableWith:!0', b'onlyAvailableWith:null', 'swedish_my27_engine_rule_changed'),
            ('wltp.html', b'Polestar 3 - 2027', b'Polestar 3 - 2026', 'model_year_changed'),
            ('wltp.html', b'<caption>Performance', b'<caption>Dual motor', 'certified_performance_table_missing'),
            ('specs.html', b'<th>Dual motor</th><th>Performance</th>', b'<th>Performance</th><th>Dual motor</th>', 'price_column_changed'),
            ('specs.html', b'<td>Pris 999', b'<td colspan="2">Pris 999', 'column_span_changed'),
            ('specs.html', b'800 V Litiumjonbatteri 106', b'400 V Litiumjonbatteri 111', 'unsupported_value'),
        ):
            with self.subTest(name=name, new=new), self.assertRaisesRegex(ValueError, error):
                files = fixture()
                files[name] = files[name].replace(old, new, 1)
                review(files)

    def test_rejects_first_hand_source_conflicts_and_symbol_drift(self):
        for name, old, new, error in (
            ('wltp.html', b'<td>601</td>', b'<td>647</td>', 'certified_wltp_conflict'),
            ('wltp.html', b'<td>20,5</td>', b'<td>19,0</td>', 'certified_wltp_conflict'),
            ('wltp.html', b'src="city"></td><td><img src="combined"', b'src="combined"></td><td><img src="city"', 'wltp_table_scope_changed'),
            ('tow.html', b'2 200 kg', b'1 500 kg', 'braked_tow_conflict'),
            ('seats.html', b'<th>5</th>', b'<th>6</th>', 'seat_positions_changed'),
        ):
            with self.subTest(name=name, new=new), self.assertRaisesRegex(ValueError, error):
                files = fixture()
                files[name] = files[name].replace(old, new, 1)
                review(files)

    def test_rejects_monthly_lease_as_vehicle_price_and_incomplete_source_set(self):
        files = fixture()
        files['specs.html'] = files['specs.html'].replace(b'999 000 kr', b'9 995 kr/m&aring;n')
        with self.assertRaisesRegex(ValueError, 'unsupported_value'):
            review(files)
        del files['wltp.html']
        with self.assertRaisesRegex(ValueError, 'exact_source_set_required'):
            review(files)


if __name__ == '__main__':
    unittest.main()
