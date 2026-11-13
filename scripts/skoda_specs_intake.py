"""Exact-edition Skoda facts with explicit, traceable source adjudication."""
import argparse
import hashlib
import io
import json
import re
import pdfplumber
from datetime import datetime, timezone
from pathlib import Path

from audit_catalog_sources import ROOT, SourceFetcher
from variant_refresh import RefreshError, one, parse_document

ADAPTER = 'skoda_sweden_model_page_v1'
TECHNICAL_RELEASE = 'https://www.skoda.se/nyheter-och-pressklipp/nyhet/skoda-uppdaterar-elroq-och-enyaq-infor-modellar-2027'
SOURCES = {model: 'https://www.skoda.se/modeller/' + model.lower() + '/' + model.lower()
           for model in ('Elroq', 'Enyaq')}
SCOPES = {
    'Elroq': [engine + ' ' + trim + ' Explore Edition' for engine in ('60', '85', '85x')
              for trim in ('Selection', 'Sportline')] + ['RS Explore Edition'],
    'Enyaq': ['Solid Edition 85', 'Solid Edition 85x', 'Solid Edition 85x Sportline', 'Solid Edition RS'],
}
PRICE_SOURCES = {
    'Elroq': 'https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb',
    'Enyaq': 'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660',
}


def clean(text):
    return re.sub(r'\s+([:.,])', r'\1', text)


def faq(main, question):
    heading = one((node for node in main.nodes('h3') if node.text() == question), 'unique_exact_faq_question_required')
    region = heading.parent
    if len(list(region.nodes('h3'))) != 1 or 'accordion-item' not in region.attrs.get('class', '').split():
        raise RefreshError('faq_scope_changed')
    return region


def extract(payload, variant_name, support=None, price_support=None):
    support = support or payload.get('technical_support')
    model, source, body = payload['model'], payload['source'], payload['body'].encode('utf-8')
    if (model not in SOURCES or variant_name not in SCOPES[model] or source.get('final_url') != SOURCES[model]
            or source.get('status') != 'reachable' or source.get('http_status') != 200
            or hashlib.sha256(body).hexdigest() != source.get('content_hash')):
        raise RefreshError('exact_current_swedish_model_source_required')
    document = parse_document(body, 'text/html')
    main = one(document.nodes('main'), 'unique_model_main_required')
    edition = 'Explore Edition' if model == 'Elroq' else 'Solid Edition'
    heading = one(main.nodes('h1'), 'unique_model_heading_required').text()
    if heading != model + ' ' + edition or 'modellår 2027' not in main.text():
        raise RefreshError('exact_edition_and_model_year_required')
    paragraphs = [node.text() for node in main.nodes('p')]
    facts, evidence = {}, {}

    def paragraph(pattern):
        return one((text for text in paragraphs if re.fullmatch(pattern, text)), 'missing_or_ambiguous_model_fact')

    def add(field, value, quote, scope):
        facts[field] = value
        evidence[field] = dict(value=value, quote=quote, scope=scope, model_heading=heading,
            variant_name=variant_name, source_url=source['final_url'], source_hash=source['content_hash'])

    boot = paragraph(r'Trots sin kompakta storlek har Elroq ett stort bagageutrymme på [0-9]+ liter .*' if model == 'Elroq'
                     else r'Stort bagageutrymme på [0-9]+ liter .*')
    add('boot_liters', int(re.search(r'bagageutrymme på ([0-9]+) liter', boot)[1]), boot, 'model_rear_boot_seats_up')
    drive = paragraph(re.escape('Elroq erbjuds med flera batteristorlekar och med olika drivlinor:') + r'.*' if model == 'Elroq'
                      else r'Vår populära Enyaq erbjuds som 85 och fyrhjulsdrivna 85x,.*')
    if '85x' in variant_name or 'RS' in variant_name:
        if 'fyrhjulsdrivna 85x' not in drive or model == 'Elroq' and 'Elroq RS får du hela 340 Hk och fyrhjulsdrift.' not in drive:
            raise RefreshError('explicit_drivetrain_scope_required')
        add('drivetrain', 'AWD', drive, 'explicit_engine_drivetrain')
    energy = paragraph(r'Batterikapacitet på [0-9]+ kWh ger en räckvidd på upp till [0-9]+ km för Elroq 85\. Snabbladda 10 till 80% på cirka [0-9]+ minuter \(max [0-9]+ kW DC\) med Elroq 85 och 85x\.' if model == 'Elroq'
                       else r'Batterikapacitet på [0-9]+ kWh ger upp till [0-9]+ km räckvidd\. Ladda 10-80% på [0-9]+ minuter med en maxeffekt på [0-9]+ kW \(DC\)\.')
    base85 = variant_name.startswith('85 ') if model == 'Elroq' else variant_name == 'Solid Edition 85'
    if base85:
        if model == 'Enyaq' and 'Enyaq 85 Solid Edition' not in main.text():
            raise RefreshError('base_85_identity_required')
        add('battery_kwh', int(re.search(r'Batterikapacitet på ([0-9]+) kWh', energy)[1]), energy, 'explicit_base_85_battery')
    if base85 or model == 'Elroq' and variant_name.startswith('85x '):
        add('dc_charge_kw', int(re.search(r'(?:max |maxeffekt på )([0-9]+) kW', energy)[1]), energy, 'explicit_85_dc_scope')
    if model == 'Enyaq':
        seats = paragraph(r'Enyaq har fem sittplatser och ett bagageutrymme på [0-9]+ liter \. Den har en räckvidd på upp till [0-9]+ km enligt WLTP \.')
        add('seats', 5, seats, 'model_seating')
    else:
        views = [json.loads(node.attrs['data-props'])['viewModel'] for node in main.nodes('div')
                 if node.attrs.get('data-module') == 'model-character-gallery']
        view = one((view for view in views if view.get('primaryHeadline') == 'Bagageutrymme'), 'exact_model_gallery_required')
        seats = one((item['body'] for item in view['primaryItems'] if re.fullmatch(
            r'När baksätets ryggstöd förblir upprättstående finns det 470 liters bagageutrymme för upp till fem passagerare\.', item.get('body', ''))), 'literal_model_seating_required')
        add('seats', 5, seats, 'model_gallery_seating')
    range_question = 'Hur lång räckvidd har ' + model + '?'
    region = faq(main, range_question)
    if model == 'Elroq':
        engine = variant_name.split()[0]
        label = 'Elroq Sportline ' + engine if 'Sportline' in variant_name else 'Elroq ' + ('85 och 85x' if engine in ('85', '85x') else engine)
    else:
        engine = 'RS' if 'RS' in variant_name else '85x' if '85x' in variant_name else '85'
        label = 'Enyaq 85x Sportline' if 'Sportline' in variant_name else 'Enyaq RS' if engine == 'RS' else 'Enyaq 85 och Enyaq 85x'
    row = one((node.text() for node in region.nodes('li') if clean(node.text()).startswith(label + ':')), 'exact_wltp_engine_row_required')
    value = re.fullmatch(re.escape(label) + r': upp till ([0-9]+) km\.', clean(row))
    if not value or 'WLTP' not in region.text():
        raise RefreshError('qualified_wltp_value_required')
    add('wltp_range_km', int(value[1]), row, 'faq_variant_wltp')
    evidence['wltp_range_km']['question'] = range_question
    evidence['wltp_range_km']['engine_label'] = label
    evidence['wltp_range_km']['qualification'] = 'WLTP, upp till; versionens angivna standardutförande'
    charge_question = 'Hur snabbt kan ' + model + ' laddas?'
    charge = faq(main, charge_question)
    if model == 'Elroq':
        prefix = 'Elroq 60:' if engine == '60' else 'Elroq 85, 85x och RS:'
        dc = one((node.text() for node in charge.nodes('li') if clean(node.text()).startswith(prefix) and 'maximal laddeffekt' in node.text()), 'exact_dc_engine_row_required')
        dc_match = re.search(r'maximal laddeffekt på ([0-9]+) kW', dc)
    else:
        dc = one((node.text() for node in charge.nodes('p') if node.text().startswith('Snabbladdning (DC):')), 'exact_dc_group_required')
        dc_match = re.search(r'maximal DC-laddeffekt på ([0-9]+) kW', dc)
    if not dc_match:
        raise RefreshError('literal_dc_power_required')
    add('dc_charge_kw', int(dc_match[1]), dc, 'faq_variant_dc')
    evidence['dc_charge_kw']['question'] = charge_question
    evidence['dc_charge_kw']['selection_reason'] = 'Versionsuppdelad FAQ för aktuell utgåva prioriteras framför generisk ingress och tidigare prislistas utrustningsdel.'
    ac = one((node.text() for node in charge.nodes('p') if re.search(r'kan laddas med upp till [0-9]+ kW AC', node.text())), 'literal_ac_power_required')
    add('ac_charge_kw', int(re.search(r'upp till ([0-9]+) kW AC', ac)[1]), ac, 'faq_model_ac')
    evidence['ac_charge_kw']['question'] = charge_question
    tow_question = 'Hur mycket får ' + model + ' dra?'
    tow = faq(main, tow_question)
    if 'bromsad släpvagn' not in tow.text():
        raise RefreshError('braked_trailer_qualification_required')
    label = ('Elroq 60' if engine == '60' else 'Elroq 85, 85x och RS') if model == 'Elroq' else ('Enyaq RS' if engine == 'RS' else 'Enyaq 85, 85x och 85x Sportline')
    row = one((node.text() for node in tow.nodes('li') if clean(node.text()).startswith(label + ':')), 'exact_towing_engine_row_required')
    match = re.fullmatch(re.escape(label) + r': upp till ([0-9 ]+) kg\.', clean(row))
    if not match:
        raise RefreshError('literal_tow_value_required')
    add('tow_kg', int(match[1].replace(' ', '')), row, 'faq_braked_towing')
    evidence['tow_kg'].update(question=tow_question, engine_label=label, qualification='Bromsad släpvagn; kontrollera det enskilda fordonets registreringsbevis.')
    if not ('85x' in variant_name or 'RS' in variant_name):
        quote = paragraph(r'Elroq 60 och 85 har bakhjulsdrift\.' if model == 'Elroq' else r'Enyaq 85 har en elmotor på [0-9]+ hk och bakhjulsdrift\.')
        add('drivetrain', 'RWD', quote, 'explicit_engine_drivetrain')
    else:
        quote = paragraph('Ja, ' + model + r' 85x, 85x Sportline och RS har fyrhjulsdrift.*')
        add('drivetrain', 'AWD', quote, 'explicit_engine_drivetrain')
    supporting = []
    if support:
        technical = parse_document(support['body'].encode('utf-8'), 'text/html')
        header = one((node for node in technical.nodes('h3') if node.text().startswith(model + ' ' + engine + ' ')), 'exact_model_year_engine_required')
        quote = header.parent.text()
        match = re.search(r'Batterikapacitet \([Bb]rutto/netto\) \[kWh\] ([0-9]+)\s*/\s*([0-9]+)', quote)
        if not match or hashlib.sha256(support['body'].encode('utf-8')).hexdigest() != support['source']['content_hash']:
            raise RefreshError('exact_gross_net_battery_evidence_required')
        add('battery_kwh', int(match[2]), quote, 'my2027_engine_net_battery')
        evidence['battery_kwh'].update(source_url=support['source']['final_url'], source_hash=support['source']['content_hash'],
            qualification='Nettokapacitet; brutto och netto hålls isär.', engine_label=model + ' ' + engine)
        supporting.append(support['source'])
    held = {}
    description = one((node.attrs['content'] for node in document.nodes('meta') if node.attrs.get('name') == 'description'), 'exact_model_description_required')
    if not description.startswith('Upptäck Škoda ' + model + ', ') or 'el-SUV' not in description:
        raise RefreshError('literal_model_body_type_required')
    if price_support:
        page, tables = price_support['page'], price_support['tables']
        title = 'Škoda ' + model + ' ' + edition
        if not page.startswith(title + '\nPrislista ') or '*Värde gäller för motor i grundutförande.' not in page:
            raise RefreshError('exact_edition_price_table_required')
        label = '85x Sportline' if model == 'Enyaq' and 'Sportline' in variant_name else engine
        row = one((row for row in tables[0] if row[0] == label), 'exact_engine_consumption_row_required')
        if len(row) != 8 or not re.fullmatch(r'[1-4][0-9]{2}', row[3]):
            raise RefreshError('consumption_table_shape_changed')
        # The price PDF's l/100km header is erroneous. The current model page
        # explicitly declares electric consumption in Wh/km; retain both texts.
        unit = one((node.text() for node in main.nodes('div') if node.attrs.get('data-component') == 'engine-attribute'
                    and 'Elförbrukning, blandad körning' in node.text()), 'electric_consumption_unit_required')
        if 'Wh/km' not in unit:
            raise RefreshError('manufacturer_wh_per_km_corroboration_required')
        quote = title + ' | ' + ' | '.join(row) + ' | *Värde gäller för motor i grundutförande.'
        add('wltp_consumption_kwh_100km', int(row[3]) / 10, quote, 'price_table_engine_standard_consumption')
        evidence['wltp_consumption_kwh_100km'].update(source_url=price_support['source']['final_url'],
            source_hash=price_support['source']['content_hash'], engine_label=label, raw_wh_km=int(row[3]),
            unit_quote=unit, unit_source_url=source['final_url'], unit_source_hash=source['content_hash'],
            qualification='Motor i grundutförande; utrustning och hjul kan påverka förbrukningen.',
            selection_reason='Aktuell versionsprislistas motorvärde; felaktig l/100 km-rubrik korrigeras mot modellens uttryckliga Wh/km-enhet, dividerat med 10 till kWh/100 km.')
        supporting.append(price_support['source'])
    return dict(adapter=ADAPTER, brand='Skoda', model=model, variant_name=variant_name,
        facts=facts, field_evidence=evidence, held_fields=held, extraction_confidence=0.99, source=source,
        model_facts={'body_type': 'SUV'}, model_field_evidence={'body_type': dict(value='SUV', quote=description,
            source_url=source['final_url'], source_hash=source['content_hash'], scope='exact_model_description')},
        supporting_sources=supporting, source_resolution='owner_2026_11_13_exact_current_edition_faq_over_estimated_price_list')


def collect(output):
    output.mkdir(parents=True, exist_ok=True)
    fetcher = SourceFetcher(document_parser=lambda body, _kind: body)
    drafts, held = [], []
    response = fetcher.fetch(TECHNICAL_RELEASE, {'Skoda'})
    if response.get('status') != 'reachable' or response.get('final_url') != TECHNICAL_RELEASE:
        raise RefreshError('fresh_my2027_technical_source_required')
    support = {'body': response['document'].decode('utf-8'), 'source': {name: response[name]
        for name in ('status', 'http_status', 'final_url', 'content_hash')}}
    support['source']['fetched_at'] = datetime.now(timezone.utc).isoformat()
    (output / 'technical-source.json').write_text(json.dumps(support, ensure_ascii=False) + '\n', encoding='utf-8')
    for model, url in SOURCES.items():
        result = fetcher.fetch(url, {'Skoda'})
        if result.get('status') != 'reachable' or result.get('final_url') != url:
            held.append({'model': model, 'reason': 'source_' + result.get('status', 'unknown')})
            continue
        body = result.pop('document')
        source = {name: result[name] for name in ('status', 'http_status', 'final_url', 'content_hash')}
        source['fetched_at'] = datetime.now(timezone.utc).isoformat()
        text = body.decode('utf-8')
        if text.encode('utf-8') != body:
            raise RefreshError('source_encoding_changed')
        payload = {'model': model, 'source': source, 'body': text}
        (output / (model.lower() + '-source.json')).write_text(json.dumps(payload, ensure_ascii=False) + '\n', encoding='utf-8')
        price = fetcher.fetch(PRICE_SOURCES[model], {'Skoda'})
        if price.get('status') != 'reachable' or price.get('final_url') != PRICE_SOURCES[model]:
            raise RefreshError('fresh_current_edition_price_pdf_required')
        pdf_body = price['document']
        price_source = {name: price[name] for name in ('status', 'http_status', 'final_url', 'content_hash')}
        price_source['fetched_at'] = datetime.now(timezone.utc).isoformat()
        with pdfplumber.open(io.BytesIO(pdf_body)) as pdf:
            price_support = {'source': price_source, 'page': pdf.pages[0].extract_text(), 'tables': pdf.pages[0].extract_tables()}
        (output / (model.lower() + '-price-source.pdf')).write_bytes(pdf_body)
        (output / (model.lower() + '-price-source.json')).write_text(json.dumps(price_support, ensure_ascii=False) + '\n', encoding='utf-8')
        for variant in SCOPES[model]:
            try:
                draft = extract(payload, variant, support, price_support)
                if len(draft['facts']) != 9 or draft['held_fields']:
                    raise RefreshError('complete_nine_field_technical_profile_required')
                drafts.append(draft)
            except RefreshError as error:
                held.append({'model': model, 'variant_name': variant, 'reason': str(error)})
    intake = {'adapter': ADAPTER, 'drafts': drafts, 'held': held,
              'excluded': [],
              'database_writes': 0, 'paid_calls': 0}
    (output / 'intake.json').write_text(json.dumps(intake, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'drafts': len(drafts), 'facts': sum(len(row['facts']) for row in drafts), 'held': held, 'paid_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    collect(parser.parse_args().output)
