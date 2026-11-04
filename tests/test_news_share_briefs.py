from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_share_briefs import share_briefs


class ShareBriefTests(unittest.TestCase):
    def test_recent_public_only_at_most_three_no_external_side_effects(self):
        now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        row = {'title': 'Synthetic title', 'intro': 'Synthetic intro', 'published_at': '2026-11-03T00:00:00Z'}
        rows = [{**row, 'slug': f'synthetic-{n}'} for n in range(5)]
        rows += [{**row, 'slug': 'private-draft', 'status': 'quarantined'},
                 {**row, 'slug': 'old-news', 'published_at': '2026-10-20T00:00:00Z'}]
        result = share_briefs(rows, now=now)
        self.assertEqual(len(result['briefs']), 3)
        self.assertTrue(all(b['url'].startswith('https://elbilsagenten.se/nyheter/synthetic-') for b in result['briefs']))
        self.assertEqual((result['external_posts'], result['paid_calls']), (0, 0))

    def test_no_fresh_article_means_no_invented_post(self):
        self.assertEqual(share_briefs([], now=datetime(2026, 11, 4, tzinfo=timezone.utc))['briefs'], [])


if __name__ == '__main__':
    unittest.main()
