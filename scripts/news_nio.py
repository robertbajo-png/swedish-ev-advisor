"""Exact, rendered NIO pressroom article state; never use modified/fetch/URL dates."""
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from news_http import PageText, canonical_url, iso_date, MAX_BYTES
from news_document_evidence import NarrativeText


class NioPage(HTMLParser):
    def __init__(self):
        super().__init__(); self.canonicals=[];self.states=[];self.parts=None;self.main_count=0;self.titles=[];self.headings=[];self.tags=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='main':self.main_count+=1
        if tag=='h1' and 'main' in self.tags:self.headings.append([])
        if tag=='link' and 'canonical' in a.get('rel','').split():self.canonicals.append(a.get('href'))
        if tag=='meta' and a.get('property')=='og:title':self.titles.append(a.get('content',''))
        if tag=='script' and a.get('id')=='__NEXT_DATA__' and a.get('type')=='application/json':self.parts=[]
        if tag not in {'meta','link','br','hr','img','input','source','wbr','area','base','embed','param','track'}:self.tags.append(tag)
    def handle_data(self,text):
        if self.parts is not None:self.parts.append(text)
        if 'h1' in self.tags and 'main' in self.tags and self.headings:self.headings[-1].append(text)
    def handle_endtag(self,tag):
        if tag=='script' and self.parts is not None:
            self.states.append(json.loads(''.join(self.parts)));self.parts=None
        if tag in self.tags:
            index=len(self.tags)-1-self.tags[::-1].index(tag);del self.tags[index:]


def document(html,url):
    if len(html.encode())>MAX_BYTES:raise ValueError('nio_document_too_large')
    p=urlsplit(canonical_url(url))
    if canonical_url(url)!=url or p.hostname!='www.nio.com' or p.query or not re.fullmatch(r'/news/[0-9]{11}',p.path):
        raise ValueError('nio_article_outside_authority')
    page=NioPage();page.feed(html)
    if page.canonicals!=[url] or page.main_count!=1 or len(page.states)!=1 or page.parts is not None:
        raise ValueError('nio_identity_or_state_ambiguous')
    state=page.states[0]
    if not isinstance(state,dict):raise ValueError('nio_article_state_invalid')
    try:
        news=state['props']['pageProps']['news']
        if (state['page']!='/news/[id]' or state['query']!={'id':p.path.rsplit('/',1)[-1]}
                or state['locale']!='en_US' or state['isFallback'] is not False
                or news['urlPath']!='/'+state['query']['id'] or news['brand']!='nio'
                or news['locale']!='en_US' or news['type']!='news'
                or news['status']!='published' or news['isDeleted'] is not False):
            raise ValueError('nio_article_state_identity_conflict')
        original=iso_date(news['publishedAt'])
        displayed=iso_date(news.get('displayPublishedAt') or news['publishedAt'])
        for value in (news['publishedAt'],news.get('displayPublishedAt') or news['publishedAt']):
            if not isinstance(value,str) or not re.search(r'(?:Z|[+-][0-9]{2}:[0-9]{2})$',value):
                raise ValueError('nio_publication_timestamp_invalid')
        if not original or not displayed or abs((datetime.fromisoformat(original)-datetime.fromisoformat(displayed)).total_seconds())>86400:
            raise ValueError('nio_publication_dates_conflict')
        title, content=news['title'],news['content']
        if not isinstance(title,str) or not 5<=len(title)<=500 or not isinstance(content,str):
            raise ValueError('nio_article_text_invalid')
        flat=lambda value:' '.join(value.split())
        if len(page.headings)!=1 or flat(' '.join(page.headings[0]))!=flat(title):
            raise ValueError('nio_article_title_conflict')
        if any(flat(value) not in (flat(title),flat(title)+' - News | NIO') for value in page.titles):
            raise ValueError('nio_article_title_conflict')
        narrative=NarrativeText();narrative.feed(content);body=narrative.plain()
        rendered=PageText();rendered.feed(html)
        visible=' '.join(rendered.main_texts[0].split()) if len(rendered.main_texts)==1 else ''
        if not 300<=len(body.encode())<=45000 or body not in visible:
            raise ValueError('nio_article_body_not_rendered_or_incomplete')
        published=min((original,displayed),key=datetime.fromisoformat)
        return {'title':title.strip(),'published_at':published,'summary':news.get('description') or '', 'body':body}
    except (KeyError,TypeError,AttributeError) as error:
        raise ValueError('nio_article_state_incomplete') from error
