import copy
import io
import json
import sys
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from toyota_chr_plus_intake import extract,configuration,PROFILES,RANGE,MODEL_ID
from toyota_price_intake import parse_pdf
from variant_refresh import RefreshError
from prerender_static_routes import public_variant_routes


class ChrPlusIntakeTests(unittest.TestCase):
    def setUp(self):
        d=json.loads((Path(__file__).parent/'fixtures/toyota_chr_plus_packets.json').read_text(encoding='utf8'))
        self.p,self.market=d['packets'],d['market']
        self.now=max(datetime.fromisoformat(s['source']['fetched_at']) for s in [*self.p.values(),self.market])

    def changed(self,key,old,new,part='html',page=None):
        p=copy.deepcopy(self.p)
        value=p[key][part] if page is None else p[key][part][page]
        self.assertIn(old,value)
        if page is None:p[key][part]=value.replace(old,new)
        else:p[key][part][page]=value.replace(old,new)
        return p

    def test_three_complete_swedish_profiles_not_hybrid_or_us_car(self):
        d=extract(self.p,self.market,self.now)
        self.assertEqual(d['model']['model'],'C-Hr+')
        for r,p in zip(d['drafts'],PROFILES):
            self.assertEqual(r['manufacturer_identity'],p[1]);self.assertEqual(len(r['facts']),9)
            self.assertEqual(r['facts']['battery_kwh'],77);self.assertEqual(r['facts']['seats'],5)
            self.assertEqual(r['facts']['boot_liters'],416);self.assertEqual(r['price_evidence']['value'],p[7])

    def test_exact_plus_electric_generation_and_left_hand_drive(self):
        for old,new in [('Nya Toyota C-HR+','Nya Toyota C-HR'),(MODEL_ID,'11111111-1111-4111-8111-111111111111'),
            ('&quot;steering&quot;: &quot;L&quot;','&quot;steering&quot;: &quot;R&quot;'),
            ('&quot;code&quot;: &quot;BEV&quot;','&quot;code&quot;: &quot;HEV&quot;'),
            ('&quot;country&quot;: &quot;se&quot;','&quot;country&quot;: &quot;us&quot;'),('6.HD','old-version')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):
                extract(self.changed('specifications',old,new),self.market,self.now)
        m=copy.deepcopy(self.market);m['row']['model_raw']='C-HR'
        with self.assertRaises(RefreshError):extract(self.p,m,self.now)

    def test_exact_default_grade_and_unique_configuration(self):
        for old,new in [(PROFILES[2][1],PROFILES[0][1]),('SUV 5-d','SUV 3-d')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):
                extract(self.changed('specifications',old,new),self.market,self.now)
        duplicate=self.p['specifications']['html'].replace('</html>',self.p['specifications']['html']+'</html>')
        with self.assertRaises(RefreshError):configuration(duplicate)

    def test_range_is_final_per_grade_and_standard_wheel_not_generic_max(self):
        for old,new in [('Executive AWD: 507 km','Executive AWD: 548 km'),('Active AWD 18": 548 km','Active AWD 18": 607 km'),
            ('slutliga homologiseringsvärden','preliminära uppskattningar')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.changed('model',old,new),self.market,self.now)
        d=extract(self.p,self.market,self.now)
        self.assertEqual([r['facts']['wltp_range_km'] for r in d['drafts']],[607,548,507])

    def test_battery_is_77_gross_not_generic_copied_other_model_paragraph(self):
        with self.assertRaises(RefreshError):extract(self.changed('model','bruttobatterikapacitet','nettobatterikapacitet'),self.market,self.now)
        p=copy.deepcopy(self.p);p['model']['html']=p['model']['html'].replace('</html>','<p>Urban Cruiser:49 kWh,61 kWh,344 km,426 km.</p></html>')
        self.assertEqual([r['facts']['battery_kwh'] for r in extract(p,self.market,self.now)['drafts']],[77,77,77])

    def test_grade_consumption_and_onboard_ac_not_all_22(self):
        for key,old,new,part,page in [('price_pdf','Ombordladdare 22 kW AC','Ombordladdare 11 kW AC','pages',3),
            ('price_pdf','Ombordladdare 11 kW AC','Ombordladdare 22 kW AC','pages',2),
            ('price_pdf','15.5 kWh/100km','14.4 kWh/100km','left_columns',1),
            ('price_pdf','snabbladdning 150 kW DC','snabbladdning 350 kW DC','pages',3)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.changed(key,old,new,part,page),self.market,self.now)
        d=extract(self.p,self.market,self.now)
        self.assertEqual([r['facts']['ac_charge_kw'] for r in d['drafts']],[11,11,22])
        self.assertEqual([r['facts']['wltp_consumption_kwh_100km'] for r in d['drafts']],[13.4,14.4,15.5])

    def test_towing_is_braked_per_motor_not_max_or_train_weight(self):
        for old,new in [('750                                                       1500','1500                                                      1500'),
            ('Dragvikt bromsat släp','Dragvikt obromsat släp')]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.changed('price_pdf',old,new,'pages',5),self.market,self.now)
        self.assertEqual([r['facts']['tow_kg'] for r in extract(self.p,self.market,self.now)['drafts']],[750,1500,1500])

    def test_cash_prices_not_loan_campaign_or_swapped_grade(self):
        for old,new,page in [('519 900 kr','3 610 kr',0),('540 900 kr','519 900 kr',0),('593 900 kr','15 000 kr',1)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.changed('price_pdf',old,new,'left_columns',page),self.market,self.now)
        for r in extract(self.p,self.market,self.now)['drafts']:
            self.assertEqual(r['price_evidence']['price_type'],'list_price')
            self.assertIsNone(r['price_evidence']['price_valid_until'])
            self.assertNotIn('2027-01-11',r['price_evidence']['quote'])

    def test_price_list_must_be_current_linked_and_only_page5_may_be_visual(self):
        for key,old,new,part,page in [('model','https://pdf.toyotasverigebroschyr.com/price-list/nya-toyota-c-hr','https://comparison.invalid/price','html',None),
            ('price_pdf','Uppdaterad: 2026','Uppdaterad: 2025','pages',8)]:
            with self.subTest(old=old),self.assertRaises(RefreshError):extract(self.changed(key,old,new,part,page),self.market,self.now)
        p=copy.deepcopy(self.p);p['price_pdf']['pages'][2]=''
        with self.assertRaises(RefreshError):extract(p,self.market,self.now)
        writer=PdfWriter();page=writer.add_blank_page(width=595,height=842)
        stream=DecodedStreamObject();stream.set_data(b'q Q');page.replace_contents(stream)
        raw=io.BytesIO();writer.write(raw)
        with self.assertRaises(RefreshError):parse_pdf(raw.getvalue(),'application/pdf')
        self.assertEqual(parse_pdf(raw.getvalue(),'application/pdf',allowed_empty_pages={1})['pages'],[''])

    def test_sources_and_market_activity_do_not_confirm_availability(self):
        for key,value in [('http_status',403),('content_hash','bad'),('final_url','https://wrong.invalid/')]:
            p=copy.deepcopy(self.p);p['price_pdf']['source'][key]=value
            with self.subTest(key=key),self.assertRaises(RefreshError):extract(p,self.market,self.now)
        for patch in [dict(needs_mapping=True),dict(fuel_type_raw='ELHYBRID'),dict(registrations_last_month=0)]:
            m=copy.deepcopy(self.market);m['row'].update(patch)
            with self.subTest(patch=patch),self.assertRaises(RefreshError):extract(self.p,m,self.now)
        with self.assertRaises(RefreshError):extract(self.p,self.market,self.now+timedelta(days=1))

    def test_initial_metadata_preserves_plus_exact_price_and_upper_wltp_scope(self):
        for r in extract(self.p,self.market,self.now)['drafts']:
            row=dict(brand='Toyota',model='C-Hr+',variant_name=r['variant_name'],**r['facts'],
                price_sek=r['price_evidence']['value'],price_type='list_price',validation_status='published',
                source_quote=' | '.join(e['quote'] for e in r['field_evidence'].values()))
            route=public_variant_routes([row])[0]
            self.assertIn('C-HR+',route['title']);self.assertIn('upp till',route['description'])
            ld=route['json_ld'][0]
            self.assertEqual(ld['offers']['price'],row['price_sek'])
            self.assertEqual(next(p['value'] for p in ld['additionalProperty'] if p['name']=='AC-laddning'),str(row['ac_charge_kw'])+' kW')


if __name__=='__main__':unittest.main()
