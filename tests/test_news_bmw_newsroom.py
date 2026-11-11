"""Synthetic BMW PressPage layout tests, not news or live source evidence."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_bmw_newsroom import document

URL = 'https://newsroom.bmwgroup.com/global/synthetic-i3-charging-test/'
TITLE = 'BMW i3: synthetic charging test in 2h 46m'


def page():
    meta = {'@type': 'Article', 'headline': TITLE, 'datePublished': '2026-11-10T10:31:00+01:00',
            'dateModified': '2026-11-11T12:00:00+01:00',
            'mainEntityOfPage': {'@id': URL}, 'publisher': {'name': 'GLOBAL'}}
    return ('<html><head><link rel="canonical" href="' + URL + '">'
        '<meta property="og:title" content="' + TITLE + '">'
        '<script type="application/ld+json">' + json.dumps(meta) + '</script></head><body>'
        '<main id="pp-main"><article class="div_text_companyprofile">'
        '<div class="div_date_location"><div class="pp_date_day">10</div>'
        '<div class="pp_date_month">November</div><div class="pp_date_year">2026</div></div>'
        '<h1>BMW i3 completes a synthetic charging test across Europe.</h1>'
        '<div class="ppmodule_textblock"><p>' + ('Synthetic main evidence about a manufacturer demonstration. ' * 8) + '</p>'
        '<p>The demonstration uses a standard production vehicle, not an independent measurement.</p>'
        '<p hidden>Hidden advertising is not evidence.</p>'
        '<div class="text_boilerplate"><p>Unrelated company workforce and historic sales.</p></div></div>'
        '<aside><div class="pp_date_day">11</div><div class="pp_date_month">November</div>'
        '<div class="pp_date_year">2026</div>Related item date is not publication.</aside>'
        '</article></main></body></html>')


class BmwNewsroomTests(unittest.TestCase):
    def test_original_date_and_article_root_are_not_boilerplate(self):
        doc = document(page(), URL)
        self.assertEqual(doc['published_at'], '2026-11-10T09:31:00+00:00')
        self.assertIn('standard production vehicle', doc['body'])
        self.assertNotIn('workforce', doc['body'])
        self.assertNotIn('Hidden advertising', doc['body'])
        self.assertNotIn('Related item date', doc['body'])

    def test_rejects_wrong_host_canonical_model_date_or_missing_scope(self):
        edits = [(URL, URL.replace('bmwgroup.com', 'bmwgroup.com.evil.example')),
                 ('BMW i3 completes', 'BMW iX3 completes'),
                 ('pp_date_day">10', 'pp_date_day">11'),
                 ('id="pp-main"', 'id="unknown"'),
                 ('ppmodule_textblock', 'unknown_narrative'),
                 ('datePublished', 'dateModifiedOnly')]
        for old, new in edits:
            with self.subTest(new=new), self.assertRaises(ValueError):
                document(page().replace(old, new), URL)

    def test_ambiguous_main_is_not_accepted(self):
        with self.assertRaises(ValueError):
            document(page().replace('</main>', '</main><main id="pp-main"></main>'), URL)

    def test_only_exact_sidebar_chrome_tables_can_be_excluded(self):
        known = '<aside class="pp-side-column"><table class="table_flags"><tr><td>English</td></tr></table></aside>'
        self.assertEqual(document(page().replace('</main>', known + '</main>'), URL)['excluded_chrome_tables'], 1)
        for table in ('<table><tr><td>90 kWh</td></tr></table>',
                      '<aside class="pp-side-column"><table><tr><td>90 kWh</td></tr></table></aside>',
                      '<table class="table_flags"><tr><td>90 kWh</td></tr></table>'):
            with self.subTest(table=table), self.assertRaisesRegex(ValueError, 'unvalidated_table'):
                document(page().replace('</main>', table + '</main>'), URL)


if __name__ == '__main__':
    unittest.main()
