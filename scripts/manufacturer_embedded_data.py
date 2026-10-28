"""Read Mazda's public static JSON containers; never execute source JavaScript."""
import json
import re
from html.parser import HTMLParser


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('duplicate_manufacturer_json_key')
        result[key]=value
    return result


def material_context(value):
    """Normalize only per-render form/overlay UUIDs, retaining content IDs and text."""
    if isinstance(value,list):
        return [material_context(item) for item in value]
    if not isinstance(value,dict):
        return value
    result={}
    for key,item in value.items():
        if key in ('id','requestId','overlayId') and isinstance(item,str):
            match=re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}(\|[0-9]+)?',item,re.I)
            if match:
                item='render-uuid'+(match[1] or '')
        result[key]=material_context(item)
    return result


class ScriptData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.inside = False
        self.parts = []
        self.scripts = []
        self.script_attrs = []
        self.current_attrs = {}
        self.language = None
        self.page = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'html':
            self.language = values.get('lang')
        if tag == 'body':
            self.page = values.get('data-page')
        if tag == 'script':
            self.inside = True
            self.parts = []
            self.current_attrs = values

    def handle_data(self, text):
        if self.inside:
            self.parts.append(text)

    def handle_endtag(self, tag):
        if tag == 'script' and self.inside:
            self.scripts.append(''.join(self.parts))
            self.script_attrs.append(self.current_attrs)
            self.inside = False


def mazda_document(body):
    import json5
    if len(body) > 8000000:
        raise ValueError('oversized_manufacturer_document')
    parser = ScriptData()
    parser.feed(body.decode('utf-8'))
    result = []
    pattern = re.compile(r"\s*window\.mxp\.data\.push\(JSON\.parse\(('(?:[^'\\]|\\.)*')\)\);?\s*", re.S)
    for script in parser.scripts:
        if not script.lstrip().startswith('window.mxp.data.push(JSON.parse('):
            continue
        if len(script) > 2000000:
            raise ValueError('oversized_static_component')
        match = pattern.fullmatch(script)
        if not match:
            raise ValueError('nonliteral_manufacturer_component')
        serialized = json5.loads(match[1], allow_duplicate_keys=False)
        if not isinstance(serialized, str):
            raise ValueError('static_json_string_required')
        item = json.loads(serialized,object_pairs_hook=unique_object)
        if not isinstance(item, dict) or not isinstance(item.get('type'), str):
            raise ValueError('component_identity_required')
        result.append(item)
    if not result:
        raise ValueError('manufacturer_static_components_missing')
    return {'components':result,'language':parser.language,'page':parser.page}


def mazda_components(body):
    return mazda_document(body)['components']


def stock_document(body, content_type):
    from variant_refresh import parse_document
    if 'html' not in content_type or len(body)>8000000:
        raise ValueError('bounded_stock_html_required')
    parser=ScriptData()
    parser.feed(body.decode('utf-8'))
    objects=[];page_props=None
    for attrs,text in zip(parser.script_attrs,parser.scripts):
        if attrs.get('id')=='__NEXT_DATA__' and attrs.get('type')=='application/json':
            if page_props is not None:raise ValueError('duplicate_next_data')
            page_props=json.loads(text,object_pairs_hook=unique_object).get('props',{}).get('pageProps')
        if attrs.get('type')!='application/ld+json':continue
        value=json.loads(text,object_pairs_hook=unique_object)
        items=value if isinstance(value,list) else value.get('@graph',[value])
        if not isinstance(items,list):raise ValueError('invalid_stock_json_graph')
        objects.extend(items)
    return {'document':parse_document(body,content_type),'cars':[item for item in objects if isinstance(item,dict) and item.get('@type')=='Car'],
        'page_props':page_props}
