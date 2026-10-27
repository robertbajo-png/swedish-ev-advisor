import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_licensed_images import prepare
from audit_image_rights import build_report
from discover_licensed_images import canonical_license, image_url, plain


class LicensedImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'review').mkdir()
        self.content = b'\xff\xd8\xffsynthetic-jpeg-fixture'
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.name = 'fixture-one-' + self.digest[:12] + '.jpg'
        (self.root / 'review' / self.name).write_bytes(self.content)
        self.row = dict(model_key='fixture|one', title='File:Fixture.jpg', revision=123,
            source_url='https://commons.wikimedia.org/wiki/File:Fixture.jpg',
            evidence_url='https://commons.wikimedia.org/w/index.php?title=File:Fixture.jpg&oldid=123',
            license_id='CC-BY-SA-4.0', license_url='https://creativecommons.org/licenses/by-sa/4.0/',
            license_eligible=True, restrictions='', license_statement='Synthetic license fixture',
            author='Fixture author', review_filename=self.name, content_sha256=self.digest,
            original_url='https://upload.wikimedia.org/fixture.jpg',
            asset_url='https://thumb.wikimedia.org/fixture.jpg')
        self.catalog = self.root / 'catalog.json'
        self.catalog.write_text(json.dumps({'records': [{'brand': 'Fixture', 'model': 'One'}]}))

    def run_prepare(self, rows=None, digest=None):
        path = self.root / 'manifest.json'
        path.write_text(json.dumps({'models': rows or [self.row]}))
        return prepare(path, digest or hashlib.sha256(path.read_bytes()).hexdigest(), self.catalog, date(2026, 10, 27))

    def test_review_is_exact_and_preparation_does_not_publish(self):
        registry, lookup, files = self.run_prepare()
        self.assertEqual(lookup['fixture|one'], '/media/vehicles/' + self.name)
        self.assertEqual(len(files), 1)
        self.assertEqual(registry['assets'][0]['status'], 'documented')
        self.assertFalse((self.root / 'public').exists())

    def test_changed_or_partial_review_is_rejected(self):
        for patch in [{'model_key': 'other|car'}, {'license_eligible': False}, {'restrictions': 'Permission required'},
                      {'review_filename': '../other.jpg'}, {'author': ''}, {'evidence_url': 'https://other.invalid/license'},
                      {'license_url': 'https://creativecommons.org.evil.invalid/licenses/by-sa/4.0/'}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.run_prepare([{**self.row, **patch}])
        with self.assertRaises(ValueError):
            self.run_prepare([self.row, copy.deepcopy(self.row)])
        with self.assertRaises(ValueError):
            self.run_prepare(digest='0' * 64)
        (self.root / 'review' / self.name).write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.run_prepare()

    def test_local_asset_hash_and_path_are_verified(self):
        registry, _, _ = self.run_prepare()
        asset = {key: registry['assets'][0][key] for key in ('model_key', 'asset_url')}
        destination = self.root / 'public/media/vehicles'
        destination.mkdir(parents=True)
        (destination / self.name).write_bytes(self.content)
        self.assertTrue(build_report([asset], registry, date(2026, 10, 27), self.root)['all_documented'])
        (destination / self.name).write_bytes(b'corrupted')
        self.assertIn('local_image_hash_mismatch', build_report([asset], registry, date(2026, 10, 27), self.root)['checks'][0]['errors'])
        unsafe = {**asset, 'asset_url': '/../secret.jpg'}
        self.assertFalse(build_report([unsafe], registry, date(2026, 10, 27), self.root)['all_documented'])

    def test_license_and_download_hosts_cannot_be_guessed(self):
        expected = 'https://creativecommons.org/licenses/by-sa/4.0/'
        self.assertEqual(canonical_license('CC-BY-SA-4.0', expected + 'deed.en/'), expected)
        self.assertIsNone(canonical_license('CC-BY-SA-4.0', 'https://evil.invalid/terms'))
        self.assertEqual(plain('<b>Photo</b> by <a href="/wiki/User">Author</a>'), 'Photo by Author')
        for url in ['http://upload.wikimedia.org/a.jpg', 'https://evil.invalid/a.jpg', 'https://user:pass@upload.wikimedia.org/a.jpg']:
            with self.assertRaises(ValueError):
                image_url(url)


if __name__ == '__main__':
    unittest.main()
