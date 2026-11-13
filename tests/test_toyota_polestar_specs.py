import copy
import hashlib
import json
import sys
import unittest
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from toyota_polestar_specs_intake import SOURCES, SCOPES, extract_polestar, extract_toyota
from variant_refresh import RefreshError
from test_toyota_intake import fixture as toyota_config
from audit_image_rights import rights_errors
from collect_toyota_press_photo import SOURCE, ASSET, NOTICE

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/toyota_polestar_specs.json').read_text(encoding='utf-8'))


def payload(key, body):
    return {'body': body, 'source': {'final_url': SOURCES[key], 'content_hash': hashlib.sha256(body.encode()).hexdigest(),
        'status': 'reachable', 'http_status': 200, 'fetched_at': '2026-11-13T15:00:00Z'}}


def polestar(model):
    drafts = [r for r in FIXTURE['drafts'] if r['brand'] == 'Polestar' and r['model'] == model]
    headers = ''.join('<th>' + r['variant_name'] + '</th>' for r in drafts)
    rows = []
    for field, label in [('price', 'Pris från'), ('drivetrain','Drivlina'), ('tow_kg','Dragvikt' if model == '2' else 'Dragkraft'),
                         ('wltp_range_km','Räckvidd²' if model == '2' else 'Räckviddsmål (WLTP)²'),
                         ('wltp_consumption_kwh_100km','Energikonsumtion (WLTP)²')]:
        cells = []
        for r in drafts:
            quote = r['price_evidence']['quote'].split(' | ')[-1] if field == 'price' else r['field_evidence'][field]['quote']
            if model == '4' and field == 'wltp_range_km':
                quote = label + ' ' + str(r['facts'][field]) + ' km'
            cells.append('<td><label>' + label + '</label> ' + quote.removeprefix(label + ' ') + '</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    first = drafts[0]
    definitions = []
    for field in ('battery_kwh','dc_charge_kw','ac_charge_kw','boot_liters'):
        quote = first['field_evidence'][field]['quote']
        if model == '2':
            term = {'battery_kwh':'Batterikapacitet','dc_charge_kw':'DC-laddning',
                    'ac_charge_kw':'11 kW AC laddningstid (3-fas 16A AC)¹','boot_liters':'Volym (uppfällda säten)'}[field]
        else:
            term = {'battery_kwh':'Batteri','dc_charge_kw':'DC-laddning','ac_charge_kw':'AC-laddning','boot_liters':None}[field]
        definitions.append('<dl><dt>' + term + '</dt><dd>' + quote.removeprefix(term + ' ') + '</dd></dl>' if term else '<p>' + quote + '</p>')
    body = '<html><head><title>Polestar ' + model + (' coupé' if model == '4' else '') + '</title></head><body><table><tr>' + headers + '</tr>' + ''.join(rows) + '</table>' + ''.join(definitions) + '</body></html>'
    out = {'p' + model: payload('p' + model, body)}
    if model == '2':
        out['p2_model'] = payload('p2_model','<p>En fastback som är designad för körglädje och elektrisk prestanda.</p>')
        out['p2_seats'] = payload('p2_seats','<p>Polestar 2 har fem säten.</p>')
    else:
        out['p4_seats'] = payload('p4_seats','<p>Båda bilarna är rymliga, med gott om plats för fem personer och deras bagage</p><p>Polestar 4 är en SUV-coupé</p>')
        out['p4_wltp'] = payload('p4_wltp','<p>Detta är de certifierade värdena för bilens räckvidd och användning av elektrisk energi.</p><table><caption>Bakre motor</caption><tr><td>20-tumsdäck</td><td>620</td><td>17,8</td></tr><tr><td>21-tumsdäck</td><td>600</td><td>18,4</td></tr></table>')
    return out


def toyota(data=None):
    data = data or toyota_config()
    data['car']['id'] = data['carConfigMotorization']['motorization'][0]['carId'] = '552b7e03-84d2-4b36-a5bb-87d84cb7d05c'
    data['car']['motorization']['engine']['name'] = 'Elmotor 167 hk, batteri 57,7 kWh'
    data['car']['price'].update(cash=479900, exclVat=383920, promotions=[])
    data['specs']['standardEquipment'] = [{'name': 'Ombordladdare 11 kW AC och kapacitet för snabbladdning 150 kW DC'}]
    return data


def toyota_payloads(data):
    charge = '<p>Ombordladdare 11 kW AC och kapacitet för snabbladdning 150 kW DC</p>'
    return {'toyota': payload('toyota', '<div id="specs-data">' + escape(json.dumps(data)) + '</div>' + charge),
            'toyota_model': payload('toyota_model','<h2>En elegant SUV</h2><p>Den långa hjulbasen ger ett generöst benutrymme medan det stora bagageutrymmet erbjuder 452 liters lastkapacitet.</p>')}


class ToyotaPolestarSpecsTests(unittest.TestCase):
    def test_all_six_exact_profiles_and_price_types(self):
        rows = extract_toyota(toyota_payloads(toyota())) + extract_polestar(polestar('2'),'2') + extract_polestar(polestar('4'),'4')
        self.assertEqual(len(rows),6)
        self.assertTrue(all(len(r['facts']) == 9 and len(r['field_evidence']) == 9 for r in rows))
        self.assertTrue(all(r['price_evidence']['price_type'] == 'list_price' for r in rows))
        self.assertEqual(rows[4]['facts']['boot_liters'],526)
        self.assertEqual(rows[5]['facts']['tow_kg'],2000)
        self.assertEqual(rows[0]['facts']['tow_kg'],750)

    def test_exact_column_intervals_and_certified_rear_wheel_scope(self):
        rows = extract_polestar(polestar('4'),'4')
        self.assertEqual(rows[0]['field_evidence']['wltp_range_km']['scope'],'certified_rear_motor_20_inch')
        self.assertEqual(rows[1]['field_evidence']['wltp_range_km']['scope'],'manufacturer_wltp_target')
        self.assertEqual(rows[1]['field_evidence']['wltp_consumption_kwh_100km']['interval'],[19.0,21.7])
        self.assertTrue(all(r['facts']['ac_charge_kw'] == 11 for r in rows), '22 kW is optional, not standard')

    def test_layout_source_header_and_body_changes_fail_closed(self):
        for old,new in [('Rear motor</th>','Rear motor SUV</th>'), ('Pris från','Kampanjpris'),
                        ('AC-laddning 11 kW','AC-laddning 22 kW'), ('526 liters','530 liters')]:
            sources = polestar('4')
            body = sources['p4']['body']
            if old == 'AC-laddning 11 kW':
                old,new = '<dt>AC-laddning</dt><dd>11 kW','<dt>AC-laddning</dt><dd>22 kW'
            sources['p4'] = payload('p4',body.replace(old,new))
            with self.assertRaises(RefreshError, msg=old): extract_polestar(sources,'4')
        sources = polestar('2'); sources['p2']['source']['content_hash'] = '0' * 64
        with self.assertRaises(RefreshError): extract_polestar(sources,'2')

    def test_toyota_engine_promotion_equipment_and_certification(self):
        for mutate in [lambda d: d['car']['motorization']['engine'].__setitem__('name','Elmotor 343 hk, batteri 73,1 kWh'),
                       lambda d: d['car']['price'].__setitem__('promotions',['cash_discount']),
                       lambda d: d['specs'].__setitem__('standardEquipment',[]),
                       lambda d: d['carConfigMotorization']['motorization'][0]['specs'][0].__setitem__('certification',1)]:
            data = toyota(); mutate(data)
            with self.assertRaises((RefreshError,KeyError)): extract_toyota(toyota_payloads(data))

    def test_press_photo_permission_is_specific_to_current_model_and_editorial_use(self):
        evidence = dict(model_key='toyota|bz4x',asset_url='/media/vehicles/toyota-bz4x-press-abcdef123456.jpg',
            source_url=SOURCE,evidence_url=SOURCE,license_url=SOURCE,evidence_quote=NOTICE,license_id='Toyota-editorial',
            downloaded_from=ASSET,usage_scope='independent_vehicle_editorial',full_frame=True,
            prohibited_uses=['advertising','commercial_promotion','endorsement'],metadata_sha256='a'*64,source_content_sha256='b'*64,
            author='Toyota',credit='Toyota / Toyota Media',changes='Full frame, resized',reviewed_at='2026-11-13',status='documented')
        self.assertEqual(rights_errors(evidence,evidence),[])
        for patch in [dict(model_key='toyota|bz4x touring'),dict(full_frame=False),dict(usage_scope='advertising'),
                      dict(downloaded_from=ASSET.replace('2025/12','2022/06')),dict(evidence_quote='Free to download')]:
            invalid={**evidence,**patch}
            self.assertIn('license_requires_specific_review',rights_errors(invalid,invalid))


if __name__ == '__main__': unittest.main()
