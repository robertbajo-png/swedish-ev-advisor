"""Complete six existing versions from source-bound manufacturer documents."""
import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
from urllib.robotparser import RobotFileParser

import pdfplumber
from audit_catalog_sources import SourceFetcher, USER_AGENT
from manufacturer_embedded_data import mazda_document
from variant_refresh import Node, RefreshError, one, parse_document

ADAPTER = 'mazda_renault_sweden_specs_v1'
SOURCES = {
    'mazda_model': 'https://www.mazda.se/modeller/mazda-6e/',
    'mazda_index': 'https://www.mazda.se/forms/broschyrer/',
    'mazda_link': 'https://www.mazda.se/link/598f8f5b6f374dafad038f0ac8022f15.aspx',
    'mazda_pdf': 'https://media-assets.mazda.eu/raw/upload//mazdase/globalassets/mms-local-pages/brochures-and-pricelists/mazda6e_se_2026-09-29.pdf?rnd=4a8623',
    'mazda_seats': 'https://de.mazda-press.com/api/assets/download/6e41ae9c-cada-4c65-aff2-7383fa28ccb9_Default?isDownload=false',
    'renault_index': 'https://www.renault.se/personbilar/elbilar/r5-e-tech-electric/versioner-och-priser',
    'renault_pdf': 'https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/renaultsesite/cardocuments/prislista-renault-5-e-tech-electric.pdf',
    'renault_drive': 'https://www.renault.de/elektromodelle/r5-e-tech-elektrisch-my26/konfigurator.html',
}
SCOPES = {'Mazda|6E': ['Takumi MY2027','Homura Plus MY2027','Takumi Plus MY2027'],
          'Renault|5': ['evolution 40 kWh','techno 52 kWh','iconic five 52 kWh']}


class DocumentFetcher(SourceFetcher):
    def robots_allowed(self, url):
        if super().robots_allowed(url):
            return True
        if url != SOURCES['mazda_seats']:
            return False
        # This pressroom canonicalizes robots.txt to robots.txt/. Follow ONLY
        # that observed same-origin redirect, retaining the usual 404 semantics.
        origin = 'https://de.mazda-press.com'
        try:
            self.opener.open(Request(origin + '/robots.txt', headers={'User-Agent': USER_AGENT}), timeout=self.timeout)
        except HTTPError as error:
            if error.code != 301 or error.headers.get('Location') != origin + '/robots.txt/':
                return False
        else:
            return False
        parser = RobotFileParser(origin + '/robots.txt/')
        try:
            with self.opener.open(Request(origin + '/robots.txt/', headers={'User-Agent': USER_AGENT}), timeout=self.timeout) as response:
                data = response.read(512001)
                if len(data) > 512000:
                    return False
                parser.parse(data.decode('utf-8', errors='replace').splitlines())
        except HTTPError as error:
            if error.code != 404:
                return False
            parser.parse([])
        except OSError:
            return False
        self.robots[origin] = parser
        return parser.can_fetch(USER_AGENT, url)


def normalized(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def public_engine_drive(document, label='Antriebsart'):
    # Manufacturer's technical-data dialog is delivered in HTML, collapsed
    # until its button is opened. Read only its named label/value rows, never
    # arbitrary hidden prose, scripts or unrelated recommendations.
    rows=[]
    def walk(node):
        if node.tag in ('script','style','template'):
            return
        if node.tag=='dl' and node.attrs.get('class')=='OneConfigEngineTechSpecGroups__line':
            cells=[c for c in node.children if isinstance(c,Node) and c.tag=='dd']
            if len(cells)==2 and cells[0].text()==label:
                rows.append(cells[0].text()+' '+cells[1].text())
        for child in node.children:
            if isinstance(child,Node):walk(child)
    walk(document)
    if not rows or len(set(rows))!=1:
        raise RefreshError('manufacturer_engine_drive_conflict')
    return rows[0]


def pdf_data(body):
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        pages = []
        for page in pdf.pages:
            text = page.extract_text() or ''
            tables = page.extract_tables()
            cells = None
            for table in page.find_tables():
                if table.extract()[0] == ['Teknisk specifikation','EVOLUTION\n40 kWh','TECHNO\n52 kWh','ICONIC FIVE\n52 kWh']:
                    cells = []
                    headers = table.rows[0].cells
                    for raw, geometries in zip(table.extract(), table.rows):
                        values = []
                        for column in range(1,4):
                            center = (headers[column][0] + headers[column][2])/2
                            bbox = one((c for c in geometries.cells if c and c[0] <= center < c[2]), 'unambiguous_pdf_cell_required')
                            if raw[0] == 'Homologerad räckvidd WLTP - blandad körning (km)':
                                bbox = (headers[column][0],bbox[1],headers[column][2],bbox[3])
                            values.append(normalized(page.crop(bbox).extract_text()))
                        cells.append([normalized(raw[0]), *values])
            pages.append({'text': normalized(text), 'tables': tables, 'technical_cells': cells})
        return pages


def checked(payload, key):
    if payload['source']['final_url'] != SOURCES[key] or hashlib.sha256(payload['raw']).hexdigest() != payload['source']['content_hash']:
        raise RefreshError('exact_source_bytes_required:' + key)


def row(brand, model, variant, payload):
    return dict(adapter=ADAPTER, brand=brand, model=model, variant_name=variant, facts={}, field_evidence={},
        supporting_sources=[], source=payload['source'], held_fields={}, extraction_confidence=0.99,
        source_resolution='owner_2026_11_13_exact_version_current_sources')


def add(target, field, value, quote, payload, scope, **extra):
    target['facts'][field] = value
    source = payload['source']
    target['field_evidence'][field] = dict(value=value, quote=quote, scope=scope, variant_name=target['variant_name'],
        source_url=source['final_url'], source_hash=source['content_hash'], **extra)
    if source['final_url'] != target['source']['final_url'] and source not in target['supporting_sources']:
        target['supporting_sources'].append(source)


def price(target, value, quote):
    target['price_evidence'] = dict(value=value, quote=quote, price_type='list_price', price_valid_until=None,
        source_url=target['source']['final_url'], source_hash=target['source']['content_hash'],
        classification='current_exact_variant_base_cash_price_not_finance_or_discount')


def extract_mazda(payloads):
    for key in ('mazda_pdf','mazda_model','mazda_seats'):
        checked(payloads[key],key)
    payload = payloads['mazda_pdf']
    pages = payload['pages']
    prices = one((table for page in pages for table in page['tables']
                  if table and table[0][0] == 'Mazda6e Takumi, 258 hk, 78 kWh'), 'exact_my27_price_table_required')
    if [r[0] for r in prices] != ['Mazda6e Takumi, 258 hk, 78 kWh',
            'Mazda6e Takumi Plus, 258 hk, 78 kWh, Brun interiör',
            'Mazda6e Takumi Plus, 258 hk, 78 kWh, Beige interiör', 'Mazda6e Homura Plus, 258 hk, 78 kWh']:
        raise RefreshError('my2027_grades_or_battery_changed')
    tech = one((p for p in pages if 'Mazda6e, 78 kWh' in p['text'] and 'Högvoltsbatteri' in p['text']), 'one_78_kwh_technical_page_required')
    volume = one((p for p in pages if 'Dragvikt, max (kg)' in p['text']), 'one_78_kwh_volume_page_required')
    def cell(page, label):
        return one((r[1] for t in page['tables'] for r in t if len(r)==2 and r[0]==label), 'exact_mazda_label_required:' + label)
    model = mazda_document(payloads['mazda_model']['raw'])
    if model['language'] != 'sv-SE' or model['page'] != 'ShowroomPage:2027 Mazda6e':
        raise RefreshError('swedish_my2027_identity_required')
    strings = []
    def walk(value):
        if isinstance(value,dict):
            for v in value.values(): walk(v)
        elif isinstance(value,list):
            for v in value: walk(v)
        elif isinstance(value,str): strings.append(parse_document(value.encode(),'text/html').text())
    walk(model)
    body_quote = one((s for s in strings if s.startswith('2027 Mazda6e är en helt elektrisk modell med bakhjulsdrift.')), 'my27_body_required')
    if 'femdörrars halvkombi' not in body_quote:
        raise RefreshError('literal_body_type_required')
    seats_payload=payloads['mazda_seats']
    seat_page=one((p for p in seats_payload['pages'] if 'Anzahl Sitzplätze' in p['text']), 'exact_european_my27_seating_required')
    if not all(s in seat_page['text'] for s in ('Mazda6e 2027','TAKUMI, TAKUMI PLUS, HOMURA PLUS','Anzahl Sitzplätze 5','78')):
        raise RefreshError('seats_need_same_model_year_battery_and_all_grades')
    fields = {'battery_kwh': ('Batterikapacitet (kWh)',r'([0-9]+)'),
        'dc_charge_kw': ('Maximal hastighet för DC-laddning (kW)',r'([0-9]+)'),
        'wltp_range_km': ('Elektrisk räckvidd vid blandad körning enligt WLPT (km)',r'([0-9]+)'),
        'wltp_consumption_kwh_100km': ('Blandad körning, WLTP (kWh/100 km)',r'([0-9]+,[0-9]+)'),
        'drivetrain': ('Drivning',r'(Bakhjulsdrift)')}
    result=[]
    for variant in SCOPES['Mazda|6E']:
        target=row('Mazda','6E',variant,payload)
        for field,(label,pattern) in fields.items():
            raw=cell(tech,label);m=re.fullmatch(pattern,raw)
            if not m:raise RefreshError('mazda_value_changed:' + label)
            value='RWD' if field=='drivetrain' else float(m[1].replace(',','.'))
            add(target,field,value,'Mazda6e 78 kWh | '+label+' | '+raw,payload,'my2027_78_kwh_all_grades')
        ac=one((r for t in tech['tables'] for r in t if r[0].startswith('Laddningstid (AC, 3-fas ')), 'three_phase_ac_required')
        m=re.fullmatch(r'Laddningstid \(AC, 3-fas ([0-9]+) kW\), 0–100 % \(timmar\)',ac[0])
        if not m:raise RefreshError('ac_power_not_duration_required')
        add(target,'ac_charge_kw',int(m[1]),'Mazda6e 78 kWh | '+ac[0]+' | '+ac[1],payload,'my2027_three_phase_ac_not_duration')
        tow=cell(volume,'Dragvikt, max (kg)')
        add(target,'tow_kg',int(tow.replace(' ','')),'Mazda6e 78 kWh | Dragvikt, max (kg) | '+tow,payload,'my2027_braked_towing')
        label='Lastvolym (med/utan förvaringsutrymme under golv) (alla säten uppfällda, upp till bakre hatthylla)'
        boot=normalized(cell(volume,label));m=re.fullmatch(r'([0-9]+) l / ([0-9]+) l',boot)
        if not m:raise RefreshError('boot_basis_required')
        add(target,'boot_liters',int(m[2]),'Mazda6e 78 kWh | '+label+' | '+boot,payload,'rear_boot_below_shelf_excluding_underfloor_not_frunk')
        add(target,'seats',5,'Technische Daten Mazda6e 2027 | Verfügbare Ausstattungen TAKUMI, TAKUMI PLUS, HOMURA PLUS | Anzahl Sitzplätze 5',seats_payload,'same_european_my2027_all_grades_seating_only')
        grade=variant.removesuffix(' MY2027')
        matching=[r for r in prices if r[0].startswith('Mazda6e '+grade+',')]
        if not matching or len({r[1] for r in matching})!=1:raise RefreshError('one_exact_grade_price_required')
        amount=re.fullmatch(r'([0-9 ]+) kr',matching[0][1])
        if not amount:raise RefreshError('cash_price_required')
        price(target,int(amount[1].replace(' ','')),' | '.join(matching[0]))
        target['model_facts']={'body_type':'Halvkombi'}
        source=payloads['mazda_model']['source']
        target['model_field_evidence']={'body_type':dict(value='Halvkombi',quote=body_quote,source_url=source['final_url'],source_hash=source['content_hash'])}
        target['supporting_sources'].append(source)
        target['source_decisions']=['MY2027 78 kWh replaces neither legacy 68.8 nor 80 kWh facts.',
            'Swedish MY2027 PDF: combined WLTP 16.1, not calculator 16.6 or city-cycle 12.4.',
            'Rear boot 336 L below shelf excludes the separate 72 L frunk and 466 L roof-height measurement.',
            'Swedish PDF three-phase AC 11 kW supersedes inconsistent 7.2 kW equipment caption.',
            'Only seating uses the manufacturer European MY2027 sheet; no foreign prices or availability.']
        result.append(target)
    return result


def extract_renault(payloads):
    for key in ('renault_pdf','renault_drive'):checked(payloads[key],key)
    payload=payloads['renault_pdf'];pages=payload['pages']
    first=pages[0]
    if not re.search(r'Gällande från\s*10 november 2026',first['text']) or 'oktober2026-produktion' not in first['text'].replace(' ',''):
        raise RefreshError('exact_october_2026_production_price_list_required')
    prices=one((t for t in first['tables'] if len(t[0])==10 and t[0][-3:]==['EVOLUTION','TECHNO','ICONIC FIVE']), 'exact_renault_price_columns_required')
    tech=one((p['technical_cells'] for p in pages if p.get('technical_cells')), 'exact_renault_technical_grid_required')
    if tech[0] != ['Teknisk specifikation','EVOLUTION 40 kWh','TECHNO 52 kWh','ICONIC FIVE 52 kWh']:
        raise RefreshError('renault_grade_grid_changed')
    drive_doc=parse_document(payloads['renault_drive']['raw'],'text/html')
    drive=drive_doc.text()
    if one(drive_doc.nodes('h1'),'exact_current_generation_required').text()!='RENAULT 5 E-TECH ELEKTRISCH' or not all(s in drive for s in ('E-Tech elektrisch 120 Urban Range','E-Tech elektrisch 150 Comfort Range')) or public_engine_drive(drive_doc)!='Antriebsart Vorderradantrieb':
        raise RefreshError('official_e_tech_front_drive_evidence_required')
    result=[]
    for i,variant in enumerate(SCOPES['Renault|5']):
        target=row('Renault','5',variant,payload);column=i+1
        header=tech[0][column]
        def cell(label):return one((r[column] for r in tech[1:] if r[0]==label),'renault_exact_row_required:'+label)
        price_row=one((r for r in prices[1:] if r[0]=='5 E-Tech electric' and r[1]==('40' if i==0 else '52')), 'exact_battery_price_row_required')
        expected_charge='AC 11 kW + DC '+('80' if i==0 else '100')+' kW'
        if price_row[6]!=expected_charge:raise RefreshError('battery_charging_row_changed')
        for field,label in [('battery_kwh','Kapacitet (kWh)'),('wltp_range_km','Homologerad räckvidd WLTP - blandad körning (km)'),
                            ('seats','Antal sittplatser'),('boot_liters','Bagagerumsvolym (L)')]:
            raw=cell(label)
            if not re.fullmatch(r'[0-9]+',raw):raise RefreshError('one_variant_number_required:'+label)
            add(target,field,int(raw),header+' | '+label+' | '+raw,payload,'exact_pdf_grade_column',column_header=header)
        tow=cell('Maxvikt för bromsat/obromsat släp (kg)')
        if not re.fullmatch(r'[0-9]+/[0-9]+',tow):raise RefreshError('braked_unbraked_towing_required')
        add(target,'tow_kg',int(tow.split('/')[0]),header+' | Maxvikt för bromsat/obromsat släp (kg) | '+tow,payload,'pdf_braked_towing',column_header=header)
        for field,power in [('ac_charge_kw',11),('dc_charge_kw',80 if i==0 else 100)]:
            add(target,field,power,header+' | '+expected_charge,payload,'exact_battery_peak_charging',column_header=header)
        energy=price_row[5];parts=[float(v.replace(',','.')) for v in energy.split('-')]
        if len(parts) not in (1,2):raise RefreshError('explicit_consumption_basis_required')
        quote=header+' | förbruk. (kWh/100 km) | '+energy
        if len(parts)==2:quote+=' | Förbrukning (WLTP, versionsgrupp): '+energy.replace('-', '–')+' kWh/100 km'
        add(target,'wltp_consumption_kwh_100km',parts[0],quote,payload,
            'battery_group_consumption_interval_lower_bound' if len(parts)==2 else 'exact_battery_consumption',column_header=header,interval=parts)
        add(target,'drivetrain','FWD','RENAULT 5 E-TECH ELEKTRISCH | E-Tech elektrisch 120 Urban Range | E-Tech elektrisch 150 Comfort Range | Antriebsart Vorderradantrieb',payloads['renault_drive'],'manufacturer_current_e_tech_generation_drivetrain_only')
        amount=price_row[7+i]
        if not re.fullmatch(r'[0-9 ]+ kr',amount):raise RefreshError('exact_grade_list_price_required')
        price(target,int(amount.removesuffix(' kr').replace(' ','')),header+' | Rek. cirkapris | '+amount)
        target['source_decisions']=['Current November price PDF supersedes January launch figures 312/410 km.',
            'Range is cropped against each printed grade header: 320/424/421, not a group maximum.',
            '52 kWh consumption remains the published 14.1-14.2 interval, not an invented exact-grade number.',
            'Only front-wheel architecture uses the official European E-Tech manufacturer configurator; no foreign prices/range.']
        body_source=payloads['renault_drive']['source']
        if public_engine_drive(drive_doc,'Karosserieform')!='Karosserieform Berline' or public_engine_drive(drive_doc,'Anzahl Türen')!='Anzahl Türen 5':
            raise RefreshError('five_door_berline_body_required')
        body_quote='RENAULT 5 E-TECH ELEKTRISCH | Karosserieform Berline | Anzahl Türen 5'
        target['model_facts']={'body_type':'Halvkombi'}
        target['model_field_evidence']={'body_type':dict(value='Halvkombi',quote=body_quote,source_url=body_source['final_url'],source_hash=body_source['content_hash'])}
        result.append(target)
    return result


def collect(output):
    output.mkdir(parents=True,exist_ok=True)
    fetcher=DocumentFetcher(timeout=25,document_parser=lambda body,_kind:body,
        url_policy=lambda url,brands: url in SOURCES.values() and brands <= {'Mazda','Renault'})
    payloads={}
    for key,url in SOURCES.items():
        response=fetcher.fetch(url,{'Mazda' if key.startswith('mazda') else 'Renault'})
        if response.get('status')!='reachable' or response['final_url']!=(SOURCES['mazda_pdf'] if key=='mazda_link' else url):
            raise RefreshError('source_unavailable:'+key+':'+response.get('status','unknown'))
        raw=response['document'];source=dict(status='reachable',http_status=200,final_url=response['final_url'],
            content_hash=response['content_hash'],fetched_at=datetime.now(timezone.utc).isoformat())
        source.update(country='DE' if key in ('mazda_seats','renault_drive') else 'SE', language='de' if key in ('mazda_seats','renault_drive') else 'sv')
        payloads[key]={'source':source,'raw':raw}
        if raw.startswith(b'%PDF'):payloads[key]['pages']=pdf_data(raw)
        (output/(key+('.pdf' if raw.startswith(b'%PDF') else '.html'))).write_bytes(raw)
    # Bind CDN files to the links actually supplied by the Swedish manufacturer.
    index=mazda_document(payloads['mazda_index']['raw'])
    if SOURCES['mazda_link'].removeprefix('https://www.mazda.se') not in json.dumps(index):
        raise RefreshError('mazda_current_price_link_changed')
    if payloads['mazda_link']['source']['content_hash']!=payloads['mazda_pdf']['source']['content_hash']:
        raise RefreshError('linked_mazda_pdf_changed')
    renault=parse_document(payloads['renault_index']['raw'],'text/html')
    if one((a.attrs.get('href') for a in renault.nodes('a') if a.text().strip().casefold()=='prislista'),'one_renault_price_link_required')!=SOURCES['renault_pdf']:
        raise RefreshError('renault_current_price_link_changed')
    drafts=extract_mazda(payloads)+extract_renault(payloads)
    if len(drafts)!=6 or any(len(r['facts'])!=9 for r in drafts):raise RefreshError('six_complete_profiles_required')
    intake=dict(adapter=ADAPTER,drafts=drafts,held=[],database_writes=0,paid_calls=0)
    (output/'intake.json').write_text(json.dumps(intake,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'drafts':len(drafts),'technical_facts':54,'prices':6,'paid_calls':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output)
