import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from remaining_variant_intake import elroq_grid, cupra_html, mazda_prices, vw_trend, ford_ranges, zeekr_columns, SKODA_URL, CUPRA_MODEL, MAZDA_URL, VW_URL, FORD_URL, ZEEKR_URL
from manufacturer_embedded_data import mazda_document
from variant_refresh import RefreshError, parse_document


class RemainingVariantsTests(unittest.TestCase):
    def source(self,url):
        return {'final_url':url,'content_hash':'a'*64,'fetched_at':'2026-10-27T20:00:00Z'}

    def grid(self):
        def word(text,x,y,width=12):return {'text':text,'x0':x,'x1':x+width,'top':y,'bottom':y+9}
        words=[word(t,x,130,width) for t,x,width in [('Motor',31,28),('Selection',404,43),('Sportline',461,42),('RS',532,13)]]
        for motor,y in [('60',150),('85',170),('85x',190),('RS',210)]:
            words.append(word(motor,31,y))
            for trim,x in [('Selection',404),('Sportline',461),('RS',520)]:
                if (motor=='RS')!=(trim=='RS'):
                    words.append(word('\ufffd',x,y))
                else:
                    words.extend([word('599',x,y),word('000',x+15,y),word('kr',x+30,y)])
        return words

    def test_geometry_binds_exact_trim_and_keeps_estimated_wltp_null(self):
        text='Škoda Elroq Explore Edition WLTP estimerad Erbjudandet är begränsat. Gäller tom 2026-12-15.'
        rows=elroq_grid(self.grid(),595.276,841.89,text,self.source(SKODA_URL),date(2026,10,27))
        self.assertEqual(len(rows),7)
        self.assertEqual(rows[0]['variant_name'],'60 Selection Explore Edition')
        self.assertTrue(all(r['wltp_range_km'] is None and r['price_type']=='campaign_price' for r in rows))
        self.assertTrue(all(r['price_valid_until']=='2026-12-15' for r in rows))
        for words,body in [(self.grid()[1:],text),(self.grid(),text.replace('2026-12-15','2026-09-01')),
                           (self.grid(),text.replace('Explore Edition','Solid Edition'))]:
            with self.assertRaises(RefreshError):
                elroq_grid(words,595.276,841.89,body,self.source(SKODA_URL),date(2026,10,27))
        moved=self.grid(); moved.append({'text':'123','x0':405,'x1':420,'top':150,'bottom':159})
        with self.assertRaises(RefreshError):
            elroq_grid(moved,595.276,841.89,text,self.source(SKODA_URL),date(2026,10,27))

    def test_cupra_html_card_cannot_take_another_versions_price_or_lease(self):
        body='<article><h3>Born</h3><h4>Från 466.900 kr</h4></article><article><h3>Born VZ</h3><h4>Från 596.900 kr</h4></article>'
        rows=cupra_html(parse_document(body.encode(),'text/html'),self.source(CUPRA_MODEL))
        self.assertEqual(rows[0]['variant_name'],'Born VZ')
        self.assertEqual(rows[0]['price_sek'],596900)
        self.assertIsNone(rows[0]['battery_kwh'])
        for changed in [body.replace('Från 596.900 kr','Från 3.995 kr/mån'),body+body]:
            with self.assertRaises(RefreshError):
                cupra_html(parse_document(changed.encode(),'text/html'),self.source(CUPRA_MODEL))

    def mazda(self):
        cards=[{'title':name,'priceText':'Från 469 900 kr','cta':[{'link':'/bygg-din-mazda/MAZDA%206e/5HB/'+slug+'#grade'}]}
            for name,slug in [('Takumi','takumi'),('Homura\u00a0Plus','homuraplus'),('Takumi\u00a0Plus','takumiplus')]]
        return {'language':'sv-SE','page':'ShowroomPage:2027 Mazda6e','components':[
            {'type':'header','props':{'unrelatedPrice':199000}},
            {'type':'slidingContainer','submodules':[{'type':'slidingPricePromoCards','props':{'cards':cards}}]}]}

    def test_mazda_current_grade_pointers_not_unrelated_model_or_financing(self):
        source=self.source(MAZDA_URL)
        rows=mazda_prices(self.mazda(),source)
        self.assertEqual([r['variant_name'] for r in rows],['Takumi MY2027','Homura Plus MY2027','Takumi Plus MY2027'])
        self.assertEqual(rows[0]['extraction_payload']['source_pointer'],'/components/1/submodules/0/props/cards/0')
        for mutate in [lambda d:d.update(language='da-DK'),lambda d:d.update(page='ShowroomPage:2025 Mazda6e'),
                       lambda d:d['components'][1]['submodules'][0]['props']['cards'][0].update(priceText='Från 3995 kr/mån')]:
            document=self.mazda();mutate(document)
            with self.assertRaises(RefreshError):mazda_prices(document,source)

    def test_mazda_ignores_only_generated_render_ids_not_legal_or_model_changes(self):
        first=self.mazda();second=copy.deepcopy(first)
        first['components'][1]['submodules'][0]['props']['id']='11111111-1111-4111-8111-111111111111|123'
        second['components'][1]['submodules'][0]['props']['id']='22222222-2222-4222-8222-222222222222|123'
        a=mazda_prices(first,self.source(MAZDA_URL))[0]['extraction_payload']['context_hash']
        b=mazda_prices(second,self.source(MAZDA_URL))[0]['extraction_payload']['context_hash']
        self.assertEqual(a,b)
        second['components'][1]['submodules'][0]['props']['description']='Price excludes VAT'
        self.assertNotEqual(a,mazda_prices(second,self.source(MAZDA_URL))[0]['extraction_payload']['context_hash'])

    def test_embedded_data_is_parsed_not_executed(self):
        item={'type':'slidingContainer','props':{'name':"Mazda's car"}}
        # The production syntax is single-quoted; JSON5 decodes only the literal.
        value=json.dumps(item).replace("'","\\'")
        script="window.mxp.data.push(JSON.parse('"+value+"'))"
        for suffix in ['', ';']:
            body=('<html lang="sv-SE"><body data-page="ShowroomPage:2027 Mazda6e"><script>'+script+suffix+'</script></body></html>').encode()
            self.assertEqual(mazda_document(body)['components'],[item])
        with self.assertRaises(ValueError):
            mazda_document(('<script>'+script+';evil()</script>').encode())

    def test_vw_single_battery_grade_not_model_maximum_or_another_trim(self):
        body='<h1>ID.3 Neo</h1><ul><li><h3>Life</h3>Pris inkl. moms 499 000 kr BATTERISTORLEKAR (3) WLTP 628 km</li><li><h3>Trend</h3>Pris inkl. moms 409 900 kr BATTERISTORLEKAR (1) Elbil WLTP 417 km</li></ul>'
        row=vw_trend(parse_document(body.encode(),'text/html'),self.source(VW_URL))[0]
        self.assertEqual(row['price_sek'],409900);self.assertIsNone(row['wltp_range_km'])
        for changed in [body.replace('Neo</h1>','GTI</h1>'),body.replace('(1)','(2)'),body.replace('409 900 kr','3995 kr/mån')]:
            with self.assertRaises(RefreshError):vw_trend(parse_document(changed.encode(),'text/html'),self.source(VW_URL))

    def test_ford_exact_drives_do_not_inherit_starting_price_or_awd_charge_power(self):
        quote='Men motormässigt då? Ja, en laddning räcker – enligt WLTP – 602 kilometer vid blandad körning för den bakhjulsdrivna varianten med ett batteripaket på 77 kilowattimmar. Den fyrhjulsdrivna versionen har ett batteri på 79 kilowattimmar och en räckvidd på 556 kilometer'
        body='<h1>Explorer</h1><p>Pris från 549 000 kr</p><p>'+quote+'</p><p>AWD 185 kW</p><footer>Hedin Motor Company AB</footer>'
        rows=ford_ranges(parse_document(body.encode(),'text/html'),self.source(FORD_URL))
        self.assertEqual([row['wltp_range_km'] for row in rows],[602,556])
        self.assertEqual([row['battery_kwh'] for row in rows],[77,79])
        self.assertTrue(all(row['price_sek'] is None and row['dc_charge_kw'] is None for row in rows))
        for changed in [body.replace('556 kilometer','602 kilometer'),body.replace('Hedin Motor Company AB','Unknown'),body+body]:
            with self.assertRaises(RefreshError):ford_ranges(parse_document(changed.encode(),'text/html'),self.source(FORD_URL))

    def test_zeekr_columns_are_not_global_maxima_or_charger_power(self):
        cells=[['','Privilege AWD','Long Range RWD','Core RWD'],['Motor','Dubbel','Enkel','Enkel'],
            ['Batteri','100 kWh','100 kWh','75 kWh'],['Räckvidd, upp till','545 Km','627 Km','482 Km'],
            ['Dragvikt','2000 Kg','2000 Kg','2000 Kg'],['Lastutrymme','539L VDA','539L VDA','539L VDA']]
        body='<p>627 km Cruising range (WLTP) 480 kW station</p><table>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in cells)+'</table>'
        rows=zeekr_columns(parse_document(body.encode(),'text/html'),self.source(ZEEKR_URL))
        self.assertEqual([r['wltp_range_km'] for r in rows],[545,627,482])
        self.assertEqual([r['battery_kwh'] for r in rows],[100,100,75])
        self.assertTrue(all(r['dc_charge_kw'] is None and r['price_sek'] is None for r in rows))
        for changed in [body.replace('Cruising range (WLTP)','Uncertified range'),body.replace('2000 Kg','2 ton'),body.replace('Core RWD','Other model')]:
            with self.assertRaises(RefreshError):zeekr_columns(parse_document(changed.encode(),'text/html'),self.source(ZEEKR_URL))


if __name__=='__main__':unittest.main()
