"""Exact new electric CLA stock rows from the authorized dealer's own website."""
import hashlib
import json
from datetime import datetime, timezone

from audit_catalog_sources import SourceFetcher
from manufacturer_embedded_data import stock_document
from variant_refresh import FACT_FIELDS, RefreshError, one, parse_document

URL='https://www.hoglundsbil.se/bilar?sort=0'
AUTH_URL='https://www.hoglundsbil.se/anlaggningar/mobility-motors-norrtalje'
PRIMARY_AUTH='https://www.hoglundsbil.mercedes-benz.se/passengercars/startpage.html'
AUTH_QUOTE='Vi är en fullserviceanläggning som är auktoriserad återförsäljare av Mercedes och Mazda.'
IDENTITIES={
    '19043773':('CLA 200 Advanced Edition MY2027 (lagerbil)','Mercedes-Benz CLA 200 Advanced Edition 3.95% RÄNTA'),
    '19003980':('CLA 250+ Advanced Edition MY2027 (lagerbil)','Mercedes-Benz CLA 250+ Advanced Edition 3.95% RÄNTA'),
    '19004063':('CLA 350 4MATIC Advanced Edition MY2027 (lagerbil)','Mercedes-Benz CLA 350 4MATIC Advanced Edition 3.95% RÄNTA'),
}


def extract_hoglund(parsed,source,authorization):
    cars=parsed['page_props']['carsList']
    if not isinstance(cars,list) or not 1<=len(cars)<=1000:raise RefreshError('bounded_dealer_stock_list_required')
    selected=[]
    for identity,(name,title) in IDENTITIES.items():
        index,car=one(((i,c) for i,c in enumerate(cars) if c.get('car_id')==identity),'unique_exact_cla_stock_row_required')
        expected={'name':title,'noveltyType':'new_car','year':2027,'mileage':0,'is_leasing':0,'brand_name':'Mercedes-Benz',
            'model_name':'CLA','body_type_name':'Sedan','fuel_type_name':'El','location_name':'Höglunds Bil',
            'sale_price':'','sale_car_exkl_moms':''}
        for field,value in expected.items():
            if type(car.get(field)) is not type(value) or car[field]!=value:raise RefreshError('cla_stock_identity_or_cash_scope_conflict:'+field)
        price,net=car.get('price'),car.get('car_exkl_moms')
        if not isinstance(price,int) or not isinstance(net,int) or not 100000<=price<=3000000 or net*5!=price*4:
            raise RefreshError('cla_inclusive_vat_cash_price_required')
        selected.append((index,car))
    context={'rows':[car for _,car in selected],'terms':parsed['document'].text()}
    context_hash=hashlib.sha256(json.dumps(context,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    result=[]
    for index,car in selected:
        name=IDENTITIES[car['car_id']][0]
        stock={field:car[field] for field in ['car_id','name','noveltyType','year','mileage','is_leasing','brand_name','model_name',
            'body_type_name','fuel_type_name','location_name','price','car_exkl_moms','sale_price','sale_car_exkl_moms']}
        quote=json.dumps(stock,ensure_ascii=False,separators=(',',':'))
        row={**{field:None for field in FACT_FIELDS},'brand':'Mercedes-Benz','model':'Cla','variant_name':name,'price_sek':car['price'],
            'price_type':'dealer_offer','source_url':URL,'source_hash':source['content_hash'],'source_quote':quote,
            'source_name':'Höglunds Bil','source_authority':'authorized_dealer','source_type':'authorized_dealer_stock_page',
            'authorization_evidence_url':PRIMARY_AUTH,'fetched_at':source['fetched_at'],'extraction_confidence':0.99}
        row['extraction_payload']={'policy':'current_exact_variants_2026_10_v2','adapter':'hoglund_exact_new_cla_stock_v1',
            'context_hash':context_hash,'stock_row':stock,'source_pointer':f'/props/pageProps/carsList/{index}',
            'authorization_review':authorization,'field_evidence':{'price_sek':{'quote':quote,'variant':name,'source_url':URL,'source_hash':row['source_hash']}}}
        result.append(row)
    return result


def collect_hoglund():
    from remaining_variant_intake import archive_evidence
    def fetch(url,parser):
        bodies=[]
        def parse(body,kind):bodies.append(body);return parser(body,kind)
        source=SourceFetcher(timeout=15,document_parser=parse,url_policy=lambda candidate,brands:candidate==url and brands=={'Mercedes-Benz'}).fetch(url,{'Mercedes-Benz'})
        if source.get('status')!='reachable' or source.get('final_url')!=url:raise RefreshError('authorized_cla_source_unavailable:'+source.get('status','unknown'))
        source['fetched_at']=datetime.now(timezone.utc).isoformat()
        archive_evidence(source,one(bodies,'unique_dealer_body_required'))
        return source
    auth=fetch(AUTH_URL,parse_document)
    if AUTH_QUOTE not in auth['document'].text():raise RefreshError('current_dealer_authorization_claim_missing')
    authorization={'url':PRIMARY_AUTH,'reviewed_on':'2026-10-27','method':'primary_manufacturer_page_review',
        'manufacturer_label':'Höglunds Bil | Mercedes-Benz Agent','supporting_url':AUTH_URL,'supporting_hash':auth['content_hash'],
        'fetched_at':auth['fetched_at'],'quote':AUTH_QUOTE}
    source=fetch(URL,stock_document)
    return extract_hoglund(source['document'],source,authorization)
