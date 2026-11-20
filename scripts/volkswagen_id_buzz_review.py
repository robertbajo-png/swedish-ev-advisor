"""Prepare a private ID. Buzz evidence packet; has no database or publisher access."""

import argparse
import hashlib
import io
import json
import re
import subprocess
import tempfile
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from audit_catalog_sources import ROOT, SourceFetcher
from volkswagen_id_buzz_preflight import (CHARGING_URL, MODEL_URL, TECHNICAL_URL, capture, capture_charging,
                                        charging_pages, match_once, source_allowed)

DEALER = 'https://mollerbil.se/erbjudanden/id-buzz-pro-sweden-olympic-edition'
AUTHORIZATION = ('https://www.volkswagen-transportbilar.se/sv/om-oss/transportmagasinet/foretag-och-forare/'
                 'anpassa-transportbilen-efter-dina-behov.html')
FINNISH_PDF = 'https://api.k-auto.fi/priceCatalog/api/PriceCatalog/d1c60397-8685-48d3-b954-e08eb0b50361'
PHOTO_PAGE = 'https://commons.wikimedia.org/wiki/File:VW_ID._Buzz_Pro_%E2%80%93_f_25012026.jpg'
PHOTO_HASH = '00832a4a6a37ac1f8f88f2d2ea3a02ba3127638529184f517be224930e0f3f7d'
MARKET_URL = ('https://mobilitysweden.se/storage/7F74570C4C61BEEEE06275646A852419323F77478AF198119E0CBBAF30A0A566/'
              'fd0832463d834757a568dc0f5a132daf/xlsx/media/cb12796565d84cb9abeedfe6d78e7b7e/'
              'M%C3%A5nadsrapport%20Nyregistreringar%20okt%202026.xlsx')
TRIMS = {'Pro': 'EBBR7R', 'Pro 4MOTION': 'EBBR5R'}
SOURCE_SCOPES = {
    MODEL_URL: ('SE', 'sv', 'manufacturer', 'Swedish model cards and battery family'),
    TECHNICAL_URL: ('SE', 'sv', 'manufacturer', 'Swedish towing and body dimensions'),
    DEALER: ('SE', 'sv', 'authorized_dealer', 'Named dealer cash offers only'),
    AUTHORIZATION: ('SE', 'sv', 'manufacturer', 'Dealer authorization only'),
    FINNISH_PDF: ('FI', 'fi', 'manufacturer', 'Matching charging hardware only'),
    CHARGING_URL: ('FR', 'fr', 'manufacturer', 'Matching charging hardware only'),
}


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def read_dealer_offer(text, authorization, today):
    auth = ' '.join(authorization.split())
    permission = match_once(
        r'M\u00f6ller Bil V\u00e4ster\u00e5s Ort:\s*V\u00e4ster\u00e5s\. Verksamhet:\s*Auktoriserad '
        r'\u00e5terf\u00f6rs\u00e4ljare och fullserviceverkstad f\u00f6r Volkswagen Transportbilar\.',
        auth, 'exact_dealer_authorization_required',
    )[0]
    compact = ' '.join(text.split())
    short_prices = {}
    starts = []
    for trim in TRIMS:
        amount = match_once(rf'ID\. Buzz {trim} Sweden Olympic Edition 5-sits pris fr\u00e5n '
                            r'([1-9]\d{2} \d{3}) kr inkl\. moms\b', compact,
                            f'exact_five_seat_dealer_price_required: {trim}')
        short_prices[trim] = {'value': int(amount[1].replace(' ', '')), 'quote': amount[0]}
        starts.append(amount.end())
    expiry = match_once(r'Erbjudandet g\u00e4ller tom (\d{2})/(\d{2}) (20\d{2})\b', compact,
                        'single_offer_expiry_required')
    until = date(int(expiry[3]), int(expiry[2]), int(expiry[1]))
    if max(starts) >= expiry.start() or expiry.start() - min(starts) > 800 or not 0 <= (until - today).days <= 180:
        raise ValueError('expired_or_unbound_dealer_offer')
    return {'authorization_quote': permission, 'expiry_quote': expiry[0],
            'price_valid_until': until.isoformat(), 'prices': short_prices}


def finnish_pages(body, content_type):
    from pypdf import PdfReader
    if 'pdf' not in content_type or not body.startswith(b'%PDF'):
        raise ValueError('finnish_primary_pdf_required')
    pdf = PdfReader(io.BytesIO(body))
    return '\f'.join(pdf.pages[i].extract_text(extraction_mode='layout') for i in (1, 3))


def read_finnish_hardware(text):
    table, separator, equipment = text.partition('\f')
    compact = ' '.join(table.split())
    if not separator or 'Pvm 18.6.2026' not in compact or 'Maahantuoja: K Auto Oy' not in compact:
        raise ValueError('finnish_importer_or_revision_changed')
    match_once(r'KOODI MALLI Istuinpaikka.*?Lataus-teho CO2.*?netto/brutto kW Vapaa', compact,
               'finnish_dc_column_context_required')
    plus = re.search(r'(?m)^PRO\+\s*\n(.*?)(?=^GTX\s*$|\Z)',
                     '\n'.join(' '.join(row.split()) for row in table.splitlines()), flags=re.S)
    if not plus or not re.search(r'(?m)^\s*ID\.BUZZ PRO\+\s*$', equipment):
        raise ValueError('finnish_pro_plus_context_required')
    ac = match_once(r'11 kW AC-latausteho\s+Vakiovaruste', equipment, 'finnish_standard_ac_required')
    results = {}
    for code, kw, hp, suffix in (('EBBR7R', 210, 286, ''), ('EBBR5R', 250, 340, ' 4Motion')):
        row = match_once(rf'(?m)^{code} ID\.Buzz {kw}kW PRO\+ 79 kWh{suffix} 5 \d{{2}}(?:\.\d)? '
                         rf'{kw}/{hp} 79/84 kWh \d{{3}} (\d{{3}})(?= 0 )', plus[1],
                         f'finnish_exact_hardware_required: {code}')
        results[code] = {'dc_charge_kw': int(row[1]), 'ac_charge_kw': 11,
                         'dc_quote': row[0], 'ac_quote': ' '.join(ac[0].split())}
    return results


def capture_support():
    def read(url, content_type, parser=None):
        policy = lambda candidate, brands: candidate == url and brands == {'Volkswagen'}
        source = SourceFetcher(timeout=12, max_bytes=16 * 1024 * 1024, url_policy=policy,
                               text_parser=parser).fetch(url, {'Volkswagen'})
        text = source.get('text', '')
        if (source.get('status') != 'reachable' or source.get('http_status') != 200 or source.get('final_url') != url
                or content_type not in source.get('content_type', '') or not text
                or source.get('text_hash') != sha256(text.encode('utf-8'))
                or not re.fullmatch(r'[a-f0-9]{64}', source.get('content_hash', ''))):
            raise ValueError(f'private_review_source_held: {url} ({source.get("status")})')
        proof = {key: source[key] for key in ('content_hash', 'text_hash', 'http_status')}
        proof['fetched_at'] = datetime.now(timezone.utc).isoformat()
        return proof, text

    sources, texts = {}, {}
    for url, kind, parser in ((DEALER, 'html', None), (AUTHORIZATION, 'html', None), (FINNISH_PDF, 'pdf', finnish_pages)):
        sources[url], texts[url] = read(url, kind, parser)
    dealer = read_dealer_offer(texts[DEALER], texts[AUTHORIZATION], datetime.now(timezone.utc).date())
    return sources, texts, dealer, read_finnish_hardware(texts[FINNISH_PDF])


def build_review(swedish, configurations, french, finnish, dealer):
    if swedish.get('publication_approved') is not False or french.get('publication_approved') is not False:
        raise ValueError('private_evidence_required')
    cards = {row['trim']: row for row in swedish['variants']}
    config = {row['trim']: row for row in configurations}
    french_codes = {row['model_code']: row for row in french['variants']}
    if (len(swedish['variants']) != 2 or len(configurations) != 2 or len(french['variants']) != 2
            or cards.keys() != TRIMS.keys() or config.keys() != TRIMS.keys() or dealer['prices'].keys() != TRIMS.keys()
            or set(french_codes) != set(TRIMS.values()) or set(finnish) != set(TRIMS.values())):
        raise ValueError('exact_two_version_evidence_required')

    def evidence(item, url):
        return {**item, 'source_url': url}

    variants = []
    for trim, code in TRIMS.items():
        card = cards[trim]['observations']
        actual = config[trim]
        if actual['motor_id'] != code or (actual['model_year'], actual['seats'], actual['wheelbase_mm']) != (2027, 5, 2989):
            raise ValueError('variant_identity_mismatch')
        spec = actual['summary']['observations']
        summary = actual['summary']['final_url']
        cash = dealer['prices'][trim]
        if not cash['value'] == spec['configured_cash_price_sek_including_vat']['value'] == card['cash_from_sek']['value']:
            raise ValueError(f'dealer_cash_differs_from_exact_configuration: {trim}')

        ac, dc = finnish[code]['ac_charge_kw'], finnish[code]['dc_charge_kw']
        local_dc = swedish['swedish_dc_claim']
        if (ac != french_codes[code]['ac_charge_kw'] or dc != local_dc['value']
                or local_dc['battery_net_kwh'] != card['battery_net_kwh']['value']):
            raise ValueError(f'charging_sources_need_further_review: {trim}')
        tow = swedish['technical_observations']['braked_towing_12pct_kg'][trim]
        cargo = (card.get('cargo_five_seats_liters') if trim == 'Pro 4MOTION'
                 else swedish['technical_observations']['short_pro_cargo_row_two_liters'])
        facts = {
            'wltp_range_km': evidence(spec['configured_wltp_range_km'], summary),
            'wltp_consumption_kwh_100km': evidence(spec['configured_wltp_consumption_kwh_100km'], summary),
            'tow_kg': evidence(tow, TECHNICAL_URL),
            'boot_liters': evidence(cargo, MODEL_URL if trim == 'Pro 4MOTION' else TECHNICAL_URL),
            'dc_charge_kw': evidence({'value': dc, 'quote': local_dc['quote'],
                                      'corroboration': evidence({'value': dc, 'quote': finnish[code]['dc_quote']}, FINNISH_PDF),
                                      'alternative': evidence({'value': french_codes[code]['dc_charge_kw'],
                                                               'quote': french_codes[code]['quote']}, CHARGING_URL)}, MODEL_URL),
            'ac_charge_kw': evidence({'value': ac, 'quote': french_codes[code]['quote'],
                                      'corroboration': evidence({'value': ac, 'quote': finnish[code]['ac_quote']}, FINNISH_PDF)}, CHARGING_URL),
            'battery_kwh': evidence(card['battery_net_kwh'], MODEL_URL),
            'seats': evidence(card['seats_standard'], MODEL_URL),
            'drivetrain': evidence(card['drivetrain'], MODEL_URL),
        }
        variants.append({'trim': trim, 'model_code': code, 'configuration_id': actual['configuration_id'],
                         'facts': facts, 'observed_configurator_tow': evidence(spec['configured_braked_towing_kg'], summary),
                         'price': evidence({**cash, 'price_type': 'dealer_offer', 'scope': 'Moller Bil only',
                                            'price_valid_until': dealer['price_valid_until'], 'expiry_quote': dealer['expiry_quote'],
                                            'authorization': evidence({'quote': dealer['authorization_quote']}, AUTHORIZATION),
                                            'manufacturer_base_cash': evidence(spec['configured_cash_price_sek_including_vat'], summary)}, DEALER)})
    return {'status': 'needs_review', 'publication_approved': False, 'database_writes': 0, 'paid_calls': 0,
            'brand': 'Volkswagen', 'model': 'ID. Buzz', 'market': 'SE', 'variants': variants,
            'remaining': ['approved_image_registration', 'mixed_source_metadata_and_model_scoped_publication_adapter']}


def photo_receipt(photo, root):
    if photo.is_symlink():
        raise ValueError('local_original_photo_required')
    path = photo.resolve(strict=True)
    if path.parent.parent != root or not path.parent.name.startswith('volkswagen-id-buzz-photo-'):
        raise ValueError('local_original_photo_required')
    body = path.read_bytes()
    if not body.startswith(b'\xff\xd8\xff') or sha256(body) != PHOTO_HASH:
        raise ValueError('reviewed_original_photo_changed')
    return {'source_url': PHOTO_PAGE, 'content_sha256': PHOTO_HASH, 'credit': 'M 93 / Wikimedia Commons',
            'license_id': 'CC BY-SA 3.0 DE',
            'license_url': 'https://creativecommons.org/licenses/by-sa/3.0/de/deed.en',
            'label': 'Model image; not the Olympic Edition or a manufacturer press photo.', 'registered': False}


def capture_market(folder):
    from import_mobility_sweden import parse_elbil_ranking
    fetcher = SourceFetcher(timeout=30, max_bytes=14000000, url_policy=lambda url, _brands: url == MARKET_URL,
                           document_parser=lambda body, _kind: body, text_parser=lambda _body, _kind: '')
    result = fetcher.fetch(MARKET_URL, set())
    if (result.get('status') != 'reachable' or result.get('final_url') != MARKET_URL or result.get('http_status') != 200
            or not result.get('document', b'').startswith(b'PK\x03\x04')
            or result.get('content_hash') != sha256(result['document'])):
        raise ValueError(f'market_workbook_held: {result.get("status")}')
    path = folder / 'mobility-october.xlsx'
    path.write_bytes(result['document'])
    rows, _ = parse_elbil_ranking(path, MARKET_URL)
    exact = [asdict(row) for row in rows if (row.brand_raw, row.model_raw, row.fuel_type_raw) == ('VW', 'ID. BUZZ', 'EL')]
    if len(exact) != 1 or exact[0]['needs_mapping'] or exact[0]['last_seen_month'] != '2026-10-01':
        raise ValueError('exact_october_passenger_bev_market_row_required')
    source = {key: result[key] for key in ('status', 'http_status', 'final_url', 'content_hash')}
    source['fetched_at'] = datetime.now(timezone.utc).isoformat()
    return {'source': source, 'row': exact[0], 'sheet': 'Elbil ranking', 'workbook_file': path.name}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configurator', required=True)
    parser.add_argument('--photo', type=Path, required=True)
    parser.add_argument('--include-market', action='store_true')
    args = parser.parse_args()
    root = (ROOT / 'data/local/release-data').resolve(strict=True)
    if not root.is_relative_to(ROOT.resolve()) or any(re.fullmatch(r'onedrive(?:commercial|consumer)?', x, re.I) for x in root.parts):
        raise ValueError('unexpected_evidence_directory')
    photo = photo_receipt(args.photo, root)
    config_capture = Path(args.configurator).resolve(strict=True)
    configs = json.loads(subprocess.check_output(['node', 'scripts/volkswagen_id_buzz_configurator.mjs', '--replay',
                                                 str(config_capture)], cwd=ROOT, encoding='utf-8', timeout=45))
    swedish, texts = capture(SourceFetcher(timeout=12, url_policy=source_allowed))
    france = SourceFetcher(timeout=18, max_bytes=16 * 1024 * 1024, text_parser=charging_pages,
                           url_policy=lambda url, brands: url == CHARGING_URL and brands == {'Volkswagen'})
    french, fr_text = capture_charging(france)
    more_sources, more_texts, dealer, finnish = capture_support()
    report = build_review(swedish, configs, french, finnish, dealer)
    sources = {**swedish['sources'], **more_sources, CHARGING_URL: french}
    all_texts = {**texts, **more_texts, CHARGING_URL: fr_text}
    out = Path(tempfile.mkdtemp(prefix='volkswagen-id-buzz-review-', dir=root))
    receipts = {}
    for index, (url, text) in enumerate(all_texts.items(), 1):
        filename = f'source-{index}.txt'
        (out / filename).write_bytes(text.encode('utf-8'))
        country, language, authority, scope = SOURCE_SCOPES[url]
        receipts[url] = {**{k: sources[url][k] for k in ('content_hash', 'text_hash', 'fetched_at')}, 'text_file': filename,
                         'country': country, 'language': language, 'authority': authority, 'scope': scope}
    report.update(sources=receipts, configurations=configs, configurator_capture=config_capture.name, photo=photo)
    if args.include_market:
        report['market'] = capture_market(out)
    (out / 'review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out), 'variants': len(report['variants']), 'status': report['status'],
                      'market_captured': 'market' in report, 'publication_approved': False, 'database_writes': 0, 'paid_calls': 0}))


if __name__ == '__main__':
    main()
