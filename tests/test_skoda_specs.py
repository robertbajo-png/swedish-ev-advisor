import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from skoda_specs_intake import extract, SOURCES, SCOPES, TECHNICAL_RELEASE, PRICE_SOURCES
from variant_refresh import RefreshError


def fixture(model='Elroq', extra=''):
    if model == 'Elroq':
        title = 'Elroq Explore Edition'
        paragraphs = [
            'Trots sin kompakta storlek har Elroq ett stort bagageutrymme på 470 liter (1580 liter med nedfällda säten) och frunk på 21 liter. Dragvikt upp till 1800 kg.',
            'Elroq erbjuds med flera batteristorlekar och med olika drivlinor: 60, 85, fyrhjulsdrivna 85x och RS. Med Elroq Sportline får du sportigare utrustning och med Elroq RS får du hela 340 Hk och fyrhjulsdrift.',
            'Batterikapacitet på 77 kWh ger en räckvidd på upp till 566 km för Elroq 85. Snabbladda 10 till 80% på cirka 28 minuter (max 165 kW DC) med Elroq 85 och 85x.',
        ]
    else:
        title = 'Enyaq Solid Edition'
        paragraphs = [
            'Upptäck Škoda Enyaq 85 Solid Edition – en specialversion.',
            'Stort bagageutrymme på 585 liter (1 710 liter med nedfällda säten) och frunk på 21 liter. Dragvikt på upp till 2 000 kg med fyrhjulsdrift.',
            'Vår populära Enyaq erbjuds som 85 och fyrhjulsdrivna 85x, sportvarianten Enyaq Sportline och Enyaq RS som ger dig större motor, högre batterikapacitet och mer dragvikt.',
            'Batterikapacitet på 77 kWh ger upp till 574 km räckvidd. Ladda 10-80% på 28 minuter med en maxeffekt på 175 kW (DC).',
            'Enyaq har fem sittplatser och ett bagageutrymme på 585 liter . Den har en räckvidd på upp till 574 km enligt WLTP .',
        ]
    def section(question, body):
        return '<div class="accordion-item"><h3>' + question + '</h3>' + body + '</div>'
    def items(rows): return '<ul>' + ''.join('<li>' + row + '</li>' for row in rows) + '</ul>'
    if model == 'Elroq':
        range_rows = ['Elroq 60: upp till 444 km.', 'Elroq 85 och 85x: upp till 569 km.', 'Elroq Sportline 60: upp till 437 km.',
                      'Elroq Sportline 85: upp till 560 km.', 'Elroq Sportline 85x: upp till 559 km.', 'Elroq RS: upp till 548 km.']
        dc = items(['Elroq 60: cirka 26 minuter från 10 till 80 procent, med en maximal laddeffekt på 105 kW.',
                    'Elroq 85, 85x och RS: cirka 29 minuter från 10 till 80 procent, med en maximal laddeffekt på 165 kW.',
                    'Elroq 60: cirka 4 timmar och 33 minuter från 10 till 80 procent.'])
        tow_rows = ['Elroq 60: upp till 1 000 kg.', 'Elroq 85, 85x och RS: upp till 1 800 kg.']
        paragraphs.append('Elroq 60 och 85 har bakhjulsdrift.')
    else:
        range_rows = ['Enyaq 85 och Enyaq 85x: upp till 574 km.', 'Enyaq 85x Sportline: upp till 565 km.', 'Enyaq RS: upp till 558 km.']
        dc = '<p>Snabbladdning (DC): Enyaq 85, 85x, 85x Sportline och RS kan snabbladdas från 10 till 80 procent på cirka 29 minuter, med en maximal DC-laddeffekt på 165 kW.</p>'
        tow_rows = ['Enyaq 85, 85x och 85x Sportline: upp till 2 000 kg.', 'Enyaq RS: upp till 2 200 kg.']
        paragraphs.append('Enyaq 85 har en elmotor på 286 hk och bakhjulsdrift.')
    paragraphs.append('Ja, ' + model + ' 85x, 85x Sportline och RS har fyrhjulsdrift (4×4). De har två elmotorer.')
    questions = section('Hur lång räckvidd har ' + model + '?', items(range_rows) + '<p>Samtliga räckvidder anges enligt WLTP.</p>')
    questions += section('Hur snabbt kan ' + model + ' laddas?', dc + '<p>' + model + ' kan laddas med upp till 11 kW AC, exempelvis hemma.</p>')
    questions += section('Hur mycket får ' + model + ' dra?', items(tow_rows) + '<p>Samtliga uppgifter gäller bromsad släpvagn.</p>')
    gallery = '<div data-module="model-character-gallery" data-props=\'' + json.dumps({'viewModel': {
        'primaryHeadline': 'Bagageutrymme', 'primaryItems': [{'body': 'När baksätets ryggstöd förblir upprättstående finns det 470 liters bagageutrymme för upp till fem passagerare.'}]}}) + '\'></div>'
    body = '<meta name="description" content="Upptäck Škoda ' + model + ', en el-SUV."><main><h1>' + title + '</h1><h2>' + model + ' modellår 2027</h2>' + ''.join('<p>' + text + '</p>' for text in paragraphs) + questions + gallery + '<div data-component="engine-attribute">Elförbrukning, blandad körning 155 171 Wh/km</div>' + extra + '</main>'
    technical = '<main>' + ''.join('<div><h3>' + model + ' ' + engine + ' Škoda ' + model + '</h3><p>Batterikapacitet (Brutto/netto) [kWh] ' +
        ('61/58' if engine == '60' else '82/77') + '</p></div>' for engine in ('60', '85', '85x', 'RS')) + '</main>'
    return dict(model=model, body=body, source=dict(final_url=SOURCES[model], status='reachable', http_status=200,
        content_hash=hashlib.sha256(body.encode()).hexdigest(), fetched_at='2026-11-13T12:00:00Z'),
        technical_support={'body': technical, 'source': dict(final_url=TECHNICAL_RELEASE, status='reachable', http_status=200,
            content_hash=hashlib.sha256(technical.encode()).hexdigest(), fetched_at='2026-11-13T12:00:00Z')})


class SkodaSpecsTests(unittest.TestCase):
    def test_elroq_battery_and_dc_keep_their_explicit_engine_scope(self):
        for variant in SCOPES['Elroq']:
            draft = extract(fixture(), variant)
            self.assertEqual(draft['facts']['boot_liters'], 470)
            self.assertEqual(draft['facts']['battery_kwh'], 58 if variant.startswith('60 ') else 77)
            self.assertEqual(draft['facts']['dc_charge_kw'], 105 if variant.startswith('60 ') else 165)
            self.assertEqual(draft['facts']['ac_charge_kw'], 11)
            self.assertEqual(draft['facts']['seats'], 5)
            self.assertEqual(draft['model_facts'], {'body_type': 'SUV'})
            self.assertEqual(draft['facts']['drivetrain'], 'AWD' if '85x' in variant or variant.startswith('RS ') else 'RWD')
            self.assertEqual(draft['facts']['tow_kg'], 1000 if variant.startswith('60 ') else 1800)
            self.assertIn(draft['facts']['wltp_range_km'], [444, 437, 569, 560, 559, 548])
            self.assertEqual(draft['source']['content_hash'], draft['field_evidence']['boot_liters']['source_hash'])

    def test_enyaq_does_not_borrow_peaq_seats_frunk_or_folded_boot(self):
        payload = fixture('Enyaq', '<p>Peaq har sju sittplatser och ett bagageutrymme på 935 liter.</p>')
        for variant in SCOPES['Enyaq']:
            facts = extract(payload, variant)['facts']
            self.assertEqual(facts['boot_liters'], 585)
            self.assertEqual(facts['seats'], 5)
            self.assertEqual(facts['battery_kwh'], 77)
            self.assertEqual(facts['dc_charge_kw'], 165)

    def test_unknown_trim_wrong_market_and_changed_bytes_are_held(self):
        with self.assertRaises(RefreshError):
            extract(fixture('Enyaq'), 'Solid Edition Unknown')
        for change in [dict(final_url=SOURCES['Elroq'].replace('.se', '.dk')), dict(content_hash='a' * 64), dict(http_status=403)]:
            payload = fixture(); payload['source'].update(change)
            with self.assertRaises(RefreshError):
                extract(payload, SCOPES['Elroq'][0])
        with self.assertRaises(RefreshError):
            extract(fixture(), '85 Premium')

    def test_changed_edition_model_year_or_ambiguous_visible_fact_is_held(self):
        for old, new in [('Explore Edition', 'Old Edition'), ('modellår 2027', 'modellår 2025')]:
            payload = fixture(); payload['body'] = payload['body'].replace(old, new)
            payload['source']['content_hash'] = hashlib.sha256(payload['body'].encode()).hexdigest()
            with self.assertRaises(RefreshError): extract(payload, SCOPES['Elroq'][0])
        extra = '<p>Trots sin kompakta storlek har Elroq ett stort bagageutrymme på 500 liter (annan version).</p>'
        with self.assertRaises(RefreshError): extract(fixture(extra=extra), SCOPES['Elroq'][0])

    def test_consumption_keeps_engine_scope_unit_correction_and_standard_equipment_caveat(self):
        for model, variant, label, raw in [('Elroq', '85 Sportline Explore Edition', '85', '156'),
                                            ('Enyaq', 'Solid Edition 85x Sportline', '85x Sportline', '159')]:
            support = {'source': dict(final_url=PRICE_SOURCES[model], content_hash='d' * 64),
                'page': 'Škoda ' + model + (' Explore Edition' if model == 'Elroq' else ' Solid Edition') +
                    '\nPrislista 5 november, 2026\n*Värde gäller för motor i grundutförande.',
                'tables': [[[label, '286', '567', raw, '0', '494 900 kr', '510 300 kr', '–']]]}
            draft = extract(fixture(model), variant, price_support=support)
            proof = draft['field_evidence']['wltp_consumption_kwh_100km']
            self.assertEqual(draft['facts']['wltp_consumption_kwh_100km'], int(raw) / 10)
            self.assertEqual(proof['engine_label'], label)
            self.assertIn('grundutförande', proof['qualification'])
            self.assertIn('Wh/km', proof['unit_quote'])
            broken = copy.deepcopy(support); broken['tables'][0][0][0] = 'Other'
            with self.assertRaises(RefreshError): extract(fixture(model), variant, price_support=broken)
            broken = copy.deepcopy(support); broken['tables'][0][0][3] = '15.6'
            with self.assertRaises(RefreshError): extract(fixture(model), variant, price_support=broken)


if __name__ == '__main__': unittest.main()
