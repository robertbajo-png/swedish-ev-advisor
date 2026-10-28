import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from manufacturer_embedded_data import stock_document
from stock_variant_intake import stock_profile, vwg_profile, VWG_STOCK, BMW_URL, VOLVO_ES90, BILIA_Q6, BILIA_AUTH
from variant_refresh import RefreshError
from hoglund_stock_intake import extract_hoglund, IDENTITIES, URL as HOGLUND_URL


class StockVariantsTests(unittest.TestCase):
    def bmw(self):
        return {'@type':'Car','name':'i4 eDrive40','url':BMW_URL,'brand':{'name':'BMW'},
            'vehicleIdentificationNumber':'WBY61HD030FW37556','vehicleEngine':{'fuelType':'Elbil'},
            'offers':[{'businessFunction':'http://purl.org/goodrelations/v1#Sell','price':'675900','priceCurrency':'SEK',
                'seller':{'name':'Bilia Nacka'},'itemCondition':'http://schema.org/NewCondition',
                'availability':'http://schema.org/InStock','priceValidUntil':'2099-12-31'},
                {'businessFunction':'http://purl.org/goodrelations/v1#Lease','price':'0','priceCurrency':'SEK'}]}

    def parse(self,car,text):
        body=('<html lang="sv"><h1>'+car['name']+'</h1><p>'+text+'</p><script type="application/ld+json">'+json.dumps(car)+'</script></html>').encode()
        return stock_document(body,'text/html')

    def source(self,url):return {'final_url':url,'content_hash':'a'*64,'fetched_at':'2026-10-27T20:00:00Z'}

    def test_bmw_cash_sale_does_not_use_zero_lease_or_add_unverified_specs(self):
        parsed=self.parse(self.bmw(),'M Sport Business Edition Kontantpris 675 900 kr')
        row=stock_profile(parsed,self.source(BMW_URL),'BMW','i4','i4 eDrive40 M Sport Business Edition (lagerbil FW37556)')[0]
        self.assertEqual(row['price_sek'],675900);self.assertEqual(row['price_type'],'dealer_offer')
        self.assertIsNone(row['wltp_range_km']);self.assertIsNone(row['tow_kg'])
        for mutate in [lambda c:c['offers'][0].update(itemCondition='http://schema.org/UsedCondition'),
                       lambda c:c['offers'][0].update(availability='http://schema.org/SoldOut'),
                       lambda c:c['offers'][0].update(priceCurrency='EUR'),lambda c:c['offers'][0].update(price='599900'),
                       lambda c:c.update(vehicleIdentificationNumber='OTHER')]:
            bad=self.bmw();mutate(bad)
            with self.assertRaises(RefreshError):stock_profile(self.parse(bad,'M Sport Business Edition Kontantpris 675 900 kr'),self.source(BMW_URL),'BMW','i4','fixture')

    def test_duplicate_json_keys_and_ambiguous_cars_are_rejected(self):
        with self.assertRaises(ValueError):stock_document(b'<script type="application/ld+json">{"price":1,"price":2}</script>','text/html')
        car=self.bmw();parsed=self.parse(car,'M Sport Business Edition Kontantpris 675 900 kr');parsed['cars'].append(copy.deepcopy(car))
        with self.assertRaises(RefreshError):stock_profile(parsed,self.source(BMW_URL),'BMW','i4','fixture')

    def test_volvo_requires_zero_mileage_new_condition_and_inclusive_vat(self):
        car={'@type':'Car','name':'Volvo ES90','model':'ES90 Single Motor Extended Range','url':VOLVO_ES90,
            'brand':{'name':'Volvo'},'vehicleModelDate':2026,'vehicleConfiguration':'SM Ext Ultra | Privatleasing 9490kr/mån',
            'vehicleEngine':{'fuelType':'El'},'mileageFromOdometer':{'@type':'QuantitativeValue','unitCode':'KMT','value':0},
            'itemCondition':'https://schema.org/NewCondition','offers':{'price':819000,'priceCurrency':'SEK',
                'availability':'https://schema.org/InStock','seller':{'name':'Volvo Car Retail'}}}
        text='Ny bil 819 000 kr 655 200 kr exkl. moms'
        row=stock_profile(self.parse(car,text),self.source(VOLVO_ES90),'Volvo','Es90','fixture')[0]
        self.assertEqual(row['price_sek'],819000);self.assertEqual(row['source_authority'],'authorized_dealer')
        self.assertTrue(row['authorization_evidence_url'].startswith('https://www.volvocars.com/'))
        for mutate in [lambda c:c['mileageFromOdometer'].update(value=3930),lambda c:c.update(model='EX90'),
                       lambda c:c.update(itemCondition='https://schema.org/UsedCondition')]:
            bad=copy.deepcopy(car);mutate(bad)
            with self.assertRaises(RefreshError):stock_profile(self.parse(bad,text),self.source(VOLVO_ES90),'Volvo','Es90','fixture')
        with self.assertRaises(RefreshError):stock_profile(self.parse(car,text.replace('655 200','600 000')),self.source(VOLVO_ES90),'Volvo','Es90','fixture')

    def test_importer_stock_binds_current_variant_not_group_or_used_car(self):
        entry=VWG_STOCK['Audi|A6 E-Tron'];price=769000
        car={'brand':'Audi','model':entry['model'],'version':entry['version'],'regNumber':entry['registration'],
            'modelYear':2027,'used':False,'mileage':0,'unPublished':False,'firstRegistrationDate':None,'fuelType':'El',
            'pricePoints':{'actualCost':price,'cost':800000,'webcalcLoanCost':8000}}
        def parsed(value):
            text='<h1>Audi A6 Sportback e-tron</h1><p>RRR07B Pris 769 000 kr Räkna på billån Administrationskostnad på 950:- tillkommer</p>'
            text+='<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'car':value}}})+'</script>'
            return stock_document(text.encode(),'text/html')
        row=vwg_profile(parsed(car),self.source(entry['url']),'Audi','A6 E-Tron',entry['variant_name'])[0]
        self.assertEqual(row['price_sek'],price+950);self.assertEqual(row['price_type'],'dealer_offer');self.assertIsNone(row['wltp_range_km'])
        self.assertEqual(row['extraction_payload']['stock_row']['cash_price_sek'],price)
        for mutate in [lambda c:c.update(used=True),lambda c:c.update(mileage=3500),lambda c:c.update(unPublished=True),
            lambda c:c.update(firstRegistrationDate='2026-01-01'),lambda c:c.update(model='A6 Avant'),lambda c:c.update(fuelType='Hybrid el/bensin'),
            lambda c:c['pricePoints'].update(actualCost=8000),lambda c:c.update(regNumber='OTHER')]:
            bad=copy.deepcopy(car);mutate(bad)
            with self.assertRaises(RefreshError):vwg_profile(parsed(bad),self.source(entry['url']),'Audi','A6 E-Tron',entry['variant_name'])
        conflict=parsed(car);conflict['cars']=[{'brand':{'name':'Audi'},'model':'A6 Sedan'}]
        with self.assertRaises(RefreshError):vwg_profile(conflict,self.source(entry['url']),'Audi','A6 E-Tron',entry['variant_name'])

    def test_bilia_stock_requires_separate_importer_authorization(self):
        car={'@type':'Car','name':'Audi Q6 e-tron quattro','model':'Q6 e-tron','url':BILIA_Q6,'brand':{'name':'Audi'},
            'vehicleModelDate':2027,'vehicleIdentificationNumber':'WAUZZZGF3VA023430','bodyType':'SUV',
            'vehicleEngine':{'fuelType':'El'},'mileageFromOdometer':{'@type':'QuantitativeValue','unitCode':'KMT','value':0},
            'itemCondition':'https://schema.org/NewCondition','offers':{'price':799800,'priceCurrency':'SEK',
                'availability':'https://schema.org/InStock','seller':{'@id':'https://www.bilia.se/anlaggningar/haninge-audi#dealer'}}}
        parsed=self.parse(car,'SUV 315 KW Kontantpris 799.800 kr')
        with self.assertRaises(RefreshError):stock_profile(parsed,self.source(BILIA_Q6),'Audi','Q6 E-Tron','fixture')
        parsed['authorization_review']={'url':BILIA_AUTH,'dealer':'Bilia Haninge Audi'}
        row=stock_profile(parsed,self.source(BILIA_Q6),'Audi','Q6 E-Tron','fixture')[0]
        self.assertEqual(row['price_sek'],799800);self.assertEqual(row['source_authority'],'authorized_dealer')
        self.assertEqual(row['authorization_evidence_url'],BILIA_AUTH)
        bad=copy.deepcopy(parsed);bad['cars'][0]['model']='Q6 Sportback e-tron'
        with self.assertRaises(RefreshError):stock_profile(bad,self.source(BILIA_Q6),'Audi','Q6 E-Tron','fixture')

    def test_cla_cash_rows_exclude_ice_estates_lease_and_campaign_without_expiry(self):
        cars=[]
        for identity,(_,title) in IDENTITIES.items():
            cars.append({'car_id':identity,'name':title,'noveltyType':'new_car','year':2027,'mileage':0,'is_leasing':0,
                'brand_name':'Mercedes-Benz','model_name':'CLA','body_type_name':'Sedan','fuel_type_name':'El','location_name':'Höglunds Bil',
                'price':559000,'car_exkl_moms':447200,'sale_price':'','sale_car_exkl_moms':''})
        def parsed(values):
            body='<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'carsList':values}}})+'</script>'
            return stock_document(body.encode(),'text/html')
        rows=extract_hoglund(parsed(cars),self.source(HOGLUND_URL),{})
        self.assertEqual(len(rows),3);self.assertTrue(all(row['price_sek']==559000 and row['price_type']=='dealer_offer' for row in rows))
        self.assertTrue(all(row['wltp_range_km'] is None for row in rows))
        for change in [{'fuel_type_name':'Bensin'},{'body_type_name':'Kombi'},{'is_leasing':1},{'noveltyType':'used_car'},
            {'mileage':1000},{'sale_price':499000},{'car_exkl_moms':559000}]:
            bad=copy.deepcopy(cars);bad[0].update(change)
            with self.assertRaises(RefreshError):extract_hoglund(parsed(bad),self.source(HOGLUND_URL),{})


if __name__=='__main__':unittest.main()
