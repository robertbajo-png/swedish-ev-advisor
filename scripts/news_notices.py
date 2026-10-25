"""Short Swedish notices from typed facts. No provider calls or publication."""
import re
import unicodedata
from decimal import Decimal

from news_notice_facts import MONTHS
from news_statistics import MONTHS as EN_MONTHS

NOTICE_RECIPE = 'news-notice-2026-10-v1'
NOTICE_REVIEW = 'deterministic_typed_notice_v1'
CATEGORIES = {'model': 'modeller', 'price': 'priser', 'statistics': 'marknad'}


def notice_event_key(packet):
    return 'notice:' + packet['subject'].casefold() + ':' + packet['source_published_at'][:10]


def notice_slug(title, article_id):
    ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower()
    return '-'.join(re.findall(r'[a-z0-9]+', ascii_title))[:90].rstrip('-')+'-'+article_id[:8]


def sv(value):
    number = Decimal(str(value))
    raw = format(number, 'f').rstrip('0').rstrip('.') if '.' in format(number, 'f') else str(number)
    integer, dot, fraction = raw.partition('.')
    grouped = f'{int(integer):,}'.replace(',', ' ')
    return grouped + (',' + fraction if dot else '')


def variant(row):
    v = row['value']
    return f"{v['model']} {v['trim']} med {sv(v['battery_kwh'])} kWh och {sv(v['power_hp'])} hk"


def compose_notice(packet):
    """Only these fixed sentences can reach a notice; never source prose or AI output."""
    kind, subject, fields = packet['kind'], packet['subject'], packet['fields']
    paragraphs = []
    def add(text, *keys):
        paragraphs.append({'text': text, 'kind': 'reporting', 'fact_ids': list(keys)})
    if kind == 'model':
        info = fields['battery_range']['value']
        title = subject + ': beställning öppnad för ny batteriversion'
        intro = (f"{packet['brand']} har öppnat förhandsbeställningen av {packet['model']} med ett batteri på "
                 f"{sv(info['battery_kwh'])} kWh. Kapaciteten anges som netto.")
        add(f"För denna batteriversion uppges högst {sv(info['range_km'])} kilometers räckvidd enligt WLTP.", 'battery_range')
        if 'charging' in fields:
            c = fields['charging']['value']
            add(f"För likströmsladdning anges {sv(c['power_kw'])} kW. Det uppgivna intervallet från "
                f"{c['from_percent']} till {c['to_percent']} procents batterinivå tar ungefär {sv(c['minutes'])} minuter.", 'charging')
        launch = fields['market_launch']['value']
        add(f"Lanseringen i Sverige uppges ske i skiftet mellan {launch['first']} och {launch['second']}.", 'market_launch')
        intro_keys = ['announcement', 'battery_range']
    elif kind == 'price':
        entries = fields['prices']['entries'][:3]
        first = entries[0]
        title = subject + ': svenska cirkapriser presenterade'
        intro = (f"{packet['brand']} har publicerat svenska cirkapriser för {packet['model']}. "
                 f"För {variant(first)} anges ett frånpris på {sv(first['value']['amount'])} kronor.")
        for index, entry in enumerate(entries[1:], 1):
            add(f"För {variant(entry)} är det angivna frånpriset {sv(entry['value']['amount'])} kronor.", 'prices:' + str(index))
        # List prices are never blended with a campaign or monthly lease figure.
        launch = fields['market_launch']['value']
        add(f"Den svenska lanseringen anges till skiftet mellan {launch['first']} och {launch['second']}.", 'market_launch')
        intro_keys = ['prices:0']
    elif kind == 'statistics':
        stats = {(f['statistic']['powertrain'], f['statistic']['metric']): f['statistic'] for f in fields['statistics']}
        share = stats[('battery-electric','market_share_percent')]
        values = share['values']
        through = MONTHS[EN_MONTHS.index(share['through_month'])]
        period = f"januari till {through} {share['year']}"
        title = f"EU: elbilar stod för {sv(values['current'])} procent av nyregistreringarna"
        intro = (f"Under {period} var {sv(values['current'])} procent av de nyregistrerade personbilarna i EU "
                 "batterielektriska, enligt ACEA.")
        units = stats[('battery-electric','units')]['values']['current']
        add(f"Antalet nyregistrerade elbilar under perioden var {sv(units)}. "
            f"Elbilarnas andel för motsvarande period året före var {sv(values['previous_same_period'])} procent.",
            'statistics:battery-electric:units', 'statistics:battery-electric:market_share_percent')
        hybrid = stats[('hybrid-electric','market_share_percent')]['values']['current']
        text = f"Hybridbilar utan extern laddning stod för {sv(hybrid)} procent av EU:s personbilsnyregistreringar under samma period."
        keys = ['statistics:hybrid-electric:market_share_percent']
        if ('plug-in-hybrid','market_share_percent') in stats:
            plugin = stats[('plug-in-hybrid','market_share_percent')]['values']['current']
            text += f" För laddhybrider var andelen {sv(plugin)} procent."
            keys.append('statistics:plug-in-hybrid:market_share_percent')
        add(text, *keys)
        intro_keys = ['statistics:battery-electric:market_share_percent']
    else:
        raise ValueError('unsupported_notice_template')
    return {'title': title, 'title_fact_ids': intro_keys, 'intro': intro, 'intro_fact_ids': intro_keys,
            'paragraphs': paragraphs, 'category': CATEGORIES[kind], 'brands': [packet['brand']] if packet['brand'] else [],
            'sources': [{'item_id': packet['item_id'], 'url': packet['source_url'], 'publisher': packet['publisher'],
                         'title': packet['source_title'], 'published_at': packet['source_published_at'], 'kind': 'primary'}],
            'image': None, 'related_models': [], 'editorial_method': 'Automatisk faktanotis med källkontroll',
            'editorial_recipe': NOTICE_RECIPE, 'notice_kind': kind, 'notice_facts': packet}


def words(article):
    return len((' '.join([article['intro'], *[p['text'] for p in article['paragraphs']]])).split())


def exact_related_models(packet, models):
    def normalized(value):
        return ' '.join(re.findall(r'\w+', value.casefold()))
    return [m for m in models.values() if normalized(m['brand'] + ' ' + m['model']) == normalized(packet['subject'])]
