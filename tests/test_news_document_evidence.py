"""Synthetic document fixtures, never live facts or publication approvals."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.robotparser import RobotFileParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_document_evidence import (html_document, parse_pdf_bytes, inspect_pdf, collect_document,
                                    MAX_PAGES, MAX_TABLES)
from news_http import Collector, MAX_BYTES
from news_publisher_sources import fetch_primary, parse_publisher, collect_bundle, refresh_bundle, same_sources
from news_store import artifact_hash
from inspect_news_documents import inspect, selection_urls, archive_document
from news_publisher_sources import bundle_errors
import test_news_original_discovery as fixtures

PDF_URL = 'https://www.aaa-data.fr/wp-content/uploads/2026/11/synthetic.pdf'
TABLE = ('<table><caption>Synthetic new passenger car registrations</caption>'
         '<thead><tr><th scope="col">Market</th><th scope="col">October 2026 units</th></tr></thead>'
         '<tbody><tr><th scope="row">France</th><td>12 345</td></tr></tbody>'
         '<tfoot><tr><td>Scope note</td><td>New registrations only</td></tr></tfoot></table>')


def pdf_bytes(*, pages=1, grid=False, encrypted=False, active=False, scanned=False, reserved=False, link=None):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject, ArrayObject, TextStringObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        parts = ['BT /F1 11 Tf 40 740 Td (Synthetic passenger car registrations for October 2026 in the French market.) Tj ET']
        if grid:
            parts += ['BT /F1 11 Tf 55 675 Td (Market) Tj 155 0 Td (October 2026 units) Tj ET',
                      'BT /F1 11 Tf 55 625 Td (France) Tj 155 0 Td (12345) Tj ET',
                      '40 600 m 400 600 l S 40 650 m 400 650 l S 40 700 m 400 700 l S',
                      '40 600 m 40 700 l S 200 600 m 200 700 l S 400 600 m 400 700 l S']
        stream = DecodedStreamObject(); stream.set_data(('\n'.join(parts) if not scanned else '').encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
        if link:
            annotation = DictionaryObject({NameObject('/Type'): NameObject('/Annot'), NameObject('/Subtype'): NameObject('/Link'),
                NameObject('/A'): DictionaryObject({NameObject('/S'): NameObject('/URI'), NameObject('/URI'): TextStringObject(link)})})
            page[NameObject('/Annots')] = ArrayObject([writer._add_object(annotation)])
    writer.add_metadata({'/Title': 'Synthetic registrations', '/CreationDate': 'D:20261102000000Z',
                         '/Keywords': 'notdm' if reserved else 'synthetic fixture'})
    if encrypted: writer.encrypt('synthetic-fixture-only')
    if active: writer.add_js('app.alert("synthetic fixture");')
    out = io.BytesIO(); writer.write(out)
    return out.getvalue()


class NewsDocumentTests(unittest.TestCase):
    def test_html_preserves_explicit_headers_cells_footnotes_and_hashes_without_inference(self):
        raw = '<article><p>Narrative about the synthetic registration report.</p>' + TABLE + '</article>'
        text, snapshot = html_document(raw)
        self.assertEqual(text, 'Narrative about the synthetic registration report.')
        table = snapshot['tables'][0]
        self.assertEqual(table['status'], 'prepared_not_verified')
        self.assertEqual(table['rows'][0][1]['text'], 'October 2026 units')
        self.assertEqual(table['rows'][1][0]['scope'], 'row')
        self.assertEqual(table['rows'][1][1]['text'], '12 345')
        self.assertTrue(table['rows'][2][1]['footnote'])
        self.assertNotIn('market', {k for k in table if k != 'caption'})
        self.assertEqual(snapshot['raw_sha256'], hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(snapshot['snapshot_hash'], artifact_hash({k: v for k, v in snapshot.items() if k != 'snapshot_hash'}))

    def test_merged_ragged_nested_missing_headers_and_malformed_tables_are_held(self):
        for body, reason in [(TABLE.replace('<td>12 345</td>', '<td colspan="2">12 345</td>'), 'spanning_cells_need_adapter'),
            (TABLE.replace('<td>12 345</td>', ''), 'ragged_or_empty_table'),
            (TABLE.replace('12 345', '<table><tr><td>Nested</td></tr></table>'), 'nested_table'),
            ('<table><tr><td>France</td><td>123</td></tr></table>', 'explicit_column_headers_required')]:
            with self.subTest(reason=reason):
                _, snapshot = html_document(body)
                self.assertEqual(snapshot['tables'][0]['status'], 'held_ambiguous')
                self.assertIn(reason, snapshot['tables'][0]['errors'])
        with self.assertRaisesRegex(ValueError, 'unclosed_table'): html_document('<table><tr><td>123')

    def test_html_table_work_is_bounded_and_cell_scripts_are_not_evidence(self):
        with self.assertRaisesRegex(ValueError, 'table_limit'): html_document(TABLE * (MAX_TABLES + 1))
        with self.assertRaisesRegex(ValueError, 'cell_limit'): html_document(TABLE.replace('12 345', 'x' * 2001))
        _, snapshot = html_document(TABLE.replace('12 345', '<script>Invented units</script>12 345'))
        self.assertEqual(snapshot['tables'][0]['rows'][1][1]['text'], '12 345')

    def test_pdf_preserves_raw_hash_page_layout_and_table_geometry_but_not_facts(self):
        raw = pdf_bytes(grid=True)
        value = parse_pdf_bytes(raw)
        self.assertEqual(value['raw_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(value['status'], 'prepared_not_verified')
        self.assertIsNone(value['publication_date'], 'Creation metadata is not a publication date')
        page = value['pages'][0]
        self.assertEqual(page['page'], 1)
        self.assertIn('October 2026', page['layout_text'])
        self.assertEqual(page['tables'][0]['cells'], [['Market', 'October 2026 units'], ['France', '12345']])
        self.assertEqual(page['tables'][0]['status'], 'needs_header_period_unit_validation')
        self.assertEqual(len(page['tables'][0]['bbox']), 4)
        self.assertNotIn('facts', value)

    def test_encrypted_active_scanned_reserved_and_excessive_pdfs_stay_held(self):
        for options, reason in [({'encrypted': True}, 'encrypted_pdf'), ({'active': True}, 'active_pdf'),
            ({'scanned': True}, 'scanned_or_unreadable'), ({'reserved': True}, 'tdm_reserved'),
            ({'pages': MAX_PAGES + 1}, 'page_limit')]:
            with self.subTest(options=options):
                with self.assertRaisesRegex(ValueError, reason): parse_pdf_bytes(pdf_bytes(**options))
        for raw in [b'not a PDF', b'%PDF-' + b'x' * MAX_BYTES]:
            with self.assertRaisesRegex(ValueError, 'invalid_or_oversized'): inspect_pdf(raw)

    def test_isolated_parser_keeps_the_raw_document_identity(self):
        raw = pdf_bytes(grid=True)
        self.assertEqual(inspect_pdf(raw), parse_pdf_bytes(raw))

    def test_pdf_hyperlinks_are_never_followed_and_active_uri_schemes_are_held(self):
        self.assertEqual(parse_pdf_bytes(pdf_bytes(link='https://www.aaa-data.fr/'))['status'], 'prepared_not_verified')
        with self.assertRaisesRegex(ValueError, 'annotated_pdf_requires_review'):
            parse_pdf_bytes(pdf_bytes(link='javascript:syntheticFixture()'))

    def test_parser_timeout_crash_and_changed_snapshot_fail_closed(self):
        raw = pdf_bytes()
        with patch('news_document_evidence.subprocess.run', side_effect=subprocess.TimeoutExpired('fixture', 12)):
            with self.assertRaisesRegex(ValueError, 'parser_timeout'): inspect_pdf(raw)
        for result, reason in [(Mock(returncode=1, stdout=b''), 'resource_limit'),
            (Mock(returncode=0, stdout=json.dumps({'raw_sha256': 'changed'}).encode()), 'hash_mismatch')]:
            with patch('news_document_evidence.subprocess.run', return_value=result):
                with self.assertRaisesRegex(ValueError, reason): inspect_pdf(raw)

    def test_binary_fetch_enforces_editorial_robots_headers_and_same_domain_policy(self):
        collector = Collector()
        robots = RobotFileParser(); robots.parse(['User-agent: *', 'Allow: /'])
        with patch.object(collector, 'policy', return_value=robots), patch.object(collector, 'request',
                return_value=(200, {'Content-Type': 'application/pdf'}, b'%PDF-fixture', PDF_URL)) as request, \
                patch('news_http.time.sleep'):
            self.assertEqual(collector.fetch_bytes(PDF_URL, {'website': 'https://www.aaa-data.fr'})[2], b'%PDF-fixture')
            self.assertTrue(request.call_args.kwargs['binary'])
            self.assertTrue(request.call_args.kwargs['policy'].can_fetch('SeekEVNews/1.0', PDF_URL))
            request.return_value = (200, {'TDM-Reservation': '1'}, b'%PDF-fixture', PDF_URL)
            with self.assertRaisesRegex(ValueError, 'tdm_reserved'): collector.fetch_bytes(PDF_URL, {'website': 'https://www.aaa-data.fr'})
        robots.parse(['User-agent: GPTBot', 'Disallow: /'])
        with patch.object(collector, 'policy', return_value=robots), patch.object(collector, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'ai_mining_robots_reserved'):
                collector.fetch_bytes(PDF_URL, {'website': 'https://www.aaa-data.fr'})
            request.assert_not_called()

    def test_collection_rejects_undeclared_urls_redirects_reserved_and_mislabeled_documents(self):
        collector = Mock()
        for url in ['https://127.0.0.1/private.pdf', 'https://www.aaa-data.fr.evil.example/test.pdf']:
            with self.assertRaisesRegex(ValueError, 'unapproved'): collect_document(url, collector)
        collector.fetch_bytes.assert_not_called()
        for response, reason in [((200, {}, b'%PDF-fixture', PDF_URL + '/changed'), 'redirected'),
            ((200, {'TDM-Reservation': '1'}, b'%PDF-fixture', PDF_URL), 'tdm_reserved'),
            ((200, {'Content-Type': 'text/html'}, b'<html>Error page</html>', PDF_URL), 'type_mismatch')]:
            collector.fetch_bytes.return_value = response
            with self.assertRaisesRegex(ValueError, reason): collect_document(PDF_URL, collector)

    def test_document_collector_never_makes_a_prepared_pdf_publication_eligible(self):
        collector = Mock()
        collector.fetch_bytes.return_value = (200, {'Content-Type': 'application/pdf'}, pdf_bytes(), PDF_URL)
        value = collect_document(PDF_URL, collector)
        self.assertFalse(value['publication_eligible'])
        self.assertEqual(value['source_id'], 'aaa-data')

    def test_private_preparer_follows_only_declared_same_authority_pdf_links_with_origin_hash(self):
        html_url = 'https://www.aaa-data.fr/actualites/synthetic-release/'
        html = ('<article><p>Official synthetic document.</p><a href="' + PDF_URL + '">PDF</a>'
                '<a href="https://unapproved.example/other.pdf">Foreign PDF</a></article>').encode()
        c = Mock()
        c.fetch_bytes.side_effect = [(200, {'Content-Type': 'text/html'}, html, html_url),
                                    (200, {'Content-Type': 'application/pdf'}, pdf_bytes(), PDF_URL)]
        value = inspect([html_url], c)
        self.assertEqual(len(value['documents']), 2)
        self.assertEqual(value['documents'][1]['discovered_from'],
                         {'url': html_url, 'raw_sha256': hashlib.sha256(html).hexdigest()})
        self.assertEqual(c.fetch_bytes.call_count, 2)
        c = Mock()
        c.fetch_bytes.return_value = (200, {'Content-Type': 'text/html'},
                                      b'<script>{"isAccessibleForFree": false}</script>', html_url)
        with self.assertRaisesRegex(ValueError, 'paywall'): collect_document(html_url, c)

    def test_tables_are_not_flattened_into_primary_or_publisher_ai_passages(self):
        html = fixtures.page(fixtures.ORIGINAL, body=fixtures.BODY + TABLE)
        collector = fixtures.FakeCollector({fixtures.ORIGINAL: html})
        item, _ = fetch_primary(fixtures.ORIGINAL, collector, fixtures.NOW)
        self.assertNotIn('12 345', item['payload']['content'])
        self.assertEqual(item['payload']['document_evidence']['tables'][0]['rows'][1][1]['text'], '12 345')
        publisher = parse_publisher(fixtures.page(fixtures.REPORT, body=fixtures.BODY + TABLE),
                                    fixtures.REPORT, 'carnewschina', now=fixtures.NOW)
        self.assertNotIn('12 345', publisher['content'])

    def test_changed_table_invalidates_refresh_even_when_narrative_is_unchanged(self):
        c = fixtures.FakeCollector({fixtures.REPORT: fixtures.page(fixtures.REPORT),
                                    fixtures.ORIGINAL: fixtures.page(fixtures.ORIGINAL, body=fixtures.BODY + TABLE)})
        bundle = collect_bundle('carnewschina', fixtures.REPORT, c, now=fixtures.NOW,
                                corroborating_items=[fixtures.catalog()])
        self.assertTrue(same_sources(bundle, refresh_bundle(bundle, c, fixtures.NOW)))
        c.documents[fixtures.ORIGINAL] += '<!-- Irrelevant dynamic page decoration -->'
        self.assertTrue(same_sources(bundle, refresh_bundle(bundle, c, fixtures.NOW)),
                        'Irrelevant HTML changes must not invalidate unchanged narrative/table evidence')
        c.documents[fixtures.ORIGINAL] = c.documents[fixtures.ORIGINAL].replace('12 345', '98 765')
        changed = refresh_bundle(bundle, c, fixtures.NOW)
        self.assertEqual(bundle['items'][1]['payload']['content_hash'], changed['items'][1]['payload']['content_hash'])
        self.assertFalse(same_sources(bundle, changed))
        tampered = copy.deepcopy(bundle)
        tampered['items'][1]['payload']['document_evidence']['tables'][0]['rows'][1][1]['text'] = '999'
        tampered['bundle_hash'] = artifact_hash({k: v for k, v in tampered.items() if k != 'bundle_hash'})
        self.assertIn('publisher_document_snapshot_invalid', bundle_errors(tampered, fixtures.NOW))

    def test_private_raw_archive_is_content_addressed_and_never_overwrites_changed_evidence(self):
        raw = pdf_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(archive_document(Path(directory), raw, digest, 'pdf'))
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(archive_document(Path(directory), raw, digest, 'pdf'), str(path))
            path.write_bytes(b'changed fixture')
            with self.assertRaisesRegex(ValueError, 'existing_archive_changed'):
                archive_document(Path(directory), raw, digest, 'pdf')
            with self.assertRaisesRegex(ValueError, 'hash_mismatch'):
                archive_document(Path(directory), raw, '0' * 64, 'pdf')

    def test_selection_inspection_is_bounded_independent_and_never_a_publication(self):
        value = {'candidates': [{'discovery_trace': [{'url': PDF_URL, 'status': 'needs_pdf_extraction'}] * 3}]}
        self.assertEqual(selection_urls(value), [PDF_URL])
        collector = Mock(); collector.fetch_bytes.side_effect = ValueError('ai_mining_robots_reserved')
        report = inspect([PDF_URL, 'https://127.0.0.1/private'], collector)
        self.assertEqual(report['documents'][0]['status'], 'held')
        self.assertIn('reserved', report['documents'][0]['reason'])
        self.assertFalse(any(row['publication_eligible'] for row in report['documents']))
        self.assertEqual((report['paid_calls'], report['database_writes'], report['publications']), (0, 0, 0))


if __name__ == '__main__': unittest.main()
