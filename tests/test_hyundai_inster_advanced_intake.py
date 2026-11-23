import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_hyundai_inster_advanced as intake


class AdvancedIntakeTests(unittest.TestCase):
    config = (
        '<title>INSTER &middot; 49kWh Advanced MY27 | Hyundai Sverige</title>'
        '<meta property="og:title" content="INSTER &middot; 49kWh Advanced MY27">'
        f'<li>{intake.SLIDING}</li><span>{intake.MATERIAL}</span>'
    )
    registry = json.dumps({'omManual': {
        'webhelpDocId': 'D202607010201', 'webhelpManual': intake.MANUAL + 'index.html',
        'webhelpToc': intake.MANUAL + 'toc.html',
        'webhelpPubdate': {'firstdate': '20260701', 'lastdate': '20261029'},
    }}).encode()
    tow = (
        '<html lang="sv-SE"><title>Bogsering av sl&auml;p</title>'
        '<h2>Bogsering av sl&auml;p</h2>'
        f'<p>{intake.NO_TRAILER}</p><p>{intake.BIKE_CARRIER}</p></html>'
    )

    def test_cargo_for_exact_sliding_seat_variant_has_two_positions(self):
        design = f'<p>{intake.CARGO}.</p>'.encode()
        self.assertEqual(intake.verify_cargo(design, self.config.encode()), {
            'boot_liters': 238, 'sliding_seats_up_max_liters': 351, 'minimum_is_seats_farthest_rearward': True,
        })

    def test_different_material_fixed_seat_and_empty_table_are_rejected(self):
        design = f'<p>{intake.CARGO}.</p>'.encode()
        for original, changed in ((intake.MATERIAL, '6XS5ZDZ7ZHH01P'), (intake.SLIDING, 'Fast baksate')):
            with self.subTest(original=original), self.assertRaises(ValueError):
                intake.verify_cargo(design, self.config.replace(original, changed).encode())
        with self.assertRaises(ValueError):
            intake.verify_cargo(b'<p>351 liter</p>', self.config.encode())

    def test_towing_requires_explicit_prohibition_not_the_bike_carrier_rating(self):
        proof = intake.verify_towing(self.registry, self.tow.encode())
        self.assertEqual((proof['value'], proof['source_url']), (0, intake.TOW))
        self.assertNotIn('75 kg', proof['quote'])
        with self.assertRaisesRegex(ValueError, 'explicit_prohibition_missing'):
            intake.verify_towing(self.registry, self.tow.replace(intake.NO_TRAILER, '').encode())
        with self.assertRaisesRegex(ValueError, 'manual_changed'):
            intake.verify_towing(self.registry.replace(b'20261029', b'20251029'), self.tow.encode())
