import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from mazda_renault_specs_intake import extract_mazda, extract_renault, SOURCES, DocumentFetcher, public_engine_drive
from variant_refresh import RefreshError, parse_document

FIXTURE=json.loads((Path(__file__).parent/'fixtures/mazda_renault_source_grids.json').read_text(encoding='utf-8'))


def payloads():
    data=copy.deepcopy(FIXTURE)
    for key,p in data.items():
        p['raw']=p['raw'].encode()
        p['source']['content_hash']=hashlib.sha256(p['raw']).hexdigest()
        p['source']['final_url']=SOURCES[key]
    return data


class MazdaRenaultSpecsTests(unittest.TestCase):
    def test_six_complete_exact_variants(self):
        p=payloads();rows=extract_mazda(p)+extract_renault(p)
        self.assertEqual(len(rows),6)
        self.assertTrue(all(len(r['facts'])==9 and len(r['field_evidence'])==9 for r in rows))
        self.assertEqual([r['facts']['wltp_range_km'] for r in rows],[560,560,560,320,424,421])
        self.assertEqual([r['facts']['dc_charge_kw'] for r in rows],[200,200,200,80,100,100])
        self.assertEqual([r['price_evidence']['value'] for r in rows],[469900,492800,492800,364900,414900,449900])
        self.assertTrue(all(r['model_facts']=={'body_type':'Halvkombi'} for r in rows))

    def test_mazda_not_legacy_battery_or_unrelated_seats(self):
        for change in ('battery','seats','my','hash','grades'):
            p=payloads()
            if change=='battery':p['mazda_pdf']['pages'][0]['tables'][0][0][0]=p['mazda_pdf']['pages'][0]['tables'][0][0][0].replace('78','68,8')
            if change=='seats':p['mazda_seats']['pages'][0]['text']=p['mazda_seats']['pages'][0]['text'].replace('Anzahl Sitzplätze 5','Anzahl Sitzplätze 7')
            if change=='my':p['mazda_seats']['pages'][0]['text']=p['mazda_seats']['pages'][0]['text'].replace('2027','2025')
            if change=='hash':p['mazda_pdf']['source']['content_hash']='0'*64
            if change=='grades':p['mazda_pdf']['pages'][0]['tables'][0][-1][0]='Mazda CX-6e Homura Plus, 258 hk, 78 kWh'
            with self.subTest(change=change),self.assertRaises(RefreshError):extract_mazda(p)

    def test_mazda_boot_not_frunk_roof_or_folded_seats_and_ac_not_hours(self):
        r=extract_mazda(payloads())[0]
        self.assertEqual(r['facts']['boot_liters'],336)
        self.assertNotIn(r['facts']['boot_liters'],[72,466,678,1074])
        self.assertEqual(r['facts']['ac_charge_kw'],11)
        self.assertNotEqual(r['facts']['ac_charge_kw'],7.9)

    def test_renault_exact_columns_and_current_production(self):
        for change in ('heading','date','charging','battery','range'):
            p=payloads();pages=p['renault_pdf']['pages']
            if change=='heading':pages[-1]['technical_cells'][0][2]='OTHER 52 kWh'
            if change=='date':pages[0]['text']=pages[0]['text'].replace('novembre','november').replace('2026','2025')
            if change=='charging':pages[0]['tables'][0][3][6]='AC 11 kW + DC 80 kW'
            if change=='battery':pages[0]['tables'][0][3][1]='40'
            if change=='range':
                for r in pages[-1]['technical_cells']:
                    if r[0].startswith('Homologerad'):r[2]='424 421'
            with self.subTest(change=change),self.assertRaises(RefreshError):extract_renault(p)

    def test_group_consumption_stays_qualified(self):
        r=extract_renault(payloads())[-1]
        p=r['field_evidence']['wltp_consumption_kwh_100km']
        self.assertEqual(p['interval'],[14.1,14.2])
        self.assertEqual(p['scope'],'battery_group_consumption_interval_lower_bound')
        self.assertIn('versionsgrupp',p['quote'])

    def test_public_modal_is_scoped_not_arbitrary_hidden_text(self):
        body='<h1>RENAULT 5 E-TECH ELEKTRISCH</h1><div hidden><p>Antriebsart Allradantrieb</p></div>'
        body+='<div aria-hidden="true"><dl class="OneConfigEngineTechSpecGroups__line"><dd>Antriebsart</dd><dd>Vorderradantrieb</dd></dl></div>'
        self.assertEqual(public_engine_drive(parse_document(body.encode(),'text/html')),'Antriebsart Vorderradantrieb')
        body+='<dl class="OneConfigEngineTechSpecGroups__line"><dd>Antriebsart</dd><dd>Allradantrieb</dd></dl>'
        with self.assertRaises(RefreshError):public_engine_drive(parse_document(body.encode(),'text/html'))

    def test_pressroom_robots_only_exact_canonical_redirect(self):
        f=DocumentFetcher();origin='https://de.mazda-press.com'
        def error(code,location=None):return HTTPError(origin+'/robots.txt',code,'fixture',{'Location':location} if location else {},None)
        with patch('audit_catalog_sources.SourceFetcher.robots_allowed',return_value=False):
            with patch.object(f.opener,'open',side_effect=[error(301,origin+'/robots.txt/'),error(404)]):
                self.assertTrue(f.robots_allowed(SOURCES['mazda_seats']))
            for errors in ([error(403)],[error(301,'https://other.test/robots.txt')],[error(301,origin+'/robots.txt/'),error(503)]):
                with patch.object(f.opener,'open',side_effect=errors):self.assertFalse(f.robots_allowed(SOURCES['mazda_seats']))
            self.assertFalse(f.robots_allowed('https://unregistered.test/document.pdf'))


if __name__=='__main__':unittest.main()
