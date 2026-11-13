"""Reconcile two legacy Explorer profiles with current Swedish MY27.25 offers."""
import argparse
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from audit_catalog_sources import ROOT, SourceFetcher
from manufacturer_embedded_data import ScriptData, unique_object
from variant_refresh import RefreshError, one

ADAPTER = 'ford_explorer_sweden_my2725_v1'
MODEL_URL = 'https://www.ford.se/bilar/personbilar-och-suver/explorer'
PREMIUM_URL = MODEL_URL + '/explorer-premium-edition'
PDF_URL = 'https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/fordsesite/cardocuments/explorer/prislista-explorer-premium-edition.pdf'
OFFERS_URL = 'https://www.ford.se/erbjudanden/privatperson'
CARGO_URL = 'https://www.ford.dk/koeb/kampagner/explorer-og-capri'
SCOPES = [
    ('Explorer RWD 77 kWh', 'RWD', 79, 572, 15.5, 185, 2000, 626000, 549000),
    ('Explorer AWD 79 kWh', 'AWD', 77, 519, 17.3, 175, 2200, 686000, 569000),
]


def normalized(text):
    return re.sub(r'\s+', ' ', text).strip()


def document_data(body):
    parser = ScriptData()
    parser.feed(body.decode('utf-8'))
    values = [json.loads(t, object_pairs_hook=unique_object) for a, t in zip(parser.script_attrs, parser.scripts)
              if a.get('id') == '__NEXT_DATA__' and a.get('type') == 'application/json']
    data = one(values, 'one_public_manufacturer_json_required')
    route = data['props']['pageProps']['page']['layout']['sitecore']['route']
    return route


def extract(pages, premium, offers, cargo, sources, now=None, public_rows=None):
    now = now or datetime.now(timezone.utc)
    expected_urls = {'pdf': PDF_URL, 'premium': PREMIUM_URL, 'offers': OFFERS_URL, 'cargo': CARGO_URL}
    for key, url in expected_urls.items():
        s = sources[key]
        age = (now - datetime.fromisoformat(s['fetched_at'].replace('Z', '+00:00'))).total_seconds()
        if (s['status'] != 'reachable' or s['http_status'] != 200 or s['final_url'] != url
                or not re.fullmatch(r'[a-f0-9]{64}', s['content_hash']) or not -60 <= age <= 900):
            raise RefreshError('fresh_registered_ford_source_required:' + key)
    if len(pages) != 2 or 'Prislista 8- 2026' not in pages[0] or 'MY27.25 - Premium Edition' not in pages[0]:
        raise RefreshError('current_premium_my2725_document_required')
    required = ['Rek. Rek.', 'pris Edition pris', 'Max räckvidd enligt Worldwide Harmonised Light Vehicles Test Procedure (WLTP).',
                'Ink, vit färg, värmepump, dragkrok och AGR-stolar (21" hjul för AWD)']
    if any(text not in pages[0] for text in required):
        raise RefreshError('price_columns_and_equipment_scope_required')
    energy = normalized(pages[1])
    for text in ['11 kW 3-fasladdare (Ombordladdare)', 'Upp till 175 kW DC-snabbladdning (AWD)',
                 'Upp till 185 kW DC-snabbladdning (RWD)',
                 'Dragvikt: LR RWD 2000 kg / LR AWD 2200 kg (MY27.25)']:
        if text not in energy:
            raise RefreshError('current_charging_and_towing_scope_required')
    premium, offers, cargo = map(normalized, (premium, offers, cargo))
    if ('Explorer Premium Edition AWD' not in premium or '5 sittplatser' not in premium
            or 'Explorer Premium Edition finns även som RWD från 549 000 kr.' not in premium):
        raise RefreshError('current_swedish_premium_identity_required')
    campaign = one(re.finditer(r'Explorer Premium Edition AWD PRIVATLEASING Från 5 595 kr/mån\* KAMPANJPRIS Från 569 000 kr .*?ERBJUDANDET GILTIGT TILL (\d{4}-\d{2}-\d{2})', offers),
                   'one_exact_awd_campaign_required')
    deadline = campaign[1]
    shared_deadline = one(re.finditer(r'Erbjudandet giltligt till och med (\d{1,2}) december (\d{4})\.', premium),
                          'one_shared_premium_edition_offer_deadline_required')
    if (deadline != '2026-12-30' or (shared_deadline[1], shared_deadline[2]) != ('30','2026')
            or datetime.fromisoformat(deadline).date() < now.date()):
        raise RefreshError('current_unexpired_awd_campaign_required')
    # The named two-car dimension table, not a generic number near Capri's boot.
    cargo_quote = one(re.finditer(r'Dimensioner Explorer® Capri® Bagagerum (\d+) liter (\d+) liter Bagagerum med sæder lagt ned ([\d.]+) liter ([\d.]+) liter', cargo),
                      'one_named_european_cargo_table_required')
    if cargo_quote.groups() != ('472', '572', '1.460', '1.510'):
        raise RefreshError('explorer_not_capri_cargo_required')
    result = []
    for legacy, drive, battery, wltp, consumption, dc, tow, reference, cash in SCOPES:
        name = f'Explorer Premium Edition {drive} {battery} kWh MY27.25'
        variant = legacy
        if public_rows is not None:
            variant = one((r['variant_name'] for r in public_rows if r['brand'] == 'Ford' and r['model'] == 'Explorer'
                           and r['variant_name'] in (legacy, name)), 'one_existing_ford_identity_required')
        pattern = (rf'Explorer {drive}, Long Range \((\d+) kWh\) Premium Edition (\d+) hk \((\d+) kW\) '
                   r'(\d+) ([\d,]+) 360 kr 2 [\d ]+ kr ([\d ]+) kr ([\d ]+) kr')
        line = one((line.strip() for line in pages[0].splitlines() if line.startswith('Explorer '+drive+',')), 'one_exact_powertrain_price_row_required')
        match = re.fullmatch(pattern, line)
        if not match:
            raise RefreshError('exact_premium_price_row_required')
        values = (int(match[1]), int(match[2]), int(match[3]), int(match[4]), float(match[5].replace(',', '.')),
                  int(match[6].replace(' ', '')), int(match[7].replace(' ', '')))
        if values != (battery, 286 if drive == 'RWD' else 340, 210 if drive == 'RWD' else 250, wltp, consumption, reference, cash):
            raise RefreshError('current_variant_or_prices_changed')
        draft = dict(adapter=ADAPTER, brand='Ford', model='Explorer', variant_name=variant,
                     replacement_variant_name=name, source=sources['pdf'],
                     supporting_sources=[sources[k] for k in ('premium', 'offers', 'cargo')],
                     source_resolution='owner_2026_11_13_current_exact_version_replacement',
                     extraction_confidence=0.99, facts={}, field_evidence={}, held_fields={})
        def add(field, value, quote, scope, key='pdf', page=None):
            s = sources[key]
            draft['facts'][field] = value
            draft['field_evidence'][field] = dict(value=value, quote=quote, scope=scope, variant_name=variant,
                column_header=f'Explorer {drive}, Long Range ({battery} kWh) Premium Edition',
                source_url=s['final_url'], source_hash=s['content_hash'], page=page)
        for field, value in [('wltp_range_km', wltp), ('wltp_consumption_kwh_100km', consumption), ('battery_kwh', battery), ('drivetrain', drive)]:
            add(field, value, line, 'exact_swedish_my2725_premium_row', page=1)
        add('ac_charge_kw', 11, '11 kW 3-fasladdare (Ombordladdare)', 'current_my2725_onboard_ac', page=2)
        add('dc_charge_kw', dc, f'Upp till {dc} kW DC-snabbladdning ({drive})', 'current_swedish_my2725_peak_dc', page=2)
        add('tow_kg', tow, 'Dragvikt: LR RWD 2000 kg / LR AWD 2200 kg (MY27.25)', 'current_swedish_my2725_braked_towing', page=2)
        add('seats', 5, '5 sittplatser', 'current_swedish_electric_explorer', 'premium')
        add('boot_liters', 472, cargo_quote[0], 'european_explorer_named_cargo_table_not_capri', 'cargo')
        # RWD is explicitly included on the same Premium Edition offer page.
        # Bind its shared validity here, never to another model's offer or lease.
        valid_until = deadline
        draft['price_evidence'] = dict(value=cash, reference_price=reference, price_type='campaign_price',
            price_valid_until=valid_until, source_url=PDF_URL, source_hash=sources['pdf']['content_hash'],
            quote='Rek. pris / Rek. Edition pris | '+line, classification='swedish_premium_edition_offer_not_reference_or_leasing',
            campaign_quote=campaign[0] if drive == 'AWD' else shared_deadline[0]+' | Explorer Premium Edition finns även som RWD från 549 000 kr.',
            campaign_source_url=OFFERS_URL if drive == 'AWD' else PREMIUM_URL,
            campaign_source_hash=sources['offers' if drive == 'AWD' else 'premium']['content_hash'])
        draft['model_facts'] = {'body_type': 'SUV'}
        draft['model_field_evidence'] = {'body_type': dict(value='SUV', source_url=PREMIUM_URL,
            source_hash=sources['premium']['content_hash'], quote='Explorer Premium Edition | Car.Tags | Personbilar SUV | El')}
        draft['source_decisions'] = [
            'Replace legacy generic powertrains with the current Swedish MY27.25 Premium Edition pair; keep canonical IDs, retire old URLs to the model catalog.',
            'Use the linked Swedish price list 8, not the old model-page paragraph, older price lists or the Nordic trim maximum.',
            'Swedish MY27.25 DC is RWD 185/AWD 175 kW, even where foreign or historical documents state 183/185.',
            'Swedish MY27.25 towing is RWD 2000/AWD 2200 kg, not the old model year 1000/1200.',
            'Preserve recommended reference prices 626000/686000 as evidence; public Edition offers 549000/569000 remain campaign prices, never lease payments.',
            'RWD is explicitly included on the shared Premium Edition offer page: use that page validity, not another model or a monthly-lease duration. AWD also has its exact dated campaign card.',
            'European Explorer boot is 472 L in the named Danish manufacturer table; never use Capri 572 L, 1460 L with seats folded or cabin storage.',
            'Keep the Danish source locale and the original field evidence. No foreign pricing, consumption, charging or availability is imported.']
        result.append(draft)
    return result


def collect(output):
    output.mkdir(parents=True, exist_ok=True)
    allowed = (MODEL_URL, PREMIUM_URL, PDF_URL, OFFERS_URL, CARGO_URL)
    fetcher = SourceFetcher(timeout=35, document_parser=lambda b, k: b,
                            url_policy=lambda url, brands: url in allowed and brands == {'Ford'})
    packets = {}
    for key, url in [('premium', PREMIUM_URL), ('pdf', PDF_URL), ('offers', OFFERS_URL), ('cargo', CARGO_URL)]:
        r = fetcher.fetch(url, {'Ford'})
        if r.get('status') != 'reachable' or r['final_url'] != url:
            raise RefreshError('ford_source_unavailable:'+key+':'+r.get('status', 'unknown'))
        raw = r.pop('document')
        (output/(key+('.pdf' if key == 'pdf' else '.html'))).write_bytes(raw)
        source = {k:r[k] for k in ('status', 'http_status', 'final_url', 'content_hash')}
        source['fetched_at'] = datetime.now(timezone.utc).isoformat()
        if key == 'pdf':
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                content = [p.extract_text() for p in pdf.pages]
        else:
            content = r['text']
        packets[key] = dict(source=source, content=content)
        if key == 'premium':
            route = document_data(raw)
            car = route['fields']['Car']['fields']
            if (route['name'] != 'explorer premium edition' or car['Documents'][0]['url'] != PDF_URL
                    or car['Button3']['value']['href'] != PDF_URL
                    or not any(t['name'] == 'Personbilar SUV' for t in car['Tags'])):
                raise RefreshError('current_swedish_pdf_discovery_required')
    sources = {key:value['source'] for key,value in packets.items()}
    public_rows = json.loads((ROOT/'public/data/public_ev_variants.json').read_text(encoding='utf-8'))['records']
    drafts = extract(packets['pdf']['content'], *[packets[k]['content'] for k in ('premium','offers','cargo')], sources, public_rows=public_rows)
    for filename, value in [('source-packets.json', packets), ('intake.json', dict(adapter=ADAPTER, drafts=drafts, held=[], database_writes=0, paid_calls=0))]:
        (output/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(drafts=2, technical_facts=18, prices=2, database_writes=0, paid_calls=0)))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output)
