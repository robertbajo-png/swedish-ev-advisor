"""Read-only exact 2026-11-27 source/price plan preparation.
No production write entry point: installation and dispatch require separate
review of the SQL contract and a fresh exact baseline receipt.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from remaining_variant_intake import COLLECTORS, SKODA_URL, VW_URL
from stock_variant_intake import VWG_STOCK, VOLVO_ES90, VOLVO_EX30, BILIA_Q6
from variant_refresh import FACT_FIELDS, RefreshError
from audit_catalog_sources import ROOT, SourceFetcher

ADAPTER = 'scoped_price_reverification_20261127_v1'
SCOPE = {}
def register(brand, model, variant, price, kind, expiry, url, name, authority, adapter, status=200):
    SCOPE[(brand,model,variant)] = dict(price_sek=price,price_type=kind,price_valid_until=expiry,
        source_url=url,source_name=name,source_authority=authority,adapter=adapter,http_status=status)
for variant, amount in [('60 Selection',449500),('60 Sportline',469900),('85 Selection',494900),
    ('85 Sportline',510300),('85x Selection',544900),('85x Sportline',559900),('RS',591900)]:
    register('Skoda','Elroq',variant+' Explore Edition',amount,'campaign_price','2026-12-15',
        SKODA_URL,'Skoda Sverige','manufacturer','skoda_elroq_explore_grid_v1')
register('Volkswagen','Id.3','ID.3 Neo Trend',409900,'list_price',None,VW_URL,
    'Volkswagen Sverige','manufacturer','vw_id3_neo_trend_config_v1')
register('Volkswagen','Id.4','ID.4 Pro 4MOTION 77 kWh MY2027 (lagerbil BSJ09L)',628550,
    'dealer_offer',None,VWG_STOCK['Volkswagen|Id.4']['url'],'Volkswagen Group Sverige','importer','vwg_exact_new_stock_v1')
register('Volvo','Es90','ES90 Single Motor Extended Range Ultra MY2026 (lagerbil JWR04C)',819000,
    'dealer_offer',None,VOLVO_ES90,'Volvo Car Retail','authorized_dealer','exact_new_stock_cash_v1')
register('Volvo','Ex30','EX30 P5 Long Range Core MY2027 (lagerbil)',484000,
    'dealer_offer',None,VOLVO_EX30,'Volvo Car Retail','authorized_dealer','exact_new_stock_cash_v1')
register('Audi','A6 E-Tron','A6 Sportback e-tron performance S-line 270 kW MY2027 (lagerbil RRR07B)',769950,
    'dealer_offer',None,VWG_STOCK['Audi|A6 E-Tron']['url'],'Volkswagen Group Sverige','importer','exact_stock_offer_unavailable_v1',500)
register('Audi','Q6 E-Tron','Q6 e-tron quattro SUV 315 kW MY2027 (lagerbil JCE98Y)',799800,
    'dealer_offer',None,BILIA_Q6,'Bilia Haninge Audi','authorized_dealer','exact_stock_offer_unavailable_v1',410)

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def unique(items):
    values=list(items)
    if len(values)!=1: raise RefreshError('exact_unique_price_identity_required')
    return values[0]

def fresh(value, now):
    age=(now-datetime.fromisoformat(value)).total_seconds()
    if age < -60 or age > 900: raise RefreshError('stale_price_observation')

def collect():
    """Use the existing registered, robots-aware source collectors."""
    rows=[]
    for group in ('Skoda|Elroq','Volkswagen|Id.3','Volkswagen|Id.4','Volvo|Es90','Volvo|Ex30'):
        rows.extend(COLLECTORS[group]())
    failures={}
    for key, spec in SCOPE.items():
        if spec['http_status']==200: continue
        u=spec['source_url']; brand=key[0]
        result=SourceFetcher(timeout=15,url_policy=lambda candidate,brands: candidate==u and brands=={brand}).fetch(u,{brand})
        if (result.get('status'),result.get('http_status'),result.get('final_url')) != ('http_error',spec['http_status'],u):
            raise RefreshError('withholding_source_outcome_changed_recheck_scope')
        failures[key]={'http_status':result['http_status'],'source_url':u,
            'observed_at':datetime.now(timezone.utc).isoformat()}
    return rows,failures

def build_plan(baseline, rows, failures, archive=None, now=None, *, allow_elroq_registry_alignment=False):
    now=now or datetime.now(timezone.utc)
    archive=archive or ROOT/'data/local/source-evidence'
    if len(rows)!=11 or len(failures)!=2: raise RefreshError('exact_13_target_scope_required')
    current={(m['brand'],m['model']):m for m in baseline['models']}
    targets=[]
    alignment=None
    for key,spec in SCOPE.items():
        brand,model,name=key
        parent=current.get((brand,model))
        if not parent or parent['validation_status']=='rejected': raise RefreshError('missing_exact_parent')
        prior=unique(v for v in baseline['variants'] if v['canonical_model_id']==parent['id'] and v['variant_name']==name)
        if (prior.get('validation_status') not in ('published','published_reviewed') or
            any(prior.get(k)!=spec[k] for k in ('price_sek','price_type','price_valid_until')) or
            prior.get('price_source_url')!=spec['source_url'] or prior.get('price_source_name')!=spec['source_name']):
            raise RefreshError('canonical_price_baseline_changed')
        registry=unique(s for s in baseline['sources'] if s['url']==spec['source_url'])
        if (registry['canonical_model_id'],registry['brand'],registry['model'],registry['country'],registry['language']) != (parent['id'],brand,model,'SE','sv'):
            raise RefreshError('exact_price_source_registry_alignment_required')
        if registry['source_authority']!=spec['source_authority']:
            if (not allow_elroq_registry_alignment or spec['source_url']!=SKODA_URL
                or registry['source_authority'] is not None or registry.get('source_name') is not None
                or registry.get('source_type')!='manufacturer_official_override_source'
                or not registry.get('id') or any(v.get('source_id')==registry['id'] or (v.get('source_url')==SKODA_URL and not (
                    v.get('validation_status')=='needs_review' and v.get('canonical_model_id')==registry['canonical_model_id']
                    and v.get('variant_name') in ('60 Selection','85 Selection','85x Selection','RS'))) for v in baseline['variants'])):
                raise RefreshError('exact_price_source_registry_alignment_required')
            alignment={'expected':registry}
        proof={k:spec[k] for k in ('source_url','source_name','adapter','http_status')}
        if spec['http_status']==200:
            row=unique(r for r in rows if (r['brand'],r['model'],r['variant_name'])==key)
            if (any(row.get(k)!=spec[k] for k in ('price_sek','price_type','price_valid_until','source_url','source_name','source_authority'))
              or row['extraction_payload'].get('adapter')!=spec['adapter']
              or not 0.92<=row['extraction_confidence']<=1
              or any(row.get(k) is not None for k in FACT_FIELDS if k not in ('price_sek','price_type','price_valid_until'))):
                raise RefreshError('exact_price_only_evidence_changed')
            fresh(row['fetched_at'],now)
            evidence=row['extraction_payload']['field_evidence']['price_sek']
            if any(evidence.get(k)!=row[k] for k in ('source_url','source_hash')) or evidence.get('quote')!=row['source_quote'] or evidence.get('variant')!=name:
                raise RefreshError('unbound_price_quote')
            files=[p for p in archive.glob(row['source_hash']+'.*') if p.suffix in ('.pdf','.html') and hashlib.sha256(p.read_bytes()).hexdigest()==row['source_hash']]
            if len(files)!=1: raise RefreshError('missing_content_bound_source_archive')
            proof.update({k:row.get(k) for k in ('price_sek','price_type','price_valid_until','source_hash','source_quote')})
            proof['observed_at']=row['fetched_at']
            if model=='Elroq':
                page=row['extraction_payload'].get('page_bound_campaign') or {}
                if (page.get('source_page'),page.get('source_page_count'),page.get('optional_equipment_footer_expiry'))!=(1,3,'2026-06-16'):
                    raise RefreshError('exact_elroq_page_evidence_required')
                proof['page_bound']=page
            if model=='Id.4':
                payload=row['extraction_payload']
                if (payload.get('stock_row',{}).get('cash_price_sek'),payload.get('mandatory_fee_sek'))!=(627600,950):
                    raise RefreshError('mandatory_fee_proof_missing')
                proof.update(advertised_cash=627600,mandatory_fee=950)
            operation='refresh'
        else:
            failure=failures[key]
            if (failure['source_url'],failure['http_status'])!=(spec['source_url'],spec['http_status']):
                raise RefreshError('withholding_source_outcome_changed')
            fresh(failure['observed_at'],now)
            proof.update(observed_at=failure['observed_at'],reason='source_unavailable' if spec['http_status']==500 else 'source_gone')
            operation='withhold'
        targets.append(dict(id=prior['id'],brand=brand,model=model,variant_name=name,expected=prior,proof=proof,operation=operation))
    plan=dict(adapter=ADAPTER,baseline=baseline,targets=targets)
    if alignment:plan['source_alignment']=alignment
    return {**plan,'batch_id':digest(plan)}
