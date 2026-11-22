"""Private Swedish evidence for the seven-seat IONIQ 9 AWD Advanced MY27."""

import hashlib
import io
import json
import re
import sys
import urllib.request
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'data/local/release-data'
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_catalog_sources import SourceFetcher, source_text
from import_mobility_sweden import parse_elbil_ranking
from variant_refresh import parse_document

MODEL = 'https://www.hyundai.com/se/sv/bilar/ioniq9.html'
INDEX = 'https://www.hyundai.com/se/sv/bilar/ioniq9/tekniska-data-nedladdningar.html'
MATERIAL = 'GOW7YCZ7ZHH530'
CONFIG = f'https://lager.hyundai.se/model/IONIQ%209/{MATERIAL}?customer=private&ext=R5P&int=NNB'
DOC = 'https://dmassets.hyundai.com/is/content/hyundaiautoever/'
PRICE = DOC + 'Hyundai_Sverige_Prislista_20261102pdf'
TECH = DOC + '250829_IONIQ9_TechSheetpdf-AFpdf'
PRESS = 'https://www.mynewsdesk.com/se/hyundai/images/hyundai-ioniq-9-2024-exterior-charging-fq-punkt-jpg-3276354'
PHOTO = 'https://mnd-assets.mynewsdesk.com/image/upload/fl_attachment/x0nqg0qala939yqnu0940w'
GEOMETRY = (11324, 7923)
HPP = 'https://org-eu-www.hyundai.com/eu/papi'
MARKET = ('https://mobilitysweden.se/statistik/Nyregistreringar_per_manad_1/nyregistreringar-2026/'
          'tydligt-skifte-fran-laddhybrider-till-elbilar-i-oktober')
WORKBOOK = ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
            'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
            'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx')
WORKBOOK_HASH = '1fee5254c4671bd9239b0a0b3819c027c30eac46e1c3a9c1df9c7e9bc55d92c6'
ORIGINAL_HASH = '4556561b89d96c575f1f99c2050a303a9dea7745c4ba3b7c351dada127b4e0b7'
WEB_HASH = '7e75436a099d0532501198666d6715ae50165d6942eeac91f8c779d6403cb0e0'
SOURCES = {'model': MODEL, 'downloads': INDEX, 'config': CONFIG, 'price': PRICE, 'technical': TECH,
           'press': PRESS, 'photo': PHOTO, 'market': MARKET, 'workbook': WORKBOOK}
QUERIES = {
    'Trims': '''query Trims($country:TrimmedString!,$language:TrimmedString!,$service:TrimmedString!,$modelId:TrimmedString!){
      hppFscs2(country:$country,language:$language,service:$service,modelId:$modelId){
        fsc trimName:trimNm trimId powertrainId fscPrice packages{pkgNm}
      }
    }''',
    'EmissionQuery': '''query EmissionQuery($country:TrimmedString!,$language:TrimmedString!,$service:TrimmedString!,$fsc:TrimmedString!){
      hppCo2(country:$country,language:$language,service:$service,fsc:$fsc){ allElectricRange electricityConsumpCombined }
    }''',
}
FACT_QUOTES = {
    'wltp_range_km': ('technical', '20" \u2013 Upp till 606 km \u2013'),
    'wltp_consumption_kwh_100km': ('technical', '19" / 20": 20,4 / 21": 20,6'),
    'battery_kwh': ('model', '110,3 kWh'),
    'dc_charge_kw': ('model', '233 kW'),
    'ac_charge_kw': ('technical', 'Trefas: 11 (10,5)'),
    'boot_liters': ('technical', 'Bagagevolym bakom 3:e s\u00e4tesraden l (VDA 211) 338'),
    'tow_kg': ('technical', 'Sl\u00e4pvagnsvikt med broms 1 600 2 500 2 500'),
    'seats': ('config', 'IONIQ 9 \u00b7 7s AWD 110kWh Advanced MY27'),
    'drivetrain': ('config', 'IONIQ 9 \u00b7 7s AWD 110kWh Advanced MY27'),
}


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('Unexpected official source redirect')


def factory_payload(operation, variables):
    return {'query': QUERIES[operation],
            'variables': {'country': 'se', 'language': 'sv', 'service': 'S03', **variables}}


def factory_query(operation, variables):
    body = json.dumps(factory_payload(operation, variables)).encode()
    request = urllib.request.Request(HPP, body, {'content-type':'application/json', 'accept':'application/json'}, method='POST')
    with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
        if response.status != 200 or response.headers.get_content_type() != 'application/json':
            raise ValueError('Configure API did not return JSON')
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError('Unexpectedly large factory response')
    decoded = json.loads(raw)
    if decoded.get('errors') or 'data' not in decoded:
        raise ValueError('Factory query did not resolve IONIQ 9')
    return body, raw, decoded['data'], {'source_url':HPP, 'fetched_at':utc(), 'http_status':200,
                                       'content_hash':hash_bytes(raw), 'request_hash':hash_bytes(body)}


def check(text, token):
    if token not in text:
        raise ValueError('Official source scope changed: ' + token.encode('ascii','backslashreplace').decode())


def review(bodies, texts, trims, emissions):
    links = {n.attrs.get('href') for n in parse_document(bodies['downloads'], 'text/html').nodes('a')}
    if not {TECH, PRICE} <= links:
        raise ValueError('Current Swedish download index no longer binds both technical and price PDFs')
    config = parse_document(bodies['config'], 'text/html')
    title = 'IONIQ 9 \u00b7 7s AWD 110kWh Advanced MY27'
    if [n.text() for n in config.nodes('title')] != [title+' | Hyundai Sverige'] or MATERIAL.encode() not in bodies['config']:
        raise ValueError('Require exact seven-seat MY27 Swedish material')
    if '20\u201d aluminiumf\u00e4lgar' not in {n.text() for n in config.nodes('li')}:
        raise ValueError('Require the 20-inch equipment at the quoted price')
    exact = [row for row in trims['hppFscs2'] if row['fsc'] == MATERIAL]
    if len(exact) != 1 or any(exact[0].get(k) != v for k,v in {
        'trimName':'Advanced','trimId':'TR0002','powertrainId':'GOW7YCZ7Z|0','fscPrice':850900,'packages':[]}.items()):
        raise ValueError('Current factory material, trim, powertrain or price changed')
    air = emissions['hppCo2']
    if (air.get('allElectricRange'), air.get('electricityConsumpCombined')) != ('606','20.40'):
        raise ValueError('Current equipment-scoped combined WLTP changed')
    price = re.search(r'IONIQ 9\s+(.*?)\s+STARIA', ' '.join(texts['price'].split()))
    if not price:
        raise ValueError('Require current IONIQ 9 price table')
    check(price[1], 'AWD 110kWh Advanced 2,04 - 0 850 900 kr')
    for source,quote in FACT_QUOTES.values():
        if source != 'config':
            check(' '.join(texts[source].split()), quote)
    check(' '.join(texts['technical'].split()), 'AWD Advanced / Calligraphy Line')
    check(bodies['model'].decode('utf-8'), 'helelektrisk SUV med tre s\u00e4tesrader')
    for token in ('Medieanv\u00e4ndning', 'i dess helhet', 'Hyundai_IONIQ_9_2024_exterior_Charging_FQ.jpg'):
        check(texts['press'],token)
    return {'material':MATERIAL, 'model_year':2027, 'wheels_inches':20, 'price_sek':850900,
            'facts':{'wltp_range_km':606,'wltp_consumption_kwh_100km':20.4,'battery_kwh':110.3,
                     'dc_charge_kw':233,'ac_charge_kw':10.5,'boot_liters':338,'tow_kg':2500,'seats':7,'drivetrain':'AWD'},
            'scope':{'price_type':'manufacturer_list_price_before_paint','dc':'shared IONIQ 9 800V hardware',
                     'cargo':'all seven seats up, no frunk','tow':'braked, requires towing equipment','ac':'actual three-phase 10.5 kW'},
            'photo_status':'whole_frame_verified','publication_approved':False,'database_writes':0,'paid_calls':0}


def publisher_links(raw):
    doc = parse_document(raw,'text/html')
    if PHOTO not in {n.attrs.get('href') for n in doc.nodes('a') if n.text() == 'Ladda ner'}:
        raise ValueError('Press page does not link to the locked original')
    main = [n for n in doc.nodes('img') if 'panel__media-image' in n.attrs.get('class','').split()]
    if len(main) != 1 or tuple(int(main[0].attrs.get(k,0)) for k in ('width','height')) != GEOMETRY:
        raise ValueError('Press image dimensions changed')
    links = [x.split() for x in re.split(r'(?<=w),\s+', main[0].attrs.get('srcset',''))]
    if [w for _,w in links] != ['746w','1782w'] or any(not u.startswith('https://mnd-assets.mynewsdesk.com/image/upload/')
            or u.rsplit('/',1)[-1]!=PHOTO.rsplit('/',1)[-1] for u,_ in links):
        raise ValueError('Publisher responsive assets changed')
    return {int(w[:-1]):u for u,w in links}


def fetch_photo(url,media,limit):
    request=urllib.request.Request(url,headers={'accept':media})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=40) as response:
        if response.status!=200 or response.headers.get_content_type()!=media:
            raise ValueError('Unexpected press image response')
        data=response.read(limit+1)
    if not 0<len(data)<=limit:
        raise ValueError('Press image size outside bound')
    return data


def check_photo_frames(original, web):
    if hash_bytes(original) != ORIGINAL_HASH or set(web) != {746} or hash_bytes(web[746][1]) != WEB_HASH:
        raise ValueError('Require the reviewed original and exact publisher web rendition')
    def reference(raw, size, kind):
        with Image.open(io.BytesIO(raw),formats=[kind]) as photo:
            if photo.size!=size or getattr(photo,'n_frames',1)!=1 or photo.getexif().get(274,1)!=1:
                raise ValueError('Press image frame or orientation changed')
            # Downscale before RGB conversion for a bounded inspection of the 90 Mpx original.
            return photo.resize((180,126),Image.Resampling.LANCZOS).convert('RGB')
    full=reference(original,GEOMETRY,'JPEG')
    receipts={}
    for width,(url,raw) in web.items():
        height=round(width*GEOMETRY[1]/GEOMETRY[0])
        with Image.open(io.BytesIO(raw),formats=['JPEG','WEBP']) as encoded:
            kind=encoded.format
        preview=reference(raw,(width,height),kind)
        delta=ImageChops.difference(full,preview)
        error=max(max(ImageStat.Stat(delta.crop((x,y,x+90,y+63))).mean) for x in (0,90) for y in (0,63))
        if error>=2:
            raise ValueError('Publisher rendition changed the original image frame')
        receipts[str(width)]={'source_url':url,'width':width,'height':height,'sha256':hash_bytes(raw),
                              'file':f'photo-{width}.'+('webp' if kind=='WEBP' else 'jpg'),'frame_delta':round(error,3)}
    return receipts


def media_type(key):
    return 'image/jpeg' if key=='photo' else 'application/pdf' if key in ('technical','price') else 'text/html'


def filename(key):
    if key == 'workbook':
        return 'market.xlsx'
    return key + {'image/jpeg':'.jpg','application/pdf':'.pdf','text/html':'.html'}[media_type(key)]


def market_review(article, workbook):
    from urllib.parse import urljoin
    links = {urljoin(MARKET, n.attrs.get('href', '')) for n in parse_document(article, 'text/html').nodes('a')}
    if WORKBOOK not in links or hash_bytes(workbook.read_bytes()) != WORKBOOK_HASH:
        raise ValueError('October market release and pinned workbook no longer agree')
    models, _ = parse_elbil_ranking(workbook, WORKBOOK)
    row, = [r for r in models if (r.brand_raw, r.model_raw, r.fuel_type_raw) == ('HYUNDAI','IONIQ 9','EL')]
    if row.model_group or row.needs_mapping or (row.last_seen_month, row.registrations_last_month,
                                               row.registrations_ytd) != ('2026-10-01',43,330):
        raise ValueError('Swedish model-level October registration row changed')
    return {'sheet':'Elbil ranking','row':{key:getattr(row,key) for key in (
        'brand_raw','model_raw','fuel_type_raw','normalized_brand','normalized_model','last_seen_month',
        'registrations_last_month','registrations_ytd','needs_mapping')}}


def replay(folder):
    folder=folder.resolve(strict=True)
    if folder.parent!=PRIVATE or not re.fullmatch(r'hyundai-ioniq9-advanced-[0-9a-z_]+',folder.name):
        raise ValueError('Require a local IONIQ 9 evidence directory')
    receipt=json.loads((folder/'report.json').read_bytes())
    bodies={name:(folder/filename(name)).read_bytes() for name in SOURCES}
    for name,body in bodies.items():
        proof=receipt['sources'][name]
        if (proof['source_url'],proof['content_hash'],proof['http_status'])!=(SOURCES[name],hash_bytes(body),200):
            raise ValueError('Replay source changed: '+name)
    def factory_data(name, source, variable, value):
        req=(folder/(name+'-request.json')).read_bytes()
        response=(folder/(name+'-response.json')).read_bytes()
        evidence=receipt['sources'][source]
        if json.loads(req) != factory_payload(name, {variable: value}) or (
                evidence['source_url'], evidence['http_status']) != (HPP,200):
            raise ValueError('Factory request scope changed: '+name)
        if (evidence['request_hash'],evidence['content_hash'])!=(hash_bytes(req),hash_bytes(response)):
            raise ValueError('Factory evidence changed: '+name)
        return json.loads(response)['data']
    texts={k:source_text(b,media_type(k)) for k,b in bodies.items() if k not in ('photo','workbook')}
    again=review(bodies,texts,factory_data('Trims','factory_trim','modelId','GO|W7||'),
                 factory_data('EmissionQuery','factory_wltp','fsc',MATERIAL))
    if any(receipt[k]!=v for k,v in again.items()):
        raise ValueError('Verified IONIQ 9 field or scope changed')
    if receipt['market_index'] != market_review(bodies['market'], folder/'market.xlsx'):
        raise ValueError('Replayed market row changed')
    links=publisher_links(bodies['press'])
    web={}
    for width,data in receipt['publisher_responsive_variants'].items():
        if int(width) not in links or data['file'] not in (f'photo-{width}.jpg',f'photo-{width}.webp'):
            raise ValueError('Unknown publisher rendition in receipt')
        web[int(width)] = (links[int(width)],(folder/data['file']).read_bytes())
    if 746 not in web:
        raise ValueError('Require the verified small publisher rendition')
    if check_photo_frames(bodies['photo'],web)!=receipt['publisher_responsive_variants']:
        raise ValueError('Replayed responsive image bytes changed')
    return receipt


def main():
    args=ArgumentParser()
    mode = args.add_mutually_exclusive_group(required=True)
    mode.add_argument('--replay',type=Path)
    mode.add_argument('--capture',action='store_true')
    args.add_argument('--rendition',type=Path)
    flags=args.parse_args()
    if PRIVATE.resolve(strict=True) != PRIVATE or any('onedrive' in p.lower() for p in PRIVATE.parts):
        raise ValueError('Require unlinked local evidence directory')
    if flags.replay:
        result=replay(flags.replay)
        print(json.dumps({'verified':len(result['facts']),'price_sek':result['price_sek'],
                          'responsive_candidates':len(result['publisher_responsive_variants']),
                          'replayed':True,'publication_approved':False}))
        return
    if not flags.rendition or not flags.rendition.resolve(strict=True).is_relative_to(PRIVATE):
        raise ValueError('Supply the exact, previously reviewed publisher rendition in the local evidence directory')
    bodies, texts, sources = {}, {}, {}
    fetcher = SourceFetcher(timeout=15, max_bytes=3_000_000, document_parser=lambda b,_:b,
                            url_policy=lambda u,b: b=={'Hyundai'} and u in SOURCES.values(),
                            text_parser=lambda _body,_kind: '')
    for key,url in SOURCES.items():
        if key == 'photo':
            continue
        res = fetcher.fetch(url, {'Hyundai'})
        if (res['status'],res['http_status'],res['final_url']) != ('reachable',200,url):
            raise ValueError(f'Swedish {key} unavailable: {res["status"]}')
        bodies[key] = res['document']
        if key!='workbook':
            texts[key] = source_text(bodies[key],res['content_type'])
        sources[key] = {'source_url':url, 'content_hash':hash_bytes(bodies[key]), 'fetched_at':utc(), 'http_status':200}
    tr_req,tr_raw,trims,sources['factory_trim'] = factory_query('Trims',{'modelId':'GO|W7||'})
    em_req,em_raw,emissions,sources['factory_wltp'] = factory_query('EmissionQuery',{'fsc':MATERIAL})
    result = review(bodies,texts,trims,emissions)
    links = publisher_links(bodies['press'])
    if not fetcher.robots_allowed(PHOTO):
        raise ValueError('Original press media collection not permitted')
    bodies['photo'] = fetch_photo(PHOTO,'image/jpeg',12_000_000)
    sources['photo'] = {'source_url':PHOTO,'fetched_at':utc(),'http_status':200,'content_hash':hash_bytes(bodies['photo'])}
    # Keep the source's own web rendition already inspected. Do not retry the refused web endpoint.
    web={746:(links[746],flags.rendition.resolve(strict=True).read_bytes())}
    result['publisher_responsive_variants']=check_photo_frames(bodies['photo'],web)
    result['sources']=sources
    folder=Path(mkdtemp(prefix='hyundai-ioniq9-advanced-',dir=PRIVATE))
    for key,body in bodies.items():
        (folder / filename(key)).write_bytes(body)
    for name,raw in [('Trims-request',tr_req),('Trims-response',tr_raw),('EmissionQuery-request',em_req),('EmissionQuery-response',em_raw)]:
        (folder / (name+'.json')).write_bytes(raw)
    for width,(_,raw) in web.items():
        (folder / result['publisher_responsive_variants'][str(width)]['file']).write_bytes(raw)
    result['market_index']=market_review(bodies['market'],folder/'market.xlsx')
    (folder / 'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'folder':str(folder),'technical_fields':len(result['facts']),'price_sek':result['price_sek'],
                      'publication_approved':False}))


if __name__ == '__main__':
    main()
