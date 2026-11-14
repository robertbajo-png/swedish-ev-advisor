"""Complete five existing Swedish EV5 profiles from exact manufacturer evidence."""
import argparse
import io
import json
import re
from datetime import datetime,timezone
from pathlib import Path
import pdfplumber
from audit_catalog_sources import SourceFetcher
from manufacturer_embedded_data import ScriptData,unique_object
from variant_refresh import RefreshError,one,parse_document

ADAPTER='kia_ev5_sweden_completion_v1'
BASE='https://www.kia.com'
URLS=dict(technical=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev5/kia-sweden-ev5-specification.pdf',
 specifications=BASE+'/se/nya-bilar/ev5/specifikationer/',gt_specifications=BASE+'/se/nya-bilar/ev5-gt/specifikationer/',
 gt=BASE+'/se/nya-bilar/ev5-gt/upptack/',model=BASE+'/se/nya-bilar/ev5/upptack/',
 energy=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf',
 price_pdf=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
 poland_pdf=BASE+'/content/dam/kwcms/kme/pl/pl/assets/contents/utility/Price_list/ev5/Cennik_EV5_MY26-1_RP26_2026-06-18.pdf',
 gt_germany=BASE+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV5-GT-Preisliste.pdf')
VERSIONS=[
 ('EV5 FWD','LX1','X9W5ZHZ7Z-LX1',18,554900,'FWD',552,16.0,1200),
 ('EV5 Plus AWD Long Range','SX1_V00','X9W5YLZ7Z-SX1_V00',18,624900,'AWD',513,17.2,1800),
 ('EV5 GT Line AWD Long Range','GX1_V00','X9W5YLZ7Z-GX1_V00',19,658900,'AWD',491,18.1,1800),
 ('EV5 GT Line Panorama AWD Long Range','GX1_V00','X9W5YLZ7Z-GX1_V00',19,670900,'AWD',491,18.1,1800),
 ('EV5 GT (306hk) AWD Long Range','GX2','X9W5YRZ7Z-GX2',20,700900,'AWD',476,18.6,1800),
]
GT_BLOCK='EV5 GT Batterikapacitet: 81.4 kWh Laddningstid (min. DC 10-80%): 30 minuter Motoreffekt: 225 kW / 306 hk Max släpvagnsvikt, bromsat släp: 1,800 kg 0-100 km/h: 6.2 sekunder Toppfart: 180 km/h Max räckvidd (km) enligt WLTP (Upp till): 476 km'
TECHNICAL_QUOTES=dict(battery_kwh='Batterikapacitet (kWh) 81.4 81.4',ac_charge_kw='Bilens laddare (On Board Charger) (kW) 10.5',
 dc_charge_kw='DC snabbladdning max kW 150',boot_liters='BAGAGEUTRYMME Baksäte uppfällt / Nedfällt / Frunk 566 / 1 650 / 44',
 tow_kg='Max släpvagnsvikt, bromsat släp 1 200 1 800',drivetrain='FWD AWD',
 wltp_consumption_kwh_100km='FÖRBRUKNING Blandad, kWh/100km enligt WLTP 16,0 (16,6 GT Line) 17,2 (18,1 GT Line)')
RANGES={'FWD':'Max räckvidd (km) enligt WLTP (Upp till): FWD 552km, (534km GT Line)',
 'AWD':'Max räckvidd (km) enligt WLTP (Upp till): AWD 513km, (491km GT Line)'}
GT_QUOTES=dict(ac_charge_kw=('poland_pdf',15,'polish_same_306hp_gt_standard_not_22K','81.4 kWh AWD GT | Maksymalna moc ładowarki pokładowej [kW] 10.5 / 22 (z pakietem 22K)'),
 dc_charge_kw=('gt_germany',10,'german_same_225kw_gt_nominal_peak','Motor 81,4 kWh AWD | Leistung max. (kW/PS) 225/306 | Max. DC-Ladeleistung (kW) 150'),
 boot_liters=('gt_germany',11,'german_same_gt_seats_up_including_double_floor','Motor 81,4 kWh AWD | Laderaumvolumen bei aufgestellter Rücksitzbank, mit Einrechnung des doppelten Bodens 566'),
 wltp_consumption_kwh_100km=('energy',1,'swedish_october_306hp_gt_not_204hp_footer','EV5 | Elmotor 306hk AWD LR | 18,6 kWh'))

def require(value,reason):
    if not value:raise RefreshError(reason)

def clean(value):return re.sub(r'\s+',' ',str(value or '')).strip()

def engine_data(html,gt=False):
    parser=ScriptData();parser.feed(html);require(parser.language in ('sv','sv-SE'),'swedish_engine_page_required')
    tables=[]
    for script in parser.scripts:
        m=re.search(r'eut\.tableDatas\["[0-9]+"\]\s*=\s*',script)
        if not m:continue
        d,end=json.JSONDecoder(object_pairs_hook=unique_object).raw_decode(script[m.end():])
        require(script[m.end()+end:].lstrip().startswith(';'),'literal_engine_table_required')
        if d.get('tableType')=='engine':tables.append(d)
    d=one(tables,'one_exact_engine_table_required');name='EV5 GT' if gt else 'EV5'
    require((d.get('modelName'),d.get('modelCode'),d.get('bodyTypeCode'))==(name,'X9','W5'),'exact_ev5_body_and_model_required')
    require("window.dtmDataLayer.vehicle_name = '"+('ev5gt' if gt else 'ev5')+"';" in html,'exact_vehicle_name_required')
    groups=d.get('enginesDetail');trims=d.get('trimsDetail')
    require(isinstance(groups,list) and isinstance(trims,list) and len(groups)==len(trims)==1,'one_nested_powertrain_group_required')
    require(groups[0].get('powerTrainModelName')==trims[0].get('powerTrainModelName')==name,'same_nested_model_group_required')
    return dict(d,engines=groups[0]['engines'],trims=trims[0]['trims'])

def extract(packets,now=None):
    now=now or datetime.now(timezone.utc)
    for key,url in URLS.items():
        s=packets[key]['source'];age=(now-datetime.fromisoformat(s['fetched_at'].replace('Z','+00:00'))).total_seconds()
        require(s['status']=='reachable' and s['http_status']==200 and s['final_url']==url
            and re.fullmatch('[a-f0-9]{64}',s['content_hash']) and -60<=age<=900,'fresh_exact_source_required:'+key)
    pages=packets['technical']['pages'];require(len(pages)==5 and '14 oktober 2026 (Modellår 2027)' in pages[0],'swedish_my27_edition_required')
    require('18" aluminiumfälgar' in pages[0] and '19" aluminiumfälgar' in pages[0],'standard_wheel_scope_required')
    technical=clean(pages[2]);require('MOTOR Long Range 81.4kWh FWD AWD' in technical and 'Motoreffekt hk 217 265' in technical,'exact_fwd_awd_columns_required')
    require(not re.search('preliminär|homologering',technical[:400],re.I),'final_regular_header_required')
    for quote in [*TECHNICAL_QUOTES.values(),*RANGES.values()]:require(quote in technical,'technical_row_changed:'+quote)
    require('Panoramaglastak - - T' in clean(pages[1]),'panorama_is_gt_line_option_required')
    specs=engine_data(packets['specifications']['html']);gt_specs=engine_data(packets['gt_specifications']['html'],True)
    model_text=clean(parse_document(packets['model']['html'].encode(),'text/html').text())
    require('Upptäck Kia EV5 AWD, en el-SUV med gott om utrymme' in model_text,'explicit_swedish_suv_required')
    require(GT_BLOCK in clean(parse_document(packets['gt']['html'].encode(),'text/html').text()),'swedish_306hp_gt_block_required')
    energy=clean(packets['energy']['pages'][0])
    require('OKTOBER 2026' in energy and 'EV5 Elmotor 265hk AWD LR El Euro 6ax 17,2-18,1 kWh 0 360 30 000 / 24 Elmotor 306hk AWD LR El Euro 6ax 18,6 kWh' in energy,'same_ev5_gt_energy_block_required')
    prices=packets['price_pdf']['pages'];require(len(prices)==2 and '2026-11-01' in prices[0] and '2026-11-30' in prices[0],'november_swedish_cash_price_period_required')
    de=packets['gt_germany']['pages'];require(len(de)==12,'registered_german_gt_layout_required')
    for q in ['Motor 81,4 kWh AWD','Leistung max. (kW/PS) 225/306','Max. DC-Ladeleistung (kW) 150','Kombiniert (kWh/100 km) 18,6','Anzahl der Sitze 5']:
        require(q in clean(de[9]),'same_german_gt_column_required:'+q)
    require('Laderaumvolumen bei aufgestellter Rücksitzbank, mit Einrechnung des doppelten Bodens 566' in clean(de[10]) and 'Reichweite2, max. (km) 476' in clean(de[10]),'gt_boot_not_folded_or_city_range_required')
    pl=packets['poland_pdf']['pages'];require(len(pl)==16,'registered_polish_pdf_layout_required')
    for q in ['81.4 kWh 81.4 kWh 81.4 kWh FWD AWD AWD GT','Maksymalna moc łączna [KM] 217 265 306',
        'Maksymalna moc ładowarki pokładowej [kW] 10.5 / 22 (z pakietem 22K)','476 (20”)']:
        require(q in clean(pl[14]),'same_polish_gt_standard_ac_column_required:'+q)
    drafts=[]
    for name,trim,engine,wheel,cash,drive,range_km,consumption,tow in VERSIONS:
        gt=trim=='GX2';panorama='Panorama' in name;data=gt_specs if gt else specs;key='gt_specifications' if gt else 'specifications'
        e=one((e for e in data['engines'] if e['id']==engine),'one_exact_engine_required')
        tr=one((t for t in data['trims'] if t['id']==trim),'one_exact_trim_required');pe=one(tr['enginesInTrim'],'one_trim_engine_required')
        engine_cash=(658900 if panorama else cash)-1000
        require(e['number of seats']=='5' and pe['id']==engine and int(pe['price'])==engine_cash,'same_engine_seats_and_observed_web_price_required')
        require(('225 KW (306 hk)' if gt else '195 KW (265 hk)' if drive=='AWD' else '160 KW (218 hk)') in e['name'],'same_motor_power_not_other_model_required')
        price_name='EV5 FWD Long Range' if name=='EV5 FWD' else name
        line=one((clean(l) for l in prices[1].splitlines() if re.match(re.escape(price_name)+r' [0-9]{3},[0-9]{3} kr(?: |$)',clean(l))),'one_exact_price_row_required')
        require(line.startswith(price_name+' '+f'{cash:,}'+' kr'),'cash_not_lease_or_paint_required')
        if panorama:
            require(cash-658900==12000 and 'EV5 GT Line AWD Long Range 658,900 kr' in clean(prices[1]),'exact_awd_gt_line_panorama_price_pair_required')
        primary='gt' if gt else 'technical';header=f'{name} | {engine} | {wheel} tum'
        r=dict(adapter=ADAPTER,brand='Kia',model='Ev5',variant_name=name,source=packets[primary]['source'],
            supporting_sources=[packets[k]['source'] for k in URLS if k!=primary and k not in ('gt','technical')],
            source_resolution='exact_swedish_ev5_my27_powertrain_wheel_and_panorama_not_gt_line_as_gt',
            extraction_confidence=0.99,facts={},field_evidence={},held_fields={})
        def add(field,value,source_key,quote,scope,page=None):
            r['facts'][field]=value;r['field_evidence'][field]=dict(value=value,variant_name=name,column_header=header,
                source_url=URLS[source_key],source_hash=packets[source_key]['source']['content_hash'],quote=quote,scope=scope,page=page)
        facts=dict(battery_kwh=81.4,wltp_range_km=range_km,wltp_consumption_kwh_100km=consumption,
            dc_charge_kw=150,ac_charge_kw=10.5,tow_kg=tow,boot_liters=566,drivetrain=drive)
        for field,value in facts.items():
            if not gt:add(field,value,'technical',RANGES[drive] if field=='wltp_range_km' else TECHNICAL_QUOTES[field],
                'swedish_my27_gt_line_panorama_option_group' if panorama else 'swedish_my27_powertrain_and_standard_wheels',3)
            elif field in GT_QUOTES:
                k,page,scope,quote=GT_QUOTES[field];add(field,value,k,quote,scope,page)
            elif field=='drivetrain':add(field,value,'gt_specifications',engine+' | '+e['name'],'exact_swedish_nested_gt_drivetrain')
            else:add(field,value,'gt',GT_BLOCK,'swedish_306hp_gt_not_gt_line')
        require(drive in e['name'],'same_engine_drivetrain_required')
        add('seats',5,key,engine+' | '+e['name']+' | number of seats 5','exact_swedish_nested_engine_and_panorama_option' if panorama else 'exact_swedish_nested_trim_engine')
        r['model_facts']={'body_type':'SUV'};r['model_field_evidence']={'body_type':dict(value='SUV',source_url=URLS['model'],
            source_hash=packets['model']['source']['content_hash'],quote='Upptäck Kia EV5 AWD, en el-SUV med gott om utrymme')}
        r['price_evidence']=dict(value=cash,price_type='list_price',price_valid_until='2026-11-30',page=2,source_url=URLS['price_pdf'],
            source_hash=packets['price_pdf']['source']['content_hash'],quote=line,classification='dated_november_swedish_list_not_undated_engine_or_lease')
        r['price_alternative']=dict(source_url=URLS[key],source_hash=packets[key]['source']['content_hash'],engine_code=engine,
            embedded_price=engine_cash,reason='undated_base_trim_price_excludes_panorama_total' if panorama else 'undated_engine_price_1000_below_dated_november_pdf')
        r['price_evidence']['alternative']=r['price_alternative']
        r['source_decisions']=[
            'Preserve five existing canonical identities/routes and all price amounts. EV5 FWD is the explicit alias of Swedish EV5 FWD Long Range.',
            'Swedish14October2026 MY2027 PDF supplies18inch FWD552/16.0 and PlusAWD513/17.2,19inch GTLine491/18.1; do not select old foreign530/484 or generic footer16.9/18.2.',
            'FWD engine JSON218hk and PDF217hk both identify160kW/X9W5; do not infer another motor from horsepower rounding or borrow204hp EV5 energy-declaration typo.',
            'GTLinePanorama is the documented GTLineAWD option: exact November658900/670900 price pair plus PDF optional Panoramaglastak; use qualified group maxima, not an invented individual homologation.',
            'Swedish nested X9/W5 trim/engine groups bind five seats; GT225kW306hp is separate from regularAWD195kW265hp.',
            'Swedish GT block supplies476km/81.4kWh/1800kg. October306hp energy row supplies18.6; German same-GT table supplies DC150 and seats-up boot566 including double floor.',
            'Polish manufacturer PDF page15 explicitly includes81.4kWh AWD GT306hp and standard onboardAC10.5; optional22K is not standard. German AC11 supply timing is not selected as exact onboard maximum.',
            'All four regular versions use explicit Swedish onboardAC10.5, DC150, boot566 with seats up excluding44frunk/1650folded, tow1200FWD/1800AWD.',
            'Choose dated Swedish November1-30 list PDF over undated embedded prices1000SEK lower; store both observations. Never use lease6xxx/7xxx, paint20000 or foreign offers as cash list price.',
            'Preserve shared price/energy source model* and uppercase EV5 labels for existing model/spec pages. Leave unrelated old EV4 price HTML source unchanged.',
            'Retain exact EV5 Baseline press photo and full frame with model/equipment notice, not a claim of GT equipment. Foreign evidence retains PL/pl and DE/de labels.']
        drafts.append(r)
    return drafts

def collect(output):
    output.mkdir(parents=True,exist_ok=True);packets={}
    fetcher=SourceFetcher(timeout=25,max_bytes=14*1024*1024,document_parser=lambda b,k:b,url_policy=lambda u,brands:u in URLS.values() and brands=={'Kia'})
    for key,url in URLS.items():
        result=fetcher.fetch(url,{'Kia'});require(result['status']=='reachable' and result['final_url']==url,'ev5_source_unavailable:'+key+':'+result['status'])
        raw=result['document'];source={k:result[k] for k in ['status','http_status','final_url','content_hash']};source['fetched_at']=datetime.now(timezone.utc).isoformat()
        packet={'source':source};(output/(key+('.pdf' if url.endswith('.pdf') else '.html'))).write_bytes(raw)
        if url.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(raw)) as doc:packet['pages']=[p.extract_text() or '' for p in doc.pages]
        else:packet['html']=raw.decode('utf8')
        packets[key]=packet
    drafts=extract(packets)
    for name,value in [('source-packets.json',packets),('intake.json',dict(adapter=ADAPTER,drafts=drafts,held=[],database_writes=0,paid_calls=0))]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(drafts=len(drafts),technical_facts=45,prices=5,database_writes=0,paid_calls=0)))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);collect(parser.parse_args().output)
