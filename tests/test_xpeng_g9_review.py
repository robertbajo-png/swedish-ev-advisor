import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from xpeng_g9_review import APPOINTMENT, AWD, FACTORY, LONG, STANDARD, TRIMS
from xpeng_g9_review import configurator_identities, dealer_prices, locator_appointment, review, swedish_cards, table_scope


def version_state(market, *, order='new_G9', change=None):
    keys = TRIMS if market == 'SE' else FACTORY
    rows = []
    for i, trim in enumerate(keys, start=1):
        rows.append(dict(id=str(i), carSeriesId='651' if market == 'SE' else '631',
                         carSeriesName='New G9' if market == 'SE' else 'G9',
                         carSeriesCode='E38bV', carVersionCode=FACTORY[trim], powerType='BEV',
                         carVersionName=trim, carVersionAlias=trim, msrpBeforeSubsidy=TRIMS[trim]['price'] if market == 'SE' else 59600,
                         msrpAfterSubsidy=TRIMS[trim]['price'] if market == 'SE' else 59600))
    if change:
        rows[0].update(change)
    chunk = ['$', ['$', '$L1', None, {'states': {'carSeriesCode':order, 'carVersionListData':rows}}]]
    payload = json.dumps([1, 'a:' + json.dumps(chunk) + '\n'])
    return f'<html lang="{market.lower().replace("se","sv")}"><script>self.__next_f.push({payload})</script></html>'.encode()


def cards(*, price=None, battery=None, range_km=None):
    def card(trim):
        p = TRIMS[trim]
        wd = 'bakhjulsdrivna' if trim == STANDARD else 'fyrhjulsdrivna'
        label = 'Standard Range' if trim == STANDARD else trim
        dec = lambda value: str(value).replace('.', ',')
        gross = battery if trim == STANDARD and battery is not None else p['gross']
        km = range_km if trim == STANDARD and range_km is not None else p['wltp']
        d = [
            f'R\xe4ckvidd (WLTP): {km} km*', f'Max effekt: {p["power"]} kW (351 hk)',
            f'Batterikapacitet (brutto): {dec(gross)} kWh', f'Genomsnittlig f\xf6rbrukning (WLTP): {dec(p["consumption"])} kWh/100km',
            'Plattform: 800 Volt Sepa 2.0', f'DC-laddning: upp till {p["dc"]} kW', 'AC-laddning: 11 kW (3-fas)',
            f'Bruttovikt: {p["gvw"]:,} kg'.replace(',', '.'), 'Dragvikt: 1.500 kg',
        ]
        amount = price if trim == STANDARD and price is not None else (f'{p["price"]:,} kr').replace(',', ' ')
        values = ' \xb7 '.join(d)
        return (f'<div class="detailCard_detailCard__x"><span class="detailCard_title__x">{trim}</span>'
                f'<article>NYA XPENG G9 {label} \xe4r den {wd} versionen Viktiga specifikationer: {values}'
                f' Exteri\xf6r {p["wheels"]}" aluminiumf\xe4lgar. Bagagevolym: 660 liter / 1.576 liter med nedf\xe4llt baks\xe4te.'
                ' All teknisk data \xe4r beroende av typgodk\xe4nnandet.</article>'
                f'<div class="detailCard_priceValue__x">{amount}</div></div>')
    return ('<h2>BYGG DIN XPENG G9</h2><div class="settingCard_content__x">'
            + ''.join(card(trim) for trim in TRIMS) + '</div>').encode()


class XpengG9ReviewTest(unittest.TestCase):
    def test_join_matches_only_the_two_exact_swedish_factory_identities(self):
        se = configurator_identities(version_state('SE'), market='SE')
        de = configurator_identities(version_state('DE'), market='DE')
        self.assertNotIn(LONG, se)
        self.assertIn(LONG, de)
        self.assertEqual({k: de[k]['value'] for k in se}, {k: v['value'] for k, v in se.items()})

    def test_rejects_wrong_generation_fuel_code_and_subsidized_price(self):
        for change in ({'carSeriesCode':'E38V'}, {'carVersionCode':'EEBB'}, {'powerType':'EREV'},
                       {'msrpAfterSubsidy':699900}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                configurator_identities(version_state('SE', change=change), market='SE')
        with self.assertRaises(ValueError):
            configurator_identities(version_state('SE', order='G9L'), market='SE')

    def test_starting_price_and_wltp_belong_to_each_variant(self):
        rows = swedish_cards(cards())
        self.assertEqual(rows[STANDARD]['price']['value'],719900)
        self.assertEqual(rows[AWD]['price']['value'],849900)
        self.assertEqual(rows[STANDARD]['facts']['battery_kwh']['value'],79)
        self.assertEqual(rows[AWD]['facts']['battery_kwh']['value'],93.1)
        self.assertEqual(rows[AWD]['facts']['wltp_range_km']['value'],540)
        self.assertNotIn('tow_kg', rows[STANDARD]['facts'])
        for bad in (cards(price='5 399 kr/m\xe5n'), cards(battery=80.3), cards(range_km=585)):
            with self.subTest(bad=bad[:70]), self.assertRaises(ValueError):
                swedish_cards(bad)

    def test_dealer_must_validate_cash_prices_not_monthly_amounts(self):
        body = ('<h1>XPENG G9</h1> RWD Standard Range Elbil Erbjudande Pris fr. 719 900kr '
                'Nya XPENG G9 Standard Range AWD Performance: K\xf6ppris: 849 900 kr '
                'F\xf6rbrukning, blandad k\xf6rning (WLTP): 18,4 kWh/100 km').encode()
        variants = swedish_cards(cards())
        self.assertEqual(dealer_prices(body,variants)[AWD]['value'],849900)
        for altered in (body.replace(b'849 900',b'839 900'), body.replace(b'849 900',b'6 374')):
            with self.assertRaises(ValueError):
                dealer_prices(altered,variants)

    def test_dealer_is_bound_to_the_exact_official_karlstad_outlet(self):
        body = dict(final_url=APPOINTMENT,http_status=200,body_kind='rendered_official_outlet_card',
                    rendered_html='<h3>XPENG Experience Center Sweden Karlstad</h3><p>Blockgatan 5, 653 41 Karlstad</p><p>info@lecab.se</p>')
        self.assertEqual(locator_appointment(json.dumps(body).encode())['value'],'Lecab Bil Karlstad')
        for change in ({'final_url':'https://lecab.se/'}, {'http_status':403},
                       {'rendered_html':body['rendered_html'].replace('Blockgatan 5','Blockgatan 7')}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                locator_appointment(json.dumps({**body,**change}).encode())

    def test_a_pdf_value_applies_to_other_trims_only_if_cell_spans_them(self):
        label = 'Anh\xe4ngelast gebremst / ungebremst (kg)'
        rows = [['GVW','2730','2810','2910'],[label,'1500 / 750',None,None]]
        boxes = [[(0,0,5,1),(5,0,10,1),(10,0,15,1),(15,0,20,1)],
                 [(0,1,5,2),(5,1,20,2),None,None]]
        table = SimpleNamespace(extract=lambda: rows, rows=[SimpleNamespace(cells=cells) for cells in boxes])
        self.assertEqual(table_scope(table,'GVW')(label),('1500 / 750',)*3)
        narrower = copy.deepcopy(boxes)
        narrower[1][1] = (5,1,10,2)
        table.rows[1].cells = narrower[1]
        with self.assertRaisesRegex(ValueError,'cell_not_bound'):
            table_scope(table,'GVW')(label)

    def test_a_partial_packet_is_held(self):
        with self.assertRaisesRegex(ValueError,'full_pinned_source_packet_required'):
            review({'config.html':cards()})


if __name__ == '__main__':
    unittest.main()
