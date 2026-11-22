"""Capture and replay private Swedish Polestar 3 Performance evidence."""

import argparse
import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from openpyxl import load_workbook

from audit_catalog_sources import ROOT, SourceFetcher
from import_mobility_sweden import parse_ranking_sheet
from variant_refresh import definition, exact_number, one, parse_document

SE = 'https://www.polestar.com/se/'
MANUAL = SE + 'manual/polestar-3/2027/article/'
SOURCES = {
    'overview.html': SE + 'polestar-3/',
    'specs.html': SE + 'polestar-3/specifications/',
    'configuration.html': SE + 'configure/polestar-3/versions/performance?customerSubtype=None&customerType=B2C&productType=Cash',
    'wltp.html': MANUAL + '0ed816eed33d98cac0a8cc377bc12bc7-32882fb459557dbec0a8b097072c55bf-8664b2fa77a7e089c0a8296870d1a409/',
    'tow.html': MANUAL + '0ed816eed33d98cac0a8cc377bc12bc7-70bede2dc073ca71c0a8b0975b1e6fa3-8664b2fa77a7e089c0a8296870d1a409/',
    'seats.html': MANUAL + '0ed816eed33d98cac0a8cc377bc12bc7-30eab915efda26f3c0a8b08a3ef5efb7-8664b2fa77a7e089c0a8296870d1a409/',
}
LIMIT = 8_000_000
MARKET_SOURCES = {
    'market.html': ('https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/'
                    'tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober'),
    'market.xlsx': ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
                    'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
                    'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx'),
}
PERFORMANCE_COLUMNS = ['Dual motor', 'Performance']


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def heading(document, tag, text):
    return one((n for n in document.nodes(tag) if n.text() == text), 'polestar_3_heading_changed')


def cells(row, tags=('td',)):
    return [node for node in row.children if getattr(node, 'tag', None) in tags]


def image(cell):
    return one(cell.nodes('img'), 'polestar_3_wltp_symbol_missing').attrs.get('src', '')


def performance_column(document):
    tables = [t for t in document.nodes('table') if [n.text() for n in t.nodes('th')] == PERFORMANCE_COLUMNS]
    table = one((t for t in tables if any(n.text().startswith('Pris ') for n in t.nodes('td'))),
                'polestar_3_price_column_changed')
    require(all(n.attrs.get(span, '1') == '1' for tag in ('th', 'td') for n in table.nodes(tag)
                for span in ('rowspan', 'colspan')), 'polestar_3_column_span_changed')
    rows = [cells(row) for row in table.nodes('tr') if cells(row)]
    require(all(len(row) == 2 for row in rows), 'polestar_3_column_count_changed')

    def value(prefix):
        row = one((r for r in rows if r[1].text().startswith(prefix)), 'polestar_3_column_row_missing')
        require(row[0].text().startswith(prefix), 'polestar_3_column_label_mismatch')
        return row[1].text()

    return value


def certified_pair(document):
    heading(document, 'h1', 'Bilens certifierade v\u00e4rden f\u00f6r r\u00e4ckvidd och elf\u00f6rbrukning')
    table = one((t for t in document.nodes('table') if [n.text() for n in t.nodes('caption')] == ['Performance']),
                'polestar_3_certified_performance_table_missing')
    # The MY27 table uses pictograms, not textual column names.
    def symbol(prefix):
        row = one((r for r in document.nodes('tr') if len(cells(r)) == 2 and cells(r)[1].text().startswith(prefix)),
                  'polestar_3_wltp_legend_changed')
        icon = image(cells(row)[0])
        require(bool(icon), 'polestar_3_wltp_symbol_missing')
        return icon

    range_icon = symbol('Certifierat v\u00e4rde f\u00f6r bilens potentiella r\u00e4ckvidd')
    consumption_icon = symbol('Certifierat v\u00e4rde f\u00f6r bilens elf\u00f6rbrukning')
    city_icon = symbol('Stads- och f\u00f6rortsk\u00f6rning')
    combined_icon = symbol('Medelv\u00e4rde \u00f6ver alla fyra k\u00f6rcykelfaser')
    low_icon = symbol('L\u00e5gt v\u00e4rde.')
    high_icon = symbol('H\u00f6gt v\u00e4rde.')
    require(len({range_icon, consumption_icon, city_icon, combined_icon, low_icon, high_icon}) == 6,
            'polestar_3_wltp_legend_ambiguous')
    rows = [cells(r) for r in table.nodes('tr')]
    require([len(row) for row in rows] == [3, 2, 4, 4]
            and rows[0][1].attrs.get('colspan') == '2'
            and [image(c) for c in rows[0][1:]] == [range_icon, consumption_icon]
            and [image(c) for c in rows[1]] == [city_icon, combined_icon]
            and [image(row[0]) for row in rows[2:]] == [low_icon, high_icon],
            'polestar_3_wltp_table_scope_changed')
    low, high = [[c.text() for c in row[1:]] for row in rows[2:]]
    wltp = [int(exact_number(row[1], r'(\d{3})')) for row in (low, high)]
    consumption = [exact_number(row[2], r'(\d{2},\d)') for row in (low, high)]
    require(wltp[0] > wltp[1] and consumption[0] < consumption[1], 'polestar_3_wltp_endpoint_conflict')
    return wltp[0], consumption, 'Performance | ' + ' | '.join(low + high)


def seat_positions(document):
    heading(document, 'h1', '\u00d6versiktstabell \u00f6ver l\u00e4mpliga placeringar av barnskydd')
    table = one((t for t in document.nodes('table')
                 if any(n.text().startswith('S\u00e4tesplats ') for n in t.nodes('th'))),
                'polestar_3_seat_table_missing')
    headings = [n.text() for n in table.nodes('th')]
    # The front passenger position appears twice, once for each airbag state.
    require(len(headings) == 7 and headings[1] == '1' and headings[2].startswith('2 (med inaktiverad krockkudde,')
            and headings[3].startswith('2 (med aktiverad krockkudde,') and headings[4:] == ['3', '4', '5'],
            'polestar_3_seat_positions_changed')
    return 5, ' | '.join(headings)


def configuration_identity(document):
    heading(document, 'h1', 'Polestar 3 Performance')
    require('22-tums Performance-f\u00e4lgar' in document.text(), 'polestar_3_config_wheel_scope_changed')
    # Read the public serialized rules as text. The selected default PNO is Dual motor.
    ref = r'\$R\[\d+\]='
    anchors = (
        r'\["configuration-rules",' + ref + r'\{pno3:"359",modelYear:"2027",locale:"se",',
        r'title:"Performance",shortTitle:"Performance",[^}]{1,640}slug:"performance",pnoType:"engine",pnoCode:"DA",',
        r'preview:"359 - 2027 - DA - Engine - 22-inch Performance wheels"',
        r'from:' + ref + r'\{code:"XPFWHE",pnoType:"options"\},to:' + ref
        + r'\[' + ref + r'\{code:"DA",pnoType:"engine"\}\],onlyAvailableWith:!0',
    )
    scripts = (''.join(x for x in node.children if isinstance(x, str)) for node in document.nodes('script'))
    by_script = ([re.findall(pattern, script) for pattern in anchors] for script in scripts)
    matches = one((groups for groups in by_script if all(len(group) == 1 for group in groups)),
                  'polestar_3_swedish_my27_engine_rule_changed')
    return ' | '.join(group[0] for group in matches)


def review(files):
    require(files.keys() == SOURCES.keys(), 'polestar_3_exact_source_set_required')
    require(all(0 < len(raw) <= LIMIT for raw in files.values()), 'polestar_3_source_size_changed')
    docs = {name: parse_document(raw, 'text/html') for name, raw in files.items()}
    sources = {name: {'source_url': SOURCES[name], 'source_hash': hashlib.sha256(raw).hexdigest()}
               for name, raw in files.items()}
    for name in ('wltp.html', 'tow.html', 'seats.html'):
        require('Polestar 3 - 2027' in docs[name].text(), 'polestar_3_manual_model_year_changed')
    heading(docs['overview.html'], 'h1', 'Polestar 3')
    suv = heading(docs['overview.html'], 'h2', 'Ja, det \u00e4r en SUV. Med k\u00e4nslan av en sportbil.')
    configuration_quote = configuration_identity(docs['configuration.html'])
    specs = docs['specs.html']
    require(any(n.text().startswith('Polestar 3 - Tekniska specifikationer') for n in specs.nodes('title')),
            'polestar_3_specs_model_changed')
    column = performance_column(specs)
    price_quote = column('Pris ')
    price = exact_number(price_quote, r'Pris ([\d ]+) kr')
    power_quote = column('Effekt\u00b9 ')
    power = exact_number(power_quote, r'Effekt\u00b9 (\d+) kW\s*/\s*680 hk')
    require(power == 500, 'polestar_3_800_v_powertrain_changed')
    drivetrain = column('Drivlina ')
    require(drivetrain == 'Drivlina Fyrhjulsdrift', 'polestar_3_drivetrain_changed')
    ranges_seen = exact_number(column('R\u00e4ckvidd (WLTP)\u00b2 '), r'R\u00e4ckvidd \(WLTP\)\u00b2 (\d{3}) km')
    consumption_re = r'Energikonsumtion \(WLTP\)\u00b2 (\d{2},\d) - (\d{2},\d) kWh/100 km'
    consumption_match = re.fullmatch(consumption_re, column('Energikonsumtion (WLTP)\u00b2 '))
    require(consumption_match is not None, 'polestar_3_consumption_range_changed')
    consumption_seen = [float(n.replace(',', '.')) for n in consumption_match.groups()]
    wltp, consumption, wltp_quote = certified_pair(docs['wltp.html'])
    require((wltp, consumption) == (ranges_seen, consumption_seen), 'polestar_3_certified_wltp_conflict')
    tow_seen = exact_number(column('Dragkraft '), r'Dragkraft Upp till ([\d ]+) kg')
    braked = heading(docs['tow.html'], 'h2', 'Bromsad sl\u00e4pvagn')
    tow_row = one((cells(r) for r in braked.parent.nodes('tr') if len(cells(r)) == 2
                   and cells(r)[0].text() == 'Max. sl\u00e4pvagnsvikt'), 'polestar_3_braked_tow_missing')
    tow = exact_number(tow_row[1].text(), r'([\d ]+) kg')
    require(tow == tow_seen, 'polestar_3_braked_tow_conflict')
    seats, seats_quote = seat_positions(docs['seats.html'])

    def proof(name, value, quote, scope):
        return {**sources[name], 'value': value, 'source_quote': quote, 'scope': scope}

    def shared(label, pattern, scope):
        term, description = definition(specs, label)
        return proof('specs.html', exact_number(description, pattern), f'{term} {description}', scope)

    facts = {
        'wltp_range_km': proof('wltp.html', wltp, wltp_quote, 'my27_performance_quoted_combined_wltp_maximum'),
        'wltp_consumption_kwh_100km': proof('wltp.html', consumption[0], wltp_quote, 'my27_performance_paired_combined_wltp_minimum'),
        'battery_kwh': shared('Batteri', r'800 V Litiumjonbatteri (106) kWh kapacitet, 16 moduler', '800_v_capacity_not_usable_claim'),
        'dc_charge_kw': shared('Laddkapacitet', r'Upp till (\d+) kW \(800 V\) Upp till 120 kW \(400 V\)', 'peak_dc_at_800_v'),
        'ac_charge_kw': shared('Hemma- eller publik laddning (0-100%)', r'\d+ timmar \((\d+) kW AC\)\u00b9', 'ac_charging_basis'),
        'boot_liters': shared('Volym (s\u00e4ten uppf\u00e4llda)',
                              r'(\d+) liter upp till ryggst\u00f6den, inklusive 90 liter under golvet \d+ liter upp till innertaket, inklusive 90 liter under golvet',
                              'rear_seats_up_to_backrests_includes_underfloor_not_frunk'),
        'tow_kg': proof('tow.html', int(tow), f'{braked.text()} | {tow_row[0].text()} {tow_row[1].text()}', 'braked'),
        'seats': proof('seats.html', seats, seats_quote, 'my27_five_unique_left_hand_drive_seat_positions'),
        'drivetrain': proof('specs.html', 'AWD', drivetrain, 'performance_column'),
    }
    require(100_000 <= price <= 3_000_000 and 50 <= wltp <= 1200 and 5 <= consumption[0] <= 60
            and 0 <= tow <= 4000 and 20 <= facts['dc_charge_kw']['value'] <= 600
            and 1 <= facts['ac_charge_kw']['value'] <= 44 and 1 <= facts['boot_liters']['value'] <= 3000,
            'polestar_3_specification_out_of_bounds')
    return {
        'status': 'technical_source_review_held', 'market': 'SE', 'model': 'Polestar 3',
        'variant': 'Performance', 'technical_manual_model_year': 2027, 'market_configuration_model_year': 2027,
        'configuration': {**proof('configuration.html', '359/DA/XPFWHE', configuration_quote,
                                 'swedish_b2c_cash_model_engine_and_standard_wheels'),
                          'wheel_inches': 22, 'configuration_price_returned': False},
        'powertrain': proof('specs.html', int(power), power_quote, 'performance_column_kw'),
        'price': proof('specs.html', int(price), price_quote, 'manufacturer_listed_variant_price_sek'),
        'body': proof('overview.html', 'SUV', suv.text(), 'model_body'),
        'facts': facts, 'sources': sources,
        'held': ['review_exact_model_photo_and_rights', 'verify_canonical_draft_and_alias',
                 'isolated_insertion_and_release_review'],
        'publication_approved': False, 'database_writes': 0, 'paid_calls': 0,
    }


def review_market(files):
    article, workbook_url = MARKET_SOURCES.values()
    require(files.keys() == MARKET_SOURCES.keys(), 'polestar_3_exact_market_sources_required')
    require(any(urljoin(article, n.attrs.get('href', '')) == workbook_url
                for n in parse_document(files['market.html'], 'text/html').nodes('a')),
            'polestar_3_official_workbook_link_missing')
    workbook = load_workbook(io.BytesIO(files['market.xlsx']), read_only=True, data_only=True)
    try:
        rows, _ = parse_ranking_sheet(workbook['Elbil ranking'], article)
        row = one((model for model in rows if (model.brand_raw, model.model_raw, model.fuel_type_raw) ==
                   ('POLESTAR', '3', 'EL')), 'polestar_3_exact_bev_row_missing')
        require(row.last_seen_month == '2026-10-01' and row.registrations_last_month > 0
                and not row.needs_mapping and not row.model_group,
                'polestar_3_market_month_or_identity_changed')
        return {
            'row': {key: getattr(row, key) for key in ('brand_raw', 'model_raw', 'fuel_type_raw', 'normalized_brand',
                'normalized_model', 'last_seen_month', 'registrations_last_month', 'registrations_ytd')},
            'sources': {key: {'source_url': url, 'source_hash': hashlib.sha256(files[key]).hexdigest()}
                        for key, url in MARKET_SOURCES.items()},
        }
    finally:
        workbook.close()


def checked_report(files, timestamps):
    report = {'source_capture_times': timestamps, **review({name: files[name] for name in SOURCES})}
    if files.keys() != SOURCES.keys():
        require(files.keys() == (SOURCES | MARKET_SOURCES).keys(), 'polestar_3_source_set_changed')
        report['market_index'] = review_market({name: files[name] for name in MARKET_SOURCES})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    parser.add_argument('--include-market', action='store_true')
    args = parser.parse_args()
    require(not args.include_market or args.capture, 'polestar_3_include_market_requires_capture')
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    require(root == ROOT.resolve() / 'data/local/release-data'
            and not any(re.fullmatch(r'onedrive(?:commercial|consumer)?', part, re.I) for part in root.parts),
            'polestar_3_private_release_directory_required')
    if args.capture:
        fetcher = SourceFetcher(timeout=20, max_bytes=LIMIT, document_parser=lambda body, _: body)
        files = {}
        timestamps = {}
        urls = SOURCES | MARKET_SOURCES if args.include_market else SOURCES
        market_fetcher = SourceFetcher(timeout=30, max_bytes=LIMIT, document_parser=lambda body, _: body,
                                      text_parser=lambda *_: '',
                                      url_policy=lambda url, _: url in MARKET_SOURCES.values())
        for name, url in urls.items():
            result = (market_fetcher if name in MARKET_SOURCES else fetcher).fetch(url, ('Polestar',))
            require(result['status'] == 'reachable' and result.get('http_status') == 200
                    and result.get('final_url') == url, f'polestar_3_source_unavailable: {name} {result["status"]}')
            files[name] = result['document']
            timestamps[name] = datetime.now(timezone.utc).isoformat()
        report = checked_report(files, timestamps)
        folder = Path(tempfile.mkdtemp(prefix='polestar-3-review-', dir=root))
        for name, raw in files.items():
            (folder / name).write_bytes(raw)
        (folder / 'review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    else:
        folder = args.replay.resolve(strict=True)
        require(folder == args.replay.absolute() and folder.parent == root
                and re.fullmatch(r'polestar-3-review-[a-z0-9_]+', folder.name), 'polestar_3_private_capture_required')

        def read(name, limit):
            path = folder / name
            require(path.resolve(strict=True) == path and path.is_file() and path.stat().st_size <= limit,
                    'polestar_3_regular_capture_file_required')
            return path.read_bytes()

        saved = json.loads(read('review.json', 100_000))
        timestamps = saved['source_capture_times']
        require(timestamps.keys() in (SOURCES.keys(), (SOURCES | MARKET_SOURCES).keys())
                and all(datetime.fromisoformat(t).utcoffset() == timezone.utc.utcoffset(None) for t in timestamps.values()),
                'polestar_3_capture_times_invalid')
        report = checked_report({name: read(name, LIMIT) for name in timestamps}, timestamps)
        require(report == saved, 'polestar_3_capture_or_review_changed')
    print(json.dumps({'review': str(folder / 'review.json'), 'technical_facts': len(report['facts']),
                      'status': report['status'], 'publication_approved': False}))


if __name__ == '__main__':
    main()
