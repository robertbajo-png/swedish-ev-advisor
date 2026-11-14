"""Current seven-version EV3 intake. Preserve decimals and manufacturer scope."""
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

ADAPTER='kia_ev3_sweden_completion_v1'
BASE='https://www.kia.com'
URLS=dict(
 technical=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev3/Faktablad-Kia-EV3.pdf',
 specifications=BASE+'/se/nya-bilar/ev3/specifikationer/',
 gt_specifications=BASE+'/se/nya-bilar/ev3-gt/specifikationer/',
 gt=BASE+'/se/nya-bilar/ev3-gt/upptack/',
 energy=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf',
 price_pdf=BASE+'/content/dam/kwcms/kme/se/sv/assets/contents/utility/prislista/kia-sweden-pricelist.pdf',
 poland=BASE+'/pl/modele/ev3/dane-techniczne/',
 gt_germany=BASE+'/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV3-GT-Preisliste.pdf')
# Canonical identity, manufacturer trim/engine, wheels, exact Swedish cash price.
VERSIONS=[
 ('EV3 FWD','TX1','9VW5ZHZ7Z-TX1',17,434900,'FWD',58.3,436,14.9,101,500,460),
 ('EV3 FWD Long Range','LX1','9VW5ZHZ7Z-LX1',17,508300,'FWD',81.4,605,14.9,128,1000,460),
 ('EV3 Plus FWD Long Range','LX2','9VW5ZHZ7Z-LX2',17,540300,'FWD',81.4,605,14.9,128,1000,460),
 ('EV3 GT Line FWD Long Range','SX1','9VW5ZHZ7Z-SX1',19,590300,'FWD',81.4,563,16.2,128,1000,460),
 ('EV3 Plus AWD Long Range','LX3','9VW5YGZ7Z-LX3',19,575300,'AWD',81.4,572,15.8,128,1500,413),
 ('EV3 GT Line AWD Long Range','SX2','9VW5YGZ7Z-SX2',19,625300,'AWD',81.4,572,15.8,128,1500,413),
 ('EV3 GT (292hk) AWD Long Range','DX1','9VW5YGZ7Z-DX1',20,650900,'AWD',81.4,532,17.1,128,1500,413),
]


def require(value,reason):
    if not value:raise RefreshError(reason)


def clean(value):return re.sub(r'\s+',' ',str(value or '')).strip()


def engine_data(html,gt=False):
    parser=ScriptData();parser.feed(html)
    require(parser.language in ('sv','sv-SE'),'swedish_engine_page_required')
    tables=[]
    for script in parser.scripts:
        m=re.search(r'eut\.tableDatas\["[0-9]+"\]\s*=\s*',script)
        if not m:continue
        value,end=json.JSONDecoder(object_pairs_hook=unique_object).raw_decode(script[m.end():])
        require(script[m.end()+end:].lstrip().startswith(';'),'literal_engine_data_required')
        if value.get('tableType')=='engine':tables.append(value)
    data=one(tables,'one_manufacturer_engine_table_required')
    require((data['modelName'],data['modelCode'],data['bodyTypeCode'])==('EV3 GT' if gt else 'EV3','9V','W5'),'exact_ev3_body_and_model_required')
    name='ev3gt' if gt else 'ev3'
    require("window.dtmDataLayer.vehicle_name = '"+name+"';" in html
            and "'suv---stadsjeep'" in html,'model_bound_suv_identity_required')
    return data


def extract(packets,now=None):
    now=now or datetime.now(timezone.utc)
    for key,url in URLS.items():
        s=packets[key]['source'];age=(now-datetime.fromisoformat(s['fetched_at'].replace('Z','+00:00'))).total_seconds()
        require(s['status']=='reachable' and s['http_status']==200 and s['final_url']==url
                and re.fullmatch('[a-f0-9]{64}',s['content_hash']) and -60<=age<=900,'fresh_registered_ev3_source_required:'+key)
    technical=packets['technical']['pages'];require(len(technical)==5 and '16 september 2026' in technical[0],'current_september_swedish_edition_required')
    text=clean(technical[2]);preliminary='(AWD, Preliminär information i väntan på homologering)'
    for q in [preliminary,'58.3kWh 81.4kWh FWD FWD/AWD','Batterikapacitet (kWh) 58.3 81.4',
              'Bilens laddare (On Board Charger) (kW) 10.5','DC snabbladdning max kW 101 128',
              'Max räckvidd (km) enligt WLTP (Upp till) FWD 436 (17") 605 (17") & 563 (19")',
              'Max räckvidd (km) enligt WLTP (Upp till) AWD 572 (19")',
              'BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv (liter) FWD 460 / 1251 / 25',
              'Baksäte uppfällt / nedfällt / under framhuv (liter) AWD 413 / 1204 / 25',
              'Max släpvagnsvikt, bromsat släp 500 1 000 / 1500']:
        require(q in text,'exact_swedish_technical_binding_changed:'+q)
    energy=clean(packets['energy']['pages'][0]);require('OKTOBER 2026' in energy,'current_swedish_consumption_edition_required')
    energy_block='Elmotor 204hk FWD SR El Euro 6ax 14,9 kWh 0 360 30 000 / 24 EV3 Elmotor 204hk FWD LR El Euro 6ax 14,9-16,2 kWh 0 360 30 000 / 24 Elmotor 265hk AWD LR El Euro 6ax 15,8 kWh 0 360 30 000 / 24 Elmotor 292hk AWD LR El Euro 6ax 17,1 kWh 0 360 30 000 / 24'
    require(energy_block in energy,'swedish_ev3_four_motor_energy_rows_required')
    price=packets['price_pdf']['pages'][0]
    require('2026-11-01' in price and '2026-11-30' in price,'current_november_list_price_period_required')
    specs=engine_data(packets['specifications']['html']);gt_specs=engine_data(packets['gt_specifications']['html'],True)
    gt=clean(parse_document(packets['gt']['html'].encode(),'text/html').text())
    gt_block='EV3 GT Batterikapacitet: 81.4 kWh Laddningstid (min. DC 10-80%): 31 minuter Motoreffekt: 215 kW / 292 hk Max släpvagnsvikt, bromsat släp: 1,500 kg 0-100 km/h: 5.7 sekunder Toppfart: 170 km/h Max räckvidd (km) enligt WLTP (Upp till): 532 km'
    require(gt_block in gt,'current_swedish_gt_292_not_gt_line_required')
    german=clean(packets['gt_germany']['pages'][11])
    require('Motor 81,4 kWh AWD GT' in german and 'Leistung max. (kW/PS) 215/292' in german
            and 'Max. DC-Ladeleistung (kW) 128' in german,'exact_gt_manufacturer_peak_dc_required')
    poland=parse_document(packets['poland']['html'].encode(),'text/html')
    tables=[[[c.text() for c in r.children if not isinstance(c,str) and c.tag in ('td','th')] for r in t.nodes('tr')] for t in poland.nodes('table')]
    headers=[r for table in tables for r in table if r[:5]==['','58,3 kWh FWD','81,4 kWh FWD','81,4 kWh AWD','81,4 kWh AWD GT']]
    require(len(headers)==3,'exact_polish_four_powertrain_headers_required')
    electrical=one((t for t in tables if any(r and r[0]=='Max. moc ładowarki pokładowej AC [kW]' for r in t)),'one_polish_electrical_table_required')
    ac=one((r for r in electrical if r[0]=='Max. moc ładowarki pokładowej AC [kW]'),'one_onboard_ac_row_required')
    require(ac[1:5]==['10,5 / 22 (opcja)']*4,'standard_not_optional_onboard_ac_required')
    require(one((r for r in electrical if r[0]=='Max. moc łączna [KM]'),'one_power_binding_required')[1:5]==['204','204','265','292'],'four_powertrain_columns_required')
    cargo=one((t for t in tables if any(r and r[0]=='Pojemność bagażnika tył [l]' for r in t)),'one_manufacturer_cargo_table_required')
    boot=one((r for r in cargo if r[0]=='Pojemność bagażnika tył [l]'),'one_seats_up_boot_row_required')
    require(boot[1:5]==['460 / 1 251','460 / 1 251','413 / 1 204','413 / 1 204'],'gt_and_awd_seats_up_boot_required')
    drafts=[]
    for name,trim,engine,wheel,cash,drive,battery,range_km,consumption,dc,tow,boot_liters in VERSIONS:
        is_gt=trim=='DX1';data=gt_specs if is_gt else specs
        e=one((e for e in data['engines'] if e['id']==engine),'one_exact_engine_required')
        tr=one((t for t in data['trims'] if t['id']==trim),'one_exact_trim_required')
        price_engine=one(tr['enginesInTrim'],'one_trim_engine_required')
        require(e['number of seats']=='5' and price_engine['id']==engine and int(price_engine['price'])==cash
                and ('292 hk' if is_gt else '265 hk' if drive=='AWD' else '204 hk') in e['name'],'trim_engine_seats_price_binding_required')
        line=one((clean(l) for l in price.splitlines() if re.match(re.escape(name)+r' [0-9]{3},[0-9]{3} kr(?: |$)',clean(l))),'one_exact_november_price_row_required')
        require(line.startswith(name+' '+f'{cash:,}'+' kr'),'cash_not_monthly_or_matt_paint_required')
        primary='gt' if is_gt else 'technical';header=f'{name} | {engine} | {wheel} tum'
        sources=[packets[k]['source'] for k in URLS if k!=primary and k not in ('gt','technical')]
        r=dict(adapter=ADAPTER,brand='Kia',model='Ev3',variant_name=name,source=packets[primary]['source'],
            supporting_sources=sources,source_resolution='current_swedish_exact_ev3_trim_not_gt_line_as_gt',
            extraction_confidence=0.99,facts={},field_evidence={},held_fields={})
        def add(field,value,key,quote,scope,page=None):
            s=packets[key]['source'];r['facts'][field]=value
            r['field_evidence'][field]=dict(value=value,quote=quote,scope=scope,page=page,column_header=header,
                variant_name=name,source_url=s['final_url'],source_hash=s['content_hash'])
        if is_gt:
            for field,value,quote in [('wltp_range_km',range_km,gt_block),('battery_kwh',battery,gt_block),('tow_kg',tow,gt_block),
                                      ('drivetrain',drive,'EV3 GT är utrustad med fyrhjulsdrift (AWD) med dubbla elmotorer och ett batteri på 81,4 kWh')]:
                require(quote in gt,'exact_gt_quote_missing');add(field,value,'gt',quote,'swedish_292hp_gt_not_gt_line')
            add('dc_charge_kw',128,'gt_germany','Motor 81,4 kWh AWD GT | Leistung max. (kW/PS) 215/292 | Max. DC-Ladeleistung (kW) 128','german_same_gt_nominal_peak',12)
            add('ac_charge_kw',10.5,'poland','81,4 kWh AWD GT | Max. moc ładowarki pokładowej AC [kW] 10,5 / 22 (opcja)','polish_same_292hp_gt_standard_not_optional_22')
            add('boot_liters',413,'poland','81,4 kWh AWD GT | Pojemność bagażnika tył [l] 413 / 1 204','polish_same_gt_seats_up_not_folded')
        else:
            pairs=[('battery_kwh',battery,'Batterikapacitet (kWh) 58.3 81.4'),
                ('dc_charge_kw',dc,'DC snabbladdning max kW 101 128'),('ac_charge_kw',10.5,'Bilens laddare (On Board Charger) (kW) 10.5'),
                ('wltp_range_km',range_km,'Max räckvidd (km) enligt WLTP (Upp till) '+('AWD 572 (19")' if drive=='AWD' else 'FWD 436 (17") 605 (17") & 563 (19")')),
                ('tow_kg',tow,'Max släpvagnsvikt, bromsat släp 500 1 000 / 1500'),
                ('boot_liters',boot_liters,('Baksäte uppfällt / nedfällt / under framhuv (liter) AWD 413 / 1204 / 25' if drive=='AWD' else 'BAGAGEUTRYMME Baksäte uppfällt / nedfällt / under framhuv (liter) FWD 460 / 1251 / 25')),
                ('drivetrain',drive,'FWD FWD/AWD')]
            for field,value,quote in pairs:add(field,value,'technical',(preliminary+' | ' if drive=='AWD' else '')+quote,'swedish_265hp_awd_preliminary' if drive=='AWD' else 'swedish_final_fwd_wheel_column',3)
        energy_quote=('EV3 | Elmotor 292hk AWD LR | 17,1 kWh' if is_gt else 'EV3 | Elmotor 265hk AWD LR | 15,8 kWh' if drive=='AWD'
            else 'EV3 | Elmotor 204hk FWD SR | 14,9 kWh' if battery==58.3 else 'EV3 | Elmotor 204hk FWD LR | 14,9-16,2 kWh')
        # Exact wheel consumption for FWD LR is the qualified September row,
        # not arbitrarily the low end of the October versions-group interval.
        if drive=='FWD':
            q='Blandad, kWh/100km enligt WLTP FWD 1 4,9 (17") 14,9 (17") & 16,2 (19")'
            require(q in text,'wheel_bound_swedish_fwd_consumption_required')
            add('wltp_consumption_kwh_100km',consumption,'technical',q,'swedish_fwd_exact_17_or_19_wheel',3)
        else:add('wltp_consumption_kwh_100km',consumption,'energy',energy_quote,'swedish_october_powertrain_not_foreign_wltp',1)
        key='gt_specifications' if is_gt else 'specifications'
        add('seats',5,key,engine+' | '+e['name']+' | number of seats 5','exact_swedish_engine_trim')
        r['model_facts']={'body_type':'SUV'}
        r['model_field_evidence']={'body_type':dict(value='SUV',quote="vehicle_name "+('ev3gt' if is_gt else 'ev3')+" | vehicle_type suv---stadsjeep",
            source_url=URLS[key],source_hash=packets[key]['source']['content_hash'])}
        r['price_evidence']=dict(value=cash,price_type='list_price',price_valid_until='2026-11-30',source_url=URLS['price_pdf'],
            source_hash=packets['price_pdf']['source']['content_hash'],quote=line,classification='november_swedish_list_inclusive_vat_not_lease_or_paint')
        r['source_decisions']=[
            'Preserve all seven existing canonical identities and routes. Swedish 9V/W5 exact trim/engine codes, five seats and cash amounts agree with November price PDF.',
            'November1-30 price-list validity belongs to the whole list, not a financing campaign. Preserve list_price; leasing and optional20000SEK matte paint are not cash price.',
            'FWD Swedish standard wheels:17 inches except GT Line19. Keep436/605/563km and14.9/16.2 consumption aligned, not every FWD version at605km.',
            'Standard onboard AC10.5kW is exact, never rounded to11. GT Polish manufacturer column independently distinguishes standard10.5 from optional22.',
            'Regular AWD265hp remains explicitly preliminary pending Swedish homologation, including572km. Show a qualified manufacturer target; do not satisfy hard range requirements with it.',
            'GT292hp is not GT Line265hp. Swedish model page532km and October17.1 supersede foreign501km/18.1 for Swedish buyer display; preserve the disagreement and sources.',
            'GT nominal DC128kW is explicit in the German same215kW/81.4kWh GT table, not inferred from charging time or rounded by us from Polish127.5.',
            'GT boot413L and standardAC10.5 are explicit in the matching Polish292hp GT column; keep PL/pl source locale and linked qualification, no foreign prices imported.',
            'Swedish standard FWD boot460L, AWD413L; never add25L frunk or use folded1251/1204. Braked tow500/1000/1500kg is not80kg roof or100kg ball load.',
            'Existing approved exact-model EV3 GT Line press photo remains a model photograph with equipment notice, not a photograph of every trim.',
            'No other car, model-image, availability, news or budget changes.']
        drafts.append(r)
    return drafts


def collect(output):
    output.mkdir(parents=True,exist_ok=True);packets={}
    f=SourceFetcher(timeout=20,max_bytes=14*1024*1024,document_parser=lambda b,k:b,url_policy=lambda u,brands:u in URLS.values() and brands=={'Kia'})
    for key,url in URLS.items():
        result=f.fetch(url,{'Kia'});require(result['status']=='reachable' and result['final_url']==url,'ev3_source_unavailable:'+key+':'+result['status'])
        raw=result['document'];source={k:result[k] for k in ['status','http_status','final_url','content_hash']}
        source['fetched_at']=datetime.now(timezone.utc).isoformat();packet={'source':source}
        (output/(key+('.pdf' if url.endswith('.pdf') else '.html'))).write_bytes(raw)
        if url.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(raw)) as doc:packet['pages']=[p.extract_text() or '' for p in doc.pages]
        else:packet['html']=raw.decode('utf8')
        packets[key]=packet
    drafts=extract(packets)
    for name,value in [('source-packets.json',packets),('intake.json',dict(adapter=ADAPTER,drafts=drafts,held=[],database_writes=0,paid_calls=0))]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(drafts=len(drafts),technical_facts=63,prices=7,database_writes=0,paid_calls=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);collect(p.parse_args().output)
