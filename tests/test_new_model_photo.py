import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_image_rights import PRESS_PUBLISHERS, reviewed_media_permission
from register_new_model_photo import prepare


class NewModelPhotoTests(unittest.TestCase):
    def test_ev2_permission_is_exact_and_does_not_widen_existing_publishers(self):
        policy = PRESS_PUBLISHERS['kia-ev2-mynewsdesk']
        self.assertEqual(policy['model_keys'], ['kia|ev2'])
        self.assertEqual(policy['max_asset_bytes'], 24000000)
        source = policy['origin'] + policy['approved_image_paths'][0]
        proof = dict(model_key='kia|ev2', publisher_id='kia-ev2-mynewsdesk',
            source_url=source, evidence_url=source, license_url=source, license_id=policy['license_id'],
            evidence_quote=policy['permission_excerpt']+' | '+policy['condition_excerpt'],
            downloaded_from=policy['asset_origin']+'/image/upload/fl_attachment/fixture123',
            full_frame=True, source_content_sha256='b'*64, metadata_sha256='a'*64,
            usage_scope='independent_vehicle_editorial', prohibited_uses=['advertising','commercial_promotion','endorsement'])
        self.assertTrue(reviewed_media_permission(proof))
        for patch in [dict(model_key='kia|ev3'), dict(full_frame=False),
                      dict(source_url=source.replace('gtline', 'concept')),
                      dict(usage_scope='advertising')]:
            self.assertFalse(reviewed_media_permission({**proof, **patch}))
        self.assertNotIn('max_asset_bytes', PRESS_PUBLISHERS['kia-mynewsdesk'])

    def test_new_photo_preparation_never_replaces_a_public_model_or_image(self):
        real = Path(__file__).resolve().parents[1]
        evidence = next(r for r in json.loads((real/'src/image-rights.json').read_text(encoding='utf8'))['assets']
                        if r['model_key']=='kia|ev2')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'src').mkdir()
            (root/'public/data').mkdir(parents=True)
            (root/'src/image-rights.json').write_text('{"schema_version":1,"assets":[]}', encoding='utf8')
            (root/'src/model-images.json').write_text('{}', encoding='utf8')
            (root/'public/data/public_ev_variants.json').write_text('{"records":[]}', encoding='utf8')
            body = b'\xff\xd8\xffsynthetic-reviewed-image'
            digest = hashlib.sha256(body).hexdigest()
            name = 'kia-ev2-press-'+digest[:12]+'.jpg'
            (root/name).write_bytes(body)
            candidate = {**evidence, 'content_sha256':digest, 'review_filename':name,
                         'asset_url':evidence['downloaded_from'], 'original_url':evidence['downloaded_from']}
            path = root/'candidate.json'
            path.write_text(json.dumps(candidate), encoding='utf8')
            reviewed = hashlib.sha256(path.read_bytes()).hexdigest()
            _, proof, registry, lookup = prepare(path, reviewed, root)
            self.assertEqual(lookup['kia|ev2'], '/media/vehicles/'+name)
            self.assertEqual(proof['reviewed_candidate_sha256'], reviewed)
            self.assertEqual(json.loads((root/'src/model-images.json').read_text()), {})
            self.assertFalse((root/'public/media').exists())
            with self.assertRaisesRegex(ValueError, 'reviewed_candidate_changed'):
                prepare(path, '0'*64, root)
            (root/'public/data/public_ev_variants.json').write_text('{"records":[{"brand":"Kia","model":"Ev2"}]}')
            with self.assertRaisesRegex(ValueError, 'existing_public_model_requires_separate_refresh'):
                prepare(path, reviewed, root)
            (root/'public/data/public_ev_variants.json').write_text('{"records":[]}')
            (root/'src/image-rights.json').write_text(json.dumps(registry))
            with self.assertRaisesRegex(ValueError, 'existing_image_requires_separate_refresh'):
                prepare(path, reviewed, root)


if __name__ == '__main__':
    unittest.main()
