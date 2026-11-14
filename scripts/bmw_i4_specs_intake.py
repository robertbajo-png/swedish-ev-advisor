"""Exact Swedish BMW stock identity joined to its manufacturer technical type."""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

from audit_catalog_sources import ReservationParser
from manufacturer_embedded_data import stock_document, unique_object
from variant_refresh import RefreshError, one, parse_document

ADAPTER = 'bmw_i4_sweden_61hd_v1'
VIN = 'WBY61HD030FW37556'
NAME = 'i4 eDrive40 M Sport Business Edition (lagerbil FW37556)'
HEADER = 'BMW i4 eDrive40 Gran Coupé | 61HD'
URLS = dict(technical='https://www.bmw.se/sv/alla-modeller/i-series/i4/bmw-i4-gran-coupe-technical-data.html',
            stock='https://hitta.bmw.se/r/G26E-i4/i4-eDrive40-'+VIN)
ROWS = {
    'battery_kwh': ('Batterikapacitet [kWh]', '81,3', 81.3),
    'dc_charge_kw': ('Max. laddningseffekt DC [kW]', '205', 205),
    'ac_charge_kw': ('Max. laddningseffekt AC [kW]', '11', 11),
    'tow_kg': ('Max. släpvagnsvikt (tillval), bromsad 12% / kultryck [kg]', '1 600 / 75', 1600),
    'boot_liters': ('Bagagevolym [liter]', '470–1 290', 470),
    'wltp_consumption_kwh_100km': ('Elförbrukning, blandad körning (WLTP) [kWh/100 km]', '17,1–14,9', 14.9),
}


def require(value, reason):
    if not value:
        raise RefreshError(reason)


def extract(packets, now=None):
    now = now or datetime.now(timezone.utc)
    for key, url in URLS.items():
        s = packets[key]['source']
        age = (now-datetime.fromisoformat(s['fetched_at'].replace('Z', '+00:00'))).total_seconds()
        require(s['status']=='reachable' and s['http_status']==200 and s['final_url']==url
                and re.fullmatch('[a-f0-9]{64}',s['content_hash']) and -60<=age<=900,
                'fresh_exact_bmw_source_required:'+key)
        require(hashlib.sha256(packets[key]['html'].encode()).hexdigest()==s['content_hash'], 'source_bytes_mismatch')
    stock = stock_document(packets['stock']['html'].encode(), 'text/html')
    v = stock['page_props']['vehicle']; spec=v['specification']
    require((v['vin'],v['modelCode'],v['rangeCode'],v['modelName'],v['seriesName'],v['productionYear'])
            ==(VIN,'61HD','G26E','i4 eDrive40','i4',2026), 'exact_stock_vin_type_and_year_required')
    require(spec['electric'] is True and spec['hybrid'] is False and spec['powerHp']==340
            and spec['driveType']=='Bakhjulsdriven' and spec['seatCount']==5, 'stock_engine_identity_required')
    require(v['facebookSpecification']['bodyStyle']=='COUPE', 'stock_body_required')
    def equipment(items):
        for item in items:
            yield item
            yield from equipment(item.get('children') or [])
    require(any(e.get('code')=='3AC' and e.get('name')=='Elektrisk utfällbar dragkrok'
                for e in equipment(v['equipment']+v['equipmentPackages'])), 'stock_towbar_equipment_required')
    require(any(e.get('code')=='ZMG' for e in v['equipmentPackages']), 'stock_business_edition_required')
    car=one(stock['cars'],'one_stock_car_required')
    offers=car['offers'] if isinstance(car['offers'],list) else [car['offers']]
    offer=one((o for o in offers if str(o.get('businessFunction','')).endswith('#Sell')), 'one_cash_offer_required')
    require(car['vehicleIdentificationNumber']==VIN and str(car['seatingCapacity'])=='5'
            and offer['priceCurrency']=='SEK' and int(offer['price'])==v['dealerGrossPrice']==673900
            and offer['availability']=='http://schema.org/InStock'
            and offer['itemCondition']=='http://schema.org/NewCondition'
            and offer['seller']['name']=='Bilia Nacka'
            and offer['priceValidUntil']=='2026-12-31', 'stock_cash_price_or_validity_changed')
    visible=stock['document'].text()
    require('Kontantpris' in visible and '673 900' in visible and '588' in visible, 'visible_stock_cash_range_required')
    require(spec['wltp']['electricRange']==588, 'stock_specific_wltp_required_not_model_maximum')
    doc=parse_document(packets['technical']['html'].encode(),'text/html')
    candidates=[]
    for node in doc.nodes('div'):
        if 'data-schema-org-json' not in node.attrs:continue
        data=json.loads(node.attrs['data-schema-org-json'],object_pairs_hook=unique_object)
        if data.get('@type')=='Car' and data.get('mpn')=='61HD':candidates.append((node,data))
    node,data=one(candidates,'one_exact_61hd_technical_table_required')
    require('cmp-technicaldata__wrapper--show' in node.attrs.get('class','')
            and data.get('@id')=='#Car-61HD' and data.get('name')=='BMW i4 eDrive40 Gran Coupé'
            and data.get('bodyType')=='Gran Coupé' and str(data.get('modelDate'))=='2027', 'active_current_61hd_table_required')
    table=[[c.text() for c in r.children if not isinstance(c,str) and c.tag in ('td','th')] for r in node.nodes('tr')]
    for label,expected in [('Drivlina','Bakhjulsdrift'),('Effekt [kW (hk)]','250 (340)')]:
        require(one((r for r in table if r and r[0]==label),'one_identity_row_required')[1]==expected,'technical_identity_mismatch')
    draft=dict(adapter=ADAPTER,brand='BMW',model='i4',variant_name=NAME,source=packets['technical']['source'],
        supporting_sources=[packets['stock']['source']],source_resolution='exact_stock_vin_61hd_not_21hd',
        extraction_confidence=0.99,facts={},field_evidence={},held_fields={})
    def add(field,value,key,quote,scope):
        s=packets[key]['source'];draft['facts'][field]=value
        draft['field_evidence'][field]=dict(value=value,quote=quote,scope=scope,page=None,column_header=HEADER,
            variant_name=NAME,source_url=s['final_url'],source_hash=s['content_hash'])
    for field,(label,expected,value) in ROWS.items():
        r=one((r for r in table if r and r[0]==label),'one_technical_row_required:'+field)
        require(r[1]==expected,'exact_61hd_technical_value_changed:'+field)
        add(field,value,'technical',HEADER+' | '+label+' '+expected,'manufacturer_type_61hd_not_21hd')
    for field,value,quote in [('wltp_range_km',588,'WLTP räckvidd 588 km'),('seats',5,'Antal sittplatser 5'),
                              ('drivetrain','RWD','Drivning Bakhjulsdriven')]:
        add(field,value,'stock',VIN+' | '+quote,'exact_stock_vin')
    s=packets['stock']['source']
    draft['price_evidence']=dict(value=673900,price_type='dealer_offer',price_valid_until='2026-12-31',
        source_url=URLS['stock'],source_hash=s['content_hash'],quote=VIN+' | Kontantpris 673 900 kr',
        classification='exact_new_stock_cash_offer_not_list_finance_or_zero_lease')
    draft['model_facts']={'body_type':'Coupé'}
    draft['model_field_evidence']={'body_type':dict(value='Coupé',quote=VIN+' | bodyStyle COUPE',
        source_url=URLS['stock'],source_hash=s['content_hash'])}
    draft['source_decisions']=[
        'Exact existing stock VIN FW37556, production 2026, type 61HD and M Sport Business Edition; retain identity and deep link.',
        'Fresh visible cash price and structured Sell offer agree on 673900 SEK. This replaces stale 675900, not a lease or model base price.',
        '2026-12-31 belongs to the cash Sell offer itself, never copied from financing terms.',
        '588 km is the exact stock configuration WLTP, not the type maximum 613 or older 600.',
        'Join technical table by exact type 61HD / 250 kW, not historical 21HD or xDrive40/M60. Current table modelDate2027 does not change stock production year2026.',
        '81.3 kWh is the visible battery row for 61HD; do not parse the malformed JSON-LD capacity unit or old 81.1 kWh.',
        'Consumption 14.9-17.1 kWh/100 km is a manufacturer TYPE interval, not measured exact-stock consumption; retain interval and visible qualification.',
        '205 kW DC and 11 kW onboard AC are separate manufacturer type rows, not charge time or cable rating.',
        '1600 kg braked at12% requires towing equipment; exact stock lists3AC. 75 kg ball load is not towing; 470 L is seats-up boot, not folded1290.',
        'All other models, availability flags, news and budgets remain unchanged.']
    return [draft]


def collect(output):
    output.mkdir(parents=True,exist_ok=True)
    def fetch(key):
        done=subprocess.run(['node','scripts/bmw_i4_http.mjs','--key',key,'--output',str(output)],
            capture_output=True,timeout=45)
        require(done.returncode==0,'bmw_public_get_failed:'+key)
        body=(output/(key+'.body')).read_bytes()
        s=json.loads((output/(key+'.json')).read_text())
        require(hashlib.sha256(body).hexdigest()==s['content_hash'],'transport_hash_mismatch')
        return body,s
    packets={}
    for key,robots in [('technical','robots_bmw'),('stock','robots_stock')]:
        body,s=fetch(robots)
        origin='https://www.bmw.se' if key=='technical' else 'https://hitta.bmw.se'
        require(s['final_url']==origin+'/robots.txt','exact_robots_origin_required')
        text=body.decode('utf8');require('<html' not in text.lower(),'real_robots_required')
        robot=RobotFileParser();robot.parse(text.splitlines())
        require(robot.can_fetch('SwedishEVAdvisor/0.1',URLS[key]),'robots_disallows_bmw_source')
        body,s=fetch(key)
        html=body.decode('utf8');reservation=ReservationParser();reservation.feed(html)
        require(not reservation.reserved,'bmw_machine_reservation')
        packets[key]=dict(source=s,html=html)
    drafts=extract(packets)
    for name,value in [('source-packets.json',packets),('intake.json',dict(adapter=ADAPTER,drafts=drafts,held=[],database_writes=0,paid_calls=0))]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(drafts=1,technical_facts=9,prices=1,database_writes=0,paid_calls=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    collect(p.parse_args().output)
