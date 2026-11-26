import copy
import hashlib
import json
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_image_rights import POLESTAR_NOTICE, PRESS_PUBLISHERS, rights_errors, reviewed_press_permission, reviewed_media_permission
from adopt_press_photos import prepare
from audit_image_rights import ROOT, home_featured_report
from prepare_home_featured_photos import prepare as prepare_featured
from prepare_home_featured_web import prepare as prepare_publisher_web


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

    def test_g6_full_frame_presentation_matches_the_reviewed_media(self):
        source = Path(__file__).resolve().parents[1] / 'src'
        registry = lambda name: json.loads((source / name).read_text(encoding='utf-8'))
        key = 'xpeng|g6'
        asset = registry('model-images.json')[key]
        rights, = [row for row in registry('image-rights.json')['assets'] if row['model_key'] == key]
        style = registry('image-presentation.json')['models'][key]
        self.assertTrue(rights['full_frame'])
        self.assertEqual(style['asset_url'], asset)
        self.assertEqual(style['content_sha256'], rights['content_sha256'])
        self.assertEqual(style['content_sha256'], registry('image-variants.json')[asset]['source_sha256'])
        self.assertEqual((style['status'], style['object_fit']), ('approved', 'contain'))

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
        for publisher in ('mazda-se-mynewsdesk','renault-se-mynewsdesk','mercedes-se-mynewsdesk','ford-se-mynewsdesk','cupra-dk-mynewsdesk'):
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
            if publisher=='mercedes-se-mynewsdesk':
                for path in ('/se/other-manufacturer/images/mercedes-benz-cla-with-eq-technology-3210998',
                             '/se/mercedes-benz-sverige/images/cla-shooting-brake-123'):
                    other=policy['origin']+path
                    self.assertFalse(reviewed_media_permission({**proof,'source_url':other,'license_url':other,'evidence_url':other}))


class HomepagePhotoTests(unittest.TestCase):
    def setUp(self):
        self.registry=json.loads((ROOT/'src/home-featured-photos.json').read_text(encoding='utf-8'))
        self.manifest=ROOT/'data/review/home-featured-photo-source-candidates.json'
        self.sha=hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.web_manifest=ROOT/'data/review/home-featured-publisher-web-evidence.json'
        self.web_sha=hashlib.sha256(self.web_manifest.read_bytes()).hexdigest()

    def test_only_two_exact_originals_with_home_only_rights(self):
        self.assertTrue(home_featured_report()['all_documented'])
        self.assertEqual(len(home_featured_report()['checks']),2)
        displays=home_featured_report()['publisher_web']
        self.assertEqual(len(displays),2)
        self.assertEqual(sum(row['bytes'] for row in displays),347636)
        for row in self.registry['assets']:
            asset={'model_key':row['model_key'],'asset_url':row['asset_url'],'surface':'home_featured'}
            self.assertTrue(reviewed_media_permission(row))
            self.assertEqual(rights_errors(asset,row),[])
            self.assertIn('image_placement_scope_mismatch',rights_errors({**asset,'surface':'vehicle'},row))
            for patch in ({'placement':None},{'author':'Unverified photographer'},
                          {'full_frame':False},{'source_content_sha256':'a'*64},
                          {'downloaded_from':'https://mnd-assets.mynewsdesk.com/image/upload/fl_attachment/different'},
                          {'usage_scope':'advertising'},{'source_url':'https://www.mynewsdesk.com/se/ford/images/another-123'}):
                self.assertFalse(reviewed_media_permission({**row,**patch}),patch)

    def test_frozen_source_and_bytes_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            copy_manifest=folder/'source.json'
            shutil.copyfile(self.manifest,copy_manifest)
            for row in self.registry['assets']:
                shutil.copyfile(ROOT/'public'/row['asset_url'].lstrip('/'),folder/Path(row['asset_url']).name)
            self.assertEqual(len(prepare_featured(copy_manifest,self.sha)),2)
            with self.assertRaisesRegex(ValueError,'source_manifest_changed'):
                prepare_featured(copy_manifest,'0'*64)
            target=folder/Path(self.registry['assets'][0]['asset_url']).name
            target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'original_bytes_changed'):
                prepare_featured(copy_manifest,self.sha)

    def test_changed_manifest_or_credit_or_canonical_lookup_fails_audit(self):
        for mutation in ['credit','manifest','scope','original_lookup','web_bytes','web_manifest','web_sha','missing_display']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as d:
                folder=Path(d)
                (folder/'src').mkdir()
                (folder/'data/review').mkdir(parents=True)
                (folder/'public/media/vehicles').mkdir(parents=True)
                (folder/'public/media/responsive').mkdir(parents=True)
                manifest=folder/'data/review'/self.manifest.name
                shutil.copyfile(self.manifest,manifest)
                web=folder/'data/review'/self.web_manifest.name
                shutil.copyfile(self.web_manifest,web)
                lookup=json.loads((ROOT/'src/model-images.json').read_text(encoding='utf-8'))
                registry=copy.deepcopy(self.registry)
                for row in registry['assets']:
                    shutil.copyfile(ROOT/'public'/row['asset_url'].lstrip('/'),folder/'public'/row['asset_url'].lstrip('/'))
                    display=row['publisher_display']['url'].lstrip('/')
                    shutil.copyfile(ROOT/'public'/display,folder/'public'/display)
                if mutation=='credit': registry['assets'][0]['credit']='Changed'
                if mutation=='manifest': manifest.write_bytes(manifest.read_bytes()+b' ')
                if mutation=='scope': registry['assets'][0]['placement']='vehicle'
                if mutation=='original_lookup': lookup['bmw|i4']=registry['assets'][0]['asset_url']
                if mutation=='web_bytes': (folder/'public'/registry['assets'][0]['publisher_display']['url'].lstrip('/')).write_bytes(b'changed')
                if mutation=='web_manifest': web.write_bytes(web.read_bytes()+b' ')
                if mutation=='web_sha': registry['assets'][0]['publisher_display']['sha256']='b'*64
                if mutation=='missing_display': del registry['assets'][0]['publisher_display']
                (folder/'src/model-images.json').write_text(json.dumps(lookup),encoding='utf-8')
                (folder/'src/home-featured-photos.json').write_text(json.dumps(registry),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'home_featured_(exact_photo_scope|publisher_web)_mismatch'):
                    home_featured_report(folder)


    def test_publisher_web_prepare_only_exact_unchanged_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            manifest=folder/'web.json'
            shutil.copyfile(self.web_manifest,manifest)
            for row in self.registry['assets']:
                url=row['publisher_display']['url']
                shutil.copyfile(ROOT/'public'/url.lstrip('/'),folder/Path(url).name)
            prepared, files=prepare_publisher_web(manifest,self.web_sha)
            self.assertEqual(prepared,self.registry)
            self.assertEqual(len(files),2)
            with self.assertRaisesRegex(ValueError,'publisher_web_manifest_changed'):
                prepare_publisher_web(manifest,'0'*64)
            files[0][0].write_bytes(b'tamper')
            with self.assertRaisesRegex(ValueError,'home_featured_publisher_web_mismatch'):
                prepare_publisher_web(manifest,self.web_sha)

if __name__ == '__main__':
    unittest.main()
