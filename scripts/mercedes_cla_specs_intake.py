"""Bind Swedish CLA browser evidence to three exact, freshly checked dealer offers."""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

from audit_catalog_sources import ROOT, SourceFetcher, USER_AGENT
from hoglund_stock_intake import AUTH_URL, AUTH_QUOTE, PRIMARY_AUTH, URL, IDENTITIES, extract_hoglund
from manufacturer_embedded_data import stock_document
from variant_refresh import RefreshError, one, parse_document

ADAPTER = 'mercedes_cla_sweden_browser_specs_v1'
MODEL_URL = 'https://www.mercedes-benz.se/passengercars/models/saloon/cla-electric/overview.html'
HEADERS = ['CLA 200', 'CLA 250+', 'CLA 350 4MATIC']
DETAILS = {
    '19043773': 'https://www.hoglundsbil.se/bil/mercedes-benz-cla-200-advanced-edition-2-95-ranta',
    '19003980': 'https://www.hoglundsbil.se/bil/mercedes-benz-cla-250-advanced-edition-2-95-ranta-3',
    '19004063': 'https://www.hoglundsbil.se/bil/mercedes-benz-cla-350-4matic-advanced-edition-2-95-ranta',
}
POST_IDS = {'19043773':3523992,'19003980':3523954,'19004063':3523969}
QUALIFIER = 'Detta värde kan avvika beroende på vilken utrustning som valts.'
ORDER_QUOTE = 'Denna bil är en beställningsbil och finns ej på plats hos oss - kontakta en säljare för mer information.'


def normalize(value):
    return re.sub(r'\s+', ' ', value).strip()


def capture_content(capture):
    return {key: capture[key] for key in ('url', 'canonical', 'lang', 'h1', 'dialog_heading', 'rows',
                                         'tdm_reservation', 'pressroom_url', 'robots')}


def validate_capture(capture, now=None):
    now = now or datetime.now(timezone.utc)
    age = (now - datetime.fromisoformat(capture['captured_at'].replace('Z', '+00:00'))).total_seconds()
    if not -60 <= age <= 900:
        raise RefreshError('fresh_connected_browser_capture_required')
    if (capture['url'] != MODEL_URL or capture['canonical'] != MODEL_URL or capture['lang'] != 'sv-SE'
            or capture['h1'] != 'CLA Elektrisk' or capture['dialog_heading'] != 'Alla tekniska data (Electric)'
            or capture['retrieval_method'] != 'connected_browser_dom' or capture['http_status'] is not None
            or capture['tdm_reservation'] is not None
            or capture['pressroom_url'] != 'https://www.mynewsdesk.com/se/mercedes-benz-sverige'):
        raise RefreshError('exact_swedish_live_manufacturer_dom_required')
    robot = RobotFileParser()
    robot.parse(capture['robots'].splitlines())
    if not capture['robots'].startswith('User-agent: *') or not robot.can_fetch(USER_AGENT, MODEL_URL):
        raise RefreshError('manufacturer_browser_robots_denied')
    rows = capture['rows']
    if len(rows) != 37 or rows[0] != ['', *HEADERS] or any(len(r) not in (1, 4) for r in rows):
        raise RefreshError('exact_three_column_technical_dialog_required')
    if one((r[1:] for r in rows if r[0] == 'Bränsletyp'), 'one_fuel_row_required') != ['Electric'] * 3:
        raise RefreshError('electric_not_hybrid_required')
    return rows


def extract(capture, offers, details, now=None, public_rows=None):
    rows = validate_capture(capture, now)
    content = json.dumps(capture_content(capture), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    source = dict(status='browser_reachable', http_status=None, final_url=MODEL_URL,
                  content_hash=hashlib.sha256(content).hexdigest(), fetched_at=capture['captured_at'],
                  retrieval_method='connected_browser_dom', hash_basis='normalized_named_technical_dialog_and_identity_v1')
    result = []
    for i, (identity, (legacy, _title)) in enumerate(IDENTITIES.items()):
        offer = one((r for r in offers if r['extraction_payload']['stock_row']['car_id'] == identity), 'exact_stock_offer_required')
        detail = details[identity]
        car = detail['car']
        stock = car['bytbil']
        header = HEADERS[i]
        if (car['databaseId'] != POST_IDS[identity]
                or stock['carYearmodel'] != 2027 or stock['carNoveltyType'] != 'new_car'
                or stock['carPriceSek'] != str(offer['price_sek']) or stock['carExklMoms'] != str(offer['price_sek'] * 4 // 5)
                or car['fuelTypes']['nodes'] != [{'name':'El'}]
                or car['bodyTypes']['nodes'] != [{'databaseId':28, 'name':'Sedan'}]
                or stock['carModeldescription'] != offer['extraction_payload']['stock_row']['name'].removeprefix('Mercedes-Benz ')
                or ORDER_QUOTE not in stock['carInfo'] or detail['source']['final_url'] != DETAILS[identity]):
            raise RefreshError('exact_my2027_order_offer_changed')
        equipment = parse_document(stock['carEquipment'].encode(), 'text/html').text()
        if 'Laddningssystem AC 11kW' not in equipment or ('Laddningssystem DC 800V 200kW' if i == 0 else 'Laddningssystem DC 800V') not in equipment:
            raise RefreshError('current_order_charging_equipment_changed')
        replacement = legacy.replace('(lagerbil)', '(beställningsbil)')
        variant = legacy
        if public_rows is not None:
            variant = one((r['variant_name'] for r in public_rows if r['brand'] == 'Mercedes-Benz'
                and r['model'] == 'Cla' and r['variant_name'] in (legacy, replacement)), 'one_current_canonical_cla_identity_required')
        target = dict(adapter=ADAPTER, brand='Mercedes-Benz', model='Cla', variant_name=variant,
            replacement_variant_name=replacement, source=source, supporting_sources=[], facts={}, field_evidence={},
            held_fields={}, extraction_confidence=0.99, source_resolution='owner_2026_11_13_exact_version_current_sources')
        def cell(label):
            return one((r[i+1] for r in rows if r[0] == label), 'one_exact_label_required:' + label)
        def add(field, value, label, scope):
            target['facts'][field] = value
            target['field_evidence'][field] = dict(value=value, quote=header+' | '+label+' | '+cell(label),
                variant_name=variant, column_header=header, scope=scope, source_url=MODEL_URL, source_hash=source['content_hash'])
        for field, label, unit in [
            ('wltp_range_km', 'Elektrisk räckvidd, blandad körning', 'km'),
            ('wltp_consumption_kwh_100km', 'Förbrukning blandad körning', 'kWh/100km'),
            ('battery_kwh', 'Användbart energiinnehåll batteri', 'kWh'),
            ('dc_charge_kw', 'Maximal laddeffekt DC'+QUALIFIER, 'kW'),
            ('ac_charge_kw', 'Maximal laddeffekt AC'+QUALIFIER, 'kW'),
            ('boot_liters', 'BagageutrymmesvolymBagageutrymmesvolymen kan avvika beroende på tillval.', 'l'),
            ('seats', 'Sittplatser', '')]:
            raw = cell(label)
            match = re.fullmatch(r'([0-9]+(?:,[0-9]+)?)'+(' '+re.escape(unit) if unit else ''), raw)
            if not match:
                raise RefreshError('exact_technical_value_required:' + field)
            value = float(match[1].replace(',', '.'))
            add(field, int(value) if value.is_integer() else value, label, 'swedish_c174_exact_powertrain_column')
        label = 'Tillåten släpvagnsvikt (bromsad släpvagn vid 12 %)'+QUALIFIER
        tow = re.fullmatch(r'([0-9 ]+) kg \(([0-9 ]+) kg\)', cell(label))
        if not tow:
            raise RefreshError('equipment_qualified_braked_towing_required')
        add('tow_kg', int(tow[2].replace(' ', '')), label, 'maximum_braked_towing_with_required_equipment')
        drive = {'Bakhjulsdrift':'RWD', 'Fyrhjulsdrift':'AWD'}[cell('Drivlina')]
        add('drivetrain', drive, 'Drivlina', 'swedish_c174_exact_powertrain_column')
        target['price_evidence'] = dict(value=offer['price_sek'], price_type='dealer_offer', price_valid_until=None,
            source_url=offer['source_url'], source_hash=offer['source_hash'], quote=offer['source_quote'],
            classification='exact_current_swedish_order_offer_cash_inclusive_vat',
            authorization_review=offer['extraction_payload']['authorization_review'],
            order_source=detail['source'], order_quote=ORDER_QUOTE,
            stock_identity=offer['extraction_payload']['stock_row'])
        target['model_facts'] = {'body_type':'Sedan'}
        target['model_field_evidence'] = {'body_type':dict(value='Sedan', source_url=detail['source']['final_url'],
            source_hash=detail['source']['content_hash'], quote=header+' Advanced Edition MY2027 | Kaross Sedan | Bränsle El')}
        target['source_decisions'] = [
            'Live Swedish C174 technical dialog, not cached search excerpts, Finnish trim data, Shooting Brake or the older petrol CLA.',
            'Combined WLTP follows each powertrain column, not the model hero maximum or urban range.',
            'AC is the 11 kW powertrain/offer equipment, not the optional 22 kW charger or cable rating.',
            'Rear boot 405 L excludes the separate front compartment.',
            'Maximum braked towing uses the equipment-qualified parenthesized value; no installed towbar is claimed.',
            'Dealer explicitly says order car, not in-stock. Retain cash amount/type, replace the misleading label and preserve legacy links.',
            'Browser-rendered DOM is hash-bound; HTTP status is not observed and remains null, never invented as 200.']
        result.append(target)
    return result


def collect(output):
    capture_path = os.environ.get('CLA_BROWSER_CAPTURE')
    if not capture_path:
        raise RefreshError('fresh_connected_browser_capture_path_required')
    capture = json.loads(Path(capture_path).read_text(encoding='utf-8'))
    validate_capture(capture)
    output.mkdir(parents=True, exist_ok=True)
    fetcher = SourceFetcher(timeout=25, document_parser=lambda raw, _kind: raw,
        url_policy=lambda url, brands: url in (URL, AUTH_URL, *DETAILS.values()) and brands == {'Mercedes-Benz'})
    def fetch(url, filename):
        response = fetcher.fetch(url, {'Mercedes-Benz'})
        if response.get('status') != 'reachable' or response['final_url'] != url:
            raise RefreshError('exact_cla_dealer_source_unavailable:' + response.get('status', 'unknown'))
        raw = response['document']
        (output/filename).write_bytes(raw)
        source = {key:response[key] for key in ('status','http_status','final_url','content_hash')}
        source['fetched_at'] = datetime.now(timezone.utc).isoformat()
        return raw, source
    auth_raw, auth_source = fetch(AUTH_URL, 'authorization.html')
    if AUTH_QUOTE not in parse_document(auth_raw, 'text/html').text():
        raise RefreshError('current_dealer_authorization_required')
    authorization = dict(url=PRIMARY_AUTH, supporting_url=AUTH_URL, supporting_hash=auth_source['content_hash'],
        quote=AUTH_QUOTE, fetched_at=auth_source['fetched_at'], method='existing_primary_appointment_and_fresh_dealer_identity')
    raw, source = fetch(URL, 'stock.html')
    offers = extract_hoglund(stock_document(raw, 'text/html'), source, authorization)
    details = {}
    for identity, url in DETAILS.items():
        raw, source = fetch(url, identity+'.html')
        details[identity] = dict(car=stock_document(raw, 'text/html')['page_props']['car'], source=source)
    public_rows = json.loads((ROOT/'public/data/public_ev_variants.json').read_text(encoding='utf-8'))['records']
    drafts = extract(capture, offers, details, public_rows=public_rows)
    (output/'browser-capture.json').write_text(json.dumps(capture, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'source-packets.json').write_text(json.dumps(dict(capture=capture, offers=offers, details=details), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'intake.json').write_text(json.dumps(dict(adapter=ADAPTER, drafts=drafts, held=[], database_writes=0, paid_calls=0), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(drafts=3, technical_facts=27, prices=3, database_writes=0, paid_calls=0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    collect(parser.parse_args().output)
