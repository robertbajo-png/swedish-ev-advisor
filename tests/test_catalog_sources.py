import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_catalog_sources import allowed_url, source_text, assess_record, run, SourceFetcher


class CatalogSourceTests(unittest.TestCase):
    def setUp(self):
        self.row = {'brand': 'Kia', 'model': 'EV3', 'variant_name': 'Long Range', 'price_sek': 500000,
                    'source_url': 'https://www.kia.com/se/nya-bilar/ev3/', 'source_quote': 'Long Range WLTP 605 km.',
                    'source_hash': 'fixture-hash', 'verified_at': None}
        self.fetched = {'status': 'reachable', 'content_hash': 'fixture-hash', 'text_hash': 'text-hash',
                        'text': 'Long Range WLTP 605 km. ' + 'Manufacturer information. ' * 40}

    def test_exact_brand_market_https_and_redirect_targets(self):
        self.assertTrue(allowed_url(self.row['source_url'], {'Kia'}))
        for url in ['https://www.kia.com/us/ev3', 'https://ev-database.org/ev3',
                    'https://kia.com.example.org/se/', 'https://secret@www.kia.com/se/', 'http://www.kia.com/se/']:
            self.assertFalse(allowed_url(url, {'Kia'}))
        self.assertFalse(allowed_url('https://www.bmw.se/sv/i4', {'Kia'}))

    def test_html_parser_ignores_scripts(self):
        self.assertEqual(source_text(b'<p>Long Range</p><script>999 km</script><p>605 km</p>', 'text/html'), 'Long Range 605 km')

    def test_http_success_is_not_fact_verification(self):
        self.assertEqual(assess_record(self.row, {**self.fetched, 'text': '<html>Loading</html>'}), 'rendered_content_required')
        self.assertEqual(assess_record(self.row, {**self.fetched, 'content_hash': 'new'}), 'source_changed_evidence_present')
        self.assertEqual(assess_record(self.row, self.fetched), 'hash_and_evidence_unchanged')
        self.assertIsNone(self.row['verified_at'])
        self.assertEqual(assess_record({**self.row, 'source_quote': 'Long Range | WLTP 605 km.'}, self.fetched), 'hash_and_evidence_unchanged')
        self.assertEqual(assess_record({**self.row, 'source_quote': 'Long Range | Invented value'}, self.fetched), 'evidence_not_found')

    def test_variant_model_maxima_and_preliminary_values_are_not_promoted(self):
        self.assertEqual(assess_record({**self.row, 'variant_name': 'EV3'}, self.fetched), 'exact_variant_mapping_required')
        self.assertEqual(assess_record({**self.row, 'variant_name': 'AWD'}, self.fetched), 'variant_scope_not_found')
        self.assertEqual(assess_record(self.row, {**self.fetched, 'text': self.fetched['text'] + ' Uppgifterna är preliminära.'}), 'preliminary_figures_require_reverification')
        self.assertEqual(assess_record({**self.row, 'source_quote': 'invented'}, self.fetched), 'evidence_not_found')

    def test_stale_price_documents_and_campaign_expiry(self):
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.assertEqual(assess_record({**self.row, 'source_url': 'https://www.kia.com/se/2024-08-01.pdf'}, self.fetched, now), 'dated_price_document_requires_current_source')
        self.assertEqual(assess_record({**self.row, 'price_valid_until': '2026-10-19'}, self.fetched, now), 'expired_price')
        self.assertEqual(assess_record({**self.row, 'price_valid_until': '2026-10-20'}, self.fetched, now), 'hash_and_evidence_unchanged')

    def test_disallowed_robots_prevents_content_request(self):
        fetcher = SourceFetcher()
        fetcher.robots_allowed = lambda _: False
        fetcher.opener.open = lambda *_args, **_kwargs: self.fail('Do not fetch robots-denied content')
        self.assertEqual(fetcher.fetch(self.row['source_url'], {'Kia'})['status'], 'robots_denied_or_unavailable')
        self.assertEqual(fetcher.fetch('https://example.org', {'Kia'})['status'], 'rejected_domain_or_market')

    def test_document_extraction_respects_reservations_before_parser(self):
        class Response:
            headers = {'content-type': 'text/html'}
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, _): return self.body
        response = Response()
        fetcher = SourceFetcher(document_parser=lambda *_: self.fail('Reserved document must not reach extraction'))
        fetcher.robots_allowed = lambda _: True
        fetcher.opener.open = lambda *_args, **_kwargs: response
        for body in [b'<meta name="tdm-reservation" content="1">', b'<meta content="1" NAME="tdm-reservation">']:
            response.body = body
            self.assertEqual(fetcher.fetch(self.row['source_url'], {'Kia'})['status'], 'machine_reservation')
        response.body = b'<p>Allowed fixture</p>'
        calls = []
        fetcher.document_parser = lambda body, kind: calls.append((body, kind)) or 'structured fixture'
        result = fetcher.fetch(self.row['source_url'], {'Kia'})
        self.assertEqual(result['document'], 'structured fixture')
        self.assertEqual(len(calls), 1)

    def test_deduplication_idempotence_failure_isolation_and_no_writes(self):
        class FakeFetcher:
            calls = 0
            def fetch(inner, url, brands):
                inner.calls += 1
                return dict(self.fetched) if 'ev3' in url else {'status': 'http_error', 'http_status': 403}
        fixture = FakeFetcher()
        records = [self.row, {**self.row, 'variant_name': 'Base'}, {**self.row, 'source_url': 'https://www.kia.com/se/blocked'}]
        with tempfile.TemporaryDirectory() as directory:
            first = run(records, Path(directory), fixture)
            second = run(records, Path(directory), FakeFetcher())
        self.assertEqual(fixture.calls, 2)
        self.assertEqual(first['facts_verified'], 0)
        self.assertFalse(first['remote_writes'])
        self.assertEqual(first['openai_calls'], 0)
        self.assertEqual(len(first['jobs']), 3)
        self.assertEqual([job['job_id'] for job in first['jobs']], [job['job_id'] for job in second['jobs']])
        self.assertNotIn('verified_at', json.dumps(first['jobs']))


if __name__ == '__main__':
    unittest.main()
