"""Source-bound current Born VZ MY2027 intake; no paid extraction or publication."""
import argparse
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber
from pypdf import PdfReader
from audit_catalog_sources import SourceFetcher, source_text
from variant_refresh import RefreshError, one

ADAPTER = 'cupra_born_sweden_my2027_v1'
BASE = 'https://www.cupraofficial.se'
URLS = dict(
    index=BASE+'/kopa/broschyrer-prislistor',
    model=BASE+'/bilar/born',
    price=BASE+'/content/dam/countries/se/cupra-website/prislistor/born/cupra-born-modellar-27.pdf',
    energy=BASE+'/content/dam/countries/se/cupra-website/broschyr/cupra-bransledeklaration-okt2026.pdf',
    manuals=BASE+'/aga/instruktionsbocker/manual-details/_jcr_content/par/modeldetails.data.manualsModelDetails.born.json',
    manual=BASE+'/datamanual-manual/manuals/cupra/se-se/CUPRA_Born_03_26_SE.pdf',
    characteristics=BASE+'/datamanual-manual/manuals/cupra/se-se/CUPRA_Born_Datos_tecnicos_03_26_SE.pdf',
    technical='https://www.seat-cupra-mediacenter.com/content/dam/seat-media-center/models-all-brands/cupra-models/cupra-born/technical-data/New_CUPRA_Born_Technical_Data_26.pdf',
)
HEADER = 'VZ (240kW/79kWh)'
TOW_QUOTE = 'Bilen är inte godkänd för dragkrok.'


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('\u00ad', '')).strip()


def row(table, label):
    return one((r for r in table if clean(r[0]) == label), 'one_named_technical_row_required:'+label)


def extract(packets, now=None):
    now = now or datetime.now(timezone.utc)
    for key, url in URLS.items():
        s = packets[key]['source']
        age = (now-datetime.fromisoformat(s['fetched_at'].replace('Z','+00:00'))).total_seconds()
        if (s['status'] != 'reachable' or s['http_status'] != 200 or s['final_url'] != url
                or not re.fullmatch(r'[a-f0-9]{64}',s['content_hash']) or not -60 <= age <= 900):
            raise RefreshError('fresh_registered_cupra_source_required:'+key)
    index = packets['index']['content']
    if URLS['price'] not in packets['index']['links'] or URLS['energy'] not in packets['index']['links'] or 'Prislista modellår 27 (7 april' not in index:
        raise RefreshError('current_swedish_document_discovery_required')
    metadata = packets['manuals']['content']
    edition = one((m for m in metadata['manuals'] if m['manualId']=='CUPRA_K1_2027_14'), 'exact_my2027_manual_required')
    paths = {s['pdfPath'] for c in edition['categories'] for s in c['languages']}
    years = metadata['modelYears']
    if (metadata['modelName']!='Born' or not any(y['modelYear']=='2027' and any(e['manualId']=='CUPRA_K1_2027_14' and e['editionName']=='Upplaga 03.26' for e in y['editions']) for y in years)
            or not {URLS['manual'],URLS['characteristics']} <= paths):
        raise RefreshError('current_swedish_edition_binding_required')
    price_pages = packets['price']['content']
    if len(price_pages)!=2 or 'Samtliga priser är inklusive moms och avser modellår 2027.' not in clean(price_pages[0]):
        raise RefreshError('current_swedish_price_year_required')
    price_line = one((clean(t) for t in price_pages[0].splitlines() if t.startswith('Born VZ ')), 'one_vz_price_row_required')
    if price_line != 'Born VZ 79 kWh 240 kW (326 hk) 596 900:–':
        raise RefreshError('current_exact_vz_list_price_changed')
    energy = clean(packets['energy']['content'][0])
    energy_quote = 'Born 79 kWh Batteri 240 kW / 326 hk – 14,2 0'
    if not all(q in energy for q in [energy_quote,'OKTOBER 2026','grundversion','WLTP']):
        raise RefreshError('swedish_vz_consumption_basis_required')
    tables = packets['characteristics']['tables']
    manual_table = one((t for t in tables if t[0][0]=='240 kW/84 kWh elmotor'), 'one_exact_swedish_vz_table_required')
    manual_values = [('Drivning','Bak'),('Maximal effekt (kW)','240'),('Batteriets bruttokapacitet (kWh)','84'),
                     ('Batteriets nettokapacitet (kWh)','79'),('Maximal AC-laddningsef- fekt (kW)','11')]
    if any(clean(row(manual_table,label)[1])!=value for label,value in manual_values):
        raise RefreshError('exact_vz_net_battery_drive_onboard_ac_required')
    technical = packets['technical']['table']
    if row(technical,'LINE-UP') != ['LINE-UP','BORN (140kW/58kWh)','ENDURANCE (170kW/79kWh)',HEADER]:
        raise RefreshError('exact_final_vz_column_required')
    range_row = row(technical,'Range (km)')
    dc_row = row(technical,'Charging time DC 183kW 10-80% SoC (h)')
    # The technical PDF visibly merges Endurance/VZ cells; require that exact shape.
    if (range_row != ['Range (km)','484 - 413','627 - 538','631 - 552']
            or dc_row != ['Charging time DC 183kW 10-80% SoC (h)','','0:29',None]
            or row(technical,'HV- Battery net /gross (kWh)') != ['HV- Battery net /gross (kWh)','58/61','79/84',None]):
        raise RefreshError('final_vz_range_and_shared_79kwh_dc_required')
    manual = clean(packets['manual']['content'])
    if (packets['manual']['page']!=290 or TOW_QUOTE not in manual
            or 'aldrig tillåtet att använda den för att dra en släpvagn eller ett fordon' not in manual):
        raise RefreshError('explicit_trailer_prohibition_required_not_carrier_load')
    model = clean(packets['model']['content'])
    if not all(q in model for q in ['Bagagerumsvolym 385 L','Säten 5','kombisedan']):
        raise RefreshError('current_swedish_body_boot_seats_required')
    draft = dict(adapter=ADAPTER,brand='Cupra',model='Born',variant_name='Born VZ',
                 source=packets['characteristics']['source'],
                 supporting_sources=[packets[k]['source'] for k in ('price','energy','technical','manual','model')],
                 source_resolution='exact_my2027_swedish_vz_final_technical_data',
                 extraction_confidence=0.99,facts={},field_evidence={},held_fields={})
    def add(field,value,key,quote,scope,page=None):
        s=packets[key]['source'];draft['facts'][field]=value
        draft['field_evidence'][field]=dict(value=value,quote=quote,scope=scope,page=page,
            column_header=HEADER,variant_name='Born VZ',source_url=s['final_url'],source_hash=s['content_hash'])
    for field,value,label in [('battery_kwh',79,'Batteriets nettokapacitet (kWh)'),('drivetrain','RWD','Drivning'),
                               ('ac_charge_kw',11,'Maximal AC-laddningsef- fekt (kW)')]:
        add(field,value,'characteristics','240 kW/84 kWh elmotor | '+label+' '+clean(row(manual_table,label)[1]),'sv_my2027_vz_net_and_onboard',3)
    add('wltp_range_km',631,'technical','VZ (240kW/79kWh) | Range (km) 631 - 552','final_global_vz_wltp_interval_maximum',1)
    add('dc_charge_kw',183,'technical','ENDURANCE (170kW/79kWh) / VZ (240kW/79kWh) | Charging time DC 183kW 10-80% SoC (h) 0:29','final_shared_79kwh_peak_dc_not_58kwh',1)
    add('wltp_consumption_kwh_100km',14.2,'energy',energy_quote+' | grundversion | WLTP','swedish_october_vz_grundversion',1)
    add('tow_kg',0,'manual',TOW_QUOTE,'explicit_not_approved_for_trailers_not_missing',290)
    add('boot_liters',385,'model','Bagagerumsvolym 385 L','current_swedish_born',None)
    add('seats',5,'model','Säten 5','current_swedish_born',None)
    draft['price_evidence']=dict(value=596900,price_type='list_price',price_valid_until=None,
        source_url=URLS['price'],source_hash=packets['price']['source']['content_hash'],quote=price_line,
        classification='swedish_my2027_vz_including_vat_not_lease_or_accessory')
    draft['model_facts']={'body_type':'Halvkombi'}
    draft['model_field_evidence']={'body_type':dict(value='Halvkombi',quote='kombisedan',
        source_url=URLS['model'],source_hash=packets['model']['source']['content_hash'])}
    draft['source_decisions']=[
        'Current Swedish MY2027 Born VZ 79 kWh / 240 kW price row controls version and 596900 SEK list price, never monthly leasing or carrier accessory price.',
        'Swedish MY2027 manual edition 03.26 right-hand 240 kW table: 79 net / 84 gross kWh, rear drive and 11 kW onboard AC, not the optional 22 kW cable rating.',
        'Final international VZ technical table supersedes indicative launch estimates (about 600 km / 185 kW): WLTP 552-631 km, DC 183 kW. Keep international source locale and visible qualification.',
        '631 is the VZ interval maximum, not a guarantee for every Swedish wheel/equipment configuration; do not borrow Endurance 627 or standard Born 484.',
        'Swedish October 2026 VZ 240 kW consumption is 14.2 in grundversion; do not substitute global interval 14.1-16.2.',
        'Swedish current manual page 288 (PDF page 290) explicitly prohibits trailers. Zero denotes no approved trailer capacity, not missing evidence; carrier vertical 55/75 kg is not towing.',
        'Current Swedish model page supplies only 385 L boot, five seats and hatchback body; its stale indicative maximum is not version-specific WLTP.',
        'Preserve canonical identity, independent price evidence, market flags and all other variants. No availability inference from a price list.']
    return [draft]


def selected_text(body, content_type):
    doc=PdfReader(io.BytesIO(body))
    if len(doc.pages)!=375:
        raise RefreshError('current_manual_layout_changed')
    return doc.pages[289].extract_text() or ''


def collect(output):
    output.mkdir(parents=True,exist_ok=True)
    packets={}
    fetcher=SourceFetcher(timeout=40,max_bytes=16*1024*1024,document_parser=lambda b,k:b,
        url_policy=lambda u,brands:u in URLS.values() and brands=={'Cupra'})
    for key in ['technical',*[key for key in URLS if key!='technical']]:
        url=URLS[key]
        fetcher.text_parser=(lambda b,k:b.decode('utf-8')) if key=='manuals' else selected_text if key=='manual' else source_text
        result=fetcher.fetch(url,{'Cupra'})
        if result.get('status')!='reachable' or result['final_url']!=url:
            raise RefreshError('cupra_source_unavailable:'+key+':'+result.get('status','unknown'))
        raw=result['document'];(output/(key+('.pdf' if url.endswith('.pdf') else '.json' if key=='manuals' else '.html'))).write_bytes(raw)
        source={k:result[k] for k in ('status','http_status','final_url','content_hash')}
        source['fetched_at']=datetime.now(timezone.utc).isoformat()
        packet=dict(source=source,content=result['text'])
        if key=='manuals':packet['content']=json.loads(raw)
        elif key=='manual':packet['page']=290
        elif url.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(raw)) as doc:
                packet['content']=[p.extract_text() or '' for p in doc.pages]
                if key=='characteristics':packet['tables']=doc.pages[2].extract_tables()
                if key=='technical':packet['table']=one((t for t in doc.pages[0].extract_tables() if len(t)>15),'one_global_technical_table_required')
        if key=='index':
            from html.parser import HTMLParser
            class Links(HTMLParser):
                def handle_starttag(self,tag,attrs):
                    if tag=='a' and dict(attrs).get('href'):links.append(urljoin(URLS['index'],dict(attrs)['href']))
            links=[];Links().feed(raw.decode('utf-8'));packet['links']=links
        packets[key]=packet
    (output/'source-packets.json').write_text(json.dumps(packets,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    drafts=extract(packets)
    for name,value in [('source-packets.json',packets),('intake.json',dict(adapter=ADAPTER,drafts=drafts,held=[],database_writes=0,paid_calls=0))]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(drafts=1,technical_facts=9,prices=1,database_writes=0,paid_calls=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    collect(p.parse_args().output)
