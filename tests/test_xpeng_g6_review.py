import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from xpeng_g6_review import (configured_identities, configured_versions, dealer_appointment, dealer_prices,
                             seats_reference, standard_braked_reference)


def variant_card(title, version, kw, battery, dc, drive, km, use, price):
    return f'''
    <div class="detailCard_detailCard__test">
      <span class="detailCard_title__test">{title}</span>
      <article>NYA XPENG G6 {version} \xe4r en mellanklass-SUV. Specifikationer:
        \xb7 Max effekt: {kw} kW (250 hk)
        \xb7 Batterikapacitet (Brutto): {battery} kWh
        \xb7 DC-laddning: upp till {dc} kW (10-80 % p\xe5 ca. 12 min)**
        \xb7 Motor: XPENG ({drive})
        \xb7 Dragvikt: 1.500 kg
        \xb7 R\xe4ckvidd: (WLTP): {km} km*
        \xb7 Genomsnittlig f\xf6rbrukning (WLTP): {use} kWh/100km
        \xb7 AC-laddning: 11 kW (3-fas)
        \xb7 Bagagerum: 571 liter / 1.374 liter med nedf\xe4llt baks\xe4te
        Exteri\xf6r:
        \xb7 20" aluminiumf\xe4lgar Interi\xf6r:
        All teknisk data \xe4r beroende av typgodk\xe4nnande
      </article>
      <div class="detailCard_priceValue__test">{price} kr</div>
    </div>'''


def configurator():
    sr = variant_card('RWD Standard Range', 'Standard Range', 185, '68,5', 382, 'bakhjulsdrift', 470, '16,9', '499 900')
    lr = variant_card('RWD Long Range', 'Long Range', 218, '80,8', 451, 'bakhjulsdrift', 525, '17,9', '579 900')
    awd = variant_card('AWD Performance', 'AWD Performance', 358, '80,8', 451, 'fyrhjulsdrift', 510, '18,4', '619 900')
    return (f'<h2>BYGG DIN XPENG G6</h2>'
            f'<div class="settingCard_hiddenContent__test">{sr.replace("499 900", "459 900")}{lr}{awd}</div>'
            f'<div class="settingCard_content__test">{sr}{lr}{awd}</div>'
            '<footer>Ber\xe4knat pris 619 900 kr</footer>').encode()


def dealer():
    return ('<h1>XPENG G6 RWD Standard Range</h1>'
            'Privatleasing Elbil Erbjudande Pris fr. 499 900kr Privatleasing fr. 5 995kr/m\xe5n* '
            'NYA XPENG G6 Standard Range \xe4r en SUV. Finns \xe4ven i f\xf6ljande utf\xf6randen: '
            'RWD Long Range: K\xf6ppris: 579 900 kr Privatleasing: 7 295 kr/m\xe5n* '
            'AWD Performance: K\xf6ppris: 619 900 kr Privatleasing: 8 095 kr/m\xe5n* '
            'Tillval vid privatleasing: Metall').encode()


class XpengG6ReviewTests(TestCase):
    def test_factory_identity_and_unsubsidized_price_bound_to_the_swedish_card(self):
        variants = configured_versions(configurator())
        rows = [
            dict(carSeriesId='731', carSeriesCode='F30bV', carSeriesName='New G6', powerType='BEV', id=record_id,
                 carVersionCode=code, carVersionName=trim, carVersionAlias=trim,
                 msrpBeforeSubsidy=variants[trim]['price']['value'], msrpAfterSubsidy=variants[trim]['price']['value'])
            for trim, record_id, code in zip(variants, ['2761', '1881', '1886'], ['FFCB', 'FFAB', 'FFBB'], strict=True)
        ]

        def source(language='sv'):
            state = dict(carSeriesCode='new_G6', carVersionListData=rows)
            frame = json.dumps([1, '5:' + json.dumps(['', ['$', '$L22', None, {'states': state}]])])
            return f'<html lang="{language}"><script>self.__next_f.push({frame})</script></html>'.encode()

        self.assertEqual(configured_identities(source(), variants)['RWD Standard Range']['value'], 'F30bV$FFCB')
        with self.assertRaisesRegex(ValueError, 'g6_swedish_configurator_language_required'):
            configured_identities(source('en'), variants)
        rows[1]['msrpAfterSubsidy'] = 499900
        with self.assertRaisesRegex(ValueError, 'g6_before_subsidy_visible_price_required'):
            configured_identities(source(), variants)
        rows[1]['carVersionName'] = rows[0]['carVersionName']
        with self.assertRaisesRegex(ValueError, 'g6_exact_factory_version_required'):
            configured_identities(source(), variants)

    def test_exact_visible_sweden_cards_and_price(self):
        result = configured_versions(configurator())
        self.assertEqual([x['price']['value'] for x in result.values()], [499900, 579900, 619900])
        self.assertEqual([x['facts']['wltp_range_km']['value'] for x in result.values()], [470, 525, 510])
        self.assertEqual([x['facts']['dc_charge_kw']['value'] for x in result.values()], [382, 451, 451])
        self.assertEqual([x['facts']['drivetrain']['value'] for x in result.values()], ['RWD', 'RWD', 'AWD'])
        self.assertEqual(result['RWD Standard Range']['facts']['battery_kwh']['capacity_basis'], 'gross')
        self.assertNotIn('tow_kg', result['RWD Standard Range']['facts'])

    def test_old_g6_or_other_battery_cannot_be_promoted(self):
        with self.assertRaisesRegex(ValueError, 'g6_facelift_power_battery_dc_or_drive_changed'):
            configured_versions(configurator().replace(b'68,5 kWh', b'66,0 kWh'))

    def test_reject_wrong_wheels_or_overoptimistic_wltp_pair(self):
        with self.assertRaisesRegex(ValueError, 'g6_swedish_20_inch_scope_required'):
            configured_versions(configurator().replace(b'20" aluminium', b'18" aluminium'))
        with self.assertRaisesRegex(ValueError, 'g6_swedish_20_inch_wltp_pair_changed'):
            configured_versions(configurator().replace(b'525 km', b'535 km').replace(b'17,9 kWh', b'17,5 kWh'))

    def test_dealer_amounts_are_cash_and_independent_of_monthly_values(self):
        variants = configured_versions(configurator())
        self.assertEqual(dealer_prices(dealer(), variants)['AWD Performance']['value'], 619900)
        with self.assertRaisesRegex(ValueError, 'g6_exact_dealer_cash_price_required'):
            dealer_prices(dealer().replace(b'619 900 kr', b'619 900 kr/m'), variants)
        with self.assertRaisesRegex(ValueError, 'g6_configurator_dealer_cash_price_conflict'):
            dealer_prices(dealer().replace(b'579 900 kr', b'569 900 kr'), variants)

    def test_dealer_appointment_is_exact_location_not_generic_partner(self):
        source = ('<h1>XPENG expanderar och \xf6ppnar i Karlstad</h1>'
                  '<p>Tillsammans med Lecab, som fr\xe5n och med september blir '
                  '\xe5terf\xf6rs\xe4ljare av XPENGs produkter.</p>').encode()
        self.assertEqual(dealer_appointment(source)['value'], 'Lecab Bil Karlstad')
        with self.assertRaisesRegex(ValueError, 'g6_xpeng_swedish_lecab_appointment_required'):
            dealer_appointment(source.replace(b'Karlstad</h1>', b'Malmo</h1>'))

    def test_uk_hardware_support_is_only_for_braked_towing(self):
        raw = (b'<article>The XPENG G6 RWD Standard Range is the rear-wheel-drive version - 185 kW '
               b'- Battery capacity (gross): 68.5 kWh LFP - Max DC charging power: 382 kW '
               b'- Gross vehicle weight: 2,535 kg - Braked towing capacity: Up to 1,500 kg '
               b'- Unbraked towing capacity: Up to 750 kg XPILOT ASSIST</article>')
        self.assertEqual(standard_braked_reference(raw)['value'], 1500)
        with self.assertRaisesRegex(ValueError, 'g6_uk_variant_hardware_or_braked_towing_changed'):
            standard_braked_reference(raw.replace(b'1,500 kg', b'750 kg'))
        with self.assertRaisesRegex(ValueError, 'g6_uk_variant_hardware_or_braked_towing_changed'):
            standard_braked_reference(raw.replace(b'68.5', b'80.8'))

    def test_seats_only_from_the_matching_three_column_facelift_sheet(self):
        sheet = '\n'.join(('XPENG G6 SPECIFICATIONS', 'Version RWD Standard Range RWD Long Range AWD Performance',
                           'Drivetrain RWD RWD AW D', 'Power output (kW) 185 218 218+140',
                           'Gross battery capacity (kWh) 68.5 80.8 80.8', 'DC Max charging power (kW) 382 451 451',
                           'Number of Seats 5', 'WLTP Driving Range (km) 480 (R18) 535 (R18) 510 (R20)'))
        page = SimpleNamespace(extract_text=lambda **_: sheet)
        with patch('xpeng_g6_review.PdfReader', return_value=SimpleNamespace(pages=[page, None])):
            self.assertEqual(seats_reference(b'%PDF-fixture')['value'], 5)
            sheet = sheet.replace('185 218 218+140', '190 218 218+140')
            with self.assertRaisesRegex(ValueError, 'g6_matching_facelift_seat_columns_required'):
                seats_reference(b'%PDF-fixture')
