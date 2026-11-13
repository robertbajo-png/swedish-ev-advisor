import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_image_rights import POLESTAR_NOTICE, PRESS_PUBLISHERS, rights_errors, reviewed_press_permission, reviewed_media_permission
from adopt_press_photos import prepare


class PressImageTests(unittest.TestCase):
    def setUp(self):
        self.evidence = dict(model_key='polestar|4', asset_url='/media/vehicles/polestar-4-press-abcdef123456.jpg',
            source_url='https://media.polestar.com/gallery/images/123',
            evidence_url='https://media.polestar.com/copyright', evidence_quote=POLESTAR_NOTICE,
            license_id='Polestar-editorial', license_url='https://media.polestar.com/copyright',
            author='Polestar', credit='Polestar / Polestar Press', changes='Manufacturer web copy; displayed at smaller size.',
            reviewed_at='2026-11-12', status='documented',
            downloaded_from='https://media.polestar.com/assets/images/small/123-model.jpg',
            usage_scope='independent_vehicle_editorial',
            prohibited_uses=['advertising', 'commercial_promotion', 'endorsement'], metadata_sha256='a' * 64)

    def test_exact_press_asset_is_not_relabelled_as_creative_commons(self):
        self.assertTrue(reviewed_press_permission(self.evidence))
        self.assertEqual(rights_errors(self.evidence, self.evidence), [])
        self.assertEqual(self.evidence['license_id'], 'Polestar-editorial')

    def test_other_models_domains_and_uses_are_not_implicitly_approved(self):
        for patch in [dict(model_key='kia|ev3'), dict(source_url='https://media.polestar.com.evil.invalid/gallery/images/123'),
                      dict(downloaded_from='https://media.polestar.com/assets/images/small/124-other.jpg'),
                      dict(usage_scope='advertising'), dict(prohibited_uses=[]), dict(metadata_sha256=''),
                      dict(evidence_quote='Downloadable means free'), dict(evidence_url='https://other.invalid/license')]:
            value = {**self.evidence, **patch}
            self.assertFalse(reviewed_press_permission(value), patch)
            self.assertIn('license_requires_specific_review', rights_errors(value, value))

    def test_an_old_review_cannot_approve_another_model_asset(self):
        other = copy.deepcopy(self.evidence)
        other['asset_url'] = '/media/vehicles/other-abcdef123456.jpg'
        self.assertIn('exact_asset_or_model_mismatch', rights_errors(other, self.evidence))

    def test_registered_manufacturer_media_permission_preserves_the_entire_frame(self):
        policy = PRESS_PUBLISHERS['kia-mynewsdesk']
        source = policy['origin'] + '/images/kia-ev3-clean-123'
        evidence = {**self.evidence, 'model_key': 'kia|ev3', 'license_id': policy['license_id'],
            'publisher_id': 'kia-mynewsdesk', 'source_url': source, 'license_url': source, 'evidence_url': source,
            'evidence_quote': policy['permission_excerpt'] + ' | ' + policy['condition_excerpt'],
            'downloaded_from': policy['asset_origin'] + '/image/upload/fl_attachment/fixture123',
            'full_frame': True, 'source_content_sha256': 'b' * 64}
        self.assertTrue(reviewed_media_permission(evidence))
        self.assertEqual(rights_errors(evidence, evidence), [])
        for patch in [dict(full_frame=False), dict(publisher_id='unapproved'), dict(model_key='tesla|model 3'),
                      dict(source_url='https://other.mynewsdesk.com/images/kia-ev3-clean-123'),
                      dict(downloaded_from='https://mnd-assets.mynewsdesk.com.evil.invalid/image/upload/fl_attachment/fixture123'),
                      dict(source_content_sha256=''), dict(evidence_quote='Can download'), dict(usage_scope='advertising')]:
            changed = {**evidence, **patch}
            self.assertFalse(reviewed_media_permission(changed), patch)
            self.assertIn('license_requires_specific_review', rights_errors(changed, changed))

    def test_danish_skoda_permission_does_not_allow_coupe_as_suv(self):
        policy = PRESS_PUBLISHERS['skoda-dk-mynewsdesk']
        source = policy['origin'] + '/images/new-skoda-enyaq-photo-123'
        evidence = {**self.evidence, 'model_key': 'skoda|enyaq', 'license_id': policy['license_id'],
            'publisher_id': 'skoda-dk-mynewsdesk', 'source_url': source, 'license_url': source, 'evidence_url': source,
            'evidence_quote': policy['permission_excerpt'] + ' | ' + policy['condition_excerpt'],
            'downloaded_from': policy['asset_origin'] + '/image/upload/fl_attachment/fixture123',
            'full_frame': True, 'source_content_sha256': 'b' * 64}
        self.assertTrue(reviewed_media_permission(evidence))
        for model, page in [('skoda|enyaq', source.replace('enyaq-', 'enyaq-coupe-')),
                            ('skoda|epiq', source), ('kia|ev3', source)]:
            changed = {**evidence, 'model_key': model, 'source_url': page, 'evidence_url': page, 'license_url': page}
            self.assertFalse(reviewed_media_permission(changed))

    def test_adoption_binds_the_reviewed_file_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'src').mkdir()
            (root / 'public/data').mkdir(parents=True)
            (root / 'public/data/public_ev_variants.json').write_text(json.dumps({'records': [{'brand': 'Polestar', 'model': '4'}]}))
            original_registry = {'schema_version': 1, 'assets': [{'model_key': 'polestar|4', 'asset_url': '/media/vehicles/old.jpg'}]}
            (root / 'src/image-rights.json').write_text(json.dumps(original_registry))
            (root / 'src/model-images.json').write_text(json.dumps({'polestar|4': '/media/vehicles/old.jpg'}))
            content = b'\xff\xd8\xffsynthetic-photo-fixture'
            digest = hashlib.sha256(content).hexdigest()
            filename = 'polestar-4-press-' + digest[:12] + '.jpg'
            (root / filename).write_bytes(content)
            candidate = {**self.evidence, 'review_filename': filename, 'content_sha256': digest,
                'asset_url': self.evidence['downloaded_from'], 'original_url': self.evidence['downloaded_from']}
            path = root / 'candidate.json'
            path.write_text(json.dumps(candidate))
            reviewed_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            registry, lookup, file, evidence = prepare(path, reviewed_hash, root)
            self.assertEqual(lookup['polestar|4'], '/media/vehicles/' + filename)
            self.assertEqual(evidence['reviewed_candidate_sha256'], reviewed_hash)
            self.assertEqual(json.loads((root / 'src/image-rights.json').read_text()), original_registry)
            self.assertFalse((root / 'public/media').exists())
            with self.assertRaisesRegex(ValueError, 'reviewed_candidate_changed'):
                prepare(path, '0' * 64, root)
            file.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'reviewed_photo_changed'):
                prepare(path, reviewed_hash, root)


    def test_mazda_renault_only_the_reviewed_exterior_pages(self):
        for publisher in ('mazda-se-mynewsdesk','renault-se-mynewsdesk'):
            policy=PRESS_PUBLISHERS[publisher]
            source=policy['origin']+policy['approved_image_paths'][0]
            proof={**self.evidence,'model_key':policy['model_keys'][0],'publisher_id':publisher,
                'license_id':policy['license_id'],'source_url':source,'license_url':source,'evidence_url':source,
                'evidence_quote':policy['permission_excerpt']+' | '+policy['condition_excerpt'],
                'downloaded_from':policy['asset_origin']+'/image/upload/fl_attachment/fixture123',
                'full_frame':True,'source_content_sha256':'b'*64}
            self.assertTrue(reviewed_media_permission(proof))
            for path in ('/images/other-model-123','/images/interior-only-456'):
                other=policy['origin']+path
                self.assertFalse(reviewed_media_permission({**proof,'source_url':other,'license_url':other,'evidence_url':other}))


if __name__ == '__main__':
    unittest.main()
