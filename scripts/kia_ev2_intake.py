"""Deterministic source-bound EV2 pilot; no AI or canonical writes."""
import argparse
import io
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from openpyxl import load_workbook
from audit_catalog_sources import SourceFetcher
from import_mobility_sweden import parse_elbil_ranking
from manufacturer_embedded_data import ScriptData, unique_object
from variant_refresh import RefreshError, one, parse_document

ADAPTER = 'kia_ev2_sweden_pilot_v1'
BASE = 'https://www.kia.com'
URLS = dict(technical=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev2/kia-sweden-ev2-specification.pdf',
    model=BASE+'/se/nya-bilar/ev2/upptack/', specifications=BASE+'/se/nya-bilar/ev2/specifikationer/',
    price_pdf=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf')
MARKET_URL = 'https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx'
PROFILES = [
    ('EV2 FWD 5-sits','6NW5ZFZ7Z-TX2','TX2','EV2',331900,42.2,317,15.1,16,'107,8 kW / 146,5 hk'),
    ('EV2 FWD Long Range 5-sits','6NW5ZFZ7Z-TX2_V00','TX2_V00','EV2 Long Range',381000,61,453,14.9,16,'99,5 kW / 135 hk'),
    ('EV2 GT Line FWD Long Range 5-sits','6NW5ZFZ7Z-LX1','LX1','EV2 GT Line Long Range',459900,61,413,16.3,19,'99,5 kW / 135 hk'),
]
QUOTES = dict(battery_kwh='Batterikapacitet (kWh) 42,2 61',
    ac_charge_kw='Bilens laddare (On Board Charger) (kW) 10,5',
    dc_charge_kw='DC snabbladdning max kW 150 150',
    wltp_range_km='Max räckvidd (km) enligt WLTP (Upp till) SR = 317 (16") & 308 (18") LR = 453 (16"), 439 (18") & 413 (19")',
    wltp_consumption_kwh_100km='FÖRBRUKNING Blandad, kWh/100km enligt WLTP SR = 15,1 (16") & 15,5 (18") LR =14,9 (16"), 15,2 (18") & 16,3 (19")',
    boot_liters='BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv (ej basversionen) 5 säten = 362 / 1201 / 15',
    tow_kg='Max släpvagnsvikt, bromsat släp 750 750')
BODY = 'en självsäker och smart SUV'


def require(value, reason):
    if not value:
        raise RefreshError(reason)


def clean(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def engine_data(html):
    parser = ScriptData()
    parser.feed(html)
    require(parser.language in ('sv','sv-SE'), 'swedish_engine_page_required')
    tables = []
    for script in parser.scripts:
        m = re.search(r'eut\.tableDatas\["[0-9]+"\]\s*=\s*', script)
        if not m:
            continue
        data, end = json.JSONDecoder(object_pairs_hook=unique_object).raw_decode(script[m.end():])
        require(script[m.end()+end:].lstrip().startswith(';'), 'literal_json_table_required')
        if data.get('tableType') == 'engine':
            tables.append(data)
    data = one(tables, 'one_engine_table_required')
    require((data.get('modelName'),data.get('modelCode'),data.get('bodyTypeCode')) == ('EV2','6N','W5|W4'),
            'exact_ev2_model_and_seating_bodies_required')
    groups = data.get('enginesDetail'), data.get('trimsDetail')
    require(all(isinstance(g,list) and len(g)==1 and g[0]['powerTrainModelName']=='EV2' for g in groups),
            'exact_ev2_nested_group_required')
    return dict(engines=groups[0][0]['engines'], trims=groups[1][0]['trims'])


def extract(packets, market, now=None):
    now = now or datetime.now(timezone.utc)
    require(set(packets)==set(URLS), 'complete_exact_source_set_required')
    for key,url in {**URLS,'market':MARKET_URL}.items():
        s = market['source'] if key=='market' else packets[key]['source']
        age = (now-datetime.fromisoformat(s['fetched_at'].replace('Z','+00:00'))).total_seconds()
        require(s['status']=='reachable' and s['http_status']==200 and s['final_url']==url
            and re.fullmatch('[a-f0-9]{64}',s['content_hash']) and -60<=age<=900, 'fresh_exact_source_required:'+key)
    m = market['row']
    require(m['brand_raw']=='KIA' and m['model_raw']=='EV2' and m['fuel_type_raw']=='EL' and not m['needs_mapping']
        and m['normalized_brand']=='kia' and m['normalized_model']=='ev2' and m['last_seen_month']=='2026-10-01'
        and 0<m['registrations_last_month']<=m['registrations_ytd'] and market['sheet']=='Elbil ranking', 'exact_market_presence_required')
    pages = packets['technical']['pages']
    require(len(pages)==5 and '29 september 2026' in pages[0] and 'KIA EV2.' in pages[0], 'current_swedish_technical_edition_required')
    technical = clean(pages[2])
    require('MOTOR Standard Range Long Range 42,2kWh 61kWh' in technical and
        'Motoreffekt kW 107,8 99,5' in technical and not re.search('preliminär|homologering',technical[:180],re.I), 'final_exact_powertrain_columns_required')
    for q in QUOTES.values():
        require(q in technical, 'technical_row_changed:'+q)
    require('16" aluminiumfälgar' in pages[0] and '19" aluminiumfälgar' in pages[0]
        and '4 säten = 321-403 / 1201 / 15' in technical, 'separate_wheels_and_seat_boot_scope_required')
    require(BODY in clean(parse_document(packets['model']['html'].encode(),'text/html').text()), 'official_suv_body_required')
    engines = engine_data(packets['specifications']['html'])
    price = packets['price_pdf']['pages']
    require(len(price)==2 and '2026-11-01' in price[0] and '2026-11-30' in price[0]
        and '2026-11-01'<=now.date().isoformat()<='2026-11-30', 'current_november_swedish_price_list_required')
    drafts = []
    for name,engine,trim,price_name,cash,battery,km,consumption,wheel,power in PROFILES:
        e = one((r for r in engines['engines'] if r['id']==engine), 'exact_engine_required')
        tr = one((t for t in engines['trims'] if t['id']==trim and any(r['id']==engine for r in t['enginesInTrim'])), 'exact_trim_engine_pair_required')
        pe = one((r for r in tr['enginesInTrim'] if r['id']==engine), 'one_trim_price_required')
        require(e['number of seats']=='5' and 'FWD' in e['name'] and pe['maxPower']==power and int(pe['price'])==cash
            and tr['name']==price_name+' - 5 Seats', 'same_five_seat_motor_price_and_power_required')
        line = one((clean(s) for s in price[0].splitlines() if clean(s).startswith(price_name+' '+f'{cash:,}'+' kr')), 'one_cash_price_row_required')
        require(re.fullmatch(re.escape(price_name)+' '+f'{cash:,}'+r' kr(?: [0-9,]+ kr)?',line), 'cash_not_lease_or_four_seat_price_required')
        facts = dict(wltp_range_km=km,wltp_consumption_kwh_100km=consumption,battery_kwh=battery,
            dc_charge_kw=150,ac_charge_kw=10.5,boot_liters=362,tow_kg=750,seats=5,drivetrain='FWD')
        evidence = {}
        for field,value in facts.items():
            key,page,q = 'technical',3,QUOTES.get(field)
            if field in ('seats','drivetrain'):
                key,page,q = 'specifications',None,engine+' | '+e['name']+' | number of seats 5 | '+pe['maxPower']
            evidence[field] = dict(value=value,variant_name=name,column_header=f'{name} | {engine} | {wheel} tum | 5 sittplatser',
                source_url=URLS[key],source_hash=packets[key]['source']['content_hash'],quote=q,page=page)
        drafts.append(dict(variant_name=name,manufacturer_identity=engine,facts=facts,field_evidence=evidence,
            extraction_confidence=0.99,price_evidence=dict(value=cash,price_type='list_price',price_valid_until='2026-11-30',
                source_url=URLS['price_pdf'],source_hash=packets['price_pdf']['source']['content_hash'],page=1,quote=line)))
    return dict(adapter=ADAPTER,model=dict(brand='Kia',model='Ev2',normalized_brand='kia',normalized_model='ev2',body_type='SUV'),
        model_evidence=dict(body_type=dict(value='SUV',quote=BODY,source_url=URLS['model'],source_hash=packets['model']['source']['content_hash'])),
        sources=[dict(**p['source'],key=k,source_type='technical_pdf' if k=='technical' else 'price_list_pdf' if k=='price_pdf' else 'manufacturer_page',
            shared=k=='price_pdf',source_name='Kia Sverige',country='SE',language='sv',source_authority='manufacturer') for k,p in packets.items()],
        market=market,drafts=drafts,source_decisions=[
            'September29 final Swedish technical sheet supersedes the old preliminary brochure. Keep all5-seat profiles separate from4-seat Plus and BlackLine.',
            'Base16inch SR317km/15.1 and LR453km/14.9; GTLine19inch LR413km/16.3. No AWD is offered in these exact engines.',
            'Five seats in use:362L, not four-seat sliding-row maximum403L, folded1201L or frunk15L (base version has no frunk).',
            'OnboardAC10.5 and actual peakDC150. Towing750kg is explicitly the braked row.',
            'November list cash amounts331900/381000/459900 match each exact Swedish engine. Never use leasing3495/4195/5595 or another seating price.',
            'Mobility Sweden provides registration activity only; keep availability unconfirmed unless separately evidenced.',
        ],paid_calls=0,database_writes=0)


def collect(output):
    output.mkdir(parents=True,exist_ok=True)
    fetcher = SourceFetcher(timeout=30,max_bytes=14*1024*1024,document_parser=lambda body,kind:body,
        text_parser=lambda body,kind:'',url_policy=lambda url,brands:url in [*URLS.values(),MARKET_URL])
    packets = {}
    for key,url in {**URLS,'market':MARKET_URL}.items():
        r = fetcher.fetch(url,{'Kia'} if key!='market' else set())
        require(r['status']=='reachable' and r['final_url']==url, 'source_unavailable:'+key+':'+r['status'])
        raw = r['document'];s = {n:r[n] for n in ['status','http_status','final_url','content_hash']}
        s['fetched_at']=datetime.now(timezone.utc).isoformat()
        path=output/(key+('.xlsx' if key=='market' else '.pdf' if url.endswith('.pdf') else '.html'));path.write_bytes(raw)
        if key=='market':
            rows,_=parse_elbil_ranking(path,url)
            row=one((asdict(v) for v in rows if v.brand_raw=='KIA' and v.model_raw=='EV2'),'one_bev_market_row_required')
            book=load_workbook(path,read_only=True,data_only=True)
            try:
                sheet=book['Elbil ranking']
                number=one((i for i,row in enumerate(sheet.iter_rows(min_row=10,values_only=True),10) if row[3]=='KIA EV2'),'exact_workbook_row_required')
            finally:
                book.close()
            market=dict(source=s,row=row,sheet='Elbil ranking',cells=f'D{number},F{number},M{number}')
        elif url.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(raw)) as doc:
                packets[key]=dict(source=s,pages=[page.extract_text() or '' for page in doc.pages])
        else:
            packets[key]=dict(source=s,html=raw.decode('utf8'))
    (output/'source-packets.json').write_text(json.dumps(packets,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (output/'market-packet.json').write_text(json.dumps(market,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    intake=extract(packets,market)
    (output/'intake.json').write_text(json.dumps(intake,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(drafts=3,technical_facts=27,prices=3,market_month=market['row']['last_seen_month'],database_writes=0,paid_calls=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output)
