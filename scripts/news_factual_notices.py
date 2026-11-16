"""Single official facts -> fixed notices -> separate review -> LOCAL drafts only.

This preparation recipe cannot use the historical notice RPC or AI publisher.
Long articles and existing notices keep their own contracts and release gates.
"""
import copy
import hashlib
import re
from datetime import datetime, timedelta, timezone

from kia_price_intake import URL as KIA_URL, extract_rows
from news_notice_facts import NoticeRejected, source_errors, unique
from news_notices import notice_slug, sv, words
from news_store import artifact_hash, stable_id, now_iso
from variant_refresh import parse_document

RECIPE = 'news-single-official-fact-2026-11-v1'
REVIEW = 'deterministic_single_official_fact_v1'
KIA = {'id': 'kia-sweden-prices', 'name': 'Kia Sverige', 'kind': 'primary',
       'website': 'https://www.kia.com/se/'}


def source_packet(packet, item, kind):
    p = item['payload']
    return {**packet, 'kind': kind, 'item_id': item['id'], 'source_id': item['source_id'],
            'source_url': item['url'], 'source_hash': p['content_hash'], 'publisher': p['publisher'],
            'source_title': p['title'], 'source_published_at': p.get('published_at')}


def price_source(capture, now=None, held=None):
    now = now or datetime.now(timezone.utc)
    source, html = capture['source'], capture['html']
    if not isinstance(html, str) or not html or len(html.encode()) > 3_000_000:
        raise NoticeRejected('brief_invalid_source_capture')
    if (source.get('status') != 'reachable' or source.get('http_status') != 200
            or source.get('final_url') != KIA_URL or source.get('content_hash') != hashlib.sha256(html.encode()).hexdigest()):
        raise NoticeRejected('brief_exact_official_price_source_required')
    try:
        fetched = datetime.fromisoformat(source['fetched_at'].replace('Z', '+00:00'))
        if not -timedelta(minutes=5) <= now-fetched <= timedelta(days=1):
            raise ValueError('stale')
    except (ValueError, KeyError, TypeError):
        raise NoticeRejected('brief_price_source_not_fresh') from None
    document = parse_document(html.encode(), 'text/html')
    unsupported = []
    rows = extract_rows(document, source, unsupported)
    if unsupported and held is None:
        raise NoticeRejected('brief_unsupported_cash_price')
    for row in unsupported:
        held.append({'source_id': KIA['id'], 'stage': 'evidence', 'reason': ['brief_unsupported_cash_price'],
                     'row_identity_hash': artifact_hash(row['row_label'])})
    content = document.text()
    item = {'id': stable_id('brief-source:' + KIA_URL), 'source_id': KIA['id'], 'url': KIA_URL,
            'status': 'processed', 'cluster_id': None, 'payload': {
                'title': 'Kias svenska prislista', 'publisher': KIA['name'], 'source_kind': 'primary',
                'access_status': 'accessible', 'final_url': KIA_URL, 'published_at': None,
                'source_date_kind': 'evergreen_price_snapshot', 'fetched_at': source['fetched_at'],
                'content': content, 'content_hash': hashlib.sha256(content.encode()).hexdigest(),
                'source_capture': copy.deepcopy(capture)}}
    return item, rows


def render(packet, item, source):
    fact, subject = packet['fact'], packet['subject']
    if fact['type'] == 'swedish_list_price':
        title = 'Svenskt listpris: ' + fact['variant']
        intro = (f"Det svenska listpriset för {fact['variant']} är {sv(fact['price_sek'])} kronor "
                 'inklusive moms, enligt Kia Sverige.')
        context = 'Prisuppgiften kontrollerades mot Kias svenska prislista den ' + item['payload']['fetched_at'][:10] + '.'
        category = 'priser'
    elif fact['type'] == 'swedish_order_opening':
        title = subject + ': beställningen har öppnat i Sverige'
        intro = f"Volkswagen uppger att det nu går att beställa {packet['model']} i Sverige."
        context = 'Uppgiften publicerades av ' + source['name'] + ' den ' + item['payload']['published_at'][:10] + '.'
        category = 'modeller'
    else:
        raise NoticeRejected('brief_unsupported_fact_type')
    return {'title': title, 'title_fact_ids': ['f1'], 'intro': intro, 'intro_fact_ids': ['f1'],
            'paragraphs': [{'text': context, 'kind': 'reporting', 'fact_ids': ['f1']}],
            'category': category, 'brands': [packet['brand']], 'sources': [{
                'item_id': item['id'], 'url': item['url'], 'publisher': source['name'],
                'title': item['payload']['title'], 'published_at': item['payload'].get('published_at'), 'kind': 'primary'}],
            'image': None, 'related_models': [], 'editorial_recipe': RECIPE, 'notice_kind': packet['kind'],
            'editorial_method': 'Kort faktanotis med källkontroll', 'notice_facts': packet}


def price_packet(row, item):
    model = re.fullmatch(r'Prislista för Kia (EV\d+)(?:\b.*)?', row['caption'], re.I)
    if not model or not re.match(re.escape(model[1]) + r'\b', row['row_label'], re.I):
        raise NoticeRejected('brief_price_model_identity_mismatch')
    label = row['row_label']
    suffix = label[len(model[1]):].strip()
    if len(label) > 120 or not re.fullmatch(
            r'(?:FWD|RWD|AWD|GT|Line|Plus|Long|Range|Standard|Business|Edition|Premium|Performance|'
            r'[4-9]-sits|[0-9]+(?:[.,][0-9]+)?\s?kWh)(?:\s+(?:FWD|RWD|AWD|GT|Line|Plus|Long|Range|'
            r'Standard|Business|Edition|Premium|Performance|[4-9]-sits|[0-9]+(?:[.,][0-9]+)?\s?kWh))*', suffix, re.I):
        raise NoticeRejected('brief_unsupported_price_variant_label')
    return source_packet({'subject': 'Kia ' + model[1].upper(), 'brand': 'Kia', 'model': model[1].upper(), 'fact': {
        'id': 'f1', 'type': 'swedish_list_price', 'variant': 'Kia ' + row['row_label'],
        'row_key': row['row_key'], 'price_sek': row['price_sek'], 'price_type': 'list_price',
        'currency': 'SEK', 'market': 'SE', 'vat_included': True, 'evidence': row['source_quote'],
        'source_hash': item['payload']['content_hash'], 'raw_source_hash': row['source_hash']}}, item, 'price')


def prepare_price_notices(capture, now=None, *, held=None):
    item, rows = price_source(capture, now, held)
    prepared = []
    for row in rows:
        try:
            article = render(price_packet(row, item), item, KIA)
        except NoticeRejected as error:
            if held is None:
                raise
            held.append({'source_id': KIA['id'], 'stage': 'evidence', 'reason': [str(error)],
                         'row_identity_hash': artifact_hash(row['row_key'])})
            continue
        prepared.append({'item': copy.deepcopy(item), 'source': copy.deepcopy(KIA), 'article': article})
    return prepared


def prepare_official_notice(item, source, now=None):
    errors = source_errors(item, source, now)
    if errors or source['id'] != 'vw-sweden-press':
        raise NoticeRejected('brief_official_source_rejected:' + ','.join(errors))
    text = ' '.join(item['payload']['content'].split())
    match = unique(text, r'Volkswagen öppnar (?:nu )?(?:förhandsbeställningen|beställningen) av '
                   r'(?P<model>ID\. (?:Cross|Polo|[0-9](?: Tourer)?)) i Sverige\.')
    if 'Volkswagen ' + match['model'] not in item['payload']['title']:
        raise NoticeRejected('brief_model_not_in_headline')
    if re.search(r'(?:förhandsbeställningen|beställningen) av ' + re.escape(match['model'])
                 + r'[^.!?]{0,40}\b(?:inte|ej)\b[^.!?]{0,20}(?:öppen|öppna)', text, re.I):
        raise NoticeRejected('brief_conflicting_order_status')
    packet = source_packet({'subject': 'Volkswagen ' + match['model'], 'brand': 'Volkswagen', 'model': match['model'],
              'fact': {'id': 'f1', 'type': 'swedish_order_opening', 'market': 'SE',
                       'evidence': match[0], 'source_hash': item['payload']['content_hash']}}, item, 'model')
    return {'item': copy.deepcopy(item), 'source': copy.deepcopy(source), 'article': render(packet, item, source)}


def review_factual_notice(prepared, now=None):
    checks = {'evidence': [], 'editorial': [], 'originality': []}
    article = prepared.get('article', {})
    shaped = (isinstance(article, dict) and isinstance(article.get('intro'), str)
              and isinstance(article.get('paragraphs'), list)
              and all(isinstance(p, dict) and isinstance(p.get('text'), str) for p in article['paragraphs']))
    if not shaped:
        return {'method': REVIEW, 'passed': False, 'checks': {**checks, 'editorial': ['brief_malformed_artifact']},
                'artifact_hash': artifact_hash(article), 'word_count': 0,
                'ai_audit_performed': False, 'provider_requests': 0}
    try:
        item, source = prepared['item'], prepared['source']
        fact = article['notice_facts']['fact']
        if fact['type'] == 'swedish_list_price':
            if source != KIA:
                raise NoticeRejected('brief_price_publisher_changed')
            candidates = prepare_price_notices(item['payload']['source_capture'], now, held=[])
            exact = [p for p in candidates if p['article']['notice_facts']['fact']['row_key'] == fact['row_key']]
            if len(exact) != 1 or exact[0]['item'] != item:
                raise NoticeRejected('brief_price_source_identity_changed')
            expected = exact[0]['article']
        else:
            expected = prepare_official_notice(item, source, now)['article']
        if article != expected:
            checks['evidence'].append('brief_source_fact_or_artifact_changed')
        if any(article.get(key) != expected[key] for key in ('title', 'intro', 'paragraphs')):
            checks['originality'].append('brief_non_template_prose')
        if words(article) > 120:
            checks['editorial'].append('brief_overlong')
    except (ValueError, KeyError, TypeError) as error:
        checks['evidence'].append('brief_source_recheck_failed:' + type(error).__name__)
    return {'method': REVIEW, 'passed': not any(checks.values()), 'checks': checks,
            'artifact_hash': artifact_hash(article), 'word_count': words(article),
            'ai_audit_performed': False, 'provider_requests': 0}


def event_key(article):
    p = article['notice_facts']
    f = p['fact']
    # Evergreen price pages are not republished every time their fetch date changes.
    identity = ({k: f[k] for k in ('type', 'row_key', 'price_sek', 'price_type', 'currency', 'market')}
                if f['type'] == 'swedish_list_price' else {
                    'type': f['type'], 'subject': p['subject'], 'market': f['market'],
                    'date': article['sources'][0]['published_at'][:10]})
    return RECIPE + ':' + artifact_hash(identity)


def stage_factual_notices(store, prepared, now=None):
    if store.backend != 'sqlite':
        raise NoticeRejected('brief_preparation_is_local_only')
    if not isinstance(prepared, list) or not 1 <= len(prepared) <= 20:
        raise NoticeRejected('brief_bounded_batch_required')
    reviewed = [(p, review_factual_notice(p, now)) for p in prepared]
    results = []
    for p, review in reviewed:
        article, item, source = (p[key] for key in ('article', 'item', 'source'))
        try:
            key = event_key(article)
        except (KeyError, TypeError, ValueError):
            if review['passed']:
                raise
            key = RECIPE + ':quarantine:' + artifact_hash(article)
        cluster_id, article_id = stable_id(key), stable_id('article:' + key)
        old = store.get('news_articles', article_id)
        if old and old['status'] == 'published':
            raise NoticeRejected('brief_cannot_edit_published_article')
        store.put('news_sources', {'id': source['id'], 'payload': source})
        store.put('news_story_clusters', {'id': cluster_id, 'event_key': key, 'payload': {'recipe': RECIPE, 'notice_recipe': RECIPE}})
        # A price-list page supports several distinct facts through article_sources.
        store.put('news_items', {**item, 'cluster_id': None})
        row = store.put('news_articles', {'id': article_id, 'cluster_id': cluster_id,
            'slug': notice_slug(article['title'], article_id), 'published_at': None,
            'status': 'draft' if review['passed'] else 'quarantined', 'payload': article})
        store.put('news_article_sources', {'id': stable_id(article_id + item['id']),
            'article_id': article_id, 'item_id': item['id'], 'payload': article['sources'][0]})
        for kind, errors in review['checks'].items():
            store.put('news_quality_checks', {'id': stable_id(article_id + kind + row['artifact_hash']),
                'article_id': article_id, 'kind': kind, 'artifact_hash': row['artifact_hash'], 'passed': not errors,
                'payload': {'errors': errors, 'policy_version': RECIPE, 'review_method': REVIEW,
                            'notice_recipe': RECIPE, 'source_hash': article['notice_facts']['source_hash'],
                            'reviewed_artifact_hash': review['artifact_hash'],
                            'audit_performed': False, 'deterministic_review_performed': True,
                            'checked_at': (now.isoformat() if now else now_iso())}})
        results.append({'article_id': article_id, 'status': row['status'], 'review': review})
    return results
