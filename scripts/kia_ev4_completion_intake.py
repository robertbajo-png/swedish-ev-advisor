"""Source-bound completion of the three existing Swedish EV4 hatchback profiles."""
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

ADAPTER='kia_ev4_sweden_completion_v1'
BASE='https://www.kia.com'
URLS=dict(
 technical=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev4/kia-sweden-ev4-specification.pdf',
 specifications=BASE+'/se/nya-bilar/ev4/specs/',
 gt_specifications=BASE+'/se/nya-bilar/ev4-gt/specifications/',gt=BASE+'/se/nya-bilar/ev4-gt/upptack/',
 energy=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf',
 price_pdf=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
 poland=BASE+'/pl/modele/ev4/dane-techniczne/',
 gt_germany=BASE+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV4-GT-Preisliste.pdf')
VERSIONS=[
 ('EV4 GT Line FWD Long Range','LX1','7ZS6ZHZ7Z-LX1',19,623400,'FWD',584,15.8,1000,435),
 ('EV4 GT Line AWD Long Range','LX1_V00','7ZS6YGZ7Z-LX1_V00',19,658400,'AWD',550,16.5,1500,359),
 ('EV4 GT (292hk) AWD Long Range','LX2','7ZS6YGZ7Z-LX2',20,711900,'AWD',505,17.9,1500,359),
]
GT_BLOCK='EV4 GT Batterikapacitet: 81.4 kWh Laddningstid (min. DC 10-80%): 31 minutes Motoreffekt: 215 kW / 292 hk Max släpvagnsvikt, bromsat släp: 1,500 kg Acceleration (0-100 km/h) : 5.6 sekunder Max räckvidd (km) enligt WLTP (Upp till): 505 km'
ENERGY_BLOCK='Elmotor 204hk FWD LR El Euro 6ax 15,8 kWh 0 360 30 000 / 24 EV4 Elmotor 265hk AWD LR El Euro 6ax 16,5 kWh 0 360 30 000 / 24 Elmotor 292hk AWD LR El Euro 6ax 17,9 kWh 0 360 30 000 / 24'
TECHNICAL_QUOTES=dict(
 battery_kwh='Batterikapacitet (kWh) 81.4',ac_charge_kw='Bilens laddare (On Board Charger) (kW) 10.5',
 dc_charge_kw='DC snabbladdning max kW 128',wltp_range_km='Max räckvidd (km) enligt WLTP (Upp till) 584 550',
 wltp_consumption_kwh_100km='FÖRBRUKNING Blandad, kWh/100km enligt WLTP 15.8 16.5',
 boot_liters='BAGAGEUTRYMME Baksäte uppfällt / nedfällt 435 / 1450 359 / 1370',
 tow_kg='Max släpvagnsvikt, bromsat släp 1 000 1 500',drivetrain='FWD AWD')


def require(value,reason):
    if not value:raise RefreshError(reason)


def clean(value):return re.sub(r'\s+',' ',str(value or '')).strip()


def engine_data(html,gt=False):
    parser=ScriptData();parser.feed(html);require(parser.language in ('sv','sv-SE'),'swedish_engine_page_required')
    tables=[]
    for script in parser.scripts:
        match=re.search(r'eut\.tableDatas\["[0-9]+"\]\s*=\s*',script)
        if not match:continue
        value,end=json.JSONDecoder(object_pairs_hook=unique_object).raw_decode(script[match.end():])
        require(script[match.end()+end:].lstrip().startswith(';'),'literal_engine_table_required')
        if value.get('tableType')=='engine':tables.append(value)
    data=one(tables,'one_exact_engine_table_required')
    require((data.get('modelName'),data.get('modelCode'),data.get('bodyTypeCode'))==('EV4 GT' if gt else 'EV4','7Z','S6'),'exact_hatchback_not_fastback_required')
    require("window.dtmDataLayer.vehicle_name = '"+('ev4gt' if gt else 'ev4')+"';" in html,'exact_vehicle_name_required')
    if gt:
        require(isinstance(data.get('engines'),list) and isinstance(data.get('trims'),list),'flat_gt_engine_shape_required')
        return data
    groups=data.get('enginesDetail');trims=data.get('trimsDetail')
    require(isinstance(groups,list) and isinstance(trims,list) and len(groups)==len(trims)==1,'one_nested_ev4_powertrain_group_required')
    require(groups[0].get('powerTrainModelName')==trims[0].get('powerTrainModelName')=='EV4','nested_group_model_identity_required')
    return dict(data,engines=groups[0]['engines'],trims=trims[0]['trims'])


def extract(packets,now=None):
    now=now or datetime.now(timezone.utc)
    for key,url in URLS.items():
        s=packets[key]['source'];age=(now-datetime.fromisoformat(s['fetched_at'].replace('Z','+00:00'))).total_seconds()
        require(s['status']=='reachable' and s['http_status']==200 and s['final_url']==url
            and re.fullmatch('[a-f0-9]{64}',s['content_hash']) and -60<=age<=900,'fresh_registered_source_required:'+key)
    pages=packets['technical']['pages'];require(len(pages)==5 and '20 augusti 2026 (Modellår 2027)' in pages[0],'current_swedish_my27_edition_required')
    require('EV4 GT LINE' in pages[0] and '19"' in pages[0],'exact_gt_line_standard_wheels_required')
    technical=clean(pages[2]);require('MOTOR Long Range Long Range FWD AWD' in technical and 'Motoreffekt hk 204 265' in technical,'swedish_two_powertrain_header_required')
    require(not re.search('preliminär|homologering',technical[:400],re.I),'final_gt_line_header_required')
    for quote in TECHNICAL_QUOTES.values():require(quote in technical,'technical_row_changed:'+quote)
    specs=engine_data(packets['specifications']['html']);gt_specs=engine_data(packets['gt_specifications']['html'],True)
    regular_text=clean(parse_document(packets['specifications']['html'].encode(),'text/html').text())
    require('Halvkombins design baktill.' in regular_text,'swedish_hatchback_description_required')
    gt_text=clean(parse_document(packets['gt']['html'].encode(),'text/html').text())
    require(GT_BLOCK in gt_text,'exact_swedish_292hp_gt_block_required')
    require('20-tums aluminiumfälgar' in clean(parse_document(packets['gt_specifications']['html'].encode(),'text/html').text()),'gt_20inch_model_scope_required')
    energy=clean(packets['energy']['pages'][0]);require('OKTOBER 2026' in energy and ENERGY_BLOCK in energy,'exact_october_ev4_three_motor_energy_rows_required')
    price=packets['price_pdf']['pages'][0];require('2026-11-01' in price and '2026-11-30' in price,'november_price_period_required')
    german=packets['gt_germany']['pages'];require(len(german)==13,'registered_german_gt_pdf_layout_required')
    electric=clean(german[10]);practical=clean(german[11])
    for q in ['Motor 81,4 kWh AWD GT','Leistung max. (kW/PS) 215/292','Max. DC-Ladeleistung (kW) 128','Kombiniert (kWh/100 km) 19,2/17,9']:
        require(q in electric,'exact_gt_nominal_dc_and_tyre_basis_required:'+q)
    for q in ['Motor 81,4 kWh AWD GT','Anzahl der Sitze 5','Laderaumvolumen bei aufgestellter Rücksitzbank, mit Einrechnung des doppelten Bodens 377','Reichweite2, max. (km) 473 (20" Michelin)/505 (20" Pirelli)']:
        require(q in practical,'gt_measurement_scope_required:'+q)
    document=parse_document(packets['poland']['html'].encode(),'text/html')
    require("window.dtmDataLayer.vehicle_name = 'ev4';" in packets['poland']['html'],'polish_ev4_not_another_model_required')
    # This layout separates each sticky header and its body into two sibling tables.
    tables=[]
    for component in document.nodes('div'):
        if 'eut_tb1' not in component.attrs.get('class','').split():continue
        children=list(component.nodes('table'))
        if not children:continue
        require(len(children)==2,'paired_polish_tables_required')
        rows=[[[c.text() for c in r.children if not isinstance(c,str) and c.tag in ('td','th')] for r in t.nodes('tr')] for t in children]
        require(len(rows[0])==1 and rows[1],'one_sticky_header_and_body_required')
        tables.append(rows[0]+rows[1])
    header=['','58,3 kWh FWD','81,4 kWh FWD','81,4 kWh AWD','81,4 kWh AWD GT']
    electrical=one((t for t in tables if any(r and r[0]=='Max. moc ładowarki pokładowej AC [kW]' for r in t)),'one_polish_electrical_table_required')
    cargo=one((t for t in tables if any(r and r[0]=='Pojemność bagażnika [l]' for r in t)),'one_polish_cargo_table_required')
    for table in [electrical,cargo]:
        require(len(table[0])==6 and table[0][:5]==header and table[0][5]==' '.join(header[1:]),'exact_four_polish_powertrain_columns_required')
        require(all(len(row)==6 and row[5]=='' for row in table[1:]),'polish_mobile_duplicate_not_data_required')
    require(one((r for r in electrical if r[0]=='Max. moc łączna [KM]'),'one_power_row_required')[1:5]==['204','204','265','292'],'exact_gt_power_column_required')
    require(one((r for r in electrical if r[0]=='Max. moc ładowarki pokładowej AC [kW]'),'one_standard_ac_row_required')[1:5]==['10,5 / 22 (opcja)']*4,'standard_not_optional_ac_required')
    boot=one((r for r in cargo if r[0]=='Pojemność bagażnika [l]'),'one_seats_up_cargo_row_required')
    require(boot[1:5]==['435 - 1 415','435 - 1 415','390','359'],'exact_gt_boot_not_generic_awd_or_double_floor_required')
    drafts=[]
    for name,trim,engine,wheel,cash,drive,range_km,consumption,tow,boot_liters in VERSIONS:
        gt=trim=='LX2';data=gt_specs if gt else specs;key='gt_specifications' if gt else 'specifications'
        e=one((e for e in data['engines'] if e['id']==engine),'one_exact_engine_required')
        tr=one((t for t in data['trims'] if t['id']==trim),'one_exact_trim_required');pe=one(tr['enginesInTrim'],'one_trim_engine_required')
        require(e['number of seats']=='5' and pe['id']==engine and int(pe['price'])==cash
            and ('292 hk' if gt else '265 hk' if drive=='AWD' else '204 hk') in e['name'],'exact_trim_seats_power_price_binding_required')
        line=one((clean(l) for l in price.splitlines() if re.match(re.escape(name)+r' [0-9]{3},[0-9]{3} kr(?: |$)',clean(l))),'one_exact_swedish_list_price_row_required')
        require(line.startswith(name+' '+f'{cash:,}'+' kr'),'cash_not_lease_or_optional_paint_required')
        primary='gt' if gt else 'technical';header_text=f'{name} | {engine} | {wheel} tum'
        r=dict(adapter=ADAPTER,brand='Kia',model='Ev4',variant_name=name,source=packets[primary]['source'],
            supporting_sources=[packets[k]['source'] for k in URLS if k!=primary and k not in ('gt','technical')],
            source_resolution='exact_swedish_ev4_hatchback_my27_not_fastback_or_gt_line_as_gt',
            extraction_confidence=0.99,facts={},field_evidence={},held_fields={})
        def add(field,value,source_key,quote,scope,page=None):
            r['facts'][field]=value;r['field_evidence'][field]=dict(value=value,variant_name=name,column_header=header_text,
                source_url=URLS[source_key],source_hash=packets[source_key]['source']['content_hash'],quote=quote,scope=scope,page=page)
        values=dict(battery_kwh=81.4,wltp_range_km=range_km,wltp_consumption_kwh_100km=consumption,
            dc_charge_kw=128,ac_charge_kw=10.5,tow_kg=tow,boot_liters=boot_liters,drivetrain=drive)
        for field,value in values.items():
            if not gt:add(field,value,'technical',TECHNICAL_QUOTES[field],'swedish_my27_gt_line_19inch_column',3)
            elif field=='wltp_consumption_kwh_100km':add(field,value,'energy','EV4 | Elmotor 292hk AWD LR | 17,9 kWh','swedish_october_gt_not_generic_footer',1)
            elif field=='dc_charge_kw':add(field,value,'gt_germany','Motor 81,4 kWh AWD GT | Leistung max. (kW/PS) 215/292 | Max. DC-Ladeleistung (kW) 128','german_same_gt_nominal_peak_not_supply_rating',11)
            elif field=='ac_charge_kw':add(field,value,'poland','81,4 kWh AWD GT | Max. moc ładowarki pokładowej AC [kW] 10,5 / 22 (opcja)','polish_same_gt_standard_not_optional_22')
            elif field=='boot_liters':add(field,value,'poland','81,4 kWh AWD GT | Pojemność bagażnika [l] 359','polish_same_gt_not_390_awd_or_377_double_floor')
            elif field=='drivetrain':add(field,value,'gt_specifications',engine+' | '+e['name'],'exact_swedish_flat_gt_drivetrain')
            else:add(field,value,'gt',GT_BLOCK,'swedish_292hp_gt_not_gt_line')
        require(('AWD' if drive=='AWD' else 'FWD') in e['name'],'exact_swedish_engine_drivetrain_required')
        add('seats',5,key,engine+' | '+e['name']+' | number of seats 5','exact_swedish_nested_trim_engine' if not gt else 'exact_swedish_flat_gt_trim_engine')
        r['model_facts']={'body_type':'Halvkombi'}
        r['model_field_evidence']={'body_type':dict(value='Halvkombi',quote='EV4 | 7Z/S6 | Halvkombins design baktill.',
            source_url=URLS['specifications'],source_hash=packets['specifications']['source']['content_hash'])}
        r['price_evidence']=dict(value=cash,price_type='list_price',price_valid_until='2026-11-30',source_url=URLS['price_pdf'],
            source_hash=packets['price_pdf']['source']['content_hash'],quote=line,classification='november_swedish_list_inclusive_vat_not_lease_or_paint')
        r['qualifications']=dict(gt_tyre_basis=dict(source_url=URLS['gt_germany'],source_hash=packets['gt_germany']['source']['content_hash'],page=12,
            quote='Reichweite2, max. (km) 473 (20" Michelin)/505 (20" Pirelli)'),gt_boot_basis=dict(source_url=URLS['gt_germany'],
            source_hash=packets['gt_germany']['source']['content_hash'],page=12,quote='Laderaumvolumen bei aufgestellter Rücksitzbank, mit Einrechnung des doppelten Bodens 377'))
        r['source_decisions']=[
            'Preserve all three canonical EV4 hatchback identities, routes and existing price amounts; exact7Z/S6, never EV4 Fastback.',
            'Swedish regular engine/trimsDetail nested groups bind204/265hp, five seats and623400/658400SEK; flat GT292hp engine binds711900SEK.',
            'MY2027 Swedish20August technical PDF supplies GT Line standard19inch584/550km,15.8/16.5 consumption and81.4kWh.',
            'Exact onboard AC10.5kW is not rounded to11 and not optional22. For GT use matching Polish292hp manufacturer column, preserving PL/pl locale.',
            'Swedish GT505km,81.4kWh and1500kg plus October292hp consumption17.9 take precedence over generic footer values or other models.',
            'GT German215kW/81.4kWh table supplies nominal DC128, not350kW charger supply or Polish127.5 rounded by the extractor.',
            'German GT page12 binds505km to20inchPirelli and473km to20inchMichelin; preserve tyre conditions, not an identical range for all options.',
            'GT boot359L comes from exact Polish GT column, not generic AWD390 or German377 including the double floor. Keep both measurement bases visible.',
            'Swedish GT Line boot435FWD/359AWD overrides other-market generic AWD390; no folded1450/1370 or roof75/ball100kg used as boot/towing.',
            'November1-30 Swedish PDF prices match engine prices. Keep list_price and its validity, not Euro offers, lease amounts or optional paint.',
            'Shared price/energy source model label is* with no canonical parent; preserve legacyEV4priceHTML row and every other vehicle.',
            'Existing approved EV4 GT Line press photograph is a hatchback model photograph with equipment notice, not each trim or Fastback.']
        drafts.append(r)
    return drafts


def collect(output):
    output.mkdir(parents=True,exist_ok=True);packets={}
    fetcher=SourceFetcher(timeout=20,max_bytes=14*1024*1024,document_parser=lambda b,k:b,url_policy=lambda u,brands:u in URLS.values() and brands=={'Kia'})
    for key,url in URLS.items():
        result=fetcher.fetch(url,{'Kia'});require(result['status']=='reachable' and result['final_url']==url,'ev4_source_unavailable:'+key+':'+result['status'])
        raw=result['document'];source={k:result[k] for k in ['status','http_status','final_url','content_hash']};source['fetched_at']=datetime.now(timezone.utc).isoformat()
        packet={'source':source};(output/(key+('.pdf' if url.endswith('.pdf') else '.html'))).write_bytes(raw)
        if url.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(raw)) as doc:packet['pages']=[p.extract_text() or '' for p in doc.pages]
        else:packet['html']=raw.decode('utf8')
        packets[key]=packet
    drafts=extract(packets)
    for name,value in [('source-packets.json',packets),('intake.json',dict(adapter=ADAPTER,drafts=drafts,held=[],database_writes=0,paid_calls=0))]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(drafts=len(drafts),technical_facts=27,prices=3,database_writes=0,paid_calls=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);collect(parser.parse_args().output)
