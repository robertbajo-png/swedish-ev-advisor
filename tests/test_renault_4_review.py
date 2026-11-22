import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from renault_4_review import (ALL_SOURCES, AUTH_SKOBES, CARD_LABELS, CONFIGURATOR, EFFICIENCY_SOURCES, PRELIMINARY, PRICE_LIST, RANGE, TECHNO_SOURCES,
                             STOCK_SOURCES, TRIMS, VERSION_IDS, apply_current_review, configurator_reference,
                             exact_rn_consumption, finnvedens_techno, manufacturer_version_cards, pair_review, price_list, review,
                             skobes_corroboration, stock_support, techno_selection, web_crosscheck)
from renault_4_evolution_candidate import DEALER, LOCATOR, dealer_appointment


def example_table():
    technical = [
        ['Teknisk specifikation', *TRIMS],
        [PRELIMINARY, None, None, None],
        [RANGE, '407', '398', '394'],
        ['Antal sittplatser', '5', None, None],
        ['Kapacitet (kWh)', '52', None, None],
        ['Inbyggd laddare', 'Anpassningsbar en-/trefas fr\xe5n 1 kW till 11 kW', None, None],
        ['Snabbladdning upp till DC 100 kW (15-80%)', '30 min', None, None],
        ['Maxvikt f\xf6r bromsat/obromsat sl\xe4p (kg)', '750/750', None, None],
        ['Bagagerumsvolym (L)', '420 (VDA 339)', None, None],
        ['Max. effekt kW (hk)', '110 (150)', None, None],
        ['Referensf\xe4lgar (18")', '195/60 R18 96H', None, None],
    ]
    header = [(0, 0, 100, 10), (100, 0, 200, 10), (200, 0, 300, 10), (300, 0, 400, 10)]
    table = SimpleNamespace(extract=lambda: technical,
                            rows=[SimpleNamespace(cells=header)] +
                            [SimpleNamespace(cells=[header[0], (100, 10, 400, 20), None, None])
                             for _ in technical[1:]])
    cover = MagicMock()
    cover.extract_text.return_value = 'RENAULT 4 E-TECH ELECTRIC\nRek. cirkaprislista G\xe4llande fr\xe5n 12 oktober 2026'
    cover.extract_tables.return_value = [[
        ['Modell', 'batteri', 'motor', 'r', 'CO2', 'f', 'laddare', *TRIMS[:2], 'TECHNO PLEIN SUD (CANVAS TOP)'],
        ['4 E-Tech electric', '52', '150', '394-407', '0', '15,2-15,7', 'AC 11 kW + DC 100 kW',
         '414 900 kr', '434 900 kr', '454 900 kr'],
    ]]
    technical_page = MagicMock()
    technical_page.extract_text.return_value = 'RN Nordic AB'
    technical_page.find_tables.return_value = [table]
    return SimpleNamespace(pages=[cover, None, technical_page]), table, technical


def website(with_techno=True, techno_price='434900', link=PRICE_LIST):
    sections = [
        ('evolution EV52', '414900'), ('techno EV52', techno_price if with_techno else ''),
        ('techno EV52 Plein Sud', '454900'),
    ]
    cash = 'Kontantpriset \xe4r {} kr och du betalar en kontantinsats'
    body = ''.join(f'<p>{name}&nbsp;:&nbsp;Smarta Bill\xe5n med Renault Finans: 3990 kr/m\xe5n. '
                   f'{cash.format(amount) if amount else ""}.</p>'
                   for name, amount in sections)
    return (f'<a href="{link}">prislista</a><a href="{CONFIGURATOR}">bygg din bil</a><p>rekommenderade priser inklusive moms. '
            f'G\xe4ller vid k\xf6p av nya Renault 4 t.o.m. 4/1 2027.</p>{body}').encode()


def next_page(key, props, *, schema=None, locale='sv-SE'):
    url = TECHNO_SOURCES[key]
    state = {'locale': locale, 'query': {'path': urlsplit(url).path.strip('/').split('/')}, 'props': {'pageProps': props}}
    ld = f'<script type="application/ld+json">{json.dumps(schema)}</script>' if schema else ''
    return (f'<link rel="canonical" href="{url}">{ld}'
            f'<script type="application/json" id="__NEXT_DATA__">{json.dumps(state)}</script>').encode()


def techno_inputs(**vehicle_changes):
    stock, locator = 'hedin-techno-18.html', 'renault-sales-locator.html'
    car = {'car_id': '258900', 'car_brand': 'Renault', 'car_model': '4 E-Tech', 'car_fuel': 'El',
           'car_year': 2026, 'car_version': 'R4 E-TECH TECHNO EV52', 'car_drive': 'Framhjulsdrift',
           'battery_size': 52, 'car_site_id': 'bce650651b22d99090829863b24bcb40', 'car_site_city': 'Helsingborg',
           'car_equipment': ['18" aluminiumf\xe4lgar'], 'wltp_electric_range': 398, 'wltp_electric_range_text': '398 km',
           'wltp_electric_consumption': 15.5, 'wltp_electric_consumption_text': '16 kWh/100 km', **vehicle_changes}
    dealer = {'dealerId': '75225550', 'name': 'Hedin Automotive Helsingborg', 'streetAddress': 'Garnisonsgatan 5',
              'markerType': 'sales', 'services': {'RenaultPassengerCarSales': 'True'}}
    files = {stock: next_page(stock, {'componentProps': {'vehicle': {'car': car}}})
                   + b'<a href="/anlaggningar/hedin-automotive-helsingborg-ostra">Garnisonsgatan 5</a>',
             locator: next_page(locator, {'componentProps': {'branches': [dealer]}})}
    common = dict(battery_kwh=52, ac_charge_kw=11, boot_liters=420, tow_kg=750, seats=5)
    result = {'manufacturer_exact_version_cards': {'TECHNO': {'range_reference': {'value': 398},
              'matches_preliminary_range': True, 'agreed_dc_charge_kw': {'value': 100}}},
              'private_efficiency_review': {'TECHNO': {'combined_consumption': {'value': 15.5},
              'corroboration': {'range': {'value': 398}, 'combined_consumption': {'value': 15.5}},
              'range_alternative': {'value': 400}}}, 'swedish_current_ev52_versions': {'TECHNO': {'price': {'value': 434900}}},
              'manufacturer_price_crosschecks': {'TECHNO': {'value': 434900}},
              'shared_technical_evidence': {key: {'value': value} for key, value in common.items()}}
    return files, result


class TechnoSelectionTest(TestCase):
    def test_prepares_nine_fields_without_promoting_the_conflicting_range(self):
        candidate = techno_selection(*techno_inputs())
        self.assertEqual(len(candidate['fields']), 9)
        self.assertEqual(candidate['fields']['wltp_range_km']['value'], 398)
        self.assertEqual(candidate['fields']['wltp_consumption_kwh_100km']['value'], 15.5)
        self.assertEqual(candidate['range_alternative']['value'], 400)
        self.assertEqual(candidate['price']['value'], 434900)
        self.assertEqual(candidate['manufacturer_version_id'], VERSION_IDS[1])
        self.assertFalse(candidate['publication_approved'])

    def test_rejects_changes_to_roof_trim_wheels_unit_numbers_or_dealer_authority(self):
        for changes in ({'car_version': 'TECHNO PLEIN SUD'}, {'car_equipment': ['19" wheels']},
                        {'wltp_electric_range': 400}, {'wltp_electric_consumption_text': '16 Wh/km'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                techno_selection(*techno_inputs(**changes))
        files, result = techno_inputs()
        key = 'renault-sales-locator.html'
        files[key] = files[key].replace(b'"RenaultPassengerCarSales": "True"', b'"RenaultPassengerCarSales": "False"')
        with self.assertRaisesRegex(ValueError, 'sales_appointment_changed'):
            techno_selection(files, result)

    def test_pair_cannot_use_a_partial_capture_or_mix_old_source_times(self):
        report = {'captured_at': '2026-11-21T12:00:00+00:00'}
        files = dict.fromkeys(TECHNO_SOURCES, b'fixture')
        fresh = dict.fromkeys(files, '2026-11-21T11:59:30+00:00')
        with self.assertRaisesRegex(ValueError, 'all_sources_from_one_capture'):
            pair_review(report, files, {})
        for bad_time in ('2026-11-21T11:44:59+00:00', '2026-11-21T12:00:01+00:00'):
            with self.subTest(bad_time=bad_time), self.assertRaisesRegex(ValueError, 'capture_window_exceeded'):
                pair_review(report, files, {**fresh, 'hedin-techno-18.html': bad_time})

    def test_truncated_consumption_label_cannot_replace_exact_vehicle_agreement(self):
        files, result = techno_inputs()
        prior = result['private_efficiency_review']['TECHNO']
        support = prior['corroboration']
        support['unqualified_consumption_observation'] = support.pop('combined_consumption')
        self.assertEqual(techno_selection(files,result)['fields']['wltp_consumption_kwh_100km']['value'],15.5)
        prior['combined_consumption']['value'] = 15.7
        with self.assertRaisesRegex(ValueError,'scope_or_efficiency_approval_required'):
            techno_selection(files,result)


def version_cards(*, battery=52, evo_dc=80, swap=False):
    versions = [{'id': code, 'fields': {'VersionName': {'value': label},
                 'VersionSubtitle': {'value': f'150 hk | {battery} kWh | r\xe4ckvidd {km} km'},
                 'EquipmentBlock': {'value': f'<ul><li>AC 11 kW laddning + DC {dc}</li></ul>'}}}
                for code, label, km, dc in zip(VERSION_IDS, CARD_LABELS, (407, 398, 394), (evo_dc, 100, 100), strict=True)]
    car = {'id': '8415daf9-b7fd-45b9-b492-fe9946c04cf4', 'name': 'RENAULT 4 E-TECH ELECTRIC', 'fields': {'Versions': versions}}
    second = {**car, 'fields': {'Versions': versions[::-1] if swap else versions}}
    groups = [{'componentName': 'SubNavigationGroup', 'fields': {'Pages': [{'fields': {'Car': row}} for row in (car, second)]}}]
    return next_page('versions.html', {'page': {'layout': {'sitecore': {'route': {'placeholders': {'headless-main': groups}}}}}})


def independent_stock(*, consumption='15.7 kWh/100km', trim='Plein Sud', year='2027'):
    pairs = [('p', 'Tillverkare', 'Renault'), ('p', 'Version', '52 kWh'), ('p', 'Modell\xe5r', year),
             ('h5', 'Motor', '52 kWh (110 kW)'), ('h5', 'Elr\xe4ckvidd WLTP', '398 km'),
             ('h5', 'Elf\xf6rbrukning WLTP', consumption), ('h5', 'Drivningstyp', 'Framhjulsdrift')]
    body = ''.join(f'<div><{tag}>{name}</{tag}><p>{value}</p></div>' for tag, name, value in pairs)
    return {'skobes-stock.html': (f'<h1>Renault 4 E-Tech techno {trim} 52kWh</h1>'
                                  f'<p>Skobes Bil Nyk\xf6ping</p>{body}').encode(),
            'skobes-dealer.html': (f'<h1>V\xe4lkommen till Skobes Bil i Nyk\xf6ping</h1><p>{AUTH_SKOBES}</p>').encode()}


def configurator(*, models=None, **kwargs):
    cmp = {'componentName': 'NewCarConfigurator', 'uid': 'cfg', 'fields': {'CarCompany': {'value': 'RenaultSE'}}}
    route = {'placeholders': {'headless-main': [cmp]}}
    if models is None:
        models = [{'modelId': 60, 'modelCode': 'R5E', 'name': 'R5 E-Tech Electric'}]
    return next_page('configurator.html', {'page': {'layout': {'sitecore': {'route': route}}},
        'componentProps': {'cfg': {'modelsData': {'RenaultSE': {'models': models}}}}}, **kwargs)


def stock(*, plein=False, **overrides):
    key = 'plein-sud-stock.html' if plein else 'techno-stock.html'
    ident, model, version, year, dealer, price, km, consumption = (
        ('260151', '4 E-Tech', 'Plein Sud', 2027, 'Hedin Automotive Halmstad', 454900, 398, 156) if plein else
        ('240062', '4', 'Techno | 52kWh | Backkamera | Carplay |', 2026, 'RN Automotive Sp\xe5nga', 434900, 400, 15.5))
    car = {'car_id': ident, 'car_brand': 'Renault', 'car_model': model, 'car_version': version, 'car_year': year,
           'car_mileage': 0, 'car_fuel': 'El', 'car_condition': 'Ny', 'car_is_factory_vehicle': False,
           'car_price_currency': 'SEK', 'car_has_campaign_price': False, 'car_drive': 'Framhjulsdrift',
           'car_price': price, 'car_retail_price': price, 'wltp_electric_range': km,
           'wltp_electric_consumption': consumption, **overrides}
    schema = {'@type': ['Product', 'Car'], 'brand': {'name': 'Renault'}, 'model': model, 'vehicleModelDate': year,
              'offers': {'seller': {'name': dealer}, 'availability': 'https://schema.org/InStock',
                         'priceCurrency': 'SEK', 'price': price, 'itemCondition': 'https://schema.org/UsedCondition'}}
    return next_page(key, {'componentProps': {'listing': {'car': car, 'similarCars': [
        {'car_version': 'Evolution 40kWh', 'wltp_electric_range': 308, 'car_price': 384900}]}}}, schema=schema)


def support_files():
    return {'versions.html': website(), 'configurator.html': configurator(), 'techno-stock.html': stock(),
            'plein-sud-stock.html': stock(plein=True), 'rn-dealer.html':
                (f'<link rel="canonical" href="{STOCK_SOURCES["rn-dealer.html"]}">RN Automotive AB \xe4r auktoriserad '
                 '\xe5terf\xf6rs\xe4ljare och servicepartner').encode(), 'hedin-dealer.html':
                (f'<link rel="canonical" href="{STOCK_SOURCES["hedin-dealer.html"]}">Som \xe5terf\xf6rs\xe4ljare '
                 'f\xf6r Nissan, MG, Isuzu, RAM, Renault och Dacia').encode()}


class Renault4ReviewTests(TestCase):
    def read(self, pdf):
        with patch('renault_4_review.pdfplumber.open') as reader, patch('renault_4_review.PdfReader', return_value=pdf):
            reader.return_value.__enter__.return_value = pdf
            return price_list(b'%PDF-fixture')

    def test_shared_hardware_and_preliminary_grade_ranges_stay_separate(self):
        profiles, facts, consumption = self.read(example_table()[0])
        self.assertEqual([p['price']['value'] for p in profiles.values()], [414900, 434900, 454900])
        self.assertEqual([p['preliminary_wltp_range']['value'] for p in profiles.values()], [407, 398, 394])
        self.assertNotIn('wltp_range_km', facts)
        self.assertNotIn('wltp_consumption_kwh_100km', facts)
        self.assertEqual(consumption['value'], [15.2, 15.7])
        self.assertEqual([facts[k]['value'] for k in
                          ('seats', 'battery_kwh', 'ac_charge_kw', 'dc_charge_kw', 'tow_kg', 'boot_liters')],
                         [5, 52, 11, 100, 750, 420])
        self.assertEqual(facts['boot_liters']['page'], 3)

    def test_evolution_requires_exact_manufacturer_sales_appointment(self):
        sales = {'dealerId': '75225600', 'name': DEALER, 'markerType': 'sales',
                 'services': {'RenaultPassengerCarSales': 'True', 'RenaultPassengerCarService': 'True'}}

        def page(rows, locale='sv-SE', url=LOCATOR):
            state = {'locale': locale, 'query': {'path': ['om-oss', 'aterforsaljare']},
                     'props': {'pageProps': {'componentProps': {'locator': {'dealers': rows}}}}}
            return (f'<link rel="canonical" href="{url}"><script type="application/json" id="__NEXT_DATA__">'
                    + json.dumps(state) + '</script>').encode()

        self.assertEqual(dealer_appointment(page([sales]))['value'], DEALER)
        for raw in (page([sales, sales]), page([sales], locale='da-DK'), page([sales], url='https://example.invalid/'),
                    page([{**sales, 'services': {'RenaultPassengerCarService': 'True'}}]),
                    page([{**sales, 'dealerId': '75225601'}])):
            with self.assertRaises(ValueError):
                dealer_appointment(raw)

    def test_raw_wltp_consumption_requires_explicit_consistent_dealer_units(self):
        key = 'techno-stock.html'
        record = {'stock_id': '240062', 'model_year': {'value': 2026}, 'consumption_raw_observation': {'value': 15.5}}
        for display in ('16\xa0kWh/100\xa0km', '15,5 kWh/100 km'):
            result = exact_rn_consumption({key: stock(wltp_electric_consumption_text=display)}, key, record)
            self.assertEqual(result['value'], 15.5)
            self.assertEqual(result['source_url'], ALL_SOURCES[key])
        for value, display, error in ((15.5, '155 Wh/km', 'exact_consumption_unit'),
                                      (15.5, '15 kWh/100km', 'text_disagrees'),
                                      (156, '156 kWh/100km', 'exact_consumption_unit')):
            changed = {**record, 'consumption_raw_observation': {'value': value}}
            with self.subTest(display=display), self.assertRaisesRegex(ValueError, error):
                exact_rn_consumption({key: stock(wltp_electric_consumption_text=display)}, key, changed)

    def test_finnvedens_only_corroborates_the_exact_fixed_roof_car(self):
        key, branch = 'finnvedens-techno.html', 'finnvedens-linkoping.html'
        canonical = lambda k: f'<link rel="canonical" href="{EFFICIENCY_SOURCES[k]}">'
        block = lambda key, value: ('<div class="col-11 d-flex d-md-block justify-content-between">'
                                    f'<div title="{key}">{key}</div><div>{value}</div></div>')
        labels = [('Registreringsnummer', 'TCU98N'), ('Elr\xe4ckvidd', '398 km'),
                  ('Elf\xf6rbrukning (blandad k\xf6rning)', '15,5 kWh/100km')]
        pairs = ''.join(block(*entry) for entry in labels)
        page = canonical(key) + '<h1>R4 E-Tech techno 52kWh</h1><div class="row gy-2">2026 Ny El</div>' + pairs * 2
        authority = canonical(branch) + ('<h1>Link\xf6ping</h1><p>Vi s\xe4ljer nya bilar fr\xe5n Volvo, Polestar, '
                                         'Lynk &amp; Co, Renault och Dacia &ndash; och \xe4r auktoriserad verkstad f\xf6r samma m\xe4rken.</p>')
        data = {key: page.encode(), branch: authority.encode()}
        result = finnvedens_techno(data, 398)
        self.assertEqual((result['range']['value'], result['combined_consumption']['value']), (398, 15.5))
        self.assertNotIn('final_wltp', result)
        scenarios = [(page.replace('techno 52kWh', 'techno Plein Sud 52kWh'), 'edition_required'),
                     (page.replace('2026 Ny El', '2027 Ny El'), 'edition_required'),
                     (page.replace('TCU98N', 'WRONG1'), 'exact_vehicle_required'),
                     (page.replace('398 km', '400 km', 1), 'exact_field_required'),
                     (page.replace('15,5 kWh/100km', '155'), 'scope_changed')]
        for source, error in scenarios:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                finnvedens_techno({**data, key: source.encode()}, 398)
        with self.assertRaisesRegex(ValueError, 'authority_required'):
            finnvedens_techno({**data, branch: authority.replace('auktoriserad', 'oberoende').encode()}, 398)

    def test_compact_finnvedens_page_can_only_support_range(self):
        key, branch = 'finnvedens-techno.html', 'finnvedens-linkoping.html'
        head = lambda name: f'<link rel="canonical" href="{EFFICIENCY_SOURCES[name]}">'
        label = lambda title, value: ('<div class="col-11 d-flex d-md-block justify-content-between">'
                                      f'<div>{title}</div><div>{value}</div></div>')
        page = (head(key) + '<h1>R4 E-Tech techno 52kWh</h1><div class="row gy-2">2026 Ny El</div>'
                + label('Elr\xe4ckvidd', '398 km') + label('Elf\xf6rbrukning...', '15,5 kWh/100km')
                + '<div id="car-interest" class="car-interest car-loader"><div><strong>R4 E-Tech techno 52kWh</strong>'
                  '<strong>TCU98N</strong></div><form id="car-interest-form" data-regnumber="TCU98N"></form></div>')
        auth = (head(branch) + '<h1>Link\xf6ping</h1><p>Vi s\xe4ljer nya bilar fr\xe5n Volvo, Polestar, Lynk &amp; Co, Renault och Dacia, '
                '\xe4r auktoriserad verkstad f\xf6r samma m\xe4rken</p>').encode()
        files = {key:page.encode(),branch:auth}
        with self.assertRaisesRegex(ValueError,'exact_field_required'):
            finnvedens_techno(files,398)
        result = finnvedens_techno(files,398,allow_range_only=True)
        self.assertEqual(result['range']['value'],398)
        self.assertEqual(result['unqualified_consumption_observation']['value'],15.5)
        self.assertNotIn('combined_consumption',result)
        for invalid in (page.replace('data-regnumber="TCU98N"','data-regnumber="BAD12A"'),
                        page.replace('<strong>TCU98N</strong>','<strong>BAD12A</strong>'),
                        page.replace('<form id="car-interest-form" data-regnumber="TCU98N"></form>','')):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError,'exact_vehicle_required'):
                finnvedens_techno({**files,key:invalid.encode()},398,allow_range_only=True)

    def test_current_cards_preserve_variant_dc_conflict_and_do_not_certify_range(self):
        profiles, facts, _ = self.read(example_table()[0])
        result = manufacturer_version_cards(version_cards(), profiles, facts['dc_charge_kw'])
        self.assertEqual([result[t]['range_reference']['value'] for t in TRIMS], [407, 398, 394])
        self.assertIn('not_explicitly_final', result['EVOLUTION']['range_reference']['scope'])
        self.assertNotIn('agreed_dc_charge_kw', result['EVOLUTION'])
        self.assertEqual(result['EVOLUTION']['dc_observations']['version_card']['value'], 80)
        self.assertEqual(result['EVOLUTION']['dc_observations']['price_list']['value'], 100)
        self.assertEqual(result['TECHNO PLEIN SUD']['agreed_dc_charge_kw']['value'], 100)

    def test_cards_do_not_accept_availability_context_as_exact_powertrain(self):
        profiles, facts, _ = self.read(example_table()[0])
        for source, reason in ((version_cards(battery=40), 'card_powertrain_or_trim_mismatch'),
                               (version_cards(swap=True), 'exact_current_three_version_cards')):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                manufacturer_version_cards(source, profiles, facts['dc_charge_kw'])

    def test_evolution_choice_never_publishes_or_reuses_generic_stock_fields(self):
        profiles, facts, _ = self.read(example_table()[0])
        files = {**independent_stock(), 'versions.html': version_cards(), 'evolution-stock.html': b'exact'}
        result = {'publication_approved': False, 'shared_technical_evidence': facts,
                  'configuration_and_stock_support': {'stock_observations': [
                      {'trim': 'EVOLUTION', 'equipment_dc_reference': {'value': 100, 'quote': 'exact EV52'},
                       'equipment_wltp_reference': {'value': 407, 'quote': 'exact EV52'},
                       'wltp_range_observation': {'value': 398}}]}}
        apply_current_review(files, result, profiles)
        self.assertFalse(result['publication_approved'])
        self.assertNotIn('dc_charge_kw', result['shared_technical_evidence'])
        evolution = result['manufacturer_exact_version_cards']['EVOLUTION']
        self.assertEqual(evolution['preferred_dc_for_review']['value'], 100)
        self.assertEqual(evolution['preferred_range_for_review']['value'], 407)
        self.assertEqual(evolution['dc_observations']['version_card']['value'], 80)

    def test_skobes_requires_exact_roof_year_dealer_and_wltp_units(self):
        result = skobes_corroboration(independent_stock())
        self.assertEqual(result['wltp_consumption_observation']['value'], 15.7)
        self.assertEqual(result['wltp_range_observation']['value'], 398)
        self.assertEqual(result['drivetrain']['value'], 'FWD')
        for files, reason in ((independent_stock(consumption='157'), 'skobes_exact_wltp_units'),
                              (independent_stock(trim='Iconic'), 'skobes_exact_plein_sud'),
                              (independent_stock(year='2026'), 'skobes_exact_generation'),
                              ({**independent_stock(), 'skobes-dealer.html': b'Renault Service'}, 'skobes_authorized')):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                skobes_corroboration(files)

    def test_empty_cells_do_not_authorize_carry_forward(self):
        pdf, table, _ = example_table()
        table.rows[3].cells[1] = (100, 10, 200, 20)
        with self.assertRaisesRegex(ValueError, 'r4_full_width_shared_technical_cell_required'):
            self.read(pdf)

    def test_preliminary_section_change_requires_review(self):
        pdf, _, rows = example_table()
        rows[1][0] = 'WLTP'
        with self.assertRaisesRegex(ValueError, 'r4_wltp_status_changed'):
            self.read(pdf)

    def test_prices_cannot_be_mapped_without_exact_trim_grid(self):
        pdf, _, rows = example_table()
        rows[0][-1] = 'ICONIC'
        with self.assertRaisesRegex(ValueError, 'r4_exact_three_technical_columns'):
            self.read(pdf)

    def test_cash_crosschecks_not_monthly_rates_or_another_trim(self):
        profiles, _, _ = self.read(example_table()[0])
        checks = web_crosscheck(website(), profiles)
        self.assertEqual(checks['TECHNO PLEIN SUD']['value'], 454900)
        self.assertEqual(checks['EVOLUTION']['website_offer_valid_until'], '2027-01-04')
        self.assertNotIn('price_valid_until', profiles['EVOLUTION']['price'])
        with self.assertRaisesRegex(ValueError, 'r4_exact_cash_price_required:TECHNO'):
            web_crosscheck(website(with_techno=False), profiles)
        with self.assertRaisesRegex(ValueError, 'r4_website_cash_price_conflict:TECHNO'):
            web_crosscheck(website(techno_price='454900'), profiles)

    def test_mismatched_or_unlinked_sources_never_accepted(self):
        profiles, _, _ = self.read(example_table()[0])
        with self.assertRaisesRegex(ValueError, 'r4_current_source_link_required'):
            web_crosscheck(website(link=PRICE_LIST.replace('renault-4', 'renault-5')), profiles)
        with self.assertRaisesRegex(ValueError, 'r4_complete_registered_capture_required'):
            review({'prices.pdf': b'%PDF-fixture'})

    def test_configurator_presence_is_not_a_certification_or_availability_claim(self):
        self.assertFalse(configurator_reference(configurator())['value'])
        actual = configurator_reference(configurator(models=[{'modelId': 99, 'modelCode': 'R4E', 'name': 'Renault 4 E-Tech'}]))
        self.assertTrue(actual['value'])
        self.assertIn('not evidence of market availability', actual['scope'])
        with self.assertRaisesRegex(ValueError, 'r4_exact_swedish_source_route_required'):
            configurator_reference(configurator(locale='fr-FR'))
        with self.assertRaisesRegex(ValueError, 'r4_actual_configurator_model_list_required'):
            configurator_reference(configurator(models=[]))

    def test_stock_evidence_is_exact_and_conflicts_are_kept_out_of_factory_profiles(self):
        profiles, _, _ = self.read(example_table()[0])
        report = stock_support(support_files(), profiles)
        techno, plein = report['stock_observations']
        self.assertEqual([o['wltp_range_observation']['value'] for o in (techno, plein)], [400, 398])
        self.assertEqual([o['model_year']['value'] for o in (techno, plein)], [2026, 2027])
        self.assertEqual([o['drivetrain']['value'] for o in (techno, plein)], ['FWD', 'FWD'])
        self.assertEqual(plein['consumption_raw_observation']['value'], 156)
        self.assertIn('stock_consumption_unit_or_value_unclear', plein['release_issues'])
        for row in (techno, plein):
            self.assertIn('range_differs_from_preliminary_manufacturer_trim', row['release_issues'])
            self.assertIn('new_condition_conflicts_with_offer_markup', row['release_issues'])
            self.assertEqual(row['cash_offer']['price_type'], 'dealer_offer')
            self.assertTrue(row['cash_offer']['matches_manufacturer_amount'])
            self.assertNotIn('wltp_range_km', profiles[row['trim']])

    def test_stock_rejects_wrong_edition_offer_condition_and_missing_dealer_evidence(self):
        profiles, _, _ = self.read(example_table()[0])
        for field, value, message in (('car_version', 'Evolution 40kWh', 'r4_registered_stock_identity_changed'),
                                      ('car_price', 384900, 'r4_structured_stock_offer_disagrees'),
                                      ('car_condition', 'Begagnad', 'r4_registered_stock_identity_changed'),
                                      ('car_has_campaign_price', True, 'r4_registered_stock_identity_changed'),
                                      ('wltp_electric_consumption', float('nan'), 'r4_stock_data_outside_review_limits')):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                stock_support({**support_files(), 'techno-stock.html': stock(**{field: value})}, profiles)
        with self.assertRaisesRegex(ValueError, 'r4_dealer_identity_or_authority_changed'):
            stock_support({**support_files(), 'rn-dealer.html': b'<p>Renault service</p>'}, profiles)
