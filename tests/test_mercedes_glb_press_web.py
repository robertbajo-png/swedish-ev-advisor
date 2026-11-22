import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mercedes_glb_press_web as subject


def encoded(image, kind):
    buffer = io.BytesIO()
    image.save(buffer, kind)
    return buffer.getvalue()


class GlbPublisherImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with Image.new('RGB', (5000, 3333), 'white') as full:
            draw = ImageDraw.Draw(full)
            draw.rectangle((0, 0, 949, 1221), fill='red')
            draw.rectangle((4220, 1881, 4999, 3332), fill='navy')
            cls.original = encoded(full, 'JPEG')
            cls.web = encoded(full.resize((746, 497)), 'WEBP')
            cls.cropped = encoded(full.crop((1000, 0, 4999, 3333)).resize((746, 497)), 'WEBP')

    def test_intact_frame_passes_and_crop_fails_at_the_same_size(self):
        policy = {'approved_source_sha256': subject.digest(self.original)}
        with patch.object(subject, 'POLICY', policy):
            result, = subject.check_frames(self.original, {'image': self.web}, {'image': 746})
            self.assertEqual(result['sha256'], subject.digest(self.web))
            with self.assertRaisesRegex(ValueError, 'no longer matches'):
                subject.check_frames(self.original, {'image': self.cropped}, {'image': 746})

    def test_same_geometry_without_the_reviewed_bytes_is_rejected(self):
        policy = {'approved_source_sha256': subject.digest(self.original), 'publisher_responsive_variants': [
            dict(source_url='image', width=746, height=497, sha256='0' * 64)]}
        with patch.object(subject, 'POLICY', policy):
            with self.assertRaisesRegex(ValueError, 'web bytes changed'):
                subject.check_frames(self.original, {'image': self.web}, {'image': 746})


if __name__ == '__main__':
    unittest.main()
