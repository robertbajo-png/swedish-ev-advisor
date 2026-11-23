import csv
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from ev_ecoc_source_review import COLUMNS, SOURCE, range_metadata, read_lines, review, sample_rows


BMW = dict(make='BMW', approval='e1*2018/858*00109*07', type='BMWi-N', variant='41CF',
           version='0AA5A000', name='iX xDrive45', category='M1', axles='2', mass_kg='2525',
           bev='Y', motor_kw='300', tyres='235/60 R20', seats='5', consumption_wh_km='183', range_km='579')
VOLVO = dict(make='VOLVO', approval='e4*2018/858*00203*01', type='T', variant='TEEV',
             version='TEST01', name='EX90', category='M1', axles='1', mass_kg='2585',
             bev='Y', motor_kw='245', tyres='255/50 R20', seats='7', consumption_wh_km='186', range_km='564')


def export(*records, drop=None):
    out = io.StringIO(newline='')
    writer = csv.writer(out, delimiter=';')
    fields = [key for key in COLUMNS if key != drop]
    writer.writerow([COLUMNS[key] for key in fields] + ['0.10. VehicleIdentificationNumber', '49. ElectricRange'])
    for record in records:
        writer.writerow([record[key] for key in fields] + ['PERSONAL_IDENTIFIER_CANARY', '999'])
    return out.getvalue().splitlines(keepends=True)


class EvEcocSourceReviewTests(unittest.TestCase):
    def test_exact_models_only_and_no_identifiers(self):
        result = review(export(BMW, BMW, VOLVO, BMW | {'variant': '51CF'},
                               VOLVO | {'name': 'EX900'}, VOLVO | {'bev': 'N'}))
        self.assertEqual(result['cohort'], {'BMW iX xDrive45': 2, 'Volvo EX90': 1})
        self.assertEqual([row['row_count'] for row in result['profiles']], [2, 1])
        self.assertNotIn('IDENTIFIER', json.dumps(result))

    def test_does_not_reconcile_different_wheels_or_conflicting_pairs(self):
        result = review(export(BMW, BMW | {'consumption_wh_km': '189', 'range_km': '560'},
                               BMW | {'tyres': '275/40 R22; second axle 275/40 R22'}))
        self.assertEqual(len(result['profiles']), 3)
        self.assertEqual({row['consumption_wh_km'] for row in result['profiles']}, {'183', '189'})

    def test_no_fallback_to_different_range_or_incomplete_profile(self):
        r = review(export(BMW | {'range_km': ''}, VOLVO | {'range_km': '99999'},
                          VOLVO | {'approval': 'unrecognized'}))
        self.assertEqual(r['profiles'], [])
        self.assertEqual(r['incomplete'], {'BMW iX xDrive45': 1, 'Volvo EX90': 2})
        with self.assertRaisesRegex(ValueError, 'required_ecoc_columns'):
            review(export(BMW, drop='consumption_wh_km'))

    def test_capture_hashes_bytes_and_rejects_partial_stream(self):
        raw = b'\xef\xbb\xbfa;b\r\n1;2\r\n'
        digest = hashlib.sha256()
        self.assertEqual(list(read_lines(io.BytesIO(raw), len(raw), digest, monotonic() + 10)),
                         ['a;b\r\n', '1;2\r\n'])
        self.assertEqual(digest.hexdigest(), hashlib.sha256(raw).hexdigest())
        with self.assertRaisesRegex(ValueError, 'ecoc_partial_download'):
            list(read_lines(io.BytesIO(raw), len(raw) + 1, digest, monotonic() + 10))
        with self.assertRaisesRegex(ValueError, 'ecoc_stream_bound_exceeded'):
            list(read_lines(io.BytesIO(raw), len(raw) - 1, digest, monotonic() + 10))

    def test_sample_discards_boundary_fragments_even_mid_character(self):
        raw = b'\xa9;partial\r\n1;2\r\n2;\xc3'
        self.assertEqual(sample_rows(raw, False).read().rstrip(), '1;2')
        self.assertEqual(sample_rows(b'prefix\r\n3;4', True).read(), '3;4')

    def test_range_requires_exact_official_bounds(self):
        class Response:
            status = 206
            geturl = lambda _: SOURCE
            headers = {'Content-Range': 'bytes 0-98/200', 'ETag': '"example"',
                       'Last-Modified': 'some date', 'Content-Length': '99'}

        self.assertEqual(range_metadata(Response(), lambda _: (0, 98))[:3], (0, 98, 200))
        with self.assertRaisesRegex(ValueError, 'ecoc_range_bounds_changed'):
            range_metadata(Response(), lambda _: (0, 99))


if __name__ == '__main__':
    unittest.main()
