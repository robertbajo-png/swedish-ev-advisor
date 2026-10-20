import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from variant_refresh import FACT_FIELDS, RefreshError, extract_polestar, parse_document, refresh_errors
from refresh_verified_variants import merge_quarantine, publish_group, toyota_document_candidates

HEADERS = ['Long range Single motor', 'Long range Dual motor', 'Long range Dual motor med Performance-paketet']


def fixture(headers=HEADERS):
    rows = [('Pris från', ['510 000 kr', '610 000 kr', '710 000 kr']),
            ('Drivlina', ['Bakhjulsdrift', 'Fyrhjulsdrift', 'Fyrhjulsdrift']),
            ('Räckvidd²', ['600 km', '550 km', 'Upp till 520 km']),
            ('Dragvikt', ['Upp till 1 500 kg'] * 3),
            ('Energikonsumtion (WLTP)', ['14,8–15,8 kWh/100 km'] * 3)]
    table = '<table><thead><tr>' + ''.join('<th>' + name + '</th>' for name in headers) + '</tr></thead><tbody>'
    table += ''.join('<tr>' + ''.join('<td><label>' + label + '</label><p>' + value + '</p></td>' for value in values) + '</tr>' for label, values in rows)
    table += '</tbody></table>'
    common = [('Batterikapacitet', '400 V litiumjonbatteri, 82 kWh kapacitet, 27 moduler'),
              ('DC-laddning', 'Upp till 205 kW'), ('11 kW AC laddningstid (3-fas 16A AC)¹', '8 timmar'),
              ('Volym (uppfällda säten)', '407 liter, inklusive under golvet')]
    return table + '<dl>' + ''.join('<div><dt>' + label + '</dt><dd>' + value + '</dd></div>' for label, value in common) + '</dl>'


def source(html):
    return {'brand': 'Polestar', 'model': '2', 'url': 'https://www.polestar.com/se/polestar-2/specifications/',
            'source_authority': 'manufacturer', 'source_type': 'manufacturer_specs_page',
            'source_validation': 'reachable_official_model_source', 'content_hash': hashlib.sha256(html.encode()).hexdigest()}


def extract(html):
    doc = parse_document(html.encode(), 'text/html')
    src = source(html)
    expected = [dict(brand='Polestar', model='2', variant_name=name) for name in HEADERS]
    return extract_polestar(doc, src, expected), doc, src, expected


class VariantRefreshTests(unittest.TestCase):
    def test_exact_columns_and_field_evidence(self):
        drafts, doc, src, previous = extract(fixture())
        self.assertEqual([row['price_sek'] for row in drafts], [510000, 610000, 710000])
        self.assertEqual([row['wltp_range_km'] for row in drafts], [600, 550, 520])
        for row, old in zip(drafts, previous):
            self.assertIsNone(row['price_type'])
            self.assertIsNone(row['seats'])
            self.assertIsNone(row['wltp_consumption_kwh_100km'])
            self.assertEqual(row['dc_charge_kw'], 205)
            self.assertEqual(row['ac_charge_kw'], 11)
            self.assertEqual(refresh_errors(row, src, doc, old), [])

    def test_changed_identity_shape_duplicate_or_preliminary_stops_batch(self):
        html = fixture()
        for broken in [fixture(['Rear motor', *HEADERS[1:]]), fixture([HEADERS[0]] * 3),
                       html.replace('Räckvidd²', 'Räckviddsmål (WLTP)'), html.replace('<td>', '<td colspan="2">', 1),
                       html.replace('<td>', '<td rowspan="2">', 1), html.replace('<th>', '<th colspan="2">', 1),
                       html.replace('<td><label>Drivlina</label>', '<td><label>Annan rad</label>', 1), html + html]:
            with self.subTest(broken=broken[:50]):
                with self.assertRaises(RefreshError):
                    extract(broken)

    def test_hidden_and_script_tables_are_not_evidence(self):
        html = fixture()
        for hidden in ['<script>' + html + '</script>', '<div hidden>' + html + '</div>', '<div aria-hidden="true">' + html + '</div>']:
            with self.assertRaises(RefreshError):
                extract(hidden)
        self.assertEqual(len(extract('<script>' + html + '</script>' + html)[0]), 3)

    def test_lease_campaign_interval_and_non_swedish_units_not_list_price(self):
        html = fixture()
        for bad in ['5 100 kr/mån', 'Kampanj 510 000 kr', '510 000 EUR', '510 000–610 000 kr']:
            with self.assertRaises(RefreshError):
                extract(html.replace('510 000 kr', bad))

    def test_evidence_wrong_variant_loss_and_large_changes_quarantined(self):
        drafts, doc, src, previous = extract(fixture())
        row = drafts[0]
        row['extraction_payload']['field_evidence']['price_sek']['column_header'] = HEADERS[1]
        self.assertIn('wrong_variant_price_sek', refresh_errors(row, src, doc, previous[0]))
        self.assertIn('would_clear_existing_seats', refresh_errors(row, src, doc, {**previous[0], 'seats': 5}))
        self.assertIn('large_change_price_sek', refresh_errors(row, src, doc, {**previous[0], 'price_sek': 100000}))
        row['extraction_payload']['field_evidence']['dc_charge_kw']['quote'] = 'Invented supporting quotation'
        self.assertIn('unsupported_dc_charge_kw', refresh_errors(row, src, doc, previous[0]))
        row['price_sek'] = 520000
        self.assertIn('value_evidence_mismatch_price_sek', refresh_errors(row, src, doc, previous[0]))
        row['dc_charge_kw'] = 999
        self.assertIn('dc_charge_kw_out_of_range', refresh_errors(row, src, doc, previous[0]))

    def test_optional_or_conflicting_common_values_are_not_assumed(self):
        html = fixture()
        for broken in [html.replace('Upp till 205 kW', 'Upp till 205 kW med paketet'),
                       html.replace('82 kWh kapacitet', '82–100 kWh kapacitet'),
                       html + '<dl><dt>DC-laddning</dt><dd>250 kW</dd></dl>']:
            with self.assertRaises(RefreshError):
                extract(broken)

    def test_stage_writes_only_private_drafts_and_publish_uses_transaction(self):
        drafts, doc, src, previous = extract(fixture())
        src.update(fetched_at='2026-10-20T12:00:00Z', final_url=src['url'])
        class Client:
            writes = []
            def select(self, table, columns, filters):
                if table == 'manufacturer_sources':
                    return [{**src, 'id': 'source', 'canonical_model_id': 'model', 'content_hash': 'a'*64, 'updated_at': '2026-01-01T00:00:00Z'}]
                return [{**row, 'id': str(index), 'canonical_model_id': 'model', 'source_hash': 'a'*64,
                         'updated_at': '2026-01-01T00:00:00Z', 'validation_status': 'published'} for index, row in enumerate(previous)]
            def upsert(self, table, rows, conflict):
                self.writes.append(table)
                return [{**row, 'id': row['variant_name']} for row in rows]
            def _request(self, method, route, payload):
                self.writes.append(route)
                assert method == 'POST' and len(payload['p_batch']['targets']) == 3
                return {'published': 3, 'already_applied': False, 'source_verified': True}
        client = Client()
        with tempfile.TemporaryDirectory() as folder, patch('refresh_verified_variants.LOCAL', Path(folder)):
            result = publish_group(client, src, drafts, doc)
            self.assertEqual(result['published'], 0)
            self.assertEqual(client.writes, ['extracted_variant_drafts'])
            self.assertEqual(publish_group(client, src, drafts, doc, publish=True)['published'], 3)
            self.assertEqual(client.writes[-1], 'rpc/publish_variant_refresh')
            client.writes.clear()
            drafts[0]['price_sek'] = 999000
            with self.assertRaises(RefreshError):
                publish_group(client, src, drafts, doc, publish=True)
            self.assertEqual(client.writes, [], 'Remote fact conflicts are stopped before staging')

    def test_quarantine_survives_unrelated_batches_and_local_validation(self):
        failed = {'brand': 'Polestar', 'model': '4', 'variants': 2, 'status': 'quarantined'}
        self.assertEqual(merge_quarantine([failed], [{'brand': 'Polestar', 'model': '2', 'status': 'published'}]), [failed])
        self.assertEqual(merge_quarantine([failed], [{**failed, 'status': 'validated_local_only'}]), [failed])
        self.assertEqual(merge_quarantine([failed], [{**failed, 'status': 'published'}]), [])

    def test_toyota_extensionless_document_is_discovery_only_with_official_link(self):
        target = 'https://pdf.toyotasverigebroschyr.com/price-list/toyota-bz4x'
        html = f'<a href="{target}">Prislista</a><a href="https://ev-database.org/toyota-bz4x.pdf">Prislista</a>'
        doc = parse_document(html.encode(), 'text/html')
        candidates = toyota_document_candidates(doc, 'https://www.toyota.se/bilar/bz4x', 'a'*64)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['url'], target)
        self.assertFalse(candidates[0]['host_approved'])
        self.assertEqual(candidates[0]['source_validation'], 'needs_discovery')
        self.assertEqual(candidates[0]['discovery_source_hash'], 'a'*64)


if __name__ == '__main__':
    unittest.main()
