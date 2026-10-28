"""Continue current-variant replacement from free, accepted Swedish sources."""
import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timezone, date
from pathlib import Path

from audit_catalog_sources import ROOT, SourceFetcher
from current_variant_intake import profile
from toyota_price_intake import parse_pdf
from variant_refresh import FACT_FIELDS, RefreshError, one, parse_document

POLICY = 'current_exact_variants_2026_10_v2'
SKODA_URL = 'https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb'
CUPRA_MODEL = 'https://www.cupraofficial.se/bilar/born'
MAZDA_URL = 'https://www.mazda.se/modeller/mazda-6e/'
VW_URL = 'https://www.volkswagen.se/sv/bygg-din-bil.html/__app/30355.app'
FORD_URL = 'https://www.ford.se/bilar/personbilar-och-suver/explorer'
ZEEKR_URL = 'https://www.zeekr.eu/sv-se/models/7x'
RETIRED = {'Skoda|Elroq': ['60 Selection', '85 Selection', '85x Selection', 'RS'], 'Cupra|Born': ['Born'],
    'Mazda|6E':['Mazda 6e Takumi'], 'Volkswagen|Id.3':['ID.3 Neo'], 'Ford|Explorer':['Explorer Business Edition'],
    'BMW|i4':['BMW i4 eDrive40 Gran Coupé','BMW i4 xDrive40'], 'Volvo|Es90':['ES90 Plus','ES90 Ultra'],
    'Volvo|Ex30':['EX30 Black Edition','EX30 Core','EX30 Cross Country','EX30 Plus','EX30 Ultra'], 'Toyota|bZ4X':['Active AWD','Active FWD'],
    'Zeekr|7X':['Core RWD','Long Range RWD','Privilege AWD'],'Audi|A6 E-Tron':['A6 Sportback e-tron'],
    'Volkswagen|Id.4':['ID.4 Pro Sweden Olympic Edition'],'Audi|Q6 E-Tron':['Q6 e-tron'],'Mercedes-Benz|Cla':['CLA Advanced Edition']}


def archive_evidence(source,body):
    digest=hashlib.sha256(body).hexdigest()
    if digest!=source['content_hash']:
        raise RefreshError('source_archive_hash_mismatch')
    folder=ROOT/'data/local/source-evidence'
    folder.mkdir(parents=True,exist_ok=True)
    extension='.pdf' if 'pdf' in source.get('content_type','') else '.html'
    destination=folder/(digest+extension)
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest()!=digest:
            raise RefreshError('existing_source_archive_changed')
    else:
        destination.write_bytes(body)
    metadata={key:source.get(key) for key in ['final_url','content_hash','content_type','http_status','fetched_at','status']}
    (folder/(digest+'.json')).write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')


def price_profile(brand, model, name, source, price, quote, adapter, expiry=None):
    row = profile(brand, model, name, source, price, quote, adapter)
    row['extraction_payload']['policy'] = POLICY
    row['source_type'] = 'price_list_pdf'
    if expiry:
        row.update(price_type='campaign_price', price_valid_until=expiry)
        row['extraction_payload']['field_evidence']['price_valid_until'] = {
            'source_url': source['final_url'], 'source_hash': source['content_hash'],
            'quote': 'Gäller tom ' + expiry, 'value': expiry}
    return row


def elroq_grid(words, width, height, text, source, today=None):
    today = today or datetime.now(timezone.utc).date()
    if source['final_url'] != SKODA_URL or not 590 <= width <= 600 or not 835 <= height <= 850:
        raise RefreshError('elroq_document_geometry_changed')
    normalized = re.sub(r'\s+', ' ', text)
    if 'Škoda Elroq Explore Edition' not in normalized or 'estimerad' not in normalized:
        raise RefreshError('elroq_edition_or_range_qualification_changed')
    dates = set(re.findall(r'G\s*äller tom (\d{4}-\d{2}-\d{2})', normalized))
    expiry = one(dates, 'unique_elroq_campaign_expiry_required')
    if date.fromisoformat(expiry) < today or 'Erbjudandet är begränsat' not in normalized:
        raise RefreshError('expired_or_unqualified_elroq_campaign')
    header = sorted([word for word in words if 125 <= word['top'] <= 140 and word['text'] in ('Motor', 'Selection', 'Sportline', 'RS')], key=lambda w:w['x0'])
    if [word['text'] for word in header] != ['Motor', 'Selection', 'Sportline', 'RS']:
        raise RefreshError('unique_elroq_column_headers_required')
    centers = [(word['x0'] + word['x1']) / 2 for word in header[1:]]
    if not (395 < centers[0] < 455 < centers[1] < 510 < centers[2] < 560):
        raise RefreshError('elroq_trim_columns_moved')
    bounds = [390, (centers[0]+centers[1])/2, (centers[1]+centers[2])/2, 565]
    rows = sorted([word for word in words if word['text'] in ('60','85','85x','RS') and 25 <= word['x0'] <= 40 and 145 <= word['top'] <= 220],key=lambda w:w['top'])
    if [word['text'] for word in rows] != ['60','85','85x','RS']:
        raise RefreshError('unique_elroq_motor_rows_required')
    result = []
    for motor in rows:
        for column, trim in enumerate(['Selection','Sportline','RS']):
            cell = sorted([word for word in words if abs(word['top']-motor['top']) < 1.5 and bounds[column] <= word['x0'] < bounds[column+1]],key=lambda w:w['x0'])
            value = ' '.join(word['text'] for word in cell)
            expected_price = (motor['text'] != 'RS' and trim != 'RS') or (motor['text'] == 'RS' and trim == 'RS')
            if not expected_price and value.strip() in ('', '-', '–', '−', '\ufffd'):
                continue
            if not expected_price:
                raise RefreshError('unexpected_price_in_unavailable_trim')
            amount = re.fullmatch(r'([0-9]{3})\s*([0-9]{3})\s*kr',value)
            if not amount or any(word['x1'] > bounds[column+1]+1 for word in cell):
                raise RefreshError('ambiguous_elroq_price_cell')
            name = (motor['text'] + (' ' + trim if motor['text'] != 'RS' else '') + ' Explore Edition')
            quote = ' | '.join(['Škoda Elroq Explore Edition',motor['text'],trim,value,'Gäller tom '+expiry])
            row = price_profile('Skoda','Elroq',name,source,int(amount[1]+amount[2]),quote,'skoda_elroq_explore_grid_v1',expiry)
            row['extraction_payload']['price_cell'] = {'page':1,'motor':motor['text'],'trim':trim,
                'column':column,'text':value,'bbox':[bounds[column],motor['top']-1.5,bounds[column+1],motor['bottom']+1.5]}
            result.append(row)
    if len(result) != 7 or len({row['variant_name'] for row in result}) != 7:
        raise RefreshError('complete_elroq_price_grid_required')
    return result


def collect_pdf(url, brand):
    source = SourceFetcher(timeout=15,document_parser=parse_pdf).fetch(url,{brand})
    if source.get('status') != 'reachable' or source.get('http_status') != 200 or source.get('final_url') != url:
        raise RefreshError('accepted_pdf_unavailable:' + source.get('status','unknown'))
    source['fetched_at'] = datetime.now(timezone.utc).isoformat()
    if hashlib.sha256(source['document']['body']).hexdigest() != source['content_hash']:
        raise RefreshError('raw_document_hash_mismatch')
    archive_evidence(source,source['document']['body'])
    return source


def collect_elroq():
    import pdfplumber
    source = collect_pdf(SKODA_URL,'Skoda')
    with pdfplumber.open(io.BytesIO(source['document']['body'])) as document:
        if len(document.pages) != 3:
            raise RefreshError('elroq_page_count_changed')
        page = document.pages[0]
        profiles = elroq_grid(page.extract_words(),page.width,page.height,source['text'],source)
    return profiles


def collect_cupra():
    # The linked PDF is encrypted and remains held by the existing PDF guard.
    # Use the independent accessible HTML version card, not decrypted PDF facts.
    bodies=[]
    def parse(body,kind):
        bodies.append(body)
        return parse_document(body,kind)
    source = SourceFetcher(document_parser=parse).fetch(CUPRA_MODEL,{'Cupra'})
    if source.get('status') != 'reachable' or source.get('final_url') != CUPRA_MODEL:
        raise RefreshError('cupra_model_page_unavailable')
    source['fetched_at'] = datetime.now(timezone.utc).isoformat()
    archive_evidence(source,one(bodies,'unique_accepted_cupra_body_required'))
    return cupra_html(source['document'],source)


def cupra_html(document,source):
    heading = one((node for node in document.nodes('h3') if node.text() == 'Born VZ'),'unique_cupra_vz_card_required')
    parent = heading.parent
    for _ in range(5):
        prices = [node.text() for node in parent.nodes('h4') if node.text().startswith('Från')]
        names = [node.text() for node in parent.nodes('h3')]
        if len(prices) == 1 and names == ['Born VZ']:
            amount = re.fullmatch(r'Från ([0-9]{3})[. ]([0-9]{3}) kr',prices[0])
            if not amount:
                raise RefreshError('cupra_cash_price_not_exact')
            row = price_profile('Cupra','Born','Born VZ',source,int(amount[1]+amount[2]),
                'Born VZ | '+prices[0],'cupra_born_vz_html_v1')
            row['source_type']='manufacturer_model_page'
            row['extraction_payload']['context_hash']=hashlib.sha256(document.text().encode('utf-8')).hexdigest()
            return [row]
        if parent.parent is None:
            break
        parent = parent.parent
    raise RefreshError('cupra_variant_price_card_not_bound')


def mazda_prices(document,source):
    from manufacturer_embedded_data import material_context
    if (source['final_url'] != MAZDA_URL or document['language'] != 'sv-SE'
            or document['page'] != 'ShowroomPage:2027 Mazda6e'):
        raise RefreshError('exact_swedish_mazda_model_year_required')
    containers = [(i,item) for i,item in enumerate(document['components']) if item['type']=='slidingContainer']
    index,container = one(containers,'unique_mazda_model_container_required')
    modules = [(i,item) for i,item in enumerate(container.get('submodules',[])) if item.get('type')=='slidingPricePromoCards']
    module_index,module = one(modules,'unique_mazda_grade_cards_required')
    context={'language':document['language'],'page':document['page'],'grade_module':module,
        'legal':[item for item in document['components'] if item['type']=='legalDisclaimer']}
    context_hash=hashlib.sha256(json.dumps(material_context(context),ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    cards = module['props']['cards']
    names = [re.sub(r'\s+',' ',card['title']).strip() for card in cards]
    if names != ['Takumi','Homura Plus','Takumi Plus']:
        raise RefreshError('mazda_grade_set_changed')
    result = []
    for card_index,(name,card,slug) in enumerate(zip(names,cards,['takumi','homuraplus','takumiplus'])):
        paths = [cta.get('link') for cta in card['cta']]
        if '/bygg-din-mazda/MAZDA%206e/5HB/'+slug+'#grade' not in paths:
            raise RefreshError('mazda_grade_link_not_bound')
        amount = re.fullmatch(r'Från ([0-9]{3}) ([0-9]{3}) kr',card['priceText'])
        if not amount:
            raise RefreshError('mazda_cash_price_not_exact')
        quote = ' | '.join(['2027 Mazda6e',name,card['priceText']])
        row = price_profile('Mazda','6E',name+' MY2027',source,int(amount[1]+amount[2]),quote,'mazda6e_my27_embedded_grades_v1')
        row['source_type']='manufacturer_model_page'
        row['extraction_payload']['source_pointer']=f'/components/{index}/submodules/{module_index}/props/cards/{card_index}'
        row['extraction_payload']['context_hash']=context_hash
        result.append(row)
    return result


def collect_mazda():
    from manufacturer_embedded_data import mazda_document
    bodies=[]
    def parse(body,kind):
        bodies.append(body)
        return mazda_document(body)
    source = SourceFetcher(timeout=15,document_parser=parse).fetch(MAZDA_URL,{'Mazda'})
    if source.get('status') != 'reachable' or source.get('final_url') != MAZDA_URL:
        raise RefreshError('mazda_swedish_model_unavailable')
    source['fetched_at']=datetime.now(timezone.utc).isoformat()
    archive_evidence(source,one(bodies,'unique_accepted_mazda_body_required'))
    return mazda_prices(source['document'],source)


def collect_html(url,brand,extract):
    bodies=[]
    def parse(body,kind):
        bodies.append(body)
        return parse_document(body,kind)
    source=SourceFetcher(timeout=15,document_parser=parse).fetch(url,{brand})
    if source.get('status')!='reachable' or source.get('final_url')!=url:
        raise RefreshError('current_model_page_unavailable:'+source.get('status','unknown'))
    source['fetched_at']=datetime.now(timezone.utc).isoformat()
    archive_evidence(source,one(bodies,'unique_accepted_html_body_required'))
    return extract(source['document'],source)


def vw_trend(document,source):
    if source['final_url']!=VW_URL or [node.text() for node in document.nodes('h1')]!=['ID.3 Neo']:
        raise RefreshError('exact_vw_model_required')
    heading=one((node for node in document.nodes('h3') if node.text()=='Trend'),'unique_trend_grade_required')
    card=heading.parent
    while card and card.tag!='li':card=card.parent
    if card is None or [node.text() for node in card.nodes('h3')]!=['Trend']:
        raise RefreshError('exclusive_vw_grade_card_required')
    text=card.text()
    prices=re.findall(r'Pris inkl\. moms ([0-9]{3})[ .]?([0-9]{3}) kr',text)
    amount=one(prices,'unique_vw_cash_price_required')
    if not re.search(r'BATTERISTORLEKAR\s*\(1\)',text) or 'Elbil' not in text:
        raise RefreshError('single_battery_electric_grade_required')
    quote='ID.3 Neo | Trend | Pris inkl. moms '+amount[0]+' '+amount[1]+' kr'
    row=price_profile('Volkswagen','Id.3','ID.3 Neo Trend',source,int(''.join(amount)),quote,'vw_id3_neo_trend_config_v1')
    row['source_type']='manufacturer_configurator'
    row['extraction_payload'].update(battery_options=1,context_hash=hashlib.sha256(document.text().encode()).hexdigest())
    return [row]


def ford_ranges(document,source):
    if source['final_url']!=FORD_URL or 'Hedin Motor Company AB' not in document.text():
        raise RefreshError('official_ford_importer_required')
    paragraph=one((node.text() for node in document.nodes('p') if node.text().startswith('Men motormässigt då?')),'unique_ford_drive_paragraph_required')
    expression=r'Men motormässigt då\? Ja, en laddning räcker – enligt WLTP – (\d+) kilometer vid blandad körning för den bakhjulsdrivna varianten med ett batteripaket på (\d+) kilowattimmar\. Den fyrhjulsdrivna versionen har ett batteri på (\d+) kilowattimmar och en räckvidd på (\d+) kilometer'
    match=re.fullmatch(expression,paragraph)
    if not match or [int(v) for v in match.groups()]!=[602,77,79,556]:
        raise RefreshError('ford_drive_range_scope_changed')
    result=[]
    for drive,battery,km in [('RWD',77,602),('AWD',79,556)]:
        name=f'Explorer {drive} {battery} kWh'
        row={**{field:None for field in FACT_FIELDS},'brand':'Ford','model':'Explorer','variant_name':name,
            'wltp_range_km':km,'battery_kwh':battery,'drivetrain':drive,'source_url':FORD_URL,
            'source_hash':source['content_hash'],'source_quote':paragraph,'source_name':'Ford Sverige',
            'fetched_at':source['fetched_at'],'extraction_confidence':0.99,'source_authority':'importer','source_type':'manufacturer_model_page'}
        row['extraction_payload']={'policy':POLICY,'adapter':'ford_explorer_exact_drive_range_v1',
            'context_hash':hashlib.sha256(document.text().encode()).hexdigest(),'field_evidence':{
                field:{'quote':paragraph,'variant':name,'source_url':FORD_URL,'source_hash':row['source_hash'],'value':row[field]}
                for field in ['wltp_range_km','battery_kwh','drivetrain']}}
        result.append(row)
    return result


def zeekr_columns(document,source):
    headers=['Privilege AWD','Long Range RWD','Core RWD']
    table=one((t for t in document.nodes('table') if any([n.text() for n in tr.nodes('td')]==['',*headers] for tr in t.nodes('tr'))),'exact_zeekr_variant_columns_required')
    values={}
    for tr in table.nodes('tr'):
        cells=list(tr.nodes('td'))
        if len(cells)!=4 or any(n.attrs.get(k,'1')!='1' for n in cells for k in ('colspan','rowspan')):raise RefreshError('zeekr_column_shape_changed')
        label=cells[0].text()
        if not label:continue
        if label in values:raise RefreshError('duplicate_zeekr_row')
        values[label]=[n.text() for n in cells[1:]]
    result=[]
    for column,header in enumerate(headers):
        row={**{field:None for field in FACT_FIELDS},'brand':'Zeekr','model':'7X','source_url':source['final_url'],
            'source_hash':source['content_hash'],'source_name':'Zeekr Sverige','source_type':'manufacturer_specs_page',
            'source_authority':'manufacturer','fetched_at':source['fetched_at'],'extraction_confidence':0.99}
        evidence={}
        for field,label,pattern in [('battery_kwh','Batteri',r'([0-9]+) kWh'),('wltp_range_km','Räckvidd, upp till',r'([0-9]+) Km'),
            ('tow_kg','Dragvikt',r'([0-9]+) Kg'),('boot_liters','Lastutrymme',r'([0-9]+)L VDA')]:
            text=values[label][column];match=re.fullmatch(pattern,text)
            if not match:raise RefreshError('zeekr_exact_column_unit_required')
            row[field]=int(match[1]);evidence[field]={'column':header,'label':label,'text':text}
        # Bind the range row to the page's explicitly WLTP-qualified summary.
        if not re.search(str(values['Räckvidd, upp till'][1].split()[0])+r' km Cruising range \(WLTP\)',document.text()):
            raise RefreshError('zeekr_wltp_basis_missing')
        row['drivetrain']='AWD' if header.endswith('AWD') else 'RWD'
        row['variant_name']=header+' '+str(row['battery_kwh'])+' kWh'
        evidence['drivetrain']={'column':header,'label':'Motor','text':values['Motor'][column]}
        if evidence['drivetrain']['text']!=('Dubbel' if row['drivetrain']=='AWD' else 'Enkel'):raise RefreshError('zeekr_motor_column_conflict')
        row['source_quote']=' | '.join([header,*[value['label']+' '+value['text'] for value in evidence.values()]])
        row['extraction_payload']={'policy':POLICY,'adapter':'zeekr7x_exact_spec_columns_v1',
            'context_hash':hashlib.sha256(document.text().encode()).hexdigest(),'column_evidence':evidence,
            'field_evidence':{field:{'quote':row['source_quote'],'variant':row['variant_name'],'value':row[field],
                'source_url':row['source_url'],'source_hash':row['source_hash']} for field in evidence}}
        result.append(row)
    return result


COLLECTORS = {'Skoda|Elroq':collect_elroq,'Cupra|Born':collect_cupra,'Mazda|6E':collect_mazda,
    'Volkswagen|Id.3':lambda:collect_html(VW_URL,'Volkswagen',vw_trend),
    'Ford|Explorer':lambda:collect_html(FORD_URL,'Ford',ford_ranges)}

def current_stock(brand):
    from stock_variant_intake import collect_stock,BMW_URL,VOLVO_ES90,VOLVO_EX30,BILIA_Q6,VWG_STOCK
    if brand in VWG_STOCK:
        entry=VWG_STOCK[brand];make,model=brand.split('|');return collect_stock(entry['url'],make,model,entry['variant_name'])
    if brand=='BMW':return collect_stock(BMW_URL,'BMW','i4','i4 eDrive40 M Sport Business Edition (lagerbil FW37556)')
    if brand=='AudiQ6':return collect_stock(BILIA_Q6,'Audi','Q6 E-Tron','Q6 e-tron quattro SUV 315 kW MY2027 (lagerbil JCE98Y)')
    if brand=='Ex30':return collect_stock(VOLVO_EX30,'Volvo','Ex30','EX30 P5 Long Range Core MY2027 (lagerbil)')
    return collect_stock(VOLVO_ES90,'Volvo','Es90','ES90 Single Motor Extended Range Ultra MY2026 (lagerbil JWR04C)')

def toyota_retention(document,source):
    from toyota_price_intake import config_from_document,extract_config,source_subset
    data=config_from_document(document)
    typed_source={**source,'url':source['final_url'],'brand':'Toyota','model':'bZ4X','source_authority':'manufacturer',
        'source_type':'manufacturer_specs_page','source_validation':'reachable_official_model_source'}
    row=one((r for r in extract_config(data,typed_source) if r['variant_name']=='Active FWD 57.7 kWh 167 hk'),'exact_current_toyota_retained_variant_required')
    return {'profiles':[],'retention_evidence':{'source_url':source['final_url'],'source_hash':source['content_hash'],
        'fetched_at':source['fetched_at'],'context_hash':hashlib.sha256(json.dumps(source_subset(data),sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'variant_name':row['variant_name'],'price_sek':row['price_sek'],'wltp_range_km':row['wltp_range_km'],
        'battery_kwh':row['battery_kwh'],'drivetrain':row['drivetrain'],'source_quote':row['source_quote']}}

COLLECTORS.update({'BMW|i4':lambda:current_stock('BMW'),'Volvo|Es90':lambda:current_stock('Volvo'),'Volvo|Ex30':lambda:current_stock('Ex30'),
    'Toyota|bZ4X':lambda:collect_html('https://www.toyota.se/bilar/bz4x/specifications','Toyota',toyota_retention),
    'Zeekr|7X':lambda:collect_html(ZEEKR_URL,'Zeekr',zeekr_columns),
    'Audi|A6 E-Tron':lambda:current_stock('Audi|A6 E-Tron'),'Volkswagen|Id.4':lambda:current_stock('Volkswagen|Id.4'),
    'Audi|Q6 E-Tron':lambda:current_stock('AudiQ6')})

def current_cla():
    from hoglund_stock_intake import collect_hoglund
    return collect_hoglund()

COLLECTORS['Mercedes-Benz|Cla']=current_cla


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'data/local/release-data/remaining-variants/intake.json')
    parser.add_argument('--only',action='append',choices=COLLECTORS)
    args = parser.parse_args()
    groups,held = [],[]
    selection=args.only
    if selection is None:
        catalog=json.loads((ROOT/'public/data/public_ev_variants.json').read_text(encoding='utf-8'))
        if catalog.get('source')!='supabase_public_ev_variants':raise RefreshError('canonical_scope_snapshot_required')
        public={(row['brand'],row['model'],row['variant_name']) for row in catalog['records']}
        selection=[identity for identity in COLLECTORS if all((*identity.split('|'),name) in public for name in RETIRED[identity])]
    for identity in selection:
        brand,model = identity.split('|')
        try:
            collected = COLLECTORS[identity]()
            fields=collected if isinstance(collected,dict) else {'profiles':collected}
            groups.append({'brand':brand,'model':model,'retire':RETIRED[identity],**fields})
        except (ValueError, KeyError, TypeError, RecursionError, AttributeError, IndexError) as error:
            held.append({'model':identity,'reason':str(error)[:160]})
    payload = {'policy':POLICY,'groups':groups,'held':held,'database_writes':0,'paid_calls':0}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'groups':len(groups),'profiles':sum(len(g['profiles']) for g in groups),'held':held,'database_writes':0,'paid_calls':0}))
    if not groups and selection or args.only and held:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
