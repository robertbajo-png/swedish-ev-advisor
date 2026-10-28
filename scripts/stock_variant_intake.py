"""Source-bound new stock profiles, never generic model starting prices."""
import hashlib
import json
import re
from datetime import datetime, timezone, date

from audit_catalog_sources import SourceFetcher
from manufacturer_embedded_data import stock_document
from variant_refresh import FACT_FIELDS, RefreshError, one

BMW_URL='https://hitta.bmw.se/r/G26E-i4/i4-eDrive40-WBY61HD030FW37556'
VOLVO_ES90='https://www.volvocarretail.se/bilar-i-lager/nya/volvo/es90/single-motor-extended-range-jwr04c'
VOLVO_EX30='https://www.volvocarretail.se/bilar-i-lager/nya/volvo/ex30/p5-long-range-01a0f17196c07c0eac58aa44aeea8ae4'
VOLVO_AUTH='https://www.volvocars.com/se/l/studios/stockholm/'
BILIA_Q6='https://www.bilia.se/bilar/sok-bil/audi/q6-e-tron/jce98y/'
BILIA_AUTH='https://lagerbilar.vwgroup.se/audi'
VWG_STOCK={
    'Audi|A6 E-Tron':{'url':'https://lagerbilar.vwgroup.se/audi/RRR07B','model':'A6 Sportback e-tron','version':'performance S-line 270 kW',
        'registration':'RRR07B','year':2027,'variant_name':'A6 Sportback e-tron performance S-line 270 kW MY2027 (lagerbil RRR07B)'},
    'Volkswagen|Id.4':{'url':'https://lagerbilar.vwgroup.se/volkswagen/BSJ09L','model':'ID.4','version':'PRO 4MOTION 220 KW/ 299 HK 77 KWH BATTERI,',
        'registration':'BSJ09L','year':2027,'variant_name':'ID.4 Pro 4MOTION 77 kWh MY2027 (lagerbil BSJ09L)'},
}


def vwg_profile(parsed,source,brand,model,name):
    expected=VWG_STOCK[brand+'|'+model]
    props=parsed['page_props']
    if not isinstance(props,dict) or not isinstance(props.get('car'),dict):raise RefreshError('importer_stock_car_data_missing')
    car=props['car']
    for field,value in {'brand':brand,'model':expected['model'],'version':expected['version'],'regNumber':expected['registration'],
        'modelYear':expected['year'],'used':False,'mileage':0,'unPublished':False,'firstRegistrationDate':None,'fuelType':'El'}.items():
        if field not in car or type(car[field]) is not type(value) or car[field]!=value:raise RefreshError('exact_importer_new_stock_identity_conflict:'+field)
    price=car.get('pricePoints',{}).get('actualCost')
    if not isinstance(price,int) or not 100000<=price<=3000000:raise RefreshError('importer_stock_cash_price_required')
    if name!=expected['variant_name'] or source['final_url']!=expected['url']:raise RefreshError('importer_stock_scope_mismatch')
    for linked in parsed['cars']:
        if linked.get('model')!=expected['model'] or linked.get('brand',{}).get('name')!=brand:raise RefreshError('conflicting_importer_stock_jsonld')
    text=parsed['document'].text()
    visible=re.search(r'\bPris ([0-9 ]+) kr Räkna på billån',text)
    if not visible or int(visible[1].replace(' ',''))!=price or expected['registration'] not in text or expected['model'] not in text:
        raise RefreshError('importer_stock_visible_price_or_identity_conflict')
    fee_pattern=r'Administrationskostnad på ([0-9]+):- tillkommer|Reg avg på ([0-9]+)kr tillkommer\.'
    fee_matches=list(re.finditer(fee_pattern,text))
    fee=one({int(m[1] or m[2]) for m in fee_matches},'explicit_mandatory_stock_fee_required')
    if not 0<=fee<=10000:raise RefreshError('unsupported_mandatory_stock_fee')
    fee_quote=fee_matches[0][0]
    quote=name+' | Pris '+f'{price:,}'.replace(',',' ')+' kr | '+fee_quote
    row={**{field:None for field in FACT_FIELDS},'brand':brand,'model':model,'variant_name':name,'price_sek':price+fee,
        'price_type':'dealer_offer','source_url':source['final_url'],'source_hash':source['content_hash'],'source_quote':quote,
        'source_name':'Volkswagen Group Sverige','source_authority':'importer','source_type':'manufacturer_configurator',
        'fetched_at':source['fetched_at'],'extraction_confidence':0.99}
    stock={key:car[key] for key in ['brand','model','version','regNumber','modelYear','used','mileage','unPublished','firstRegistrationDate','fuelType']}
    stock['cash_price_sek']=price
    row['extraction_payload']={'policy':'current_exact_variants_2026_10_v2','adapter':'vwg_exact_new_stock_v1','stock_row':stock,
        'source_pointer':'/props/pageProps/car','context_hash':hashlib.sha256(text.encode()).hexdigest(),
        'mandatory_fee_sek':fee,'fee_quote':fee_quote,'price_calculation':'advertised_cash_plus_mandatory_fee',
        'field_evidence':{'price_sek':{'quote':quote,'variant':name,'source_url':row['source_url'],'source_hash':row['source_hash']}}}
    return [row]


def stock_profile(parsed,source,brand,model,name):
    car=one(parsed['cars'],'unique_stock_car_required')
    document=parsed['document']
    if car.get('brand',{}).get('name')!=brand or car.get('url',source['final_url'])!=source['final_url']:
        raise RefreshError('stock_brand_or_self_url_mismatch')
    offers=car.get('offers',[])
    offers=offers if isinstance(offers,list) else [offers]
    if brand=='BMW':
        if car.get('name')!='i4 eDrive40' or car.get('vehicleIdentificationNumber')!='WBY61HD030FW37556':
            raise RefreshError('exact_bmw_stock_identity_required')
        if 'M Sport Business Edition' not in document.text():raise RefreshError('bmw_equipment_identity_changed')
        offer=one((item for item in offers if item.get('businessFunction')=='http://purl.org/goodrelations/v1#Sell'),'one_cash_sale_not_lease_required')
        if car.get('vehicleEngine',{}).get('fuelType')!='Elbil':raise RefreshError('battery_electric_stock_required')
        expiry=offer.get('priceValidUntil')
        if not isinstance(expiry,str) or date.fromisoformat(expiry)<datetime.now(timezone.utc).date():raise RefreshError('expired_bmw_offer')
        seller='Bilia Nacka'
        if offer.get('seller',{}).get('name')!=seller:raise RefreshError('bmw_seller_changed')
        visible=one(set(re.findall(r'Kontantpris ([0-9 ]+) kr',document.text())),'unique_bmw_cash_price_required')
        price=int(visible.replace(' ',''))
        condition=offer.get('itemCondition');availability=offer.get('availability')
        authority='manufacturer';source_name='BMW Sverige';auth=None
    elif brand=='Audi' and model=='Q6 E-Tron':
        if [car.get('name'),car.get('model'),car.get('vehicleModelDate'),car.get('vehicleIdentificationNumber'),car.get('bodyType')]!=[
            'Audi Q6 e-tron quattro','Q6 e-tron',2027,'WAUZZZGF3VA023430','SUV']:
            raise RefreshError('exact_bilia_q6_stock_identity_required')
        if car.get('vehicleEngine',{}).get('fuelType')!='El' or car.get('mileageFromOdometer')!={'@type':'QuantitativeValue','unitCode':'KMT','value':0}:
            raise RefreshError('new_zero_mileage_electric_stock_required')
        offer=one(offers,'unique_bilia_cash_offer_required')
        if offer.get('seller',{}).get('@id')!='https://www.bilia.se/anlaggningar/haninge-audi#dealer':raise RefreshError('bilia_seller_changed')
        match=re.search(r'Kontantpris ([0-9]{3})[. ]([0-9]{3}) kr',document.text())
        if not match or 'SUV 315 KW' not in document.text():raise RefreshError('visible_bilia_cash_price_or_motor_missing')
        price=int(match[1]+match[2]);expiry=None
        condition=car.get('itemCondition');availability=offer.get('availability')
        authority='authorized_dealer';source_name='Bilia Haninge Audi';auth=BILIA_AUTH
    elif brand=='Volvo':
        label,exact,year,configuration=('Volvo ES90','ES90 Single Motor Extended Range',2026,'SM Ext Ultra | Privatleasing 9490kr/mån') if model=='Es90' else ('Volvo EX30','EX30 P5 Long Range',2027,'Core')
        if car.get('name')!=label or car.get('model')!=exact or car.get('vehicleModelDate')!=year:
            raise RefreshError('exact_volvo_stock_identity_required')
        if car.get('vehicleConfiguration')!=configuration:raise RefreshError('volvo_stock_trim_changed')
        if car.get('vehicleEngine',{}).get('fuelType')!='El' or car.get('mileageFromOdometer')!={'@type':'QuantitativeValue','unitCode':'KMT','value':0}:
            raise RefreshError('new_zero_mileage_electric_stock_required')
        offer=one(offers,'unique_volvo_offer_required');price=offer.get('price')
        if not isinstance(price,int):raise RefreshError('integer_cash_price_required')
        if f'{price:,}'.replace(',',' ')+' kr' not in document.text() or 'Ny bil' not in document.text():raise RefreshError('visible_volvo_price_or_condition_missing')
        ex_vat=one(set(re.findall(r'([0-9][0-9 ]+) kr exkl\. moms',document.text())),'volvo_cash_vat_evidence_required')
        if int(ex_vat.replace(' ',''))*5!=price*4:raise RefreshError('volvo_inclusive_vat_mismatch')
        condition=car.get('itemCondition');availability=offer.get('availability')
        if offer.get('seller',{}).get('name')!='Volvo Car Retail':raise RefreshError('volvo_seller_changed')
        expiry=None;authority='authorized_dealer';source_name='Volvo Car Retail';auth=VOLVO_AUTH
    else:raise RefreshError('unsupported_stock_adapter')
    if condition not in ('http://schema.org/NewCondition','https://schema.org/NewCondition') or availability not in ('http://schema.org/InStock','https://schema.org/InStock'):
        raise RefreshError('new_and_in_stock_required')
    if offer.get('priceCurrency')!='SEK' or str(offer.get('price'))!=str(price) or not 100000<=price<=3000000:
        raise RefreshError('stock_price_currency_or_visible_conflict')
    quote=f'{name} | Kontantpris {price:,} kr'.replace(',',' ')
    row={**{field:None for field in FACT_FIELDS},'brand':brand,'model':model,'variant_name':name,'price_sek':price,
        'price_type':'dealer_offer','price_valid_until':expiry,'source_url':source['final_url'],'source_hash':source['content_hash'],
        'source_quote':quote,'source_name':source_name,'source_authority':authority,'source_type':'authorized_dealer_stock_page' if auth else 'manufacturer_configurator',
        'authorization_evidence_url':auth,'fetched_at':source['fetched_at'],'extraction_confidence':0.99}
    row['extraction_payload']={'policy':'current_exact_variants_2026_10_v2','adapter':'exact_new_stock_cash_v1',
        'context_hash':hashlib.sha256(document.text().encode()).hexdigest(),'stock_car':car,
        'field_evidence':{'price_sek':{'quote':quote,'variant':name,'source_url':row['source_url'],'source_hash':row['source_hash']}}}
    if auth==VOLVO_AUTH:
        # Primary manufacturer evidence was independently reviewed via its public page.
        # This is not a claim that the blocked raw manufacturer fetch returned HTTP 200.
        row['extraction_payload']['authorization_review']={'url':auth,'reviewed_on':'2026-10-27',
            'method':'primary_manufacturer_page_review','dealer':'Volvo Car Retail',
            'quote':'Du kan också få rådgivning och beställa din bil direkt i studion.'}
    elif auth:
        if not parsed.get('authorization_review'):raise RefreshError('fresh_importer_authorization_required')
        row['extraction_payload']['authorization_review']=parsed['authorization_review']
    return [row]


def collect_stock(url,brand,model,name):
    from remaining_variant_intake import archive_evidence
    bodies=[]
    def parse(body,kind):bodies.append(body);return stock_document(body,kind)
    approved=(BMW_URL,VOLVO_ES90,VOLVO_EX30,BILIA_Q6,*[value['url'] for value in VWG_STOCK.values()])
    def allowed(candidate,brands):return brands=={brand} and candidate==url and url in approved
    source=SourceFetcher(timeout=15,document_parser=parse,url_policy=allowed).fetch(url,{brand})
    if source.get('status')!='reachable' or source.get('final_url')!=url:raise RefreshError('new_stock_source_unavailable:'+source.get('status','unknown'))
    source['fetched_at']=datetime.now(timezone.utc).isoformat()
    archive_evidence(source,one(bodies,'unique_stock_body_required'))
    if url==BILIA_Q6:
        auth_bodies=[]
        def auth_parser(body,kind):auth_bodies.append(body);return stock_document(body,kind)
        authorization=SourceFetcher(timeout=15,document_parser=auth_parser,url_policy=lambda candidate,brands: candidate==BILIA_AUTH and brands=={'Audi'}).fetch(BILIA_AUTH,{'Audi'})
        if authorization.get('status')!='reachable':raise RefreshError('official_importer_network_unavailable')
        props=authorization['document']['page_props']
        if str(props.get('brand','')).lower()!='audi':raise RefreshError('wrong_authorization_brand')
        network=props['carsWithFilter']['filter']['retailers']
        index,item=one(((i,entry['value']) for i,entry in enumerate(network) if entry['value'].get('uniqueId')=='40584A'),'unique_bilia_importer_network_entry_required')
        if item!={'uniqueId':'40584A','name':'Bilia Haninge Audi','brandCode':'A','locationIds':[]}:raise RefreshError('bilia_network_identity_conflict')
        authorization['fetched_at']=datetime.now(timezone.utc).isoformat()
        archive_evidence(authorization,one(auth_bodies,'unique_importer_network_body_required'))
        source['document']['authorization_review']={'url':BILIA_AUTH,'source_hash':authorization['content_hash'],
            'fetched_at':authorization['fetched_at'],'method':'official_importer_network','dealer':'Bilia Haninge Audi',
            'source_pointer':f'/props/pageProps/carsWithFilter/filter/retailers/{index}/value','network_entry':item}
    return vwg_profile(source['document'],source,brand,model,name) if brand+'|'+model in VWG_STOCK else stock_profile(source['document'],source,brand,model,name)
