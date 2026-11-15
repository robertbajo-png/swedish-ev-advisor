import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_image_rights import PRESS_PUBLISHERS, reviewed_media_permission, reviewed_toyota_permission
from register_new_model_photo import prepare


class NewModelPhotoTests(unittest.TestCase):
    def test_toyota_plus_permission_is_not_a_hybrid_bz4x_or_arbitrary_photo(self):
        real=Path(__file__).resolve().parents[1]
        proof=next(r for r in json.loads((real/'src/image-rights.json').read_text(encoding='utf8'))['assets'] if r['model_key']=='toyota|c hr')
        self.assertTrue(reviewed_toyota_permission(proof))
        for patch in [dict(model_key='toyota|bz4x'),dict(source_url=proof['source_url'].replace('c-hr-design','c-hr-hybrid')),
            dict(downloaded_from=proof['downloaded_from'].replace('_014-','_010-')),dict(full_frame=False),dict(usage_scope='advertising')]:
            self.assertFalse(reviewed_toyota_permission({**proof,**patch}))

    def test_public_plus_model_is_blocked_even_when_image_key_is_normalized(self):
        real=Path(__file__).resolve().parents[1]
        proof=next(r for r in json.loads((real/'src/image-rights.json').read_text(encoding='utf8'))['assets'] if r['model_key']=='toyota|c hr')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'src').mkdir();(root/'public/data').mkdir(parents=True)
            (root/'src/image-rights.json').write_text('{"schema_version":1,"assets":[]}')
            (root/'src/model-images.json').write_text('{}')
            (root/'public/data/public_ev_variants.json').write_text('{"records":[{"brand":"Toyota","model":"C-Hr+"}]}')
            body=b'\xff\xd8\xffsynthetic-plus-model-photo';digest=hashlib.sha256(body).hexdigest()
            name='toyota-c-hr-press-'+digest[:12]+'.jpg';(root/name).write_bytes(body)
            candidate={**proof,'content_sha256':digest,'review_filename':name,'asset_url':proof['downloaded_from']}
            path=root/'candidate.json';path.write_text(json.dumps(candidate))
            with self.assertRaisesRegex(ValueError,'existing_public_model_requires_separate_refresh'):
                prepare(path,hashlib.sha256(path.read_bytes()).hexdigest(),root)

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
