"""Stream ASTRA's public EU CoC export into a private, non-identifying review."""

import argparse
import csv
import hashlib
import io
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from time import monotonic
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://opendata.astra.admin.ch/ivzod/3000-eDatenblatt/eDatenblatt.csv'
MAX_BYTES = 950_000_000
MAX_LINE = 256_000
HEAD_BYTES = 32_768
SAMPLE_BYTES = 16_000_000
COLUMNS = {
    'make': '0.1. Make',
    'approval': '0.2. TypeApprovalNumber',
    'type': '0.2. Type',
    'variant': '0.2. Variant',
    'version': '0.2. Version',
    'name': '0.2.1. CommercialName',
    'category': '0.4. VehicleCategoryCode',
    'axles': '3. NumberOfPoweredAxles',
    'mass_kg': '13.2. ActualMassOfTheVehicle',
    'bev': '23. PureElectricVehIndicator',
    'motor_kw': '27.3. MaximumNetPowerElectricEngine',
    'tyres': '35. Tyres',
    'seats': '42. NrOfSeatingPositions',
    'consumption_wh_km': '49. WLTPElecEnergyConsPureElectric',
    'range_km': '49. WLTPElectricRangePureElectric',
}
PROFILE = ('approval', 'type', 'variant', 'version', 'axles', 'mass_kg', 'motor_kw',
           'tyres', 'seats', 'consumption_wh_km', 'range_km')


def number(value, lower, upper):
    if not re.fullmatch(r'\d+(?:[.,]\d+)?', value):
        return False
    return lower <= float(value.replace(',', '.')) <= upper


def review(lines):
    reader = csv.reader(lines, delimiter=';', strict=True)
    header = next(reader, [])
    if any(header.count(name) != 1 for name in COLUMNS.values()):
        raise ValueError('required_ecoc_columns_missing_or_repeated')
    at = {key: header.index(name) for key, name in COLUMNS.items()}
    populations = Counter()
    incomplete = Counter()
    profiles = Counter()
    for row in reader:
        if not row:
            continue
        if len(row) != len(header):
            raise ValueError('ecoc_row_shape_changed')
        make = row[at['make']].strip().upper()
        if make not in ('BMW', 'VOLVO'):
            continue
        name = row[at['name']].strip().upper()
        variant = row[at['variant']].strip().upper()
        if make == 'BMW' and variant == '41CF' and name in ('IX XDRIVE45', 'IX 45 XDRIVE'):
            model = 'BMW iX xDrive45'
        elif make == 'VOLVO' and re.match(r'^EX90(?:$|\s)', name):
            model = 'Volvo EX90'
        else:
            continue
        if row[at['bev']].strip() != 'Y' or row[at['category']].strip() != 'M1':
            continue
        populations[model] += 1
        values = {key: row[at[key]].strip() for key in PROFILE}
        if (not all(values[key] for key in PROFILE)
                or not re.fullmatch(r'e\d+\*2018/858\*\d+\*\d+', values['approval'], re.I)
                or not number(values['range_km'], 50, 1200)
                or not number(values['consumption_wh_km'], 60, 500)):
            incomplete[model] += 1
            continue
        values['approval'] = values['approval'].lower()
        values['type'] = values['type'].upper()
        values['variant'] = values['variant'].upper()
        values['version'] = values['version'].upper()
        profiles[(model, *(values[key] for key in PROFILE))] += 1
        if len(profiles) > 10_000:
            raise ValueError('ecoc_review_profile_limit')
    return {
        'cohort': dict(sorted(populations.items())),
        'incomplete': dict(sorted(incomplete.items())),
        'profiles': [{'model': key[0], **dict(zip(PROFILE, key[1:])), 'row_count': count}
                     for key, count in sorted(profiles.items())],
    }


def read_lines(source, expected, digest, deadline):
    seen = 0
    while True:
        if monotonic() > deadline:
            raise TimeoutError('ecoc_stream_time_limit')
        raw = source.readline(MAX_LINE + 1)
        if not raw:
            break
        if len(raw) > MAX_LINE or seen + len(raw) > expected:
            raise ValueError('ecoc_stream_bound_exceeded')
        digest.update(raw)
        first = seen == 0
        seen += len(raw)
        yield raw.decode('utf-8-sig' if first else 'utf-8')
    if seen != expected:
        raise ValueError('ecoc_partial_download')


def capture():
    request = Request(SOURCE, headers={'User-Agent': 'Elbilsagenten (public CoC source review; kontakt@boleoai.se)',
                                       'Accept-Encoding': 'identity'})
    with urlopen(request, timeout=20) as source:
        if (source.geturl() != SOURCE or source.status != 200
                or source.headers.get('Content-Encoding', 'identity').lower() != 'identity'
                or source.headers.get('Content-Range')
                or not source.headers.get('Last-Modified')):
            raise ValueError('exact_public_ecoc_response_required')
        size = int(source.headers.get('Content-Length', '0'))
        if not 0 < size <= MAX_BYTES:
            raise ValueError('ecoc_source_size_requires_review')
        digest = hashlib.sha256()
        result = review(read_lines(source, size, digest, monotonic() + 360))
        result.update(source_url=SOURCE, source_bytes=size, source_sha256=digest.hexdigest(),
                      source_last_modified=source.headers['Last-Modified'])
    result.update(status='private_cross_market_research', dataset_market='CH',
                  collected_at=datetime.now(timezone.utc).isoformat(), swedish_configuration_verified=False,
                  publication_approved=False, database_writes=0, paid_calls=0)
    return result


def range_metadata(response, expected):
    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
    tag = response.headers.get('ETag', '')
    updated = response.headers.get('Last-Modified')
    if (response.geturl() != SOURCE or response.status != 206 or not match or not updated
            or not re.fullmatch(r'"[^"]+"', tag)
            or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
        raise ValueError('exact_ecoc_range_response_required')
    start, end, total = map(int, match.groups())
    if ((start, end) != expected(total) or not (end < total <= MAX_BYTES)
            or response.headers.get('Content-Length') != str(end - start + 1)):
        raise ValueError('ecoc_range_bounds_changed')
    return start, end, total, tag, updated


def sample_rows(body, ends_at_eof):
    # The first and last records may straddle the sample boundaries.
    _, _, after_first = body.partition(b'\n')
    whole_rows = after_first if ends_at_eof else after_first.rpartition(b'\n')[0]
    if not whole_rows:
        raise ValueError('ecoc_no_complete_sample_rows')
    return io.StringIO(whole_rows.decode('utf-8'), newline='')


def capture_sample(offset=None):
    headers = {'User-Agent': 'Elbilsagenten (public CoC source review; kontakt@boleoai.se)',
               'Accept-Encoding': 'identity'}
    with urlopen(Request(SOURCE, headers=headers | {'Range': f'bytes=0-{HEAD_BYTES - 1}'}), timeout=20) as source:
        _, _, total, tag, updated = range_metadata(source, lambda _: (0, HEAD_BYTES - 1))
        raw_header_sample = source.read(HEAD_BYTES + 1)
        if len(raw_header_sample) != HEAD_BYTES:
            raise ValueError('ecoc_partial_header_download')
        header = raw_header_sample.split(b'\n', 1)[0].decode('utf-8-sig') + '\n'
    if total <= (HEAD_BYTES + SAMPLE_BYTES):
        raise ValueError('ecoc_tail_is_not_a_bounded_sample')
    start = total - SAMPLE_BYTES if offset is None else offset
    end = start + SAMPLE_BYTES - 1
    if not HEAD_BYTES <= start <= end < total:
        raise ValueError('ecoc_sample_offset_out_of_bounds')
    request = Request(SOURCE, headers=headers | {'Range': f'bytes={start}-{end}', 'If-Match': tag})
    with urlopen(request, timeout=20) as source:
        observed = range_metadata(source, lambda _: (start, end))
        if observed != (start, end, total, tag, updated):
            raise ValueError('ecoc_source_changed_between_ranges')
        body = source.read(SAMPLE_BYTES + 1)
        if len(body) != SAMPLE_BYTES:
            raise ValueError('ecoc_incomplete_sample')
        result = review(chain((header,), sample_rows(body, end == total - 1)))
    return result | dict(status='private_cross_market_sample', dataset_market='CH', full_scan=False,
                         source_url=SOURCE, source_last_modified=updated, source_etag=tag,
                         source_total_bytes=total, sample_byte_range=[start, end],
                         header_sample_sha256=hashlib.sha256(raw_header_sample).hexdigest(),
                         sample_sha256=hashlib.sha256(body).hexdigest(), source_sample_bytes=SAMPLE_BYTES,
                         collected_at=datetime.now(timezone.utc).isoformat(),
                         swedish_configuration_verified=False, publication_approved=False,
                         database_writes=0, paid_calls=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--sample-tail', action='store_true')
    mode.add_argument('--sample-offset', type=int)
    args = parser.parse_args()
    local = ROOT / 'data/local/release-data'
    if local.resolve(strict=True) != local or any(
            re.fullmatch(r'onedrive(?:commercial|consumer)?', part, re.I) for part in local.parts):
        raise ValueError('private_local_release_directory_required')
    result = capture() if args.capture else capture_sample(args.sample_offset)
    output = Path(tempfile.mkdtemp(prefix='ev-ecoc-source-review-', dir=local)) / 'review.json'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'cohort': result['cohort'], 'incomplete': result['incomplete'],
                      'profiles': len(result['profiles']), 'status': result['status'],
                      'publication_approved': False, 'database_writes': 0}))


if __name__ == '__main__':
    main()
