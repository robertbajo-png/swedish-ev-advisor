import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import porsche_macan_release_intake as release


def photo_fixture():
    path = urlsplit(release.GALLERY)
    link = f'{path.path}?{path.query}'
    return {
        'kit.html': (f'<ul data-title="{release.GALLERY_TITLE}" data-gallery-url="{link}"></ul>').encode(),
        'gallery.json': json.dumps([{'assetId': release.ASSET_ID, 'title': release.CAPTION,
                                     'highResDownloadLink': release.PHOTO, 'extension': 'JPG',
                                     'portrait': False}]).encode(),
        'terms.html': ('<p>Angabe der jeweils ausgewiesenen Quelle ' + release.EDITORIAL_ONLY + '</p>').encode(),
        'photo.jpg': b'private test image fixture',
    }


class MacanReleaseIntakeTests(unittest.TestCase):
    def test_photo_identity_does_not_grant_catalog_rights(self):
        bodies = photo_fixture()
        with patch.object(release, 'PHOTO_SHA', release.sha(bodies['photo.jpg'])):
            result = release.photo_identity(bodies)
        self.assertEqual(result['credit'], 'Porsche AG')
        self.assertFalse(result['catalog_use_confirmed'])

    def test_wrong_gallery_and_wrong_photo_are_not_substitutes(self):
        bodies = photo_fixture()
        with self.assertRaisesRegex(ValueError, 'macan_photo_bytes_changed'):
            release.photo_identity(bodies)
        bodies['kit.html'] = bodies['kit.html'].replace(b'Macan -', b'Macan 4S -')
        with self.assertRaisesRegex(ValueError, 'require_exact_base_macan_gallery'):
            release.photo_identity(bodies)

    def test_changed_caption_terms_or_unadvertised_media_url_rejected(self):
        for source, old, new, reason in (
            ('gallery.json', b'Macan,', b'Macan 4S,', 'macan_photo_identity_changed'),
            ('gallery.json', b'crop=0', b'crop=1', 'macan_photo_identity_changed'),
            ('terms.html', b'Werbung', b'private Arbeit', 'macan_media_terms_changed'),
        ):
            with self.subTest(source=source, old=old):
                bodies = photo_fixture()
                bodies[source] = bodies[source].replace(old, new)
                with self.assertRaisesRegex(ValueError, reason):
                    release.photo_identity(bodies)

    def test_duplicate_official_asset_is_held(self):
        bodies = photo_fixture()
        assets = json.loads(bodies['gallery.json'])
        bodies['gallery.json'] = json.dumps(assets * 2).encode()
        with self.assertRaisesRegex(ValueError, 'require_exact_base_macan_asset'):
            release.photo_identity(bodies)

    def test_private_intake_keeps_market_data_out_of_field_evidence(self):
        now = datetime(2026, 11, 23, tzinfo=timezone.utc)
        specs = {
            'facts': {'wltp_range_km': 642},
            'price_sek': 970000, 'price_type': 'manufacturer_from',
            'evidence': {'wltp_range_km': {'source': 'tech', 'snippet': '642 km'}},
            'price_evidence': {'source': 'comparison', 'snippet': '970 000 kr'},
            'sources': {
                'tech': {'source_url': 'https://configurator.porsche.com/sv-SE', 'content_hash': 'a' * 64,
                         'fetched_at': now.isoformat()},
                'comparison': {'source_url': 'https://compare.porsche.com/sv-SE', 'content_hash': 'b' * 64,
                               'fetched_at': now.isoformat()},
            },
            'qualifications': {'range': 'combined WLTP'},
        }
        market = {'row': {'registrations_last_month': 43}, 'sources': {'report.xlsx': {'fetched_at': now.isoformat()}}}
        photo = {'catalog_use_confirmed': False, 'sources': {'photo.jpg': {'fetched_at': now.isoformat()}}}
        report = release.intake(specs, market, photo, now)
        self.assertEqual(report['field_evidence']['price_sek']['source_hash'], 'b' * 64)
        self.assertEqual(report['market_discovery']['registrations_last_month'], 43)
        self.assertEqual(report['price_type'], 'manufacturer_from')
        self.assertIsNone(report['price_valid_until'])
        self.assertTrue(report['all_sources_within_15_minutes'])
        self.assertFalse(report['publication_approved'])
        self.assertFalse(release.intake(specs, market, photo, now + timedelta(minutes=16))
                         ['all_sources_within_15_minutes'])
        self.assertFalse(release.intake(specs, market, photo, now - timedelta(seconds=1))
                         ['all_sources_within_15_minutes'])


if __name__ == '__main__':
    unittest.main()
