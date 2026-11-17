"""Rebuild reference XML from validated snapshots, never from the live sitemap."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


class VerificationArtifactTests(unittest.TestCase):
    def test_unchanged_deployment_uses_latest_published_snapshot_not_checkout_xml(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scripts').mkdir()
            public = root / 'public'
            (public / 'data').mkdir(parents=True)
            for name in ('generate_sitemap.py', 'news_public.py', 'site_info.py'):
                shutil.copy2(ROOT / 'scripts' / name, root / 'scripts' / name)
            catalog = {'records': [{'brand': 'Synthetic', 'model': 'EV', 'variant_name': 'EV Base',
                                    'validation_status': 'published'}]}
            car_file = public / 'data/public_ev_variants.json'
            car_file.write_text(json.dumps(catalog), encoding='utf-8')
            old_car_bytes = car_file.read_bytes()
            news_file = public / 'data/news_articles.json'
            first = {'id': 'synthetic-one', 'slug': 'synthetic-one', 'published_at': '2026-11-16T00:00:00Z'}
            news_file.write_text(json.dumps({'records': [first]}), encoding='utf-8')
            def generate():
                result = subprocess.run([sys.executable, str(root / 'scripts/generate_sitemap.py')],
                                        cwd=root, capture_output=True, text=True, check=True)
                self.assertIn('Wrote', result.stdout)
                return (public / 'sitemap.xml').read_bytes()
            checkout_xml = generate()
            latest = {**first, 'id': 'synthetic-two', 'slug': 'synthetic-two',
                      'published_at': '2026-11-17T00:00:00Z'}
            news_file.write_text(json.dumps({'records': [latest, first]}), encoding='utf-8')
            expected_xml = generate()
            self.assertNotEqual(checkout_xml, expected_xml)
            self.assertEqual(generate(), expected_xml, 'No-change runs must remain deterministic')
            urls = [node.text for node in ElementTree.fromstring(expected_xml).iter()
                    if node.tag.endswith('}loc')]
            self.assertIn('https://elbilsagenten.se/nyheter/synthetic-two', urls)
            self.assertIn('https://elbilsagenten.se/nyheter/synthetic-one', urls)
            self.assertIn('https://elbilsagenten.se/bilar/synthetic-ev-base', urls)
            self.assertEqual(car_file.read_bytes(), old_car_bytes)


if __name__ == '__main__':
    unittest.main()
