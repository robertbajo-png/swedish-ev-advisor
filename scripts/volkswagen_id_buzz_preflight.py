"""Capture exact Swedish ID. Buzz observations for review, never for publication."""

import argparse
import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from audit_catalog_sources import ROOT, SourceFetcher
from build_source_queue import VOLKSWAGEN_ID_BUZZ_TECHNICAL_URL, VOLKSWAGEN_ID_BUZZ_URL

MODEL_URL = VOLKSWAGEN_ID_BUZZ_URL
TECHNICAL_URL = VOLKSWAGEN_ID_BUZZ_TECHNICAL_URL
SOURCE_URLS = (MODEL_URL, TECHNICAL_URL)
CONFIGURATOR_URLS = tuple(
    'https://www.volkswagen-transportbilar.se/sv/bygg-din-bil.html/__app/72006/edition/' + trim + '.app'
    for trim in ('pro', 'pro-4motion')
)
CHARGING_URL = ('https://www.volkswagen-utilitaires.fr/idhub/content/dam/onehub_nfz/importers/fr/'
                'documentation/fiches-tarifs/Tarif_ID_Buzz.pdf')
EDITION = r'\s+5-sits\s+\u2013\s+Sweden Olympic Edition\s+'
TERMINATOR = r'\s+7-sits\s+\u2013\s+Sweden Olympic Edition\b'


def source_allowed(url, brands):
    return brands == {'Volkswagen'} and url in SOURCE_URLS


def match_once(pattern, text, error):
    matches = list(re.finditer(pattern, text, re.IGNORECASE))
    if len(matches) != 1:
        raise ValueError(error)
    return matches[0]


def read_short_versions(text):
    text = ' '.join(text.split())
    names = ('Pro', 'Pro 4MOTION')
    markers = {name: match_once(r'\bID\. Buzz ' + name + EDITION, text, f'missing_or_duplicate_{name}')
               for name in (*names, 'GTX')}
    section_start = match_once(r'\bVersioner ID\. Buzz Pro' + EDITION, text, 'version_section_required')
    years = list(re.finditer(r'\bS\u00e4ljstarten av ID\. Buzz modell\u00e5r (20\d{2})\b',
                             text[:section_start.start()], re.I))
    if {match[1] for match in years} != {'2027'}:
        raise ValueError('model_year_required')
    year = years[-1]
    if not section_start.end() == markers['Pro'].end() < markers['Pro 4MOTION'].start() < markers['GTX'].start():
        raise ValueError('unexpected_version_order')

    result = []
    for name, end, motor, drive in (
        ('Pro', markers['Pro 4MOTION'].start(), 210, r'Bakhjulsdrift'),
        ('Pro 4MOTION', markers['GTX'].start(), 250, r'4MOTION fyrhjulsdrift'),
    ):
        current = markers[name]
        block = text[current.end():end]
        next_card = match_once(TERMINATOR, block, 'long_version_boundary_required')
        block = block[:next_card.start()]
        observations = {}

        def add(key, pattern, transform=int):
            match = match_once(pattern, block, f'{key}_missing_or_ambiguous')
            observations[key] = {'value': transform(match[1]), 'quote': match[0]}

        if not re.match(r'fr\u00e5n [1-9]\d{0,2} \d{3} kr inkl\. moms\b', block, re.I):
            raise ValueError('cash_price_heading_required')
        add('cash_from_sek', r'fr\u00e5n ([1-9]\d{0,2} \d{3}) kr inkl\. moms\b', lambda v: int(v.replace(' ', '')))
        add('body_length_cm', r'\bL\u00e4ngd:\s*(471) cm\b')
        add('motor_kw', rf'\bMotor:\s*({motor}) kW\s*/')
        add('seats_standard', r'\bSittplatser:\s*(5) \(standard\) eller 6\b')
        add('battery_net_kwh', r'\bBatterikapacitet:\s*(79) kWh \(netto\)')
        add('combined_wltp_range_up_to_km', r'\bMaximal r\u00e4ckvidd:\s*(\d{3}) km \(WLTP, blandad k\u00f6rning\)')
        add('towing_advertised_kg', r'\bDragvikt:\s*([1-9] \d{3}) kg\b', lambda v: int(v.replace(' ', '')))
        add('drivetrain', rf'\bDrivlina:\s*({drive})\b', lambda _: 'RWD' if name == 'Pro' else 'AWD')
        if name == 'Pro 4MOTION':
            add('cargo_five_seats_liters', r'\bBagageutrymme \(5 sittplatser\):\s*([1-9] \d{3}) liter\b',
                lambda v: int(v.replace(' ', '')))
        result.append({'trim': name, 'model_year': int(year[1]), 'identity_quote': current[0].strip(),
                       'model_year_quote': year[0], 'observations': observations})
    return result


def read_short_technical(text, model_text):
    text, model_text = (' '.join(value.split()) for value in (text, model_text))
    weights = match_once(
        r'<b>Vikter</b> ID\. Buzz Pro ID\. Buzz Pro 4MOTION ID\. Buzz GTX Totalvikt\b'
        r'[^<>]*?Maximal sl\u00e4pvagnslast (.*?) Exteri\u00f6r och interi\u00f6r data\b',
        text, 'exact_weight_table_required',
    )[1]
    short = r'Kort: ([1-9][. ]\d{3}) kg \(bromsad, vid 12 ?% stigning\)'
    long = r'L\u00e5ng: [1-9][. ]\d{3} kg \(bromsad, vid 12 ?% stigning\)'
    column = rf'({short}) {long} \d{{3}} kg \(obromsad\)'
    row = re.fullmatch(' '.join([column] * 3), weights, flags=re.I)
    if not row:
        raise ValueError('exact_braked_towing_columns_required')

    # The dimension graphic identifies the short body; the FAQ identifies the seating basis.
    short_cargo = match_once(
        r'Axelavst\u00e5nd: 2[. ]989 mm Bagageutrymme 1:a s\u00e4tesraden: \d[. ]\d{3} mm '
        r'2:a s\u00e4tesraden: \d[. ]\d{3} mm Bagageutrymme, bredd: \d[. ]\d{3} mm '
        r'(Bagageutrymme, volym: ([1-9][. ]\d{3}) liter \(max\)) M\u00e5tt p\u00e5 korta versionen av ID\. Buzz\b',
        text, 'exact_short_cargo_dimensions_required',
    )
    cargo_basis = match_once(
        r'Bagageutrymmet i ID\. Buzz har en volym p\u00e5 hela ([1-9][. ]\d{3}) liter '
        r'\(bakom andra s\u00e4tesraden\)', model_text, 'cargo_requires_second_row_upright',
    )
    def integer(value):
        return int(re.sub(r'[. ]', '', value))

    cargo_liters = integer(short_cargo[2])
    if cargo_liters != integer(cargo_basis[1]):
        raise ValueError('short_cargo_sources_disagree')

    return {
        'braked_towing_12pct_kg': {
            name: {'value': integer(row[index + 1]), 'quote': row[index]}
            for name, index in (('Pro', 1), ('Pro 4MOTION', 3))
        },
        'short_pro_cargo_row_two_liters': {'value': cargo_liters, 'quote': short_cargo[1],
                                          'model_page_basis_quote': cargo_basis[0]},
    }


def read_swedish_dc_claim(text):
    claim = match_once(
        r'P\u00e5 snabbladdningsstationer \(DC\) kan ID\. Buzz laddas med upp till \d{3} kW effekt '
        r'med 86 kWh-batteriet och (\d{3}) kW effekt med 79 kWh-batteriet',
        ' '.join(text.split()), 'swedish_dc_battery_scope_required',
    )
    return {'value': int(claim[1]), 'quote': claim[0], 'battery_net_kwh': 79,
            'scope': 'swedish_battery_family_claim'}


def capture(fetcher):
    sources, texts = {}, {}
    for url in SOURCE_URLS:
        result = fetcher.fetch(url, {'Volkswagen'})
        text = result.get('text', '')
        if (result.get('status') != 'reachable' or result.get('final_url') != url
                or result.get('http_status') != 200 or 'html' not in result.get('content_type', '')
                or not re.fullmatch('[a-f0-9]{64}', result.get('content_hash', ''))
                or not text or result.get('text_hash') != hashlib.sha256(text.encode('utf-8')).hexdigest()):
            raise ValueError(f'uncaptured_source: {url} ({result.get("status")})')
        sources[url] = {**{k: result[k] for k in ('content_hash', 'text_hash', 'http_status')},
                        'fetched_at': datetime.now(timezone.utc).isoformat()}
        texts[url] = text
    variants = read_short_versions(texts[MODEL_URL])
    technical = read_short_technical(texts[TECHNICAL_URL], texts[MODEL_URL])
    for variant in variants:
        if (variant['observations']['towing_advertised_kg']['value']
                != technical['braked_towing_12pct_kg'][variant['trim']]['value']):
            raise ValueError(f'towing_sources_disagree: {variant["trim"]}')
    return {
        'status': 'needs_review', 'publication_approved': False,
        'brand': 'Volkswagen', 'model': 'ID. Buzz', 'market': 'SE', 'sources': sources,
        'variant_observation_source': MODEL_URL, 'variants': variants,
        'technical_observation_source': TECHNICAL_URL, 'technical_observations': technical,
        'swedish_dc_claim': read_swedish_dc_claim(texts[MODEL_URL]),
        'release_checks_pending': ['exact_combined_consumption', 'review_swedish_and_exact_code_charging_claims',
                                   'independent_current_cash_price_and_price_type',
                                   'reviewed_exact_model_photo', 'canonical_identity_and_transaction'],
    }, texts


def read_charging_sheet(text):
    cover, separator, table = text.partition('\f')
    if not separator or not re.search(r'\bAnn\u00e9e-mod\u00e8le 2027\b', cover):
        raise ValueError('charging_sheet_requires_my2027')
    match_once(r'Mise \u00e0 jour au 21 octobre 2026\b', cover, 'charging_sheet_revision_changed')
    header = match_once(r'Code mod\u00e8le.*?nette \(kWh\).*?\(kW/ch\).*?AC/DC \(kW\)',
                        ' '.join(table.split()), 'charging_column_context_required')
    evidence = []
    for trim, model_code, motor in (('Pro', 'EBBR7R', '210/286'), ('Pro 4Motion', 'EBBR5R', '250/340')):
        candidate = match_once(rf'(?m)^ID\. Buzz {trim} Court {model_code} 79 {motor} (\d{{2}})/(\d{{3}})'
                               r'(?= [1-9]\d? \d{2},\d\b)',
                               '\n'.join(' '.join(line.split()) for line in table.splitlines()),
                               f'charging_code_or_layout_changed_{model_code}')
        if tuple(map(int, candidate.groups())) != (11, 183):
            raise ValueError(f'charging_limits_changed_{model_code}')
        evidence.append(dict(model_code=model_code, ac_charge_kw=11, dc_charge_kw=183, quote=candidate[0]))
    return {'country': 'FR', 'model_year': 2027, 'document_revision': '2026-10-21',
            'source_page': 8, 'scope': 'matching_model_code_hardware_only',
            'column_quote': header[0], 'variants': evidence,
            'status': 'needs_review', 'publication_approved': False}


def charging_pages(body, content_type):
    from pypdf import PdfReader
    if 'pdf' not in content_type or not body.startswith(b'%PDF'):
        raise ValueError('charging_sheet_pdf_required')
    reader = PdfReader(io.BytesIO(body))
    return '\f'.join(reader.pages[i].extract_text(extraction_mode='layout') for i in (0, 7))


def capture_charging(fetcher):
    result = fetcher.fetch(CHARGING_URL, {'Volkswagen'})
    if (result.get('status') != 'reachable' or result.get('final_url') != CHARGING_URL
            or result.get('http_status') != 200 or 'pdf' not in result.get('content_type', '')
            or not re.fullmatch('[a-f0-9]{64}', result.get('content_hash', ''))):
        raise ValueError('charging_sheet_unavailable')
    text = result.get('text', '')
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != result.get('text_hash'):
        raise ValueError('charging_sheet_text_hash_mismatch')
    return {**read_charging_sheet(text), 'source_url': CHARGING_URL,
            'content_hash': result['content_hash'], 'text_hash': result['text_hash'],
            'fetched_at': datetime.now(timezone.utc).isoformat()}, text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check-configurator-access', action='store_true')
    group.add_argument('--capture-charging', action='store_true')
    args = parser.parse_args()
    if args.check_configurator_access:
        fetcher = SourceFetcher(timeout=10, url_policy=lambda url, brands: brands == {'Volkswagen'} and url in CONFIGURATOR_URLS)
        receipts = {}
        for url in CONFIGURATOR_URLS:
            result = fetcher.fetch(url, {'Volkswagen'})
            if result.get('status') != 'reachable' or result.get('final_url') != url or result.get('http_status') != 200:
                raise ValueError(f'configurator_access_held: {url} ({result.get("status")})')
            receipts[url] = {'html_sha256': result['content_hash'], 'checked_at': datetime.now(timezone.utc).isoformat()}
        print(json.dumps(receipts))
        return
    if args.capture_charging:
        fetcher = SourceFetcher(timeout=18, max_bytes=16 * 1024 * 1024, text_parser=charging_pages,
                                url_policy=lambda url, brands: brands == {'Volkswagen'} and url == CHARGING_URL)
        report, text = capture_charging(fetcher)
        directory = (ROOT / 'data/local/release-data').resolve(strict=True)
        if not directory.is_relative_to(ROOT.resolve()) or any(
            part.casefold() in {'onedrive', 'onedriveconsumer', 'onedrivecommercial'} for part in directory.parts
        ):
            raise ValueError('unexpected_evidence_directory')
        output = Path(tempfile.mkdtemp(prefix='volkswagen-id-buzz-charging-', dir=directory))
        (output / 'charging-pages.txt').write_bytes(text.encode('utf-8'))
        (output / 'observations.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'output': str(output), 'variants': len(report['variants']), 'status': report['status']}))
        return
    report, texts = capture(SourceFetcher(timeout=12, url_policy=source_allowed))
    directory = ROOT / 'data/local/release-data'
    directory.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='volkswagen-id-buzz-', dir=directory))
    for name, url in zip(('model', 'technical'), SOURCE_URLS, strict=True):
        (output / f'{name}.txt').write_bytes(texts[url].encode('utf-8'))
        report['sources'][url]['text_file'] = f'{name}.txt'
    (output / 'observations.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'variants': len(report['variants']), 'status': report['status']}))


if __name__ == '__main__':
    main()
