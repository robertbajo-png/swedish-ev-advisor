"""Private offline reference only: no provider, remote database or publication path."""
import argparse
import copy
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from news_editorial import EDITORIAL_RECIPE, article_preflight, validate_article
from news_fact_brief import writing_card
from news_store import artifact_hash
from render_news_smoke_preview import render

ROOT = Path(__file__).resolve().parents[1]


def revise_reference(article, facts):
    """Human-readable counterfactual for offline testing, not production prose."""
    if article.get('status') != 'quarantined':
        raise ValueError('offline_reference_requires_quarantined_draft')
    by_id = {fact['id']: fact for fact in facts}
    targets = []
    for index, paragraph in enumerate(article['payload']['paragraphs']):
        ids = paragraph['fact_ids']
        if paragraph['kind'] != 'reporting' or len(ids) != 1 or ids[0] not in by_id:
            continue
        card = writing_card(by_id[ids[0]]['statement'])
        if 'equipment_includes' in card:
            targets.append((index, card))
    if len(targets) != 1:
        raise ValueError('offline_reference_requires_one_exact_equipment_slot')
    index, card = targets[0]
    text = (f'{card["version"]["name"]} är grundversionen och har parkeringssensorer både baktill och framtill. '
            'Smartphoneintegreringen sker genom App Connect.')
    if card['equipment_status'] == 'standard':
        text += ' Utrustningen ingår som standard.'
    revised = copy.deepcopy(article)
    revised.pop('checks', None)
    revised['payload']['paragraphs'][index]['text'] = text
    revised['payload'].update(editorial_recipe=EDITORIAL_RECIPE, offline_reference_only=True)
    revised['artifact_hash'] = artifact_hash(revised['payload'])
    revised['id'] = 'offline-equipment-' + revised['artifact_hash'][:16]
    revised['status'] = 'quarantined'
    revised['published_at'] = None
    return revised


def output_directory(path):
    path = path.resolve()
    if not path.is_relative_to((ROOT / 'data/local').resolve()):
        raise ValueError('offline_reference_output_must_be_private')
    return path


def polish_launch_reference(article, facts):
    """Polish only the observed launch clause; do not infer dates or rewrite preorders."""
    payload = article['payload']
    if article.get('status') != 'quarantined' or payload.get('offline_reference_only') is not True:
        raise ValueError('offline_launch_requires_private_quarantined_reference')
    cited = payload['intro_fact_ids']
    cards = [writing_card(fact['statement']) for fact in facts if fact['id'] in cited]
    launches = [card for card in cards if card.get('event') == 'market_launch' and card.get('market') == 'Sweden']
    if len(launches) != 1:
        raise ValueError('offline_launch_requires_one_cited_month_boundary')
    first, second = launches[0]['timing']['boundary_months']
    old = f'Modellen lanseras i Sverige över övergången mellan {first} och {second}.'
    intro = payload['intro']
    if not intro.endswith(old) or intro.count(old) != 1:
        raise ValueError('offline_launch_reference_clause_changed_or_ambiguous')
    revised = copy.deepcopy(article)
    revised.pop('checks', None)
    revised['payload']['intro'] = intro[:-len(old)] + f'Den svenska lanseringen sker vid skiftet mellan {first} och {second}.'
    revised['payload']['editorial_recipe'] = EDITORIAL_RECIPE
    revised['artifact_hash'] = artifact_hash(revised['payload'])
    revised['id'] = 'offline-launch-' + revised['artifact_hash'][:16]
    return revised


def run(report_path, database_path, directory, polish_launch=False):
    directory = output_directory(directory)
    name = 'launch-reference' if polish_launch else 'equipment-reference'
    outputs = [directory / (name + '.' + ext) for ext in ('json', 'html')]
    if any(path.exists() for path in outputs):
        raise ValueError('offline_reference_output_already_exists')
    original_bytes = report_path.read_bytes()
    report = json.loads(original_bytes)
    if (report.get('state') != 'completed' or report.get('publish') is not False
            or not report.get('owner_shutdown_verified') or not report.get('test_allowance_closed')
            or len(report.get('articles', [])) != 1):
        raise ValueError('offline_reference_requires_stopped_single_trial')
    original = report['articles'][0]
    if artifact_hash(original['payload']) != original['artifact_hash']:
        raise ValueError('offline_reference_original_hash_mismatch')
    evidence = next(check for check in original['checks'] if check['kind'] == 'evidence'
                    and check['artifact_hash'] == original['artifact_hash'])
    facts = evidence['payload']['fact_inventory']
    with closing(sqlite3.connect(database_path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('select payload,status,artifact_hash from news_articles where id=?', (original['id'],)).fetchone()
        if not row or (json.loads(row[0]), row[1], row[2]) != (original['payload'], original['status'], original['artifact_hash']):
            raise ValueError('offline_reference_original_database_mismatch')
        items = [{'id': row[0], 'payload': json.loads(row[1])} for row in db.execute(
            'select id,payload from news_items where cluster_id=? and status=?', (original['cluster_id'], 'processed'))]
    revised = revise_reference(original, facts)
    if polish_launch:
        revised = polish_launch_reference(revised, facts)
    score = original['payload']['relevance_score']
    preflight = article_preflight(revised['payload'], facts, items, score)
    result = {'offline_reference_only': True, 'provider_requests': 0, 'publish': False,
              'source_trial_id': report['trial_id'], 'source_artifact_hash': original['artifact_hash'],
              'input_report_hash': hashlib.sha256(original_bytes).hexdigest(),
              'revised_article': revised, 'deterministic_preflight': preflight,
              'checks_without_new_audit': validate_article(revised['payload'], facts, items, None, score),
              'needs_fresh_independent_audit': True, 'original_trial_unchanged': True}
    if report_path.read_bytes() != original_bytes:
        raise ValueError('offline_reference_input_changed')
    directory.mkdir(parents=True, exist_ok=True)
    outputs[0].write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    outputs[1].write_text(render(revised, offline_reference=True), encoding='utf-8')
    return {'provider_requests': 0, 'publish': False, 'preflight': preflight,
            'needs_fresh_independent_audit': True, 'outputs': [str(path) for path in outputs]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--polish-launch', action='store_true', help='Also polish the known launch clause in the private reference')
    args = parser.parse_args()
    print(json.dumps(run(args.report, args.database, args.output_dir, polish_launch=args.polish_launch), ensure_ascii=True, indent=2))
