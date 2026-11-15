"""Collect and reconcile four existing EV9 versions; no AI or database writes."""
import argparse
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from audit_catalog_sources import SourceFetcher
from manufacturer_embedded_data import ScriptData, unique_object
from variant_refresh import RefreshError, one, parse_document

ADAPTER = 'kia_ev9_sweden_completion_v1'
BASE = 'https://www.kia.com'
URLS = dict(
    technical=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev9/kia-sweden-ev9-gtline-specification.pdf',
    model=BASE+'/se/nya-bilar/ev9/upptack/',
    specifications=BASE+'/se/nya-bilar/ev9/specifications/',
    germany=BASE+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV9-Preisliste.pdf',
    price_pdf=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
)
VERSIONS = [
    ('EV9 RWD 7-SITS', 'DOW7ZHZ7Z-LX2', 'LX2', 701900, 701900, 'RWD', 443, 18.7, 76.1, 900, 7, 19),
    ('EV9 AWD', 'DOW7YBZ7Z-TX2', 'TX2', 819900, 819900, 'AWD', 512, 22.2, 99.8, 2500, 7, 19),
    ('EV9 AWD GT Line 7-sits', 'DOW7YBZ7Z-GX1', 'GX1', 889900, 889900, 'AWD', 505, 22.8, 99.8, 2500, 7, 21),
    ('EV9 AWD GT Line 6-sits', 'DOW6YBZ7Z-SX2', 'SX2', 909900, 897900, 'AWD', 505, 22.8, 99.8, 2500, 6, 21),
]
QUOTES = dict(
    battery_kwh='Batterikapacitet (kWh) 76.1 99.8',
    ac_charge_kw='Bilens laddare (On Board Charger) (kW) 10.5',
    dc_charge_kw='DC snabbladdning max 210kW',
    wltp_range_km='Max räckvidd (km) enligt WLTP (upp till) upp till 443* * upp till 512 (19"), 505 (21")**',
    wltp_consumption_kwh_100km='FÖRBRUKNING Blandad, kWh/100km enligt WLTP 18,7 22,2 (19") 22,8 (21")',
    tow_kg='Max släpvagnsvikt (obromsat / bromsat släp) 450 / 900 750 / 2 500',
    boot_liters='BAGAGEUTRYMME 2-sits / 5-sits / 7-sits / under framhuv (liter) 2 318 / 828 / 333 / 52',
    drivetrain='MOTOR Standard Range Long Range RWD AWD',
)
BOOT6 = 'Alle Sitze in Normalposition, bis Fensterhöhe, max. 333'
BODY = 'Kia EV9 är en robust, rymlig och helt elektrifierad SUV'


def require(value, reason):
    if not value:
        raise RefreshError(reason)


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def engine_data(html):
    parser = ScriptData()
    parser.feed(html)
    require(parser.language in ('sv', 'sv-SE'), 'swedish_engine_page_required')
    tables = []
    for script in parser.scripts:
        match = re.search(r'eut\.tableDatas\["[0-9]+"\]\s*=\s*', script)
        if not match:
            continue
        data, end = json.JSONDecoder(object_pairs_hook=unique_object).raw_decode(script[match.end():])
        require(script[match.end()+end:].lstrip().startswith(';'), 'literal_engine_table_required')
        if data.get('tableType') == 'engine':
            tables.append(data)
    data = one(tables, 'one_exact_engine_table_required')
    require((data.get('modelName'), data.get('modelCode'), data.get('bodyTypeCode')) ==
            ('EV9', 'DO', 'W7|W6'), 'exact_ev9_two_seating_bodies_required')
    return data


def extract(packets, now=None):
    now = now or datetime.now(timezone.utc)
    require(set(packets) == set(URLS), 'exact_source_set_required')
    for key, url in URLS.items():
        s = packets[key]['source']
        age = (now-datetime.fromisoformat(s['fetched_at'].replace('Z', '+00:00'))).total_seconds()
        require(s['status'] == 'reachable' and s['http_status'] == 200 and s['final_url'] == url
            and re.fullmatch('[a-f0-9]{64}', s['content_hash']) and -60 <= age <= 900,
            'fresh_exact_source_required:'+key)
    pages = packets['technical']['pages']
    require(len(pages) == 5 and '20 augusti 2026' in pages[0] and 'EV9 RWD' in pages[0],
            'current_swedish_ev9_edition_required')
    technical = clean(pages[2])
    for q in QUOTES.values():
        require(q in technical, 'technical_row_changed:'+q)
    require('Motoreffekt hk 218 384' in technical and 'Motoreffekt kW 160 282' in technical,
            'same_swedish_218_384hp_columns_required')
    require('7-sittplatser' in pages[0] and '6-sittplatser (Relaxation 2:raden)*' in pages[1],
            'explicit_seating_option_required')
    de = packets['germany']['pages']
    require(len(de) == 17 and 'Der Kia EV9.' in de[0]
            and 'Motor 76,1 kWh RWD 99,8 kWh RWD 99,8 kWh AWD' in clean(de[14]),
            'same_ev9_bodies_required')
    for q in ['Anzahl der Sitze 7 7 (optional: 6)', '3.240 (7-Sitzer), 3.190 (6-Sitzer)',
              'Gepäckraumvolumen nach VDA (Liter), inkl. Ablagefach im Gepäckraumboden', BOOT6,
              '807 (6-Sitzer: 828)', '2.318 (6-Sitzer: 2.393)']:
        require(q in clean(de[14]), 'explicit_all_seats_upright_six_seat_scope_required:'+q)
    require(BODY in clean(parse_document(packets['model']['html'].encode(), 'text/html').text()),
            'explicit_swedish_suv_required')
    data = engine_data(packets['specifications']['html'])
    prices = packets['price_pdf']['pages']
    require(len(prices) == 2 and '2026-11-01' in prices[0] and '2026-11-30' in prices[0]
            and '2026-11-01' <= now.date().isoformat() <= '2026-11-30', 'current_november_prices_required')
    drafts = []
    for name, engine, trim, cash, web_cash, drive, km, consumption, battery, tow, seats, wheel in VERSIONS:
        e = one((e for e in data['engines'] if e['id'] == engine), 'exact_engine_required')
        tr = one((t for t in data['trims'] if t['id'] == trim), 'exact_trim_required')
        pe = one((e for e in tr['enginesInTrim'] if e['id'] == engine), 'exact_trim_engine_required')
        require(e['number of seats'] == str(seats) and ('218hk' if drive == 'RWD' else '384hk') in e['name']
            and drive in e['name'] and int(pe['price']) == web_cash, 'same_motor_seats_and_web_price_required')
        price_name = 'EV9 RWD 7-SITS' if drive == 'RWD' else (
            f'EV9 GT Line AWD {seats}-SITS Long Range' if 'GT Line' in name else 'EV9 AWD 7-SITS Long Range')
        price_line = one((clean(line) for line in prices[1].splitlines()
            if clean(line).startswith(price_name+' ')), 'exact_swedish_price_row_required')
        require(re.fullmatch(re.escape(price_name)+' '+f'{cash:,}'+r' kr(?: [0-9,]+ kr)?', price_line),
                'cash_not_lease_or_gt_required')
        row = dict(adapter=ADAPTER, brand='Kia', model='Ev9', variant_name=name,
            source=packets['technical']['source'], supporting_sources=[packets[k]['source'] for k in URLS if k != 'technical'],
            source_resolution='swedish_ev9_218_384hp_19_21inch_separate_six_seven_seats',
            extraction_confidence=0.99, facts={}, field_evidence={}, held_fields={})
        facts = dict(battery_kwh=battery, ac_charge_kw=10.5, dc_charge_kw=210, wltp_range_km=km,
            wltp_consumption_kwh_100km=consumption, tow_kg=tow, boot_liters=333, drivetrain=drive, seats=seats)
        for field, value in facts.items():
            key, page, q, scope = 'technical', 3, QUOTES.get(field), 'swedish_standard_wheels_and_seating'
            if field == 'seats':
                key, page, q, scope = 'specifications', None, engine+' | '+e['name']+' | number of seats '+str(seats), 'exact_swedish_flat_trim_engine'
            elif field == 'boot_liters' and seats == 6:
                key, page, q, scope = 'germany', 15, BOOT6, 'german_same_ev9_all_six_seats_upright_vda'
            row['facts'][field] = value
            row['field_evidence'][field] = dict(value=value, variant_name=name,
                column_header=f'{name} | {engine} | {wheel} tum | {seats} sittplatser', source_url=URLS[key],
                source_hash=packets[key]['source']['content_hash'], quote=q, page=page, scope=scope)
        row['model_facts'] = dict(body_type='SUV')
        row['model_field_evidence'] = dict(body_type=dict(value='SUV', source_url=URLS['model'],
            source_hash=packets['model']['source']['content_hash'], quote=BODY))
        row['price_evidence'] = dict(value=cash, price_type='list_price', price_valid_until='2026-11-30', page=2,
            source_url=URLS['price_pdf'], source_hash=packets['price_pdf']['source']['content_hash'], quote=price_line,
            classification='dated_november_swedish_cash_over_undated_engine',
            alternatives=[dict(value=web_cash, source_url=URLS['specifications'],
                source_hash=packets['specifications']['source']['content_hash'], quote=engine+' | price '+str(web_cash))])
        row['source_decisions'] = [
            'Keep all four exact existing identities/routes and cash amounts; GT Line384hp is not EV9GT508hp.',
            'Swedish dated20August2026 technical columns:76.1kWh RWD218hp and99.8kWh AWD384hp. No German563km99.8RWD or EPA/city substitution.',
            'Standard19inch:443km/18.7RWD and512km/22.2AWD. GT Line21inch505km/22.8 applies to both six and seven seats; manufacturer maximum, not individually measured option configuration.',
            'Swedish DO/W7 andDO/W6 exact engine IDs establish seven versus six seats, not engineCategory7 or door count.',
            'Swedish boot333L explicitly covers seven seats in use. German same-body VDA table also explicitly covers six seats, all upright including underfloor. Not828,2393folded or52frunk.',
            'OnboardAC10.5 is not nominal supply11; maximumDC210 is not the250kW minimum station supply in the charge-time condition.',
            'Bromsad tow900RWD/2500AWD, not B-licence750, unbraked450/750, ball load or roof load.',
            'November1-30 cash list takes precedence over undated web prices. Six-seatGTLine web897900 conflicts with dated909900: retain alternate, selected exact dated909900 unchanged.',
            'German evidence only supplies six-seat boot scope; retain source localeDE/de, no German prices, availability or consumption.',
            'Preserve shared price source model*, uppercaseEV9 legacy model/spec pages and approved exact-model press photo. Equipment/colour may differ.',
        ]
        drafts.append(row)
    return drafts


def collect(output, capture_only=False):
    output.mkdir(parents=True, exist_ok=True)
    packets = {}
    fetcher = SourceFetcher(timeout=25, max_bytes=14*1024*1024,
        document_parser=lambda body, kind: body,
        url_policy=lambda url, brands: url in URLS.values() and brands == {'Kia'})
    for key, url in URLS.items():
        result = fetcher.fetch(url, {'Kia'})
        require(result['status'] == 'reachable' and result['final_url'] == url, 'ev9_source_unavailable:'+key)
        raw = result['document']
        source = {n: result[n] for n in ['status', 'http_status', 'final_url', 'content_hash']}
        source['fetched_at'] = datetime.now(timezone.utc).isoformat()
        packet = dict(source=source)
        (output/(key+('.pdf' if url.endswith('.pdf') else '.html'))).write_bytes(raw)
        if url.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(raw)) as document:
                packet['pages'] = [p.extract_text() or '' for p in document.pages]
        else:
            packet['html'] = raw.decode('utf8')
        packets[key] = packet
    (output/'source-packets.json').write_text(json.dumps(packets, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    if capture_only:
        return
    drafts = extract(packets)
    (output/'intake.json').write_text(json.dumps(dict(adapter=ADAPTER, drafts=drafts, held=[],
        database_writes=0, paid_calls=0), ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(dict(drafts=len(drafts), technical_facts=36, prices=4, database_writes=0, paid_calls=0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.output)
