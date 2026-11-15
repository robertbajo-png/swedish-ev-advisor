"""Complete Swedish C-HR+ profiles from exact official documents. No DB or AI writes."""
import argparse
import io
import json
import re
from dataclasses import asdict
from datetime import date,datetime,timezone
from pathlib import Path
import pdfplumber
from audit_catalog_sources import SourceFetcher
from import_mobility_sweden import parse_elbil_ranking
from manufacturer_embedded_data import unique_object
from toyota_price_intake import parse_pdf
from variant_refresh import RefreshError,one,parse_document

ADAPTER='toyota_chr_plus_sweden_pilot_v1'
MODEL_ID='d3221898-3c90-4ee4-8e2e-f493b8e84ab6'
BODY_ID='30b0ef55-504f-4ce5-8f54-6856b2e8aa20'
VERSION='6.HD'
URLS=dict(model='https://www.toyota.se/bilar/toyota-c-hr-plus',
    specifications='https://www.toyota.se/bilar/toyota-c-hr-plus/specifications',
    price_pdf='https://pdf.toyotasverigebroschyr.com/price-list/nya-toyota-c-hr')
MARKET_URL='https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx'
PROFILES=[
    ('C-HR+ Active FWD 77 kWh 224 hk','dd36efb2-a7b9-4a02-82f8-94ca3f245507','Active','0ad8a6f6-9ed1-461c-839e-3b5dd2a11c3a','FWD',224,18,519900,607,13.4,11,750,'C-HR+ Active 18'),
    ('C-HR+ Active AWD 77 kWh 343 hk','8e1ce48d-02cc-4401-8c02-08c0f2e4d61b','Active','0ad8a6f6-9ed1-461c-839e-3b5dd2a11c3a','AWD',343,18,540900,548,14.4,11,1500,'C-HR+ Active AWD 18'),
    ('C-HR+ Executive AWD 77 kWh 343 hk','faa99752-7181-446b-91d8-74556b0f96b0','Executive','849be735-8d4a-45c8-a6d6-f73d5b47dbe3','AWD',343,20,593900,507,15.5,22,1500,'C-HR+ Executive AWD'),
]
RANGE='*Räckvidden beror på utrustningsnivå – Active 2WD 18": 607 km, Active 2WD 20": 560 km, Active AWD 18": 548 km, Active AWD 20": 511 km, Executive AWD: 507 km.'
GROSS='77 kWh-batteri avser bruttobatterikapacitet.'
BOOT='Toyota C-HR+ är kompakt men rymlig och erbjuder 416 liter bagageutrymme'


def require(value,reason):
    if not value:raise RefreshError(reason)


def clean(value):return re.sub(r'\s+',' ',str(value or '')).strip()


def configuration(html):
    document=parse_document(html.encode(),'text/html')
    result=[]
    for n in document.nodes('div'):
        if not n.attrs.get('id','').endswith('-data') or not n.text().startswith('{'):continue
        raw=''.join(v for v in n.children if isinstance(v,str))
        c=json.loads(raw,object_pairs_hook=unique_object,parse_constant=lambda _:require(False,'non_finite_configuration'))
        if isinstance(c,dict) and 'carConfigMotorization' in c:result.append(c)
    c=one(result,'one_literal_configuration_required')
    require({k:c['commonSettings'].get(k) for k in ['brand','country','language','component']}==
        dict(brand='toyota',country='se',language='sv',component='car-config'),'exact_swedish_configuration_required')
    car=c['car'];model=car['model']
    require(car['initialized'] is True and c['carConfigMotorization']['initialized'] is True and
        (model['id'],model['name'],model['configVersion'],model['steering'])==(MODEL_ID,'Nya Toyota C-HR+',VERSION,'L') and
        car['body']['id']==BODY_ID and car['body']['name']=='SUV 5-d','plus_bev_generation_and_body_required')
    require(car['id']==PROFILES[0][1] and car['grade']['id']==PROFILES[0][3] and car['grade']['name']=='Active','selected_active_fwd_required')
    grades=c['grades']['items']
    require([(g['name'],g['id'],g['defaultCarId']) for g in grades]==[
        ('Active',PROFILES[0][3],PROFILES[0][1]),('Executive',PROFILES[2][3],PROFILES[2][1])],'exact_grade_defaults_required')
    motors=c['carConfigMotorization']['motorization']
    require(len(motors)==2,'two_active_motorizations_required')
    for p in PROFILES[:2]:
        m=one((m for m in motors if m['carId']==p[1]),'exact_active_engine_required')
        engine=m['engine'];price=m['price'];drive=m['wheeldrive']
        require(engine['category']['code']=='BEV' and engine['internalFuelCode']=='ELECTRIC' and engine['certification']==2
            and engine['name']==f'Elmotor {p[5]} hk, batteri 77 kWh' and
            drive['internalCode']==('2WD' if p[4]=='FWD' else '4WD') and drive['name']==('Framhjulsdrift' if p[4]=='FWD' else 'AWD')
            and price['cash']==p[7] and price['exclVat']*1.25==p[7] and price['promotions']==[], 'exact_bev_motor_cash_and_drive_required')
        consumption=one((s for s in m['specs'] if s['internalCode']=='ECCOMBINEDWLTP'),'exact_motor_consumption_required')
        require(consumption['certification']==2 and consumption['unit']=='Wh/km' and float(consumption['value'])/10==p[9], 'certified_combined_consumption_required')
    require(car['price']['cash']==PROFILES[0][7] and car['price']['promotions']==[],'selected_cash_match_required')
    selected=one((m for m in motors if m['carId']==car['id']),'one_selected_motor_required')
    require(all(car['motorization']['engine'][k]==selected['engine'][k] for k in ['id','name','internalFuelCode']) and
        car['motorization']['engine']['category']['code']=='BEV' and
        all(car['motorization']['wheeldrive'][k]==selected['wheeldrive'][k] for k in ['name','internalCode']),
        'selected_car_and_motorization_must_agree')
    tech={}
    for group in c['specs']['techSpecs']:
        for item in group['data']:
            require(item['internalCode'] not in tech,'duplicate_technical_code')
            tech[item['internalCode']]=item
    for code,value,unit in [('FT','El',''),('PERCOMBINED','607','km'),('B89AC81C-6DA8','13,4','kWh/100km'),
        ('AC95940B-E5CE','77','kWh'),('3EB2873F-D852','150','kW'),('DRV','FWD',''),
        ('TOWCAPBRK','750','kg'),('NRSEAT','5','säten'),('VDALUCAPREARUP','416','l'),('TYRSIZE','235/60R18','')]:
        require(code in tech and clean(tech[code]['value'])==value and tech[code]['unit']==unit,'selected_technical_scope_changed:'+code)
    require(tech['PERCOMBINED']['certification']==2 and tech['B89AC81C-6DA8']['certification']==2,'final_wltp_required')
    require(any(e['name']=='Ombordladdare 11 kW AC och kapacitet för snabbladdning 150 kW DC' and e['standard'] is True
        for e in c['specs']['standardEquipment']),'active_onboard_not_charger_rating_required')
    return c


def extract(packets,market,now=None):
    now=now or datetime.now(timezone.utc)
    require(set(packets)==set(URLS),'exact_source_set_required')
    for key,url in {**URLS,'market':MARKET_URL}.items():
        s=market['source'] if key=='market' else packets[key]['source']
        age=(now-datetime.fromisoformat(s['fetched_at'].replace('Z','+00:00'))).total_seconds()
        require(s['status']=='reachable' and s['http_status']==200 and s['final_url']==url and
            re.fullmatch('[a-f0-9]{64}',s['content_hash']) and -60<=age<=900,'fresh_exact_source_required:'+key)
    c=configuration(packets['specifications']['html'])
    document=parse_document(packets['model']['html'].encode(),'text/html');text=clean(document.text())
    for quote in [RANGE,GROSS,BOOT,'slutliga homologiseringsvärden för kombinerad WLTP-räckvidd']:
        require(quote in text,'exact_final_model_support_required:'+quote)
    require(any(a.attrs.get('href')==URLS['price_pdf'] for a in document.nodes('a')),'current_official_pdf_link_required')
    pdf=packets['price_pdf'];pages=[clean(v) for v in pdf['pages']]
    require(len(pages)==9 and not pages[4] and all(v for i,v in enumerate(pages) if i!=4) and
        'TOYOTA C-HR+ Prislista och broschyr' in pages[0],'exact_brochure_and_only_visual_page_required')
    require('Elmotor 224 hk, batteri 77 kWh Elmotor 343 hk, batteri 77 kWh' in pages[5] and
        'Dragvikt bromsat släp (kg) 750 1500' in pages[5] and 'Antal platser 5 5' in pages[6], 'same_bev_columns_and_braked_towing_required')
    dated=re.search(r'Uppdaterad: (\d{4}-\d{2}-\d{2}) \d{2}:\d{2}',pages[8])
    require(dated and -1<=(now.date()-date.fromisoformat(dated[1])).days<=7 and
        'Alla priser' in pages[8] and 'generalagent' in pages[8], 'current_general_agent_price_document_required')
    require('Ombordladdare 11 kW AC' in pages[2] and 'Ombordladdare 22 kW AC' in pages[3] and
        all('snabbladdning 150 kW DC' in pages[i] for i in [2,3]),'grade_specific_charging_required')
    m=market['row']
    require(m['brand_raw']=='TOYOTA' and m['model_raw']=='C-HR+' and m['normalized_brand']=='toyota' and
        m['normalized_model']=='c hr' and m['fuel_type_raw']=='EL' and m['needs_mapping'] is False and
        m['last_seen_month']=='2026-10-01' and 0<m['registrations_last_month']<=m['registrations_ytd'] and
        market['sheet']=='Elbil ranking','exact_plus_electric_market_required')
    drafts=[]
    for p in PROFILES:
        name,identity,grade,gid,drive,power,wheel,cash,km,consumption,ac,tow,pdfname=p
        column=pdf['left_columns'][0 if grade=='Active' else 1]
        pattern=re.escape(pdfname)+r'\s+Fr.n:\s+([0-9 ]+) kr\s+Easy Bill.n fr.n:\s+([0-9 ]+) kr/m.n\s+Elf.rbrukning \(WLTP\):\s+([0-9.]+) kWh/100km'
        block=one(list(re.finditer(pattern,column)),'one_exact_cash_panel_required')
        require(int(block[1].replace(' ',''))==cash and float(block[3])==consumption,'cash_not_monthly_or_other_grade_required')
        facts=dict(wltp_range_km=km,wltp_consumption_kwh_100km=consumption,battery_kwh=77,dc_charge_kw=150,
            ac_charge_kw=ac,boot_liters=416,tow_kg=tow,seats=5,drivetrain=drive)
        evidence={}
        for field,value in facts.items():
            key,page,quote='price_pdf',3 if grade=='Active' else 4,block[0]
            if field=='wltp_range_km':key,page,quote='model',None,RANGE
            elif field=='battery_kwh':key,page,quote='model',None,GROSS
            elif field=='boot_liters':key,page,quote='model',None,BOOT
            elif field in ('ac_charge_kw','dc_charge_kw'):quote=f'Ombordladdare {ac} kW AC | snabbladdning 150 kW DC'
            elif field=='tow_kg':page,quote=6,'Elmotor 224 hk, batteri 77 kWh | Elmotor 343 hk, batteri 77 kWh | Dragvikt bromsat släp (kg) 750 1500'
            elif field=='seats':page,quote=7,'Elmotor 224 hk, batteri 77 kWh | Elmotor 343 hk, batteri 77 kWh | Antal platser 5 5'
            elif field=='drivetrain':
                key,page='specifications',None
                quote=f'{MODEL_ID} | {VERSION} | {grade} | {identity} | '+('Framhjulsdrift' if drive=='FWD' else 'AWD')
                if grade=='Executive':key,page,quote='price_pdf',4,pdfname
            evidence[field]=dict(value=value,variant_name=name,column_header=f'Toyota C-HR+ | {grade} | {drive} | 77 kWh brutto | {power} hk | {wheel} tum',
                manufacturer_variant_id=identity,manufacturer_model_id=MODEL_ID,config_version=VERSION,grade_id=gid,
                source_url=URLS[key],source_hash=packets[key]['source']['content_hash'],quote=quote,page=page)
        drafts.append(dict(variant_name=name,manufacturer_identity=identity,facts=facts,field_evidence=evidence,extraction_confidence=0.99,
            price_evidence=dict(value=cash,price_type='list_price',price_valid_until=None,source_url=URLS['price_pdf'],
                source_hash=pdf['source']['content_hash'],page=3 if grade=='Active' else 4,quote=block[0])))
    return dict(adapter=ADAPTER,model=dict(brand='Toyota',model='C-Hr+',normalized_brand='toyota',normalized_model='c hr',body_type='SUV'),
        model_evidence=dict(body_type=dict(value='SUV',quote=f'{MODEL_ID} | Nya Toyota C-HR+ | SUV 5-d',source_url=URLS['specifications'],source_hash=packets['specifications']['source']['content_hash'])),
        sources=[dict(**p['source'],key=k,source_type='price_list_pdf' if k=='price_pdf' else 'manufacturer_page',shared=False,
            source_name='Toyota Sverige',country='SE',language='sv',source_authority='manufacturer') for k,p in packets.items()],
        market=market,drafts=drafts,source_decisions=[
            'Exact Swedish C-HR+ BEV, model d3221898, config6.HD, left-hand drive. C-HR hybrid and US-market C-HR are excluded despite normalized-key collision.',
            'Active FWD/AWD have18inch standard wheels:607/548km. Executive AWD20inch is507km, not Active548 or generic607. Optional wheels/panorama are separate scopes.',
            'Current official model footnote explicitly gives final homologated combined WLTP for77kWh gross. Ignore the generic copied49/61kWh paragraph elsewhere on the same page.',
            'Current linked Swedish PDF gives exact grade consumption13.4/14.4/15.5, onboardAC11/11/22, DC150 and braked towing750/1500/1500. Preserve its engine columns.',
            'Five seats, rear boot416L with seats up; not folded volume, train weight or unbraked tow. Current Swedish selected-car technical rows cross-check the common body and base motor.',
            'Cash list prices519900/540900/593900 are separate from monthly financing and promotions. January11 date is a finance/leasing condition, not list-price expiry.',
            'PDF page5 is a visual-only page, not missing technical data. All other pages are required; original PDF, literal excerpts and visually checked price/technical pages are retained.',
            'Mobility Sweden proves activity only. Keep March history and unconfirmed availability; no12m total without12 distinct months.'
        ],paid_calls=0,database_writes=0)


def collect(output):
    output.mkdir(parents=True,exist_ok=True)
    fetcher=SourceFetcher(timeout=30,max_bytes=14000000,document_parser=lambda body,kind:body,
        url_policy=lambda url,brands:url in [*URLS.values(),MARKET_URL],text_parser=lambda body,kind:'')
    packets={}
    for key,url in {**URLS,'market':MARKET_URL}.items():
        r=fetcher.fetch(url,{'Toyota'} if key!='market' else set())
        require(r['status']=='reachable' and r['final_url']==url,'source_unavailable:'+key+':'+r['status'])
        raw=r['document'];source={k:r[k] for k in ['status','http_status','final_url','content_hash']}
        source['fetched_at']=datetime.now(timezone.utc).isoformat()
        path=output/(key+('.xlsx' if key=='market' else '.pdf' if key=='price_pdf' else '.html'));path.write_bytes(raw)
        if key=='market':
            rows,_=parse_elbil_ranking(path,url)
            row=one((asdict(v) for v in rows if v.brand_raw=='TOYOTA' and v.model_raw=='C-HR+'),'one_exact_market_row_required')
            market=dict(source=source,row=row,sheet='Elbil ranking')
        elif key=='price_pdf':
            pages=parse_pdf(raw,'application/pdf',allowed_empty_pages={5})['pages']
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                columns=[pdf.pages[i].crop((0,0,225,pdf.pages[i].height)).extract_text() or '' for i in [2,3]]
            packets[key]=dict(source=source,pages=pages,left_columns=columns)
        else:packets[key]=dict(source=source,html=raw.decode('utf8'))
    (output/'source-packets.json').write_text(json.dumps(dict(packets=packets,market=market),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    intake=extract(packets,market)
    (output/'intake.json').write_text(json.dumps(intake,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(drafts=len(intake['drafts']),technical_facts=27,prices=3,market_month=market['row']['last_seen_month'],database_writes=0,paid_calls=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output)
