"""Source-bound completion of six existing Toyota/Polestar versions. No DB writes."""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from audit_catalog_sources import SourceFetcher
from toyota_price_intake import HTML_URL, config_from_document, extract_config
from variant_refresh import Node, RefreshError, one, parse_document

ADAPTER = 'toyota_polestar_sweden_specs_v1'
SOURCES = {
    'toyota': HTML_URL,
    'toyota_model': 'https://www.toyota.se/bilar/bz4x',
    'p2': 'https://www.polestar.com/se/polestar-2/specifications/',
    'p2_model': 'https://www.polestar.com/se/polestar-2/',
    'p2_seats': 'https://www.polestar.com/se/manual/polestar-2/2026/article/946775eb53a5592fc0a8015165dbd2b8/',
    'p4': 'https://www.polestar.com/se/polestar-4-models/polestar-4-coupe/specifications/',
    'p4_seats': 'https://www.polestar.com/se/news/suv-vs-suv-coupe-what-is-the-difference/',
    'p4_wltp': 'https://www.polestar.com/se/manual/polestar-4-coupe/2027/article/0ed816eed33d98cac0a8cc377bc12bc7-32882fb459557dbec0a8b097072c55bf-8664b2fa77a7e089c0a8296870d1a409/',
}
SCOPES = {'2': ['Long range Single motor', 'Long range Dual motor', 'Long range Dual motor med Performance-paketet'],
          '4': ['Rear motor', 'Dual motor']}


def checked(payload, url):
    source, body = payload['source'], payload['body'].encode('utf-8')
    if (source['final_url'] != url or source['status'] != 'reachable' or source['http_status'] != 200
            or source['content_hash'] != hashlib.sha256(body).hexdigest()):
        raise RefreshError('exact_source_bytes_required')
    return parse_document(body, 'text/html')


def literal(document, text):
    if text not in document.text():
        raise RefreshError('literal_support_missing:' + text)
    return text


def number(text, pattern):
    match = re.fullmatch(pattern, text)
    if not match:
        raise RefreshError('ambiguous_technical_value:' + text)
    return float(match[1].replace(' ', '').replace(',', '.'))


def packet(brand, model, variant, source):
    return dict(adapter=ADAPTER, brand=brand, model=model, variant_name=variant,
                facts={}, field_evidence={}, supporting_sources=[], held_fields={}, extraction_confidence=0.99,
                source=source, source_resolution='owner_2026_11_13_exact_version_current_sources')


def add(row, field, value, quote, payload, scope, **extra):
    source = payload['source']
    row['facts'][field] = value
    row['field_evidence'][field] = dict(value=value, quote=quote, source_url=source['final_url'],
        source_hash=source['content_hash'], variant_name=row['variant_name'], scope=scope, **extra)
    if source['final_url'] != row['source']['final_url'] and source not in row['supporting_sources']:
        row['supporting_sources'].append(source)


def model_fact(row, body, quote, payload):
    row['model_facts'] = {'body_type': body}
    source = payload['source']
    row['model_field_evidence'] = {'body_type': dict(value=body, quote=quote,
        source_url=source['final_url'], source_hash=source['content_hash'])}
    if source['final_url'] != row['source']['final_url'] and source not in row['supporting_sources']:
        row['supporting_sources'].append(source)


def price(row, value, quote):
    row['price_evidence'] = dict(value=value, price_type='list_price', price_valid_until=None,
        quote=quote, source_url=row['source']['final_url'], source_hash=row['source']['content_hash'],
        classification='current_exact_variant_base_cash_price_not_finance_or_discount')


def extract_toyota(payloads):
    payload, support = payloads['toyota'], payloads['toyota_model']
    document, model = checked(payload, SOURCES['toyota']), checked(support, SOURCES['toyota_model'])
    config = config_from_document(document)
    extracted = one(extract_config(config, {'url': SOURCES['toyota'], 'brand': 'Toyota', 'model': 'bZ4X',
        'content_hash': payload['source']['content_hash'], 'source_authority': 'manufacturer',
        'source_type': 'manufacturer_specs_page', 'source_validation': 'reachable_official_model_source'}), 'one_selected_active_engine_required')
    variant = 'Active FWD 57.7 kWh 167 hk'
    if extracted['variant_name'] != variant or config['car']['id'] != '552b7e03-84d2-4b36-a5bb-87d84cb7d05c':
        raise RefreshError('current_active_57_7_identity_changed')
    motor = one(config['carConfigMotorization']['motorization'], 'one_selected_engine_required')
    if motor['carId'] != config['car']['id'] or motor['price'].get('promotions'):
        raise RefreshError('selected_cash_price_or_promotion_changed')
    row = packet('Toyota', 'bZ4X', variant, payload['source'])
    for field in ['wltp_range_km', 'wltp_consumption_kwh_100km', 'battery_kwh', 'drivetrain', 'tow_kg', 'seats']:
        proof = extracted['extraction_payload']['field_evidence'][field]
        add(row, field, extracted[field], extracted['source_quote'] + ' | ' + proof['source_pointer'] + ' = ' + proof['quote'],
            payload, 'selected_manufacturer_config', source_pointer=proof['source_pointer'], raw_value=proof['raw_value'],
            manufacturer_variant_id=motor['carId'], conversion=proof['conversion'])
    charge = literal(document, 'Ombordladdare 11 kW AC och kapacitet för snabbladdning 150 kW DC')
    equipment = [item for item in config['specs']['standardEquipment'] if item['name'] == charge]
    if len(equipment) != 1:
        raise RefreshError('charging_must_be_selected_standard_equipment')
    add(row, 'ac_charge_kw', 11, charge, payload, 'selected_standard_ac_not_charge_duration')
    add(row, 'dc_charge_kw', 150, charge, payload, 'selected_standard_dc_peak_not_duration')
    quote = literal(model, 'Den långa hjulbasen ger ett generöst benutrymme medan det stora bagageutrymmet erbjuder 452 liters lastkapacitet.')
    add(row, 'boot_liters', 452, quote, support, 'model_rear_boot_seats_up')
    model_fact(row, 'SUV', literal(model, 'En elegant SUV'), support)
    price(row, extracted['price_sek'], extracted['source_quote'] + ' | selected price.cash=' + str(extracted['price_sek']) +
          ' | price.exclVat=' + str(motor['price']['exclVat']) + ' | promotions=[]')
    return [row]


def extract_polestar(payloads, model):
    key = 'p' + model
    payload = payloads[key]
    document = checked(payload, SOURCES[key])
    title = one(one(document.nodes('head'), 'unique_page_head_required').nodes('title'), 'unique_page_title_required').text()
    if 'Polestar ' + model not in title or model == '4' and 'coupé' not in title:
        raise RefreshError('exact_model_body_page_required')
    table = one((table for table in document.nodes('table')
                 if [h.text() for h in table.nodes('th')] == SCOPES[model]
                 and 'Pris från' in table.text()), 'exact_drivetrain_table_required')
    rows = {}
    for tr in table.nodes('tr'):
        cells = list(tr.nodes('td'))
        if not cells:
            continue
        if len(cells) != len(SCOPES[model]) or any(c.attrs.get('colspan', '1') != '1' for c in cells):
            raise RefreshError('technical_table_shape_changed')
        labels = [one(c.nodes('label'), 'cell_label_required').text() for c in cells]
        if len(set(labels)) != 1 or labels[0] in rows:
            raise RefreshError('duplicate_or_mixed_labels')
        rows[labels[0]] = [(c.text()[len(labels[0]):].strip(), c.text()) for c in cells]

    def cell(prefix, index):
        return one((values[index] for label, values in rows.items() if label.startswith(prefix)), 'exact_variant_row_required')

    def definition(prefix):
        term = one((dt for dt in document.nodes('dt') if dt.text().startswith(prefix)), 'unique_definition_required')
        if len(list(term.parent.nodes('dt'))) != 1:
            raise RefreshError('definition_scope_changed')
        return term.parent.text()

    battery = definition('Batterikapacitet' if model == '2' else 'Batteri')
    battery_value = number(battery, r'Batterikapacitet 400 V litiumjonbatteri, ([0-9]+) kWh kapacitet, 27 moduler' if model == '2'
                           else r'Batteri 400-V Litiumjonbatteri ([0-9]+) kWh kapacitet, cell-to-pack, 110 celler')
    dc = one(
        (dt.parent.text() for dt in document.nodes('dt') if dt.text() == 'DC-laddning'), 'exact_dc_not_charge_duration_required')
    dc_value = number(dc, r'DC-laddning Upp till ([0-9]+) kW')
    if model == '2':
        ac = definition('11 kW AC laddningstid')
        ac_value = number(ac, r'([0-9]+) kW AC laddningstid \(3-fas 16A AC\)¹ 0-100 % på 8 timmar')
        boot = definition('Volym (uppfällda säten)')
        boot_value = number(boot, r'Volym \(uppfällda säten\) ([0-9 ]+) liter, inklusive under golvet')
        seating = checked(payloads['p2_seats'], SOURCES['p2_seats'])
        seat_quote = literal(seating, 'Polestar 2 har fem säten.')
        body_doc = checked(payloads['p2_model'], SOURCES['p2_model'])
        body_quote = literal(body_doc, 'En fastback som är designad för körglädje och elektrisk prestanda.')
    else:
        ac = one((dt.parent.text() for dt in document.nodes('dt') if dt.text() == 'AC-laddning'), 'standard_ac_required')
        if ac != 'AC-laddning 11 kW 22 kW (tillval)':
            raise RefreshError('standard_optional_ac_scope_changed')
        ac_value = 11
        # Rear luggage compartment only, not frunk or folded-seat volume.
        boot = literal(document, '526 liters lastkapacitet med uppfällt baksäte, inklusive under lastgolvet')
        boot_value = 526
        seating = checked(payloads['p4_seats'], SOURCES['p4_seats'])
        seat_quote = literal(seating, 'Båda bilarna är rymliga, med gott om plats för fem personer och deras bagage')
        body_quote = literal(seating, 'Polestar 4 är en SUV-coupé')
    result = []
    for index, variant in enumerate(SCOPES[model]):
        row = packet('Polestar', model, variant, payload['source'])
        for field, value, quote, scope in [('battery_kwh', battery_value, battery, 'model_gross_battery'),
                ('dc_charge_kw', dc_value, dc, 'model_peak_dc'), ('ac_charge_kw', ac_value, ac, 'model_standard_ac'),
                ('boot_liters', boot_value, boot, 'model_rear_boot_seats_up')]:
            add(row, field, value, quote, payload, scope)
        p, p_quote = cell('Pris från', index)
        price(row, int(number(p, r'([0-9 ]+) kr')), variant + ' | ' + p_quote)
        drive, drive_quote = cell('Drivlina', index)
        if drive not in ('Bakhjulsdrift', 'Fyrhjulsdrift'):
            raise RefreshError('unknown_drivetrain')
        add(row, 'drivetrain', drive, drive_quote, payload, 'exact_variant_column', column_header=variant)
        tow, tow_quote = cell('Dragvikt' if model == '2' else 'Dragkraft', index)
        add(row, 'tow_kg', int(number(tow, r'Upp till ([0-9 ]+) kg')), tow_quote, payload, 'exact_variant_column', column_header=variant)
        energy, energy_quote = cell('Energikonsumtion (WLTP)', index)
        match = re.fullmatch(r'([0-9]+,[0-9]+)[–-]([0-9]+,[0-9]+) kWh/100 km', energy)
        if not match:
            raise RefreshError('explicit_consumption_interval_required')
        low, high = [float(v.replace(',', '.')) for v in match.groups()]
        add(row, 'wltp_consumption_kwh_100km', low, energy_quote, payload, 'exact_variant_wltp_interval_lower_bound',
            column_header=variant, interval=[low, high], qualification='Tillverkarens WLTP-intervall; kalkylen använder det lägre värdet.')
        distance, distance_quote = cell('Räckvidd', index)
        add(row, 'wltp_range_km', int(number(distance, r'(?:Upp till )?([0-9]+) km')), distance_quote, payload,
            'exact_variant_wltp' if model == '2' else 'manufacturer_wltp_target', column_header=variant)
        if model == '4' and variant == 'Rear motor':
            manual_payload = payloads['p4_wltp']
            manual = checked(manual_payload, SOURCES['p4_wltp'])
            literal(manual, 'Detta är de certifierade värdena för bilens räckvidd och användning av elektrisk energi.')
            certified = one((t for t in manual.nodes('table') if t.text().startswith('Bakre motor 20-tumsdäck ')),
                            'rear_motor_certified_table_required')
            quote = one((tr.text() for tr in certified.nodes('tr') if tr.text().startswith('20-tumsdäck ')), 'standard_20_inch_required')
            if quote != '20-tumsdäck 620 17,8':
                raise RefreshError('certified_wheel_facts_changed')
            add(row, 'wltp_range_km', 620, 'Bakre motor | ' + quote, manual_payload, 'certified_rear_motor_20_inch',
                alias_basis='Rear motor = Bakre motor; standard 20-tums Aero', column_header=variant)
        add(row, 'seats', 5, seat_quote, payloads[key + '_seats'], 'exact_model_seating')
        model_fact(row, 'Fastback' if model == '2' else 'SUV', body_quote,
                   payloads['p2_model'] if model == '2' else payloads['p4_seats'])
        result.append(row)
    return result


def collect(output):
    output.mkdir(parents=True, exist_ok=True)
    fetcher = SourceFetcher(timeout=25, document_parser=lambda body, _kind: body)
    payloads = {}
    for key, url in SOURCES.items():
        response = fetcher.fetch(url, {'Toyota' if key.startswith('toyota') else 'Polestar'})
        if response.get('status') != 'reachable' or response['final_url'] != url:
            raise RefreshError('source_unavailable:' + key + ':' + response.get('status', 'unknown'))
        body = response['document']
        preflight_hash = response['content_hash']
        if key == 'toyota':
            try:
                config_from_document(parse_document(body, 'text/html'))
            except RefreshError:
                rendered = output / 'toyota-rendered.html'
                subprocess.run(['node', 'scripts/render_toyota_specs.mjs', str(rendered.resolve())], check=True, timeout=90)
                body = rendered.read_bytes()
        source = dict(status='reachable', http_status=200, final_url=url,
                      content_hash=hashlib.sha256(body).hexdigest(), fetched_at=datetime.now(timezone.utc).isoformat())
        if key == 'toyota':
            source['http_preflight_hash'] = preflight_hash
        payloads[key] = {'source': source, 'body': body.decode('utf-8')}
        (output / (key + '-source.json')).write_text(json.dumps(payloads[key], ensure_ascii=False) + '\n', encoding='utf-8')
    drafts = extract_toyota(payloads) + extract_polestar(payloads, '2') + extract_polestar(payloads, '4')
    if len(drafts) != 6 or any(len(row['facts']) != 9 for row in drafts):
        raise RefreshError('six_complete_profiles_required')
    intake = dict(adapter=ADAPTER, drafts=drafts, held=[], database_writes=0, paid_calls=0)
    (output / 'intake.json').write_text(json.dumps(intake, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'drafts': len(drafts), 'technical_facts': 54, 'prices': 6, 'paid_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    collect(parser.parse_args().output)
