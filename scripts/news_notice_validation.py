"""A deterministic source/artifact review, not a simulated LLM audit."""
from news_notice_facts import NoticeRejected, extract_notice
from news_notices import compose_notice, words, NOTICE_REVIEW
from news_statistics import statistical_scope_errors
from news_store import artifact_hash


def review_notice(article, item, source, now=None):
    checks = {'evidence': [], 'editorial': [], 'originality': []}
    packet = article.get('notice_facts')
    if not isinstance(packet, dict):
        checks['evidence'].append('notice_missing_typed_facts')
        return {'method': NOTICE_REVIEW, 'checks': checks, 'passed': False}
    try:
        fresh = extract_notice(item, source, kind=packet.get('kind'), now=now)
    except (NoticeRejected, ValueError, KeyError, TypeError) as exc:
        checks['evidence'].append('notice_source_recheck_failed:' + str(exc)[:160])
        return {'method': NOTICE_REVIEW, 'checks': checks, 'passed': False}
    if fresh != packet:
        checks['evidence'].append('notice_typed_facts_changed_or_forged')
    expected = compose_notice(fresh)
    if (not isinstance(article.get('intro'), str) or not isinstance(article.get('paragraphs'), list)
            or any(not isinstance(p, dict) or not isinstance(p.get('text'), str)
                   or not isinstance(p.get('fact_ids'), list) for p in article.get('paragraphs', []))
            or not isinstance(article.get('related_models'), list)):
        checks['editorial'].append('notice_malformed_artifact')
        return {'method': NOTICE_REVIEW, 'checks': checks, 'passed': False}
    # A writer cannot smuggle prose, prices, images or conclusions into fixed slots.
    for key in expected:
        if key == 'related_models':
            continue  # Exact canonical linking is checked separately by the stager.
        if article.get(key) != expected[key]:
            checks['evidence'].append('notice_render_mismatch:' + key)
    if set(article) != set(expected):
        checks['evidence'].append('notice_unexpected_artifact_fields')
    for linked in article.get('related_models', []):
        from news_notices import exact_related_models
        if (not isinstance(linked, dict) or not all(isinstance(linked.get(k),str) for k in ('brand','model'))
                or not exact_related_models(fresh, {'candidate': linked})):
            checks['evidence'].append('notice_unrelated_model_link')
    count = words(article)
    if count > 220 or not article.get('paragraphs'):
        checks['editorial'].append('notice_empty_or_overlong')
    if any(p.get('kind') != 'reporting' for p in article.get('paragraphs', [])):
        checks['editorial'].append('notice_analysis_not_allowed')
    if fresh['kind'] == 'statistics':
        facts = fresh['fields']['statistics']
        by_id = {'statistics:'+f['statistic']['powertrain']+':'+f['statistic']['metric']: f for f in facts}
        scoped = [dict(f, id=key) for key, f in by_id.items()]
        blocks = [{'id':'intro','kind':'reporting','text':article['intro'], 'fact_ids':article['intro_fact_ids']},
                  *[dict(p, id='p'+str(n)) for n,p in enumerate(article['paragraphs'])]]
        checks['evidence'].extend(statistical_scope_errors(blocks, scoped))
    # Originality here is construction-bound: templates never ingest source prose
    # as a sentence. Dynamic fields are validated names/numbers, not copied bodies.
    if any(article.get(k) != expected[k] for k in ('title', 'intro', 'paragraphs')):
        checks['originality'].append('notice_non_template_prose')
    return {'method': NOTICE_REVIEW, 'artifact_hash': artifact_hash(article), 'source_hash': fresh['source_hash'],
            'word_count': count, 'checks': checks, 'passed': not any(checks.values())}
