import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_image_rights import build_report, rights_errors


class ImageRightsTests(unittest.TestCase):
    def setUp(self):
        self.asset = {'model_key': 'fixture|one', 'asset_url': 'https://manufacturer.invalid/exact.jpg'}
        self.proof = {**self.asset, 'source_url': 'https://manufacturer.invalid/press',
                      'evidence_url': 'https://manufacturer.invalid/license', 'evidence_quote': 'Synthetic license fixture',
                      'license_id': 'CC-BY-4.0', 'license_url': 'https://creativecommons.org/licenses/by/4.0/',
                      'author': 'Fixture author', 'credit': 'Fixture credit', 'changes': 'Unchanged',
                      'reviewed_at': '2026-10-25', 'status': 'documented'}
        self.today = date(2026, 10, 25)

    def test_manufacturer_origin_alone_is_not_permission(self):
        self.assertEqual(rights_errors(self.asset, None, self.today), ['permission_evidence_missing'])

    def test_exact_proof_passes_without_changing_the_asset(self):
        self.assertEqual(rights_errors(self.asset, self.proof, self.today), [])

    def test_mismatch_expiry_and_incomplete_credit_are_rejected(self):
        for patch in [{'asset_url': 'https://manufacturer.invalid/other.jpg'}, {'model_key': 'fixture|two'},
                      {'valid_until': '2026-10-24'}, {'reviewed_at': '2026-10-26'}, {'author': ''},
                      {'credit': ''}, {'changes': ''}, {'evidence_quote': ''}, {'status': 'candidate'},
                      {'license_url': 'https://other.invalid/terms'}, {'evidence_url': 'https://user:password@manufacturer.invalid/license'},
                      {'license_id': 'official_manufacturer_website'}]:
            with self.subTest(patch=patch):
                self.assertTrue(rights_errors(self.asset, {**self.proof, **patch}, self.today))

    def test_duplicate_proof_or_partial_coverage_cannot_pass(self):
        registry = {'schema_version': 1, 'assets': [self.proof]}
        self.assertTrue(build_report([self.asset], registry, self.today)['all_documented'])
        other = {'model_key': 'fixture|two', 'asset_url': 'https://manufacturer.invalid/two.jpg'}
        self.assertFalse(build_report([self.asset, other], registry, self.today)['all_documented'])
        with self.assertRaises(ValueError):
            build_report([self.asset], {**registry, 'assets': [self.proof, self.proof]}, self.today)
