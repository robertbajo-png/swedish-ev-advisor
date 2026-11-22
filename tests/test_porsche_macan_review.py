import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import porsche_macan_review as macan


def pair(label, value):
    return f'<div><p>{label}</p><p>{value}</p></div>'


def documents():
    addons = [
        {'name': 'Ombordladdare 22 kW', 'price': '17900', 'priceCurrency': 'SEK'},
        {'name': 'Dragkrok, inf\u00e4llbar', 'price': '13700', 'priceCurrency': 'SEK'},
    ]
    specs = ''.join(pair(label, value) for label, value, _ in macan.TECHNICAL.values())
    equipment = ''.join(f'<h4>{t}</h4>' for entries in macan.EQUIPMENT.values() for t in entries)
    content = {
        'base': pair('Grundpris', '970 000 kr') + pair('Totalpris *', '970 000 kr'),
        'technical': specs * 2 + pair('Max. dragvikt (obromsad)', '750 kg'),
        'equipment': '<icc-p-accordion>' + equipment + '</icc-p-accordion>',
    }
    bodies = {}
    for key, html in content.items():
        url = macan.SOURCES[key]
        product = {'@type': ['Product', 'Car'], 'url': url, 'name': 'Macan', 'model': 'Macan', 'modelDate': '2027',
                   'brand': {'name': 'Porsche'},
                   'offers': {'price': '970000', 'priceCurrency': 'SEK', 'addOn': addons}}
        graph = json.dumps({'@graph': [product]})
        bodies[key] = (f'<link rel="canonical" href="{url.split("?")[0]}">'
                       f'<script type="application/ld+json">{graph}</script>{html}').encode('utf8')
    bodies['comparison'] = (f'<link rel="canonical" href="{macan.SOURCES["comparison"]}">'
                            '<section><h4>Macan</h4><p>El2027 Fr\u00e5n 970 000 kr 642 km Bakhjulsdrift 0 - 0 g/km</p></section>'
                            '<section><h4>Macan 4</h4><p>El2027 Fyrhjulsdrift</p></section>').encode('utf8')
    return bodies


class MacanReviewTests(unittest.TestCase):
    def test_exact_pass_does_not_authorize_publication(self):
        r = macan.review(documents())
        self.assertEqual(r['facts'], dict(wltp_range_km=642, wltp_consumption_kwh_100km=16.7, battery_kwh=100,
                                        dc_charge_kw=270, boot_liters=518, tow_kg=2000,
                                        ac_charge_kw=11, seats=5, drivetrain='RWD'))
        self.assertEqual(r['price_sek'], 970000)
        self.assertEqual(r['price_type'], 'manufacturer_from')
        self.assertFalse(r['publication_approved'])

    def test_rejects_different_code_year_and_non_swedish_page(self):
        for before, after in ((b'XABAA1', b'XABAB1'), (b'"2027"', b'"2026"'), (b'sv-SE', b'de-DE')):
            with self.subTest(change=after):
                b = documents()
                b['technical'] = b['technical'].replace(before, after)
                with self.assertRaisesRegex(ValueError, 'wrong_swedish_macan_model_or_year'):
                    macan.review(b)

    def test_series_range_and_one_conflicting_duplicate_fail(self):
        for before, after in (('642 km', '548 - 642 km'), ('642 km', '611 km')):
            b = documents()
            b['technical'] = b['technical'].replace(before.encode(), after.encode(), 1)
            with self.assertRaisesRegex(ValueError, 'macan_technical_value_changed:wltp_range_km'):
                macan.review(b)

    def test_equipment_must_confirm_both_seat_rows_and_standard_charger(self):
        for field, before, after in (
            ('seats', 'Baks\u00e4te 3-sits (2+1)', 'Baks\u00e4te 2-sits'),
            ('ac_charge_kw', 'Ombordladdare 11 kW', 'Ombordladdare 22 kW'),
        ):
            b = documents()
            b['equipment'] = b['equipment'].replace(before.encode(), after.encode())
            with self.assertRaisesRegex(ValueError, 'macan_standard_equipment_changed:' + field):
                macan.review(b)

    def test_add_on_cannot_be_presented_as_standard(self):
        b = documents()
        b['equipment'] = b['equipment'].replace(b'</icc-p-accordion>',
                                               b'<h4>Ombordladdare 22 kW</h4></icc-p-accordion>')
        with self.assertRaisesRegex(ValueError, 'macan_optional_equipment_scope_changed'):
            macan.review(b)

    def test_conflicting_rear_seat_configurations_are_rejected(self):
        b = documents()
        b['equipment'] = b['equipment'].replace(b'</icc-p-accordion>',
                                               '<h4>Baks\u00e4te 2-sits</h4></icc-p-accordion>'.encode())
        with self.assertRaisesRegex(ValueError, 'macan_standard_seats_ambiguous'):
            macan.review(b)

    def test_mismatched_price_or_equipment_total_fails(self):
        for key in ('base', 'comparison'):
            b = documents()
            b[key] = b[key].replace(b'970 000 kr', b'990 000 kr')
            with self.assertRaisesRegex(ValueError, 'price'):
                macan.review(b)

    def test_replay_rejects_tampered_bytes_and_report(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(macan, 'PRIVATE', Path(tmp).resolve()):
            folder = macan.PRIVATE / 'porsche-macan-my27-fixture'
            folder.mkdir()
            bodies = documents()
            r = macan.review(bodies)
            r['sources'] = {key: {'source_url': url, 'http_status': 200, 'content_hash': macan.sha(bodies[key])}
                            for key, url in macan.SOURCES.items()}
            for key, body in bodies.items():
                (folder / (key + '.html')).write_bytes(body)
            (folder / 'report.json').write_text(json.dumps(r), encoding='utf8')
            self.assertEqual(macan.replay(folder), r)
            r['publication_approved'] = True
            (folder / 'report.json').write_text(json.dumps(r), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'macan_replay_changed'):
                macan.replay(folder)
            (folder / 'base.html').write_bytes(bodies['base'] + b' ')
            with self.assertRaisesRegex(ValueError, 'macan_evidence_changed:base'):
                macan.replay(folder)
