"""Capture and replay separate Swedish Ford Puma Gen-E MY27 variants."""

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

from audit_catalog_sources import ROOT, SourceFetcher, source_text
from import_mobility_sweden import parse_ranking_sheet
from variant_refresh import one, parse_document

MODEL = 'https://www.ford.se/bilar/personbilar-och-suver/puma-gen-e'
PRICE_LIST = ('https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/'
              'media/project/hedin/distribution-cars/fordsesite/cardocuments/puma-gen-e/prislista-puma-gen-e.pdf')
SOURCES = {'model.html': MODEL, 'prices.pdf': PRICE_LIST}
HARDWARE_SOURCES = {
    'ford-se-factsheet.pdf': 'https://mnd-assets.mynewsdesk.com/image/upload/f_pdf,fl_attachment/azzjl64uf6du139svior94',
    'ford-dk-prices.html': 'https://katalog.ford.dk/prislister/personbiler/puma_gen-E/',
    'ford-dk-technical.html': 'https://katalog.ford.dk/specifikationer/puma-gen-e/',
}
MARKET_SOURCES = {
    'market.html': ('https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/'
                    'tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober'),
    'market.xlsx': ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
                    'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
                    'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx'),
}
TECHNICAL_SOURCES = SOURCES | HARDWARE_SOURCES
FULL_SOURCES = TECHNICAL_SOURCES | MARKET_SOURCES
LIMIT = 8_000_000
NAMES = ('Gen-E', 'Gen-E Premium')
PRICE_HEADER = ('Modellvariant hk / kW R\u00e4ckvidd upp till * F\u00f6rbrukning* kWh/100km '
                'Fordonsskatt (\u00c5r 1-3) F\u00f6rm\u00e5nsv\u00e4rde (50%) Rek. pris Rek. Edition pris')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def market_sections(body):
    doc = parse_document(body, 'text/html')
    require([n.text() for n in doc.nodes('h1')] == ['Puma Gen-E']
            and 'Helt elektrisk' in doc.text(), 'puma_electric_model_identity_required')
    links = {n.attrs.get('href') for n in doc.nodes('a') if n.text() == 'Ladda ner prislista'}
    require(links == {PRICE_LIST}, 'puma_current_importer_price_link_changed')
    cargo = one((n for n in doc.nodes('h3') if n.text() == 'Rymlig interi\u00f6r'),
                'puma_rear_cargo_section_missing').parent.text()
    cargo_value = one(re.finditer(r'Gigaboxen under golvet \(totalt (\d+) liter\)', cargo),
                      'puma_rear_cargo_scope_missing')
    boot = int(cargo_value[1])
    require('bak' in cargo and 'fram (upp till 43 liter)' in cargo, 'puma_rear_cargo_not_separated_from_frunk')
    cards = {}
    for name in NAMES:
        title = one((n for n in doc.nodes('h3') if n.text() == 'Puma ' + name),
                    'puma_exact_trim_card_missing')
        card = title.parent.text()
        value = re.fullmatch(r'Puma ' + re.escape(name) + r' Pris fr\u00e5n ([\d ]+) kr\. FWD 168 hk '
                             r'Laddhastighet \(10-80%\) 26 min R\u00e4ckvidd upp till (\d+) km', card)
        require(value, 'puma_exact_trim_card_changed')
        cards[name] = (int(value[1].replace(' ', '')), int(value[2]), card)
    return cards, boot, cargo


def price_rows(text):
    text = ' '.join(text.split())
    require(text.startswith('Puma Gen-E Prislista 4 - 2026 MY27 '), 'puma_swedish_price_model_year_changed')
    require(text.count(PRICE_HEADER) == 1 and 'Max r\u00e4ckvidd enligt Worldwide Harmonised' in text,
            'puma_price_columns_or_wltp_basis_changed')
    table = text.split(PRICE_HEADER, 1)[1].split('Tillvalspaket & Tillval', 1)[0].strip()
    row = (r'(?P<name>Gen-E(?: Premium)?) \((?P<battery>46,8) kWh\) 168 hk \(124 kW\) '
           r'(?P<range>\d{3}) (?P<consumption>\d{2},\d) \d+ kr \d{1,2} \d{3} kr '
           r'(?P<list_price>\d{3} \d{3}) kr (?P<edition_price>\d{3} \d{3}) kr')
    matches = list(re.finditer(row, table))
    require([m['name'] for m in matches] == list(NAMES)
            and ' '.join(m[0] for m in matches) == table, 'puma_exact_my27_two_rows_required')
    equipment = text.split('Gen-E - Standardutrustning urval', 1)
    require(len(equipment) == 2 and 'Gen-E Premium - standardutrustning urval ut\u00f6ver Gen-E' in equipment[1],
            'puma_shared_equipment_scope_changed')
    shared = equipment[1].split('Gen-E Premium - standardutrustning urval ut\u00f6ver Gen-E', 1)[0]
    ac = one(re.finditer(r'(\d+) kW 3-fasladdare \(Ombordladdare\)', shared), 'puma_onboard_ac_required')
    dc = one(re.finditer(r'Upp till (\d+) kW DC-snabbladdning', shared), 'puma_vehicle_dc_peak_required')
    return matches, ac, dc


def ipaper_pages(body, url, page_count):
    html = body.decode('utf-8')
    start = one(re.finditer(r'<script\b[^>]*>\s*window\.staticSettings\s*=\s*', html),
                'puma_ipaper_settings_missing').end()
    settings, _ = json.JSONDecoder().raw_decode(html[start:])
    require(isinstance(settings, dict) and settings.get('url') == '/' + url.split('/', 3)[3]
            and settings.get('countryCode') == 45, 'puma_ipaper_identity_changed')
    pages = settings.get('pageTexts')
    require(isinstance(pages, list) and len(pages) == page_count
            and all(isinstance(p, str) and p.strip() for p in pages), 'puma_ipaper_page_set_changed')
    return [' '.join(p.split()) for p in pages]


def hardware_evidence(files, parse_pdf, swedish_price_text, swedish_boot):
    dk_price = ipaper_pages(files['ford-dk-prices.html'], HARDWARE_SOURCES['ford-dk-prices.html'], 2)[0]
    require(dk_price.startswith('FORD PUMA GEN-E Vejl. prisliste d. 12/10-2026 SUV ')
            and 'Priserne g\u00e6lder model\u00e5r 2027.00 ' in dk_price, 'puma_dk_my27_price_identity_changed')
    towing = one(re.finditer(
        r'Maks\. anh\u00e6ngerv\u00e6gt \(med/uden bremser\) Halv\u00e5rlig ejerafgift Vejl\. udsalgspris Elbil '
        r'Select Black Edition Premium (?:124 kW/168 hk ){3}(?:\d{3} km ){3}'
        r'(\d{3}) / \d{3} kg (\d{3}) / \d{3} kg (\d{3}) / \d{3} kg ', dk_price),
        'puma_dk_braked_tow_columns_changed')
    battery = one(re.finditer(
        r'Batterikapacitet \(Netto\) Maks\. lade effekt \(AC/DC\) Lade tid \(AC\) \(0-100%\) '
        r'Lade tid \(DC\) \(10-80%\) Select Elektrisk forbrug Black Edition Premium '
        r'Puma Gen-E (\d{2},\d) kWh (\d{1,2}) / (\d{2,3}) kW 8 t\. 24 min\. 26 min\.', dk_price),
        'puma_dk_usable_battery_columns_changed')
    require('Dragkrok (avtagbar) 8 000 kr 8 000 kr' in swedish_price_text, 'puma_se_tow_option_missing')

    dims = ipaper_pages(files['ford-dk-technical.html'], HARDWARE_SOURCES['ford-dk-technical.html'], 8)[5]
    require(dims.startswith('FORD PUMA GEN-E TEKNISKE SPECIFIKATIONER UDVENDIGE DIMENSIONER ')
            and 'SELECT BLACK EDITION 17/9-2026 PREMIUM' in dims, 'puma_dk_dimensions_identity_changed')
    dimension_scope = ('Bagagerumsvolumen (uden bagagerumsbund), bag 2. s\u00e6der\u00e6kke til rygl\u00e6nskant, l. '
                       'Bagagerumsvolumen (uden bagagerumsbund), bag 2. s\u00e6der\u00e6kke til tag, l. '
                       'Bagagerumsvolumen (uden bagagerumsbund), bag 1. s\u00e6der\u00e6kke til tag, l. Gigabox, l. Frunk, l.')
    require(dims.count(dimension_scope) == 1, 'puma_dk_cargo_labels_changed')
    dim_values = dims.rsplit('Tromler ', 1)[-1]
    cargo_row = (r'(\d{3}) \d{3} \d\.\d{3} \d{3} \d{2} '
                 r'\d\.\d{3} / (?:\d{3}|-) \d\.\d{3} \d{3} / (?:\d{3}|-) \d{3}')
    cargo = re.fullmatch(' '.join([cargo_row] * 3), dim_values)
    require(cargo and set(cargo.groups()) == {str(swedish_boot)}, 'puma_dk_seats_up_cargo_conflict')

    se = ' '.join(parse_pdf(files['ford-se-factsheet.pdf']).split())
    require('FORD PUMA GEN-E LAUNCH SPECIFICATION HIGHLIGHTS 2 series Ford Puma Gen-E Ford Puma Gen-E Premium'
            in se and 'WEIGHTS: Ford Puma Gen-E Ford Puma Gen-E Premium' in se
            and 'DIMENSIONS: Ford Puma Gen-E Ford Puma Gen-E Premium' in se, 'puma_se_factsheet_identity_changed')
    braked = one(re.finditer(r'Max\. towable braked 12% gradient \(kg\) 15 (\d{3}) (\d{3})', se),
                 'puma_se_braked_tow_row_missing')
    seats_up = one(re.finditer(r'Luggage capacity ([1-9])-seat mode laden to seat back height without load floor '
                               r'\(litres\) 5 (\d{3}) (\d{3})', se), 'puma_se_seats_up_cargo_row_missing')
    require(tuple(towing.groups()) == (braked[1], braked[1], braked[2])
            and 0 < int(braked[1]) <= 4000 and 0 < int(braked[2]) <= 4000, 'puma_se_dk_braked_tow_conflict')
    require(seats_up[1] == '5' and seats_up[2] == seats_up[3] == str(swedish_boot),
            'puma_se_seats_up_cargo_conflict')
    return {'towing': towing, 'braked': braked, 'battery': battery, 'seats_up': seats_up,
            'cargo_scope': dimension_scope, 'cargo_columns': dim_values}


def market_index(files):
    article, workbook_url = MARKET_SOURCES.values()
    links = parse_document(files['market.html'], 'text/html').nodes('a')
    require(any(urljoin(article, n.attrs.get('href', '')) == workbook_url for n in links),
            'puma_official_workbook_link_missing')
    workbook = load_workbook(io.BytesIO(files['market.xlsx']), read_only=True, data_only=True)
    try:
        rows, _ = parse_ranking_sheet(workbook['Elbil ranking'], article)
        result = one((r for r in rows if (r.brand_raw, r.model_raw, r.fuel_type_raw) == ('FORD', 'PUMA', 'EL')),
                     'puma_exact_el_market_row_required')
        require(not result.needs_mapping and result.last_seen_month == '2026-10-01'
                and result.registrations_last_month > 0, 'puma_exact_october_presence_required')
        return {'brand_raw': result.brand_raw, 'model_raw': result.model_raw, 'fuel_type_raw': result.fuel_type_raw,
                'normalized_brand': result.normalized_brand, 'normalized_model': result.normalized_model,
                'needs_mapping': result.needs_mapping, 'last_seen_month': result.last_seen_month,
                'registrations_last_month': result.registrations_last_month, 'registrations_ytd': result.registrations_ytd,
                'source_url': workbook_url, 'source_name': 'Mobility Sweden'}
    finally:
        workbook.close()


def review(files, *, price_text=None):
    with_market = files.keys() == FULL_SOURCES.keys()
    extended = with_market or files.keys() == TECHNICAL_SOURCES.keys()
    require(extended or files.keys() == SOURCES.keys(), 'puma_review_source_set_changed')
    require(all(0 < len(raw) <= LIMIT and (not name.endswith('.pdf') or raw.startswith(b'%PDF-'))
                for name, raw in files.items()),
            'puma_review_body_invalid')
    # The injectable parser is only used by offline test fixtures.
    parse_price = price_text or (lambda body: source_text(body, 'application/pdf'))
    swedish_prices = ' '.join(parse_price(files['prices.pdf']).split())
    rows, ac, dc = price_rows(swedish_prices)
    cards, boot, cargo_quote = market_sections(files['model.html'])
    supporting = hardware_evidence(files, parse_price, swedish_prices, boot) if extended else None
    sources = {name: {'source_url': FULL_SOURCES[name], 'source_hash': hashlib.sha256(raw).hexdigest()}
               for name, raw in files.items()}

    def proof(src, value, quote, scope):
        return {**sources[src], 'value': value, 'source_quote': quote, 'scope': scope}

    def hardware(value, quote, scope):
        return proof('prices.pdf', value, quote, scope)

    variants = []
    for index, row in enumerate(rows):
        name = row['name']
        cash = int(row['list_price'].replace(' ', ''))
        edition = int(row['edition_price'].replace(' ', ''))
        wltp = int(row['range'])
        consumption = float(row['consumption'].replace(',', '.'))
        battery = float(row['battery'].replace(',', '.'))
        require((edition, wltp) == cards[name][:2], 'puma_price_card_or_wltp_conflict')
        require(100_000 <= edition < cash <= 3_000_000 and 50 <= wltp <= 1200 and 5 <= consumption <= 60
                and 1 <= int(ac[1]) <= 44 and 20 <= int(dc[1]) <= 600 and 1 <= boot <= 3000,
                'puma_value_out_of_range')
        variants.append({
            'variant': name, 'model_year': 2027,
            'list_price': hardware(cash, row[0], 'swedish_recommended_price_column'),
            'edition_price_reference': hardware(edition, row[0], 'separate_edition_price_not_selected'),
            'facts': {
                'wltp_range_km': hardware(wltp, row[0], 'swedish_my27_combined_wltp_maximum'),
                'wltp_consumption_kwh_100km': hardware(consumption, row[0], 'swedish_my27_combined_wltp'),
                'battery_kwh': hardware(battery, row[0], 'swedish_my27_capacity_not_labeled_gross_or_net'),
                'dc_charge_kw': hardware(int(dc[1]), dc[0], 'vehicle_peak_dc_both_trims'),
                'ac_charge_kw': hardware(int(ac[1]), ac[0], 'three_phase_onboard_ac_both_trims'),
                'boot_liters': proof('model.html', boot, cargo_quote, 'rear_including_gigabox_excluding_frunk'),
                'drivetrain': proof('model.html', 'FWD', cards[name][2], 'swedish_my27_trim_card'),
            },
        })
        if supporting:
            facts = variants[-1]['facts']
            net = supporting['battery']
            require(net.groups() == (row['battery'], ac[1], dc[1]), 'puma_se_dk_battery_or_charging_conflict')
            facts['battery_kwh']['scope'] = 'swedish_my27_capacity_confirmed_usable_by_ford_dk_my27'
            facts['battery_kwh']['corroboration'] = [proof(
                'ford-dk-prices.html', battery, net[0], 'same_124_kw_my27_powertrain_net_capacity')]
            cargo = supporting['seats_up']
            facts['boot_liters']['scope'] = 'rear_to_seatback_including_gigabox_excluding_frunk'
            facts['boot_liters']['corroboration'] = [
                proof('ford-se-factsheet.pdf', boot, cargo[0], 'same_model_launch_five_seat_seatback_scope'),
                proof('ford-dk-technical.html', boot, supporting['cargo_scope'], 'current_seatback_column')
                | {'column_values': supporting['cargo_columns']},
            ]
            facts['seats'] = proof('ford-se-factsheet.pdf', int(cargo[1]), cargo[0],
                                   'both_swedish_trims_five_seat_body_current_cargo_cross_check')
            tow = int(supporting['braked'][index + 1])
            facts['tow_kg'] = proof('ford-se-factsheet.pdf', tow, supporting['braked'][0],
                                    'braked_12_percent_gradient_requires_towbar')
            facts['tow_kg']['corroboration'] = [
                proof('ford-dk-prices.html', tow, supporting['towing'][0].strip(), 'current_my27_braked_column'),
                hardware(True, 'Dragkrok (avtagbar) 8 000 kr 8 000 kr', 'towbar_option_in_both_swedish_trims'),
            ]
    held = ['verify_bev_only_market_alias', 'finalize_photo_receipt', 'isolated_insertion_review']
    if not extended:
        held = ['verify_braked_towing', 'verify_seating', 'verify_rear_seats_up_measurement_scope',
                'verify_battery_nameplate_scope'] + held
    report = {'status': 'swedish_technical_review_held', 'model': 'Puma Gen-E', 'brand': 'Ford', 'market': 'SE',
              'sources': sources, 'variants': variants, 'held': held, 'publication_approved': False,
              'production_writes': 0, 'paid_calls': 0}
    if with_market:
        report['market_index'] = market_index(files)
        page = parse_document(files['model.html'], 'text/html')
        description = one((n.attrs.get('content') for n in page.nodes('meta')
                           if n.attrs.get('name') == 'description'), 'puma_model_description_missing')
        require(description == 'Helt elektrisk kompakt SUV | Ford Sverige', 'puma_electric_suv_description_changed')
        report['model_evidence'] = proof('model.html', 'SUV', description, 'swedish_electric_suv')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--replay', type=Path)
    parser.add_argument('--include-hardware', action='store_true', help='Capture supporting Ford hardware tables.')
    parser.add_argument('--include-market', action='store_true', help='Capture the official October BEV market row.')
    args = parser.parse_args()
    if (args.replay and (args.include_hardware or args.include_market)) or (args.include_market and not args.include_hardware):
        parser.error('--include-market requires --capture --include-hardware')
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    require(root == ROOT.resolve() / 'data/local/release-data'
            and not any(re.fullmatch(r'onedrive(?:commercial|consumer)?', part, re.I) for part in root.parts),
            'puma_private_release_directory_required')
    if args.capture:
        capture_sources = FULL_SOURCES if args.include_market else TECHNICAL_SOURCES if args.include_hardware else SOURCES
        fetcher = SourceFetcher(timeout=20, max_bytes=LIMIT, document_parser=lambda body, _: body, text_parser=lambda *_: '',
                                url_policy=lambda url, brands: url in capture_sources.values() and brands == {'Ford'})
        files, times = {}, {}
        for name, url in capture_sources.items():
            result = fetcher.fetch(url, {'Ford'})
            require(result['status'] == 'reachable' and result.get('http_status') == 200
                    and result.get('final_url') == url, f'puma_source_unavailable: {name} {result["status"]}')
            files[name] = result['document']
            times[name] = datetime.now(timezone.utc).isoformat()
        report = {'source_capture_times': times, **review(files)}
        folder = Path(tempfile.mkdtemp(prefix='ford-puma-review-', dir=root))
        for name, raw in files.items():
            (folder / name).write_bytes(raw)
        (folder / 'review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    else:
        folder = args.replay.resolve(strict=True)
        require(folder == args.replay.absolute() and folder.parent == root
                and re.fullmatch(r'ford-puma-review-[a-z0-9_]+', folder.name), 'puma_private_capture_required')

        def read(name, limit):
            path = folder / name
            require(path.resolve(strict=True) == path and path.is_file() and path.stat().st_size <= limit,
                    'puma_regular_capture_file_required')
            return path.read_bytes()

        saved = json.loads(read('review.json', 100_000))
        times = saved['source_capture_times']
        require(times.keys() in (SOURCES.keys(), TECHNICAL_SOURCES.keys(), FULL_SOURCES.keys())
                and all(datetime.fromisoformat(t).utcoffset() ==
                timezone.utc.utcoffset(None) for t in times.values()), 'puma_capture_times_invalid')
        report = {'source_capture_times': times, **review({name: read(name, LIMIT) for name in times})}
        require(report == saved, 'puma_capture_or_review_changed')
    print(json.dumps({'review': str(folder / 'review.json'), 'variants': len(report['variants']),
                      'fields': sum(len(v['facts']) for v in report['variants']), 'publication_approved': False}))


if __name__ == '__main__':
    main()
