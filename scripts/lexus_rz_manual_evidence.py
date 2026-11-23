"""Read the reviewed Swedish Lexus RZ handbook, never foreign tow values."""

import re
from io import BytesIO

from lexus_rz_review import digest


MANUAL_URL = (
    'https://customerportal.tweddle-aws.eu/content?id=16f0e745-02b7-40d0-a66c-119fa5d245f7'
    '&topicId=6ffb4817-75e3-46e8-932b-8ab5909d2c79&publicationType=OM'
)
MANUAL_SHA256 = 'a936c7038ddd8626138e40036736498e50802c2ea7a1fa370d30ece3968e7689'
MANUAL_BYTES = 81_072_359
MANUAL_ID = 'PZ471-9AS86-SV'
MANUAL_PAGE = 748
TOW_IDENTITIES = {
    ('350e Executive', 'XEBM20L-AWDCSW', 'AB'): ('FWD', 750),
    ('500e Executive', 'XEBM25L-AWDCSW', 'PB'): ('AWD', 1500),
}


def parse_towing_table(cover, page):
    cover_lines = {line.strip() for line in cover.splitlines()}
    if not all(line in cover_lines for line in (
            'RZ 550e / 500e / 350e', MANUAL_ID, 'L/O 15/07/2026')):
        raise ValueError('rz_swedish_manual_identity_changed')
    lines = [' '.join(line.split()) for line in page.splitlines() if line.strip()]
    expected = [
        'Obromsad 750 kg', 'Dragkapacitet(6) Bromsad 750 kg(4)', '1500 kg(5)',
    ]
    if (lines[0:2] != ['10-1. Specifikationer', 'Specifikationer']
            or lines[-1:] != [str(MANUAL_PAGE)] or lines.count(expected[1]) != 1):
        raise ValueError('rz_swedish_manual_table_changed')
    index = lines.index(expected[1])
    if index < 1 or lines[index - 1:index + 2] != expected or lines[-4:-1] != [
            '(4) Modeller med 2WD', '(5) AWD-modeller', '(6) Modeller med draganordning']:
        raise ValueError('rz_swedish_manual_tow_scope_changed')
    return {
        'FWD': (750, 'Bromsad 750 kg(4) | (4) Modeller med 2WD | (6) Modeller med draganordning'),
        'AWD': (1500, 'Bromsad 1500 kg(5) | (5) AWD-modeller | (6) Modeller med draganordning'),
    }


def read_manual(raw):
    if len(raw) != MANUAL_BYTES or digest(raw) != MANUAL_SHA256:
        raise ValueError('rz_reviewed_manual_hash_changed')
    from pypdf import PdfReader

    pages = PdfReader(BytesIO(raw)).pages
    return parse_towing_table(pages[0].extract_text(extraction_mode='layout'),
                              pages[MANUAL_PAGE - 1].extract_text(extraction_mode='layout'))


def confirmed_tow(manual, identity, drive, research):
    expected = TOW_IDENTITIES.get((identity[0], identity[2], identity[3]))
    if expected is None:
        return None
    selected = research['swedish_configurator']
    quotes = selected['quotes']
    rating, quote = manual[expected[0]]
    if (expected != (drive, rating) or len(quotes) != 1
            or not re.fullmatch(r'Dragvikt, (?:max )?' + str(rating) + r' *kg', quotes[0])
            or research['danish_reference_only']['braked_kg'] != rating):
        raise ValueError('rz_manual_and_exact_configuration_tow_conflict')
    return {
        'value': rating, 'source_url': MANUAL_URL, 'source_hash': MANUAL_SHA256,
        'source_quote': quote, 'source_market': 'SE', 'document_id': MANUAL_ID,
        'page': MANUAL_PAGE, 'car_id': identity[1], 'scope': 'max braked, with towing equipment',
        'corroboration': selected,
    }
