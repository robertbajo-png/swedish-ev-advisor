import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from polestar_3_press_web import DIMENSIONS, PAGE, POLICY, SIZES, verify_press_link
from prepare_responsive_images import published_variants


class Polestar3PressWebTest(unittest.TestCase):
    def source_pages(self):
        license_text = ' '.join(POLICY[key] for key in ('license_label', 'permission_excerpt', 'condition_excerpt'))
        srcset = ', '.join(f'{row["source_url"]} {row["width"]}w' for row in SIZES)
        title = 'Polestar-250527-1251_v004.jpg'
        return (
            f'<h1>Polestar 3 med 800 volt</h1><a href="{PAGE}">asset</a>'.encode(),
            (f'<h1>{title}</h1><p>{license_text}</p>'
             f'<a href="{POLICY["approved_asset_url"]}">Download</a>'
             f'<img class="panel__media-image" src="{SIZES[0]["source_url"]}" srcset="{srcset}" '
             f'width="{DIMENSIONS[0]}" height="{DIMENSIONS[1]}">').encode()
        )

    def test_exact_publisher_web_options_match_the_800_v_launch(self):
        verify_press_link(*self.source_pages())

    def test_holds_changed_rights_asset_link_dimensions_and_credit(self):
        release, page = self.source_pages()
        for other in (
            page.replace(POLICY['condition_excerpt'].encode(), b'changed term'),
            page.replace(b'746w', b'745w'),
            page.replace(b'12302', b'12301'),
            page.replace(POLICY['approved_asset_url'].encode(), b'https://other.invalid/photo.jpg'),
            page + b'<dl><dt>Fotograf:</dt><dd>Newly supplied name</dd></dl>',
        ):
            with self.subTest(other=other[-130:]):
                with self.assertRaises(ValueError):
                    verify_press_link(release, other)
        with self.assertRaises(ValueError):
            verify_press_link(release.replace(b'800 volt', b'400 volt'), page)

    def test_build_accepts_exact_native_bytes_and_refuses_missing_or_changed_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            buffer = io.BytesIO()
            Image.new('RGB', (8, 6), (60, 45, 110)).save(buffer, 'WEBP')
            raw = buffer.getvalue()
            expected = hashlib.sha256(raw).hexdigest()
            policy = {**POLICY, 'publisher_responsive_variants': [{'width':8, 'height':6, 'sha256':expected}]}
            asset = {'asset_url':'/media/vehicles/polestar-3-fixture.jpg', 'model_key':'polestar|3',
                     'downloaded_from':policy['approved_asset_url'], 'content_sha256':policy['approved_source_sha256']}
            file = root / 'public/media/responsive/polestar-3-fixture-8.webp'
            file.parent.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'unchanged publisher image'):
                published_variants(root, asset, policy)
            file.write_bytes(raw)
            self.assertEqual(published_variants(root, asset, policy),
                             [{'url':'/media/responsive/polestar-3-fixture-8.webp', 'width':8, 'sha256':expected}])
            self.assertEqual(file.read_bytes(), raw)
            with self.assertRaisesRegex(ValueError, 'exact reviewed press original'):
                published_variants(root, {**asset, 'model_key':'polestar|4'}, policy)
            file.write_bytes(raw + b' ')
            with self.assertRaisesRegex(ValueError, 'hash changed'):
                published_variants(root, asset, policy)
