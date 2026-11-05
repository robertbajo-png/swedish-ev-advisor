import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_engine import BROAD_SOURCES, registry


class BroadSourceTests(unittest.TestCase):
    def test_broad_discovery_includes_international_and_official_sources(self):
        with patch.dict(os.environ, {'NEWS_SOURCE_PROFILE': 'broad'}):
            active = {s['id']: s for s in registry() if s.get('enabled')}
        self.assertEqual(set(active), BROAD_SOURCES)
        self.assertEqual(len(active), 18)
        for key in ('electrive', 'insideevs', 'cnevpost', 'carnewschina', 'electrek', 'autocar'):
            self.assertEqual(active[key]['kind'], 'publisher')
            self.assertTrue(active[key]['feeds'])
        for key in ('vw-press', 'vw-sweden-press', 'bmw-press', 'acea', 'mobility-sweden', 'polestar-news'):
            self.assertEqual(active[key]['kind'], 'primary')
            self.assertEqual(active[key]['collection_method'], 'pressroom_index')
        self.assertEqual(active['polestar-news']['body_region'], 'main')
        self.assertTrue(active['polestar-news']['primary_date_required'])

    def test_disabled_or_unimplemented_adapters_are_not_silently_enabled(self):
        with patch.dict(os.environ, {'NEWS_SOURCE_PROFILE': 'broad'}):
            inactive = {s['id'] for s in registry() if not s.get('enabled')}
        self.assertTrue({'volvo-press', 'iea', 'naf', 'motor1', 'automobile-propre'} <= inactive)

    def test_new_free_feeds_preserve_identity_and_superseded_history(self):
        with patch.dict(os.environ, {'NEWS_SOURCE_PROFILE': 'broad'}):
            sources = {s['id']: s for s in registry()}
        self.assertTrue(sources['bevolt']['enabled'])
        self.assertTrue(sources['motor-no']['enabled'])
        self.assertEqual(sources['automobile-propre']['superseded_by'], 'bevolt')
        self.assertEqual(sources['bevolt']['publisher_group'], sources['automobile-propre']['publisher_group'])
        self.assertEqual(sources['motor-no']['publisher_group'], sources['naf']['publisher_group'])
        self.assertTrue(sources['motor-no']['feeds'][0].endswith('?lab_viewport=rss'))

    def test_editorial_short_recipe_and_access_controls_are_unchanged(self):
        from news_short_articles import SOURCES
        self.assertEqual(set(SOURCES), {'vw-sweden-press', 'firefly-china-press'})
        from news_http import reserved
        self.assertTrue(reserved({'Content-Signal': 'ai-input=no'}))
        self.assertTrue(reserved({'TDM-Reservation': '1'}))


if __name__ == '__main__':
    unittest.main()
