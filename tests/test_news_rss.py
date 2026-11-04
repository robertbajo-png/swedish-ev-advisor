"""Synthetic published-feed fixtures, never live editorial approvals."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_rss import render_feed

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)


def article(**kwargs):
    return {'slug': 'synthetic-news', 'title': 'Synthetic <EV> & battery',
            'intro': 'Synthetic intro with no private evidence.', 'published_at': '2026-11-03T12:00:00Z', **kwargs}


class NewsRssTests(unittest.TestCase):
    def test_only_valid_published_past_articles_and_no_private_fields(self):
        rows = [article(writer_packet={'secret': 'PRIVATE'}), article(status='quarantined'),
                article(status='draft'), article(published_at=None), article(published_at='invalid'),
                article(published_at='2026-11-05T12:00:00Z'), article(published_at='2026-11-03'),
                article(slug='../private'), article(title=''), None]
        feed = render_feed(rows, now=NOW)
        root = ET.fromstring(feed)
        self.assertEqual(len(root.findall('channel/item')), 1)
        self.assertNotIn('PRIVATE', feed)
        self.assertEqual(root.findtext('channel/item/title'), rows[0]['title'])
        self.assertEqual(root.findtext('channel/item/link'), 'https://elbilsagenten.se/nyheter/synthetic-news/')

    def test_deterministic_order_unique_guids_dates_and_self_link(self):
        rows = [article(), article(slug='newer', published_at='2026-11-04T10:00:00+02:00'), article()]
        feed = render_feed(rows, now=NOW)
        self.assertEqual(feed, render_feed(list(reversed(rows)), now=NOW))
        root = ET.fromstring(feed)
        self.assertTrue(root.findtext('channel/item/guid').endswith('/newer/'))
        self.assertEqual(len(root.findall('channel/item')), 2)
        self.assertEqual(root.findtext('channel/item/pubDate'), 'Wed, 04 Nov 2026 08:00:00 GMT')
        self.assertEqual(root.find('channel/{http://www.w3.org/2005/Atom}link').get('type'), 'application/rss+xml')

    def test_fifty_item_bound_and_empty_feed(self):
        self.assertEqual(len(ET.fromstring(render_feed([article(slug=f'synthetic-{i}') for i in range(65)], now=NOW)).findall('channel/item')), 50)
        self.assertEqual(ET.fromstring(render_feed([], now=NOW)).findall('channel/item'), [])

    def test_invalid_site_cannot_redirect_subscribers(self):
        for site in ['http://example.com', 'https://user:password@example.com', 'https://example.com/path', 'https://example.com?token=x']:
            with self.assertRaises(ValueError):
                render_feed([], site, NOW)

    def test_intro_is_plain_text_in_html_capable_readers_and_bad_xml_is_held(self):
        root = ET.fromstring(render_feed([article(intro='<script>not markup</script>'), article(slug='bad-xml', title='bad\x01')], now=NOW))
        self.assertEqual(len(root.findall('channel/item')), 1)
        self.assertEqual(root.findtext('channel/item/description'), '&lt;script&gt;not markup&lt;/script&gt;')

    def test_private_status_cannot_reach_prerender_or_sitemap(self):
        import json
        import tempfile
        from news_public import load_news
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.json'
            path.write_text(json.dumps({'records': [article(), article(slug='private', status='quarantined')]}), encoding='utf-8')
            self.assertEqual([r['slug'] for r in load_news(path)], ['synthetic-news'])


if __name__ == '__main__':
    unittest.main()
