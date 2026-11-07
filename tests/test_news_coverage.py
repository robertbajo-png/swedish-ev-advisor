"""Synthetic international coverage checks, not publication or model receipts."""
from datetime import timedelta
from pathlib import Path
import hashlib
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_publisher_articles as fixtures
from news_store import artifact_hash
from news_coverage import coverage_score, international_scope, coverage_scope
from news_publisher_selection import candidate_assessment
from news_publisher_articles import precheck, check_review, reviewer_call, writer_call


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
    def test_swiss_market_has_explicit_schema_evidence_and_visible_lead(self):
        b,p=fixtures.fixture()
        title='Battery technology update at its Swiss premiere'
        for row in b['items']:
            row['payload']['title']=title
            row['payload']['content']=row['payload']['content'].replace('in Europe','in Switzerland')
            row['payload']['content_hash']=hashlib.sha256(row['payload']['content'].encode()).hexdigest()
        b['bundle_hash']=artifact_hash({k:v for k,v in b.items() if k!='bundle_hash'})
        p['extraction']['event']['subject']=title
        for fact in p['extraction']['facts']:
            fact['market']='CH'
            for ref in fact['support']: ref['quote']=ref['quote'].replace('in Europe','in Switzerland')
        p['article']['title']=p['article']['title'].replace('Europa','Schweiz')
        p['article']['intro']=p['article']['intro'].replace('Europa','Schweiz')
        self.assertEqual(coverage_scope(b,fixtures.NOW),'european_development')
        self.assertTrue(precheck(b,p,fixtures.NOW)['passed'],precheck(b,p,fixtures.NOW)['errors'])
        call=writer_call(b)
        self.assertIn('CH',call[1]['properties']['extraction']['properties']['facts']['items']['properties']['market']['enum'])
        self.assertIn('additional provided passage naming that exact model',call[2])
        p['article']['title']=p['article']['title'].replace('Schweiz','utlandet')
        p['article']['intro']=p['article']['intro'].replace('Schweiz','utlandet')
        self.assertIn('publisher_foreign_scope_missing_from_lead',precheck(b,p,fixtures.NOW)['errors'])
        for fact in p['extraction']['facts']:
            for ref in fact['support']: ref['quote']=ref['quote'].replace('in Switzerland','in Europe')
        self.assertTrue(any(e.startswith('publisher_swiss_market_not_in_evidence:') for e in precheck(b,p,fixtures.NOW)['errors']))

    def test_european_development_has_own_relevance_without_swedish_availability(self):
        b,p=fixtures.fixture()
        title='Nordic Cells unveils solid-state technology for electric cars in Europe'
        for item in b['items']: item['payload']['title']=title
        b['bundle_hash']=artifact_hash({k:v for k,v in b.items() if k!='bundle_hash'})
        p['extraction']['event']['subject']=title
        p['extraction'].update(sweden_relevance=.2,significance=.75)
        self.assertEqual(coverage_scope(b,fixtures.NOW),'european_development')
        checked=precheck(b,p,fixtures.NOW)
        self.assertTrue(checked['passed'],checked['errors'])
        self.assertNotIn('publisher_insufficient_swedish_relevance',checked['errors'])
        self.assertNotIn('publisher_insufficient_international_significance',checked['errors'])
        self.assertNotIn('publisher_international_market_not_established',checked['errors'])
        p['extraction']['significance']=.4
        self.assertIn('publisher_insufficient_international_significance',precheck(b,p,fixtures.NOW)['errors'])
        p['extraction']['facts'][0]['market']='SE'
        self.assertIn('publisher_international_market_not_established',precheck(b,p,fixtures.NOW)['errors'])

    def test_european_scope_needs_visible_market_and_separate_review(self):
        b,p=fixtures.fixture()
        for item in b['items']: item['payload']['title']='Electric car battery update arrives in Europe'
        b['bundle_hash']=artifact_hash({k:v for k,v in b.items() if k!='bundle_hash'})
        p['extraction']['event']['subject']=b['items'][0]['payload']['title']
        from unittest.mock import patch
        with patch('news_publisher_articles.international_scope',return_value=True):
            review=fixtures.accepted_review(b,p)
            self.assertIn('international_scope_supported',reviewer_call(b,p)[1]['required'])
            self.assertIn('publisher_review_rejected:international_scope_supported',check_review(b,p,review))
        p['article']['title']=p['article']['title'].replace('Europa','utlandet')
        p['article']['intro']=p['article']['intro'].replace('Europa','utlandet')
        self.assertIn('publisher_foreign_scope_missing_from_lead',precheck(b,p,fixtures.NOW)['errors'])

    def test_full_body_supports_triage_without_turning_geography_into_news(self):
        p={'title':'Synthetic electric model update for Switzerland','published_at':fixtures.NOW.isoformat(),
           'summary':'Short metadata only.','content':'Background. '*180+' This battery-electric model will launch in Switzerland.'}
        self.assertEqual(candidate_assessment(p,fixtures.NOW)['reason'],'european_scope')
        self.assertTrue(candidate_assessment({'title':'Synthetic electric models launch in Austria',
                                            'published_at':fixtures.NOW.isoformat()},fixtures.NOW)['eligible'])
        for title in ('Electric car podcast in Europe','Reader question about an electric car in Germany',
                      'Batteries de voitures electriques victimes de vol en France',
                      'Electric car nominated for an award in Europe','Electric car price discount in Europe'):
            self.assertFalse(candidate_assessment({'title':title,'published_at':fixtures.NOW.isoformat()},fixtures.NOW)['eligible'])

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
