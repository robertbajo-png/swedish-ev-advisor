"""Deterministic editorial slots. Source bindings are selected before prose exists."""
import hashlib
import json
import re
import unicodedata

PLAN_VERSION = 'news-fact-plan-v2'
EVENT_PATTERNS = {
    'order_open': r'bestall|forforsalj|forsaljningsstart|\borders?\b|pre.?sale|pre.?order',
    'market_launch': r'lanser|\blaunch\w*|market debut',
    'deliveries': r'leverans|leverer|\bdeliver\w*',
}


def event_assertions(text):
    plain = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    found = {kind for kind, pattern in EVENT_PATTERNS.items() if re.search(pattern, plain)}
    return found or ({'announcement'} if re.search(r'presenter|introduc|announc', plain) else set())


def make_fact_plan(brief, provenance=None):
    if not brief or any(not f.get('id') or not f.get('statement', '').strip() for f in brief):
        raise ValueError('fact_plan_requires_facts')
    if len({f['id'] for f in brief}) != len(brief):
        raise ValueError('fact_plan_duplicate_ids')
    ordinary = [f for f in brief if f['placement'] == 'reporting']
    qualifiers = [f for f in brief if f['placement'] == 'source_context']
    if not ordinary or len(ordinary) + len(qualifiers) != len(brief):
        raise ValueError('fact_plan_invalid_placement')
    headline = next((f for f in ordinary if event_assertions(f['statement'])), ordinary[0])
    intro = [headline]
    if len(ordinary) > 3:
        timing = next((f for f in ordinary if f != headline and event_assertions(f['statement'])), None)
        if timing:
            intro.append(timing)
        details = [[f] for f in ordinary if f not in intro]
    else:
        # A small factual brief forms one compact reporting paragraph, not several repeated ones.
        intro = ordinary
        details = [list(ordinary)]
    # A uniquely scoped range condition gets one home next to its measured value.
    attached = set()
    for qualifier in qualifiers:
        if qualifier.get('qualification_topic') != 'range' or not qualifier.get('item_id'):
            continue
        matches = [fact for group in details for fact in group
                   if fact.get('item_id') == qualifier['item_id'] and 'range' in fact.get('claim_topics', [])
                   and fact['id'] not in attached]
        targets = [group for group in details if any(fact is matches[0] for fact in group)] if len(matches) == 1 else []
        if len(targets) == 1:
            targets[0].append(qualifier)
            attached.add(qualifier['id'])
    qualifiers = [fact for fact in qualifiers if fact['id'] not in attached]
    question = next((f for topic in ('range', 'charging', 'price', 'practicality', 'availability')
                     for f in ordinary if topic in f.get('claim_topics', [])), headline)

    def slot(key, role, facts):
        return {'key': key, 'role': role, 'fact_ids': [f['id'] for f in facts],
                'statements': [f['statement'] for f in facts],
                **({'statistics': [{'fact_id': f['id'], **f['statistic']} for f in facts if f.get('statistic')]}
                   if any(f.get('statistic') for f in facts) else {})}

    plan = {'version': PLAN_VERSION, 'title': slot('title', 'headline', [headline]),
            'intro': slot('intro', 'introduction', intro),
            'paragraphs': [slot(f'p{n}', 'reporting', group) for n, group in enumerate(details)],
            'source_context': [slot(f['id'], 'qualification', [f]) for f in qualifiers],
            'buyer_question': slot('buyer_question', 'personal_question', [question]),
            'provenance': provenance or {}}
    plan['hash'] = hashlib.sha256(json.dumps(plan, ensure_ascii=True, sort_keys=True,
                                            separators=(',', ':')).encode()).hexdigest()
    return plan


def planned_bindings(plan):
    body = [*plan['paragraphs'], *plan['source_context'], plan['buyer_question']]
    return {'title': plan['title']['fact_ids'], 'intro': plan['intro']['fact_ids'],
            **{f'p{n}': block['fact_ids'] for n, block in enumerate(body)}}
