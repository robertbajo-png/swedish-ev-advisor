"""Synthetic international coverage checks, not publication or model receipts."""
from datetime import timedelta
from pathlib import Path
import hashlib
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_publisher_articles as fixtures
from news_store import artifact_hash
from news_coverage import coverage_score, international_scope
from news_publisher_selection import candidate_assessment
from news_publisher_articles import precheck, check_review, reviewer_call


def international_fixture():
    b, p = fixtures.fixture()
    title = 'Cellmaker unveils solid-state technology for electric cars in China'
    for item in b['items']:
        item['payload']['title'] = title
        item['payload']['content'] = item['payload']['content'].replace('in Europe', 'in China')
        item['payload']['content_hash'] = hashlib.sha256(item['payload']['content'].encode()).hexdigest()
    b['bundle_hash'] = artifact_hash({k: v for k, v in b.items() if k != 'bundle_hash'})
    p['extraction']['event']['subject'] = title
    p['extraction']['sweden_relevance'] = .1
    for fact in p['extraction']['facts']:
        fact['market'] = 'CN'
        fact['statement'] = fact['statement'].replace('europeiska elbilar', 'elbilar i Kina')
        for ref in fact['support']:
            ref['quote'] = ref['quote'].replace('in Europe', 'in China')
    p['article']['title'] = p['article']['title'].replace('Europa', 'Kina')
    p['article']['intro'] = p['article']['intro'].replace('Europa', 'Kina')
    return b, p


class InternationalCoverageTests(unittest.TestCase):
    def test_substantive_foreign_launches_allowed_but_not_offers_rumours_or_business(self):
        for country in ('China', 'Australia', 'United States', 'Japan', 'Korea', 'India'):
            p = {'title': f'Synthetic electric car debuts in {country}', 'published_at': fixtures.NOW.isoformat()}
            self.assertTrue(candidate_assessment(p, fixtures.NOW)['eligible'])
        for title in ('Synthetic electric car dealer opens in China', 'Synthetic electric car price discount in China',
                      'Synthetic electric car could launch in China', 'Synthetic electric car factory in China',
                      'Synthetic electric car nominated for award in Europe'):
            self.assertFalse(candidate_assessment({'title': title, 'published_at': fixtures.NOW.isoformat()}, fixtures.NOW)['eligible'])

    def test_international_significance_not_fake_swedish_relevance(self):
        b, p = international_fixture()
        self.assertTrue(international_scope(b, fixtures.NOW))
        result = precheck(b, p, fixtures.NOW)
        self.assertTrue(result['passed'], result['errors'])
        self.assertGreaterEqual(result['score'], 75)
        p['extraction']['significance'] = .5
        self.assertIn('publisher_insufficient_international_significance', precheck(b, p, fixtures.NOW)['errors'])

    def test_country_and_independent_scope_review_are_required(self):
        b, p = international_fixture()
        review = fixtures.accepted_review(b, p)
        # Bind time to the synthetic source date, never refresh an old live proof.
        from unittest.mock import patch
        with patch('news_publisher_articles.international_scope', return_value=True):
            self.assertIn('international_scope_supported', reviewer_call(b, p)[1]['required'])
            self.assertIn('publisher_review_rejected:international_scope_supported', check_review(b, p, review))
            review['international_scope_supported'] = True
            self.assertEqual(check_review(b, p, review), [])
        p['article']['title'] = p['article']['title'].replace('Kina', 'utlandet')
        p['article']['intro'] = p['article']['intro'].replace('Kina', 'utlandet')
        self.assertIn('publisher_foreign_scope_missing_from_lead', precheck(b, p, fixtures.NOW)['errors'])

    def test_international_route_does_not_relax_numeric_or_availability_checks(self):
        b, p = international_fixture()
        p['extraction']['facts'][0]['statement'] += ' 999 kWh.'
        p['extraction']['facts'][0]['market'] = 'SE'
        errors = precheck(b, p, fixtures.NOW)['errors']
        self.assertTrue(any('number_not_in_evidence' in e for e in errors))
        self.assertIn('publisher_international_market_not_established', errors)
        self.assertEqual(coverage_score(b, p['extraction'], fixtures.NOW + timedelta(days=9)), 0)

    def test_editorial_refusal_remains_quarantined_not_a_fake_success(self):
        b, p = fixtures.fixture()
        p['extraction'].update(relevant=False, facts=[])
        result = precheck(b, p, fixtures.NOW)
        self.assertFalse(result['passed'])
        self.assertIn('publisher_editorial_declined', result['errors'])


if __name__ == '__main__':
    unittest.main()
