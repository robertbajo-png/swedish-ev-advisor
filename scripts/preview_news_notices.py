"""Offline proof/preview from frozen official sources. No network, AI or public files."""
import argparse
import hashlib
import json
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from news_notice_facts import extract_notice
from news_notice_validation import review_notice
from news_notice_pipeline import stage_notices
from news_notices import compose_notice
from news_store import NewsStore, artifact_hash
from refresh_verified_variants import save

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'data/local'
DEFAULT_MANIFEST = PRIVATE / 'release-data/news-production/ab-r26-manifest-2026-10-23.json'


def build(manifest_path, directory, now=None, refresh=False):
    now = now or datetime.now(timezone.utc)
    directory = Path(directory).resolve()
    if not directory.is_relative_to(PRIVATE.resolve()):
        raise ValueError('notice_preview_must_remain_private')
    frozen = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    public_file = ROOT / 'public/data/news_articles.json'
    before = hashlib.sha256(public_file.read_bytes()).hexdigest()
    request_count = 0
    if refresh:
        from news_engine import hydrate_item
        from news_http import Collector
        from smoke_news_engine import verified_context
        class CountedCollector(Collector):
            def request(self, *args, **kwargs):
                nonlocal request_count
                request_count += 1
                return super().request(*args, **kwargs)
        collector = CountedCollector(tls_context=verified_context())
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temp, closing(NewsStore(Path(temp)/'fetch.sqlite')) as store:
            for key in ['vw-sweden-press','acea']:
                fresh, _ = hydrate_item(store, frozen['items'][key], frozen['sources'], collector)
                frozen['items'][key] = fresh
    cases = []
    for kind, key in [('model','vw-sweden-press'), ('price','vw-sweden-press'), ('statistics','acea')]:
        item, config = frozen['items'][key], frozen['sources'][key]
        facts = extract_notice(item, config, kind=kind, now=now)
        article = compose_notice(facts)
        review = review_notice(article, item, config, now=now)
        if not review['passed']:
            raise ValueError('notice_offline_review_failed:'+kind)
        cases.append({'kind':kind, 'article':article, 'artifact_hash':artifact_hash(article), 'review':review})
    directory.mkdir(parents=True, exist_ok=True)
    # Stage actual events once: VW auto-selects price, ACEA selects statistics.
    # The separate model example above is a preview angle, not another event.
    with tempfile.TemporaryDirectory(dir=directory) as temp, closing(NewsStore(Path(temp)/'notices.sqlite')) as store:
        for key in ['vw-sweden-press','acea']:
            store.put('news_items',frozen['items'][key])
        staged = stage_notices(store,[frozen['sources'][key] for key in ['vw-sweden-press','acea']],{},now=now)
        if len(staged)!=2 or any(r['status']!='validated_draft' for r in staged) or store.public_articles():
            raise ValueError('notice_private_event_staging_failed')
        second = stage_notices(store,[frozen['sources'][key] for key in ['vw-sweden-press','acea']],{},now=now)
        if len(store.rows('news_articles'))!=2 or any(r['status']!='validated_draft' for r in second):
            raise ValueError('notice_private_staging_not_idempotent')
    if hashlib.sha256(public_file.read_bytes()).hexdigest()!=before:
        raise ValueError('notice_preview_changed_public_export')
    report = {'generated_at':now.isoformat(), 'offline':not refresh, 'collector_requests':request_count, 'provider_requests':0,
              'cost_usd':0, 'published':0, 'public_export_unchanged':True,
              'source_documents':2, 'demonstrated_templates':3, 'staged_events':staged,
              'passed':True, 'cases':cases}
    save(directory/'notice-report.json',report)
    (directory/'index.html').write_text(render(report),encoding='utf-8')
    return {'passed':True,'provider_requests':0,'collector_requests':request_count,'published':0,'cases':[
        {'kind':c['kind'],'words':c['review']['word_count'],'passed':c['review']['passed']} for c in cases],
        'staged_event_count':len(staged), 'preview':str(directory/'index.html'), 'report':str(directory/'notice-report.json')}


def render(report):
    sections = []
    labels = {'model':'Modellnyhet','price':'Prisnyhet','statistics':'Marknadsstatistik'}
    for case in report['cases']:
        p = case['article']
        paragraphs = ''.join('<p>'+escape(row['text'])+'</p>' for row in p['paragraphs'])
        ref = p['sources'][0]
        sections.append(f'''<section aria-labelledby="{case['kind']}"><div class="meta">{labels[case['kind']]} / {case['review']['word_count']} ord / Regelkontroll godkänd</div>
<h2 id="{case['kind']}">{escape(p['title'])}</h2><p class="intro">{escape(p['intro'])}</p>{paragraphs}
<p class="source">Källa: <a href="{escape(ref['url'],quote=True)}" rel="noopener noreferrer">{escape(ref['publisher'])}</a> · {escape(ref['published_at'][:10])}</p></section>''')
    mode = ('Sparade källor används. Inga nya nätverks- eller AI-anrop har gjorts.' if report['offline'] else
            'Källorna har hämtats på nytt med åtkomst-, datum- och hashkontroll. Inga AI-anrop har gjorts.')
    return '''<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Elbilsguiden: privata faktanotiser</title>
<style>body{margin:0;background:#f7f7f4;color:#171b1c;font:17px/1.65 system-ui,sans-serif}main{max-width:800px;margin:auto;padding:40px 24px}
header{padding-bottom:24px;border-bottom:1px solid #d7dfdc}h1{font-size:30px;line-height:1.15}h2{font-size:25px;line-height:1.25}
section{padding:32px 0;border-bottom:1px solid #d7dfdc}.intro{font-weight:600}.meta,.source{font-size:14px;color:#425b55}a{color:#245e5b}
@media(max-width:520px){main{padding:24px 20px}h1{font-size:26px}h2{font-size:22px}}</style>
<main><header><strong>Elbilsguiden</strong><h1>Korta nyheter, tydliga fakta.</h1><p>Privat prov. Inget är publicerat.</p>
<p>Tre mallar visas från två officiella källor. Modell- och prisexemplet gäller samma Volkswagen-nyhet; driftkedjan skapar endast en notis per händelse. '''+mode+'''</p></header>'''+''.join(sections)+'''
<footer><p>Resultat: 3 av 3 mallar klarar den regelbaserade kontrollen. Två privata händelser, inga publiceringar, 0 USD i AI-kostnad. Detta är en programmatisk kontroll, inte en AI-slutgranskning.</p></footer></main></html>'''


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST)
    parser.add_argument('--output',type=Path,default=PRIVATE/'news-notice-preview')
    parser.add_argument('--refresh',action='store_true',help='Fetch both official sources again; never calls paid AI')
    args = parser.parse_args()
    print(json.dumps(build(args.manifest,args.output,refresh=args.refresh),ensure_ascii=True,indent=2))
