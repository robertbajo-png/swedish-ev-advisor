"""Complete existing Swedish EV6 profiles from exact manufacturer evidence."""
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

ADAPTER = 'kia_ev6_sweden_completion_v1'
BASE = 'https://www.kia.com'
URLS = dict(
    technical=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev6/kia-sweden-ev6-specification.pdf',
    model=BASE+'/se/nya-bilar/ev6/upptack/',
    specifications=BASE+'/se/nya-bilar/ev6/technische-daten/',
    gt=BASE+'/se/nya-bilar/ev6-gt/upptack/',
    gt_specifications=BASE+'/se/nya-bilar/ev6-gt/specifikationer/',
    gt_germany=BASE+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV6-GT-Pricelist.pdf',
    energy=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf',
    price_pdf=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
)
VERSIONS = [
    ('EV6 RWD', 'ASW5ZHZ7Z-TX1', 'TX1', 596400, 'RWD', 582, 15.9, 19),
    ('EV6 AWD', 'ASW5YCZ7Z-TX1', 'TX1', 631400, 'AWD', 546, 17.0, 19),
    ('EV6 GT', 'ASW5YDZ7Z-GX2', 'GX2', 771400, 'AWD', 450, 20.9, 21),
]
TECHNICAL_QUOTES = dict(
    battery_kwh='Batterikapacitet (kWh) 84',
    ac_charge_kw='Bilens laddare (On Board Charger) (kW) 10.5',
    dc_charge_kw='DC snabbladdning max 258kW',
    wltp_range_km='Max räckvidd (km) enligt WLTP upp till 582** upp till 546**',
    wltp_consumption_kwh_100km='FÖRBRUKNING Blandad, kWh/100km enligt WLTP 15,9 17,0 19" / 17,7 20"',
    boot_liters='BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv (liter) 480 / 1290 / 50 480 / 1290 / 20',
    tow_kg='Max släpvagnsvikt (obromsat / bromsat släp) 750 / 1800 750 / 1800',
    drivetrain='MOTOR Elmotor Elmotor RWD AWD',
)
GT_BLOCK = 'Batterikapacitet: 84 kWh AWD - fyrhjulsdrift Räckvidd: upp till 450 km 12a Ultrasnabb laddning: 10-80 % på ner till 18 minuter 12b 0-100 km/h: 3,7 sekunder / 3,5 sekunder (med Launch Control aktiverat) Prestanda: 609 hk/448 kW samt vid Launch Control: 650 hk/478 kW Maxhastighet: 260 km/h Virtual Gear Shift / Adaptive Sound Design Dragvikt: upp till 1 800 kg'
GT_QUOTES = dict(
    ac_charge_kw=(10, 'Max. AC-Ladeleistung (kW) 3-phasig (AC), 10,5 kW'),
    dc_charge_kw=(10, 'Max. DC-Ladeleistung (kW) 258'),
    boot_liters=(11, 'Gepäckraumvolumen nach VDA (Liter), inkl. Ablagefach im Gepäckraumboden Sitze in Normalposition, bis Fensterhöhe, max. 480'),
)
BODY_QUOTE = 'Upptäck Kias snabbladdande crossover med en sportig design redan idag.'


def require(value, reason):
    if not value:
        raise RefreshError(reason)


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def engine_data(html, gt=False):
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
    name = 'EV6 GT' if gt else 'EV6'
    require((data.get('modelName'), data.get('modelCode'), data.get('bodyTypeCode')) ==
        (name, 'AS', 'W5'), 'exact_ev6_model_and_body_required')
    require("window.dtmDataLayer.vehicle_name = '"+('ev6gt' if gt else 'ev6')+"';" in html,
        'exact_vehicle_name_required')
    engines, trims = data.get('enginesDetail'), data.get('trimsDetail')
    require(isinstance(engines, list) and isinstance(trims, list) and len(engines) == len(trims) == 1,
        'one_nested_powertrain_group_required')
    require(engines[0].get('powerTrainModelName') == trims[0].get('powerTrainModelName') == name,
        'same_nested_model_group_required')
    return dict(data, engines=engines[0]['engines'], trims=trims[0]['trims'])


def extract(packets, now=None):
    now = now or datetime.now(timezone.utc)
    require(set(packets) == set(URLS), 'exact_source_set_required')
    for key, url in URLS.items():
        source = packets[key]['source']
        age = (now-datetime.fromisoformat(source['fetched_at'].replace('Z', '+00:00'))).total_seconds()
        require(source['status'] == 'reachable' and source['http_status'] == 200 and
            source['final_url'] == url and re.fullmatch('[a-f0-9]{64}', source['content_hash']) and
            -60 <= age <= 900, 'fresh_exact_source_required:'+key)
    pages = packets['technical']['pages']
    require(len(pages) == 5 and '20 augusti, 2026' in pages[0] and 'EV6 LONG RANGE' in pages[0],
        'current_swedish_84kwh_edition_required')
    technical = clean(pages[2])
    require('Motoreffekt kW 168 239' in technical and 'Teknisk specifikation MOTOR Elmotor Elmotor RWD AWD' in technical,
        'exact_regular_motor_columns_required')
    require(not re.search('preliminär|homologering', technical[:250], re.I), 'final_regular_header_required')
    for quote in TECHNICAL_QUOTES.values():
        require(quote in technical, 'technical_row_changed:'+quote)
    require('HJUL Däckdimension 19" (235/55 R19)' in technical and
        'GT LINE AWD (Räckvidd upp till 522km**)' in clean(pages[3]), 'standard_19inch_scope_required')
    specs = engine_data(packets['specifications']['html'])
    gt_specs = engine_data(packets['gt_specifications']['html'], True)
    model = parse_document(packets['model']['html'].encode(), 'text/html')
    require(BODY_QUOTE in packets['model']['html'] and 'EV6' in model.text(), 'explicit_swedish_crossover_required')
    gt_text = clean(parse_document(packets['gt']['html'].encode(), 'text/html').text())
    require('EV6 GT AWD' in gt_text and GT_BLOCK in gt_text, 'exact_swedish_609_650hp_gt_required')
    de = packets['gt_germany']['pages']
    require(len(de) == 12 and 'Der Kia EV6 GT.' in de[0], 'exact_german_gt_document_required')
    for quote in ['Motor 84 kWh AWD', '448/609 [478/650]', 'Kombiniert (kWh/100 km) 20,9', 'Anzahl der Sitze 5']:
        require(quote in clean(de[9]), 'same_84kwh_gt_technical_column_required:'+quote)
    require('Motor 84 kWh AWD' in clean(de[10]) and 'Reichweite max. (km)2 450' in clean(de[10]),
        'same_gt_boot_and_combined_range_required')
    for page, quote in GT_QUOTES.values():
        require(quote in clean(de[page-1]), 'exact_gt_technical_row_required:'+quote)
    energy = clean(packets['energy']['pages'][0])
    require('OKTOBER 2026' in energy and 'EV6 GT Elmotor 650hk El Euro 6ax 20,9 kWh' in energy,
        'swedish_gt_consumption_required')
    prices = packets['price_pdf']['pages']
    require(len(prices) == 2 and '2026-11-01' in prices[0] and '2026-11-30' in prices[0],
        'november_swedish_price_period_required')
    require('2026-11-01' <= now.date().isoformat() <= '2026-11-30', 'current_price_period_required')
    drafts = []
    for name, engine, trim, cash, drive, km, consumption, wheel in VERSIONS:
        gt = name == 'EV6 GT'
        key = 'gt_specifications' if gt else 'specifications'
        data = gt_specs if gt else specs
        e = one((e for e in data['engines'] if e['id'] == engine), 'one_exact_engine_required')
        tr = one((t for t in data['trims'] if t['id'] == trim), 'one_exact_trim_required')
        pe = one((e for e in tr['enginesInTrim'] if e['id'] == engine), 'one_exact_trim_engine_required')
        power = '478 KW (650 hk)' if gt else '239 KW (325 hk)' if drive == 'AWD' else '168 KW (229 hk)'
        require(e['number of seats'] == '5' and power in e['name'] and drive in e['name'] and
            int(pe['price']) == cash, 'same_engine_seats_power_and_cash_required')
        price_name = 'EV6 GT (650hk) AWD Long Range' if gt else name+' Long Range'
        line = one((clean(line) for line in prices[1].splitlines() if
            re.match(re.escape(price_name)+r' [0-9]{3},[0-9]{3} kr(?: |$)', clean(line))), 'one_exact_price_row_required')
        require(line.startswith(price_name+' '+f'{cash:,}'+' kr'), 'cash_not_lease_or_paint_required')
        primary = 'gt' if gt else 'technical'
        row = dict(adapter=ADAPTER, brand='Kia', model='Ev6', variant_name=name,
            source=packets[primary]['source'], supporting_sources=[packets[k]['source'] for k in URLS if k != primary],
            source_resolution='exact_swedish_ev6_84kwh_standard_19inch_and_separate_609_650hp_gt',
            extraction_confidence=0.99, facts={}, field_evidence={}, held_fields={})
        header = f'{name} | {engine} | {wheel} tum'

        def add(field, value, source_key, quote, scope, page=None):
            row['facts'][field] = value
            row['field_evidence'][field] = dict(value=value, variant_name=name, column_header=header,
                source_url=URLS[source_key], source_hash=packets[source_key]['source']['content_hash'],
                quote=quote, scope=scope, page=page)

        facts = dict(battery_kwh=84, wltp_range_km=km, wltp_consumption_kwh_100km=consumption,
            dc_charge_kw=258, ac_charge_kw=10.5, tow_kg=1800, boot_liters=480, drivetrain=drive)
        for field, value in facts.items():
            if not gt:
                add(field, value, 'technical', TECHNICAL_QUOTES[field], 'swedish_84kwh_base_trim_19inch', 3)
            elif field in GT_QUOTES:
                page, quote = GT_QUOTES[field]
                add(field, value, 'gt_germany', quote, 'german_same_84kwh_609_650hp_gt', page)
            elif field == 'wltp_consumption_kwh_100km':
                add(field, value, 'energy', 'EV6 GT Elmotor 650hk El Euro 6ax 20,9 kWh', 'swedish_october_gt_consumption', 1)
            else:
                add(field, value, 'gt', GT_BLOCK, 'swedish_same_gt_609hp_650hp_launch_control')
        add('seats', 5, key, engine+' | '+e['name']+' | number of seats 5', 'exact_swedish_nested_trim_engine')
        row['model_facts'] = dict(body_type='Crossover')
        row['model_field_evidence'] = dict(body_type=dict(value='Crossover', source_url=URLS['model'],
            source_hash=packets['model']['source']['content_hash'], quote=BODY_QUOTE))
        row['price_evidence'] = dict(value=cash, price_type='list_price', price_valid_until='2026-11-30', page=2,
            source_url=URLS['price_pdf'], source_hash=packets['price_pdf']['source']['content_hash'], quote=line,
            classification='dated_november_swedish_cash_list_and_matching_engine')
        row['source_decisions'] = [
            'Preserve all three existing canonical identities/routes and all three price amounts; RWD/AWD are explicit aliases of the Swedish base Long Range profiles.',
            'Regular 84kWh base versions use standard19inch wheels:582km/15.9RWD and546km/17.0AWD. Do not use optional20inch522km/17.7 or old77.4kWh GT data.',
            'Both Swedish AS/W5 engine tables are nested. TX1 has two motors despite its trim display label RWD: match the exact engine ID, not the trim label alone.',
            'GT ASW5YDZ7Z-GX2 has609hp normally and650hp only with Launch Control; the dated Swedish price name650hk identifies that same84kWh version.',
            'Swedish GT model data supplies450km/84kWh/AWD/1800kg. October energy declaration supplies20.9. German same448/609[478/650]84kWh GT supplies AC10.5/DC258 and seats-up480L including underfloor space.',
            'Resolve historical drivetrain GT to AWD only for this exact GT identity; GT is an equipment/performance label, not a driven-axle specification.',
            'Boot480L is rear seats up, not folded1250/1290 or frunk20/50. Tow1800kg is braked capacity, not750unbraked,100ball load or B-licence limits.',
            'Use exact onboardAC10.5, not nominal supply11 or DC station350. Keep German technical evidence labelled DE/de; no foreign prices are imported.',
            'November1-30 Swedish cash amounts596400/631400/771400 agree with engine JSON. Never substitute Plus price, lease12360 or optional paint20000.',
            'Keep shared price/energy sources model* and legacy uppercaseEV6 model/engine pages unchanged. Preserve the approved full-frame Baseline press image with equipment notice, not a GT-photo claim.',
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
        require(result['status'] == 'reachable' and result['final_url'] == url,
            'ev6_source_unavailable:'+key+':'+result['status'])
        raw = result['document']
        source = {name: result[name] for name in ['status', 'http_status', 'final_url', 'content_hash']}
        source['fetched_at'] = datetime.now(timezone.utc).isoformat()
        packet = {'source': source}
        (output/(key+('.pdf' if url.endswith('.pdf') else '.html'))).write_bytes(raw)
        if url.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(raw)) as document:
                packet['pages'] = [page.extract_text() or '' for page in document.pages]
        else:
            packet['html'] = raw.decode('utf8')
        packets[key] = packet
    (output/'source-packets.json').write_text(json.dumps(packets, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    if capture_only:
        print(json.dumps(dict(sources=len(packets), database_writes=0, paid_calls=0)))
        return
    drafts = extract(packets)
    (output/'intake.json').write_text(json.dumps(dict(adapter=ADAPTER, drafts=drafts, held=[],
        database_writes=0, paid_calls=0), ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(dict(drafts=len(drafts), technical_facts=27, prices=3, database_writes=0, paid_calls=0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--capture-only', action='store_true')
    args = parser.parse_args()
    collect(args.output, args.capture_only)
