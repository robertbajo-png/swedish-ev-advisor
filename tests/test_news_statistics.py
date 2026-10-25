"""Synthetic release-format fixtures; no copied live article or paid calls."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news as fixtures
from news_editorial import (extract_facts, validate_fact_extraction, validate_article,
                             build_fact_plan, generate_article, statistics_market_errors, article_preflight,
                             blocks, relevance_score, FACT_SCHEMA)
from news_statistics import source_statistical_facts, statistical_scope_errors, statistical_numbers
from test_news_fact_plan import response_for

TEXT = (
    'Up until September 2026 , battery-electric cars secured a 20.4% share of the EU market, up from 13.6% a year earlier. '
    'Hybrid-electric car registrations captured 34.2% of the market, remaining the preferred choice among EU consumers. '
    'At the same time, the combined market share of petrol and diesel cars fell to 33.1%, compared with 39.9% a year earlier. '
    'In the first nine months of 2026 , 1,612,345 new battery-electric cars were registered, capturing 20.4% of the EU market '
    'and establishing them as the second most popular powertrain choice year-to-date. '
    'Plug-in-hybrid electric car registrations continued to grow, reaching 345,678 units in January-September 2026 . '
    'New plug-in-hybrid electric cars represent 5.6% of EU registrations, up from 7% over the same period in 2025.'
)


def source(text=TEXT):
    item = fixtures.item()
    item.update(source_id='acea', url='https://www.acea.auto/pc-registrations/test-release/')
    item['payload'].update(content=text, content_hash=hashlib.sha256(text.encode()).hexdigest())
    return item


def metadata(score=0.8):
    value = fixtures.extraction()
    value.pop('facts')
    value.update(category='marknad', sweden_relevance=score,
                 event={'subject': 'EU', 'action': 'market', 'date': fixtures.DATE[:10], 'description': 'EU registrations'})
    return value


class LiteralStatisticsTests(unittest.TestCase):
    def test_two_additional_fields_require_literal_period_market_and_exact_quotes(self):
        extra = (' September 2026 YTD’s figures also showed new EU hybrid-electric car registrations rising to '
                 '2,765,432 units, supported by growth in several markets. '
                 'The new EU passenger car market showed notable resilience, rising 4.4% year-to-date '
                 'despite a challenging macroeconomic environment.')
        item = source(TEXT + extra)
        facts = source_statistical_facts(item)
        self.assertEqual(len(facts), 8)
        self.assertEqual(facts[-2]['statistic']['values']['current'], '2765432')
        self.assertEqual(facts[-1]['statistic']['metric'], 'year_to_date_change_percent')
        self.assertEqual(facts[-1]['statistic']['powertrain'], 'all_powertrains')
        self.assertEqual(validate_fact_extraction({**metadata(), 'facts': facts}, item), [])
        for fact in facts[-2:]:
            self.assertTrue(8 <= len(fact['evidence'].split()) <= 24)
            self.assertIn(fact['evidence'], item['payload']['content'])
        wrong_period = source(TEXT + extra.replace('September 2026 YTD', 'August 2026 YTD'))
        self.assertFalse(any(f['statistic']['powertrain'] == 'hybrid-electric' and f['statistic']['metric'] == 'units'
                             for f in source_statistical_facts(wrong_period)))
        growth = facts[-1]
        block = {'id': 'p0', 'kind': 'reporting', 'fact_ids': [growth['id']], 'text': 'Marknadens andel är 4,4 procent.'}
        self.assertIn('statistics_metric_mismatch:p0', statistical_scope_errors([block], facts))

    def test_r19_ranking_is_blocked_even_with_a_positive_mock_audit(self):
        item = source()
        fact = {**source_statistical_facts(item)[2], 'item_id': item['id']}
        article = {'title': 'Hybridbilar är den största drivlinan i EU', 'title_fact_ids': [fact['id']]}
        checks = validate_article(article, [fact], [item], fixtures.audit([fact]), 90)
        self.assertIn('statistics_unlicensed_ranking:title', checks['evidence'])

    def test_out_of_scale_ratings_never_become_full_score_or_silently_normalize(self):
        for value in [6.5, 8.6, 65, -0.1, float('nan'), float('inf'), '0.8', None, True]:
            for field in ['sweden_relevance', 'significance']:
                extracted = {**metadata(), 'facts': source_statistical_facts(source()), field: value}
                before = extracted[field]
                self.assertIn('invalid_rating_scale:' + field, validate_fact_extraction(extracted, source()))
                self.assertEqual(relevance_score(extracted, 0.98, fixtures.DATE), 0)
                self.assertIs(extracted[field], before)

    def test_rating_schema_and_boundary_values_enforce_zero_to_one(self):
        for field in ['sweden_relevance', 'significance']:
            self.assertEqual(FACT_SCHEMA['properties'][field], {'type': 'number', 'minimum': 0, 'maximum': 1})
        for value in [0, 0.65, 1]:
            extracted = {**metadata(value), 'facts': source_statistical_facts(source())}
            errors = validate_fact_extraction(extracted, source())
            self.assertFalse(any(error.startswith('invalid_rating_scale:') for error in errors))
        self.assertEqual(relevance_score(metadata(), 8.9, fixtures.DATE), 0)

    def test_literal_fields_preserve_values_scope_quotes_and_original_source(self):
        item = source()
        original = copy.deepcopy(item)
        facts = source_statistical_facts(item)
        self.assertEqual(len(facts), 6)
        self.assertEqual(facts[1]['statistic']['values']['current'], '1612345')
        self.assertEqual(facts[4]['statistic']['values']['current'], '345678')
        for fact in facts:
            self.assertEqual(fact['source_hash'], item['payload']['content_hash'])
            for quote in ['evidence', 'scope_evidence']:
                self.assertIn(fact[quote], item['payload']['content'])
                self.assertTrue(8 <= len(fact[quote].split()) <= 24)
            self.assertEqual(fact['statistic']['market'], 'EU')
            self.assertEqual(fact['statistic']['through_month'], 'September')
        self.assertEqual(item, original)
        self.assertEqual(facts, source_statistical_facts(copy.deepcopy(item)))

    def test_unknown_authority_access_hash_and_competing_periods_never_add_fields(self):
        for key, value in [('source_kind', 'secondary'), ('access_status', 'blocked'), ('content_hash', 'changed')]:
            item = source()
            item['payload'][key] = value
            self.assertEqual(source_statistical_facts(item), [])
        for text in [TEXT.replace('Up until', 'Only in'), TEXT + ' ' + TEXT,
                     TEXT.replace('first nine months', 'first eight months'),
                     TEXT.replace('capturing 20.4%', 'capturing 21.4%')]:
            self.assertEqual(source_statistical_facts(source(text)), [])
        for url in ['https://comparison.example/pc-registrations/test', 'https://acea.auto/not-statistics/']:
            item = source()
            item['url'] = url
            self.assertEqual(source_statistical_facts(item), [])

    def test_changed_fact_value_scope_or_quote_fails_even_after_positive_mock_audit(self):
        item = source()
        facts = source_statistical_facts(item)
        for field, value in [('statement', facts[0]['statement'].replace('20.4', '30.4')),
                             ('source_hash', 'changed'), ('scope_evidence', 'not from this source'),
                             ('statistic', {**facts[0]['statistic'], 'market': 'Sweden'})]:
            changed = [{**f, 'item_id': item['id']} for f in facts]
            changed[0][field] = value
            checks = validate_article(fixtures.draft(), changed, [item], fixtures.audit(changed), 90)
            self.assertIn('invalid_statistical_scope:' + changed[0]['id'], checks['evidence'])

    def test_ai_cannot_change_literal_facts_or_have_low_relevance_promoted(self):
        item = source()
        fake = {**metadata(0.35), 'facts': [{'statement': 'Invented Swedish total'}]}
        ai = Mock(return_value=fake)
        extracted = extract_facts(item, [], ai)
        self.assertEqual(extracted['facts'], source_statistical_facts(item))
        self.assertEqual(extracted['sweden_relevance'], 0.35)
        self.assertIn('insufficient_swedish_relevance', validate_fact_extraction(extracted, item))
        self.assertNotIn('facts', ai.call_args.args[1]['properties'])
        self.assertEqual(validate_fact_extraction(extract_facts(item, [], Mock(return_value=metadata())), item), [])

    def test_unknown_layout_uses_existing_strict_ai_extraction_not_guessed_fields(self):
        item = source('A completely different statistical release without recognized fields.')
        ai = Mock(return_value=fixtures.extraction())
        extract_facts(item, [], ai)
        self.assertIn('facts', ai.call_args.args[1]['properties'])

    def test_intervening_market_scope_cannot_be_inherited_by_hybrid_sentences(self):
        item = source(TEXT.replace('Hybrid-electric car', 'Swedish market figures follow. Hybrid-electric car'))
        facts = source_statistical_facts(item)
        self.assertFalse(any(f['statistic']['powertrain'] in {'hybrid-electric', 'petrol-and-diesel'} for f in facts))

    def test_explicit_period_end_must_match_even_when_year_is_correct(self):
        fact = source_statistical_facts(source())[0]
        block = {'id': 'p0', 'text': 'Under januari till augusti 2026 var EU:s elbilsandel 20,4 procent.',
                 'kind': 'reporting', 'fact_ids': [fact['id']]}
        self.assertIn('statistics_period_mismatch:p0', statistical_scope_errors([block], [fact]))
        block['text'] = block['text'].replace('augusti', 'september')
        self.assertEqual(statistical_scope_errors([block], [fact]), [])

    def test_block_scope_rejects_month_stock_sales_and_wrong_powertrain(self):
        fact = source_statistical_facts(source())[0]
        def errors(text):
            block = {'id': 'p0', 'text': text, 'kind': 'reporting', 'fact_ids': [fact['id']]}
            return statistical_scope_errors([block], [fact])
        for text, reason in [
            ('I september var EU-andelen 20,4 procent.', 'period'),
            ('Elbilar utgör 20,4 procent av bilbeståndet.', 'denominator'),
            ('Försäljningen uppgår till 20,4 procent.', 'metric'),
            ('Laddhybrider stod för 20,4 procent av EU:s nyregistreringar.', 'powertrain')]:
            self.assertTrue(any(error.startswith('statistics_' + reason + '_mismatch:') for error in errors(text)))
        self.assertEqual(errors('Från januari till och med september stod elbilar för 20,4 procent av EU:s nyregistreringar.'), [])
        article = {'title': 'Svenska nyregistreringar nådde en andel på 20,4 procent.', 'title_fact_ids': [fact['id']]}
        self.assertIn('statistics_market_mismatch:title:Sweden', statistics_market_errors(article, [fact]))

    def test_swedish_grouping_is_supported_without_turning_decimals_into_counts(self):
        self.assertEqual(statistical_numbers('1 612 345 och 20,4 procent under 2026'), {'1612345', '20.4', '2026'})
        self.assertEqual(statistical_numbers('345\u00a0678'), {'345678'})
        self.assertEqual(statistical_numbers('345 678. Nästa mening.'), {'345678'})
        self.assertNotEqual(statistical_numbers('1,612'), {'1612'})
        item = source()
        fact = {**source_statistical_facts(item)[1], 'item_id': item['id']}
        article = {'title': 'EU:s elbilsregistreringar', 'title_fact_ids': [fact['id']],
                   'paragraphs': [{'text': 'Under januari till september 2026 registrerades 1 612 345 elbilar i EU.',
                                   'fact_ids': [fact['id']], 'kind': 'reporting'}]}
        checks = validate_article(article, [fact], [item], None, 90)
        self.assertFalse(any(error.startswith('unsupported_numeric_claim:') for error in checks['evidence']))
        article['paragraphs'][0]['text'] = article['paragraphs'][0]['text'].replace('1 612 345', '1 612 346')
        self.assertIn('unsupported_numeric_claim:p0', validate_article(article, [fact], [item], None, 90)['evidence'])

    def test_statistics_context_and_citations_survive_planning_and_prose_binding(self):
        facts = [{**f, 'item_id': 'stat-source'} for f in source_statistical_facts(source())]
        plan = build_fact_plan(facts)
        self.assertEqual(plan['title']['statistics'][0]['market'], 'EU')
        article = generate_article(facts, Mock(return_value=response_for(plan)))
        self.assertEqual(article['title_fact_ids'], [facts[0]['id']])
        self.assertEqual(article['fact_plan_hash'], plan['hash'])

    def test_units_cannot_be_presented_as_market_share_or_vice_versa(self):
        facts = source_statistical_facts(source())
        for fact, text in [(facts[1], 'EU-andelen är 1612345 procent.'),
                           (facts[0], 'I EU registrerades 20,4 elbilar.')]:
            block = {'id': 'p0', 'text': text, 'kind': 'reporting', 'fact_ids': [fact['id']]}
            self.assertIn('statistics_metric_mismatch:p0', statistical_scope_errors([block], [fact]))

    def test_offline_statistical_reference_passes_gates_without_scope_or_number_relaxation(self):
        item = source()
        facts = [{**f, 'item_id': item['id']} for f in source_statistical_facts(item)]
        plan = build_fact_plan(facts)
        output = {'title': 'Elbilarnas EU-andel når en ny nivå under årets första nio månader',
                  'intro': 'Mellan januari och september 2026 stod batterielektriska personbilar för 20,4 procent av EU:s nyregistreringar. Motsvarande andel under samma period året före var 13,6 procent.',
                  'paragraphs': [
                      'Räknat i antal handlar det om 1 612 345 nyregistrerade batterielektriska personbilar i EU under januari till september 2026. Siffran avser registreringar av nya bilar.',
                      'För hybrider utan laddkontakt redovisas en andel på 34,2 procent. Även den uppgiften gäller EU:s nyregistrerade personbilar från januari till och med september 2026.',
                      'Bensin och diesel stod tillsammans för 33,1 procent av EU:s nya personbilsregistreringar under januari till september 2026. Året före var samma periodandel 39,9 procent.',
                      'För laddhybrider redovisas 345 678 nyregistrerade personbilar i EU från januari till september 2026.',
                      'Laddhybridernas EU-andel var 5,6 procent av nya personbilsregistreringar under januari till september 2026. Under motsvarande period föregående år uppgick andelen till 7 procent.',
                  ], 'source_context': {},
                  'buyer_question': 'Vilka uppgifter om en enskild modell behöver du innan du går vidare med ditt bilval?'}
        article = generate_article(facts, Mock(return_value=output))
        self.assertEqual(article_preflight(article, facts, [item], 90)['errors'], [])
        audit = fixtures.audit(facts)
        audit['blocks'] = [{'id': b['id'], 'supported': True, 'reason': 'Synthetic fixture, not a real audit',
                            'verdict': 'grounded_question' if b['kind'] == 'analysis' else 'evidence_supported',
                            'unsupported_claims': []} for b in blocks(article)]
        self.assertEqual(validate_article(article, facts, [item], audit, 90), {'evidence': [], 'editorial': [], 'originality': []})


if __name__ == '__main__':
    unittest.main()
