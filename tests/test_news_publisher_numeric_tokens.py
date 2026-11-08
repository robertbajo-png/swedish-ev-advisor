"""Synthetic numeric-token and attribution regressions; never live approvals."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_news_publisher_articles as fixtures
from test_news_publisher_flexible_policy import single_fixture
from test_news_reported_articles import rehash
from news_publisher_articles import numbers, precheck
from news_reporting_policy import sensitive_fact
from news_publisher_selection import candidate_assessment


class PublisherNumericTokenTests(unittest.TestCase):
    def test_model_digit_is_not_merged_with_following_percentage(self):
        for model in ('N9', 'X9', 'ID.7', '#2'):
            with self.subTest(model=model):
                self.assertEqual(numbers(model + ' 100 % electric'),
                                 numbers(model) | {'100'})

    def test_real_grouped_thousands_and_decimal_values_remain_supported(self):
        for text in ('1 200', '1\u00a0200', '1\u202f200', '1,200'):
            self.assertEqual(numbers(text, source_language=True), {'1200'})
        self.assertEqual(numbers('2,03 m and 1.83 m'), {'2.03', '1.83'})
        self.assertEqual(numbers('1 200 000'), {'1200000'})
        self.assertNotEqual(numbers('X9 100'), {'9100'})

    def test_model_context_can_match_literal_body_without_inventing_values(self):
        bundle, packet, _ = single_fixture()
        fact = packet['extraction']['facts'][0]
        old_quote = fact['support'][0]['quote']
        new_quote = old_quote.rstrip('.') + ' for the X9 100 percent electric research vehicle.'
        bundle['items'][0]['payload']['content'] = bundle['items'][0]['payload']['content'].replace(old_quote, new_quote)
        fact['support'][0]['quote'] = new_quote
        fact['statement'] += ' Projektet omfattar modell X9.'
        rehash(bundle)
        checked = precheck(bundle, packet, fixtures.NOW)
        self.assertTrue(checked['passed'], checked)
        fact['statement'] += ' Karossen ar 9100 mm bred.'
        self.assertIn('publisher_fact_number_not_in_evidence:f1',
                      precheck(bundle, packet, fixtures.NOW)['errors'])

    def test_powertrain_history_is_not_charging_performance(self):
        for description in ('laddhybrid', 'laddhybriden', 'laddbar hybrid'):
            statement = 'Modell X9 har tidigare funnits som ' + description + '.'
            self.assertFalse(sensitive_fact({'statement': statement, 'range_cycle': 'NOT_APPLICABLE'}))

    def test_critical_claims_remain_sensitive_with_powertrain_context(self):
        for claim in ('Batteriet rymmer 90 kWh.', 'Laddning tar 20 minuter.',
                      'Dragvikten ar 1500 kg.', 'Modellen kan bestallas i Sverige.',
                      'Modellen aterkallas pa grund av brandrisk.', 'Rackvidden ar 600 km.'):
            statement = 'X9 var en laddhybrid. ' + claim
            self.assertTrue(sensitive_fact({'statement': statement, 'range_cycle': 'NOT_APPLICABLE'}), claim)


class PublisherAttributionVerbTests(unittest.TestCase):
    def test_named_registered_publisher_can_write_state_or_note(self):
        for verb in ('skriver', 'anger', 'noterar'):
            bundle, packet, _ = single_fixture()
            packet['article']['paragraphs'][0]['text'] = packet['article']['paragraphs'][0]['text'].replace(
                'Enligt medierna ', 'CarNewsChina ' + verb + ' att ')
            checked = precheck(bundle, packet, fixtures.NOW)
            self.assertTrue(checked['passed'], checked)

    def test_generic_or_invented_speaker_is_not_source_attribution(self):
        for speaker in ('Tillverkaren', 'En annan tidning', 'CarNewsChinaExtra'):
            bundle, packet, _ = single_fixture()
            packet['article']['paragraphs'][0]['text'] = packet['article']['paragraphs'][0]['text'].replace(
                'Enligt medierna ', speaker + ' skriver att ')
            self.assertIn('publisher_reported_block_attribution_missing:p0',
                          precheck(bundle, packet, fixtures.NOW)['errors'])


class PublisherAdviceTriageTests(unittest.TestCase):
    def test_french_advice_questions_are_held_before_paid_writing(self):
        for verb in ('payer le parking', 'acheter', 'choisir', 'recharger'):
            item = {'payload': {'title': 'Faut-il ' + verb + ' une voiture electrique?',
                               'published_at': fixtures.NOW.isoformat()}}
            result = candidate_assessment(item, fixtures.NOW)
            self.assertFalse(result['eligible'])
            self.assertEqual(result['reason'], 'commentary_or_incident_not_vehicle_development')

    def test_concrete_development_is_not_a_how_to_question(self):
        item = {'payload': {'title': 'Nouveau moteur pour les voitures electriques en Europe',
                           'published_at': fixtures.NOW.isoformat()}}
        self.assertTrue(candidate_assessment(item, fixtures.NOW)['eligible'])


if __name__ == '__main__':
    unittest.main()
