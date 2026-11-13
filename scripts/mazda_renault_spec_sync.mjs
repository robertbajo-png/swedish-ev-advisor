import assert from 'node:assert/strict';
import { applySpecPlan as apply, buildSpecPlan as build, specPlanHash, TECHNICAL_FIELDS } from './kia_spec_sync.mjs';
export { specPlanHash };
export const ADAPTER = 'mazda_renault_sweden_specs_v1';
const mazdaPdf='https://media-assets.mazda.eu/raw/upload//mazdase/globalassets/mms-local-pages/brochures-and-pricelists/mazda6e_se_2026-09-29.pdf?rnd=4a8623';
const mazdaSeats='https://de.mazda-press.com/api/assets/download/6e41ae9c-cada-4c65-aff2-7383fa28ccb9_Default?isDownload=false';
const mazdaModel='https://www.mazda.se/modeller/mazda-6e/';
const renaultPdf='https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/renaultsesite/cardocuments/prislista-renault-5-e-tech-electric.pdf';
const renaultDrive='https://www.renault.de/elektromodelle/r5-e-tech-elektrisch-my26/konfigurator.html';
const scopes={'Mazda|6E':['Takumi MY2027','Homura Plus MY2027','Takumi Plus MY2027'],
  'Renault|5':['evolution 40 kWh','techno 52 kWh','iconic five 52 kWh']};
const canonicalFields=['price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote',
  'price_verified_at','price_source_name','price_refresh_batch_id'];
const number=text=>Number(text.replaceAll(' ','').replace(',','.'));
const key=row=>row.brand+'|'+row.model;
const sourceName=row=>row.brand+' Sverige';
const support=row=>row.brand==='Mazda'?[mazdaSeats,mazdaModel]:[renaultDrive];

function fresh(source,now) {
  assert.equal(source.status,'reachable'); assert.equal(source.http_status,200);
  assert.match(source.content_hash,/^[a-f0-9]{64}$/);
  const age=now-Date.parse(source.fetched_at);
  assert(Number.isFinite(age)&&age>=-60000&&age<=900000,'Fresh exact manufacturer sources required');
}

export function validateSpecDraft(row,now=new Date()) {
  assert.equal(row.adapter,ADAPTER); assert(scopes[key(row)]?.includes(row.variant_name));
  assert.equal(row.source_resolution,'owner_2026_11_13_exact_version_current_sources');
  assert(row.extraction_confidence>=0.92&&row.extraction_confidence<=1);
  const mazda=row.brand==='Mazda', primary=mazda?mazdaPdf:renaultPdf;
  assert.equal(row.source.final_url,primary); fresh(row.source,now);
  const registered=new Map([[primary,row.source.content_hash]]);
  assert.deepEqual(row.supporting_sources.map(s=>s.final_url).sort(),support(row).sort());
  for(const source of row.supporting_sources){fresh(source,now);registered.set(source.final_url,source.content_hash);}
  assert.deepEqual(Object.keys(row.facts).sort(),[...TECHNICAL_FIELDS,'ac_charge_kw'].sort());
  assert.deepEqual(Object.keys(row.field_evidence).sort(),Object.keys(row.facts).sort());
  const index=scopes[key(row)].indexOf(row.variant_name);
  const header=['EVOLUTION 40 kWh','TECHNO 52 kWh','ICONIC FIVE 52 kWh'][index];
  for(const [field,value] of Object.entries(row.facts)){
    const p=row.field_evidence[field];
    assert.equal(p.value,value); assert.equal(p.variant_name,row.variant_name);
    assert.equal(registered.get(p.source_url),p.source_hash); assert(typeof p.quote==='string'&&p.quote.length>5);
    if(field==='drivetrain') assert.equal(value,mazda?'RWD':'FWD');
    else {
      const bounds={wltp_range_km:[50,1200],wltp_consumption_kwh_100km:[5,50],battery_kwh:[10,250],
        dc_charge_kw:[20,600],ac_charge_kw:[1,50],boot_liters:[50,3500],tow_kg:[0,4000],seats:[1,9]}[field];
      assert(typeof value==='number'&&Number.isFinite(value)&&value>=bounds[0]&&value<=bounds[1]);
      if(!['battery_kwh','wltp_consumption_kwh_100km'].includes(field))assert(Number.isInteger(value));
    }
    if(mazda){
      const labels={battery_kwh:'Batterikapacitet (kWh)',dc_charge_kw:'Maximal hastighet för DC-laddning (kW)',
        wltp_range_km:'Elektrisk räckvidd vid blandad körning enligt WLPT (km)',
        wltp_consumption_kwh_100km:'Blandad körning, WLTP (kWh/100 km)',tow_kg:'Dragvikt, max (kg)',drivetrain:'Drivning'};
      if(field in labels){
        assert.equal(p.source_url,primary); const prefix='Mazda6e 78 kWh | '+labels[field]+' | ';
        assert(p.quote.startsWith(prefix)); const raw=p.quote.slice(prefix.length);
        assert.equal(value,field==='drivetrain'?(raw==='Bakhjulsdrift'?'RWD':null):number(raw));
        assert.equal(p.scope,field==='tow_kg'?'my2027_braked_towing':'my2027_78_kwh_all_grades');
      }else if(field==='ac_charge_kw'){
        const m=/^Mazda6e 78 kWh \| Laddningstid \(AC, 3-fas ([0-9]+) kW\), 0–100 % \(timmar\) \| ([0-9]+,[0-9]+)$/.exec(p.quote);
        assert(m); assert.equal(value,number(m[1])); assert.equal(p.source_url,primary);
        assert.equal(p.scope,'my2027_three_phase_ac_not_duration');
      }else if(field==='boot_liters'){
        assert.equal(p.source_url,primary); assert.equal(p.scope,'rear_boot_below_shelf_excluding_underfloor_not_frunk');
        const m=/^Mazda6e 78 kWh \| Lastvolym \(med\/utan förvaringsutrymme under golv\) \(alla säten uppfällda, upp till bakre hatthylla\) \| ([0-9]+) l \/ ([0-9]+) l$/.exec(p.quote);
        assert(m);assert.equal(value,number(m[2]));assert(number(m[1])>=value);
      }else{
        assert.equal(field,'seats');assert.equal(value,5);assert.equal(p.source_url,mazdaSeats);
        assert.equal(p.scope,'same_european_my2027_all_grades_seating_only');
        assert.equal(p.quote,'Technische Daten Mazda6e 2027 | Verfügbare Ausstattungen TAKUMI, TAKUMI PLUS, HOMURA PLUS | Anzahl Sitzplätze 5');
      }
    }else{
      if(field==='drivetrain'){
        assert.equal(p.source_url,renaultDrive);assert.equal(p.scope,'manufacturer_current_e_tech_generation_drivetrain_only');
        assert.equal(p.quote,'RENAULT 5 E-TECH ELEKTRISCH | E-Tech elektrisch 120 Urban Range | E-Tech elektrisch 150 Comfort Range | Antriebsart Vorderradantrieb');
      }else{
        assert.equal(p.source_url,primary);assert.equal(p.column_header,header);assert(p.quote.startsWith(header+' | '));
        const quote=p.quote.slice(header.length+3);
        if(['battery_kwh','wltp_range_km','seats','boot_liters'].includes(field)){
          const label={battery_kwh:'Kapacitet (kWh)',wltp_range_km:'Homologerad räckvidd WLTP - blandad körning (km)',seats:'Antal sittplatser',boot_liters:'Bagagerumsvolym (L)'}[field];
          assert(quote.startsWith(label+' | ')); assert.equal(value,number(quote.slice(label.length+3)));
          assert.equal(p.scope,'exact_pdf_grade_column');
          if(field==='battery_kwh')assert.equal(value,index===0?40:52);
          if(field==='wltp_range_km')assert.equal(value,[320,424,421][index]);
        }else if(field==='tow_kg'){
          const m=/^Maxvikt för bromsat\/obromsat släp \(kg\) \| ([0-9]+)\/([0-9]+)$/.exec(quote);
          assert(m);assert.equal(value,number(m[1]));assert.equal(p.scope,'pdf_braked_towing');
        }else if(['ac_charge_kw','dc_charge_kw'].includes(field)){
          assert.equal(quote,'AC 11 kW + DC '+(index===0?80:100)+' kW');assert.equal(value,field==='ac_charge_kw'?11:index===0?80:100);
          assert.equal(p.scope,'exact_battery_peak_charging');
        }else{
          assert.equal(field,'wltp_consumption_kwh_100km');
          const m=/^förbruk\. \(kWh\/100 km\) \| ([0-9]+,[0-9]+)(?:-([0-9]+,[0-9]+) \| Förbrukning \(WLTP, versionsgrupp\): [0-9]+,[0-9]+–[0-9]+,[0-9]+ kWh\/100 km)?$/.exec(quote);
          assert(m);assert.equal(value,number(m[1]));
          assert.deepEqual(p.interval,index===0?[14.3]:[14.1,14.2]);
          assert.equal(value,p.interval[0]);assert.equal(p.scope,index===0?'exact_battery_consumption':'battery_group_consumption_interval_lower_bound');
        }
      }
    }
  }
  assert.deepEqual(row.held_fields,{});assert(row.source_decisions.length>=4);
  if(mazda){
    assert.deepEqual(row.model_facts,{body_type:'Halvkombi'});
    const p=row.model_field_evidence.body_type;
    assert.equal(p.value,'Halvkombi');assert.equal(p.source_url,mazdaModel);assert.equal(registered.get(p.source_url),p.source_hash);
    assert(p.quote.startsWith('2027 Mazda6e är en helt elektrisk modell med bakhjulsdrift.'));
    assert(p.quote.includes('femdörrars halvkombi'));
  }else{
    assert.deepEqual(row.model_facts,{body_type:'Halvkombi'});
    const p=row.model_field_evidence.body_type;
    assert.equal(p.value,'Halvkombi');assert.equal(p.source_url,renaultDrive);assert.equal(registered.get(p.source_url),p.source_hash);
    assert.equal(p.quote,'RENAULT 5 E-TECH ELEKTRISCH | Karosserieform Berline | Anzahl Türen 5');
  }
  const price=row.price_evidence;
  assert.equal(price.source_url,primary);assert.equal(price.source_hash,row.source.content_hash);
  assert.equal(price.price_type,'list_price');assert.equal(price.price_valid_until,null);
  assert.equal(price.classification,'current_exact_variant_base_cash_price_not_finance_or_discount');
  assert(Number.isInteger(price.value)&&price.value>=100000&&price.value<=3000000);
  assert.equal(price.value,mazda?[469900,492800,492800][index]:[364900,414900,449900][index]);
  assert(price.quote.startsWith(mazda?'Mazda6e '+row.variant_name.replace(' MY2027','')+', 258 hk, 78 kWh':header+' | Rek. cirkapris | '));
  assert.equal(number(/([0-9 ]+) kr$/.exec(price.quote)?.[1]||''),price.value);
  return row;
}

const policy={adapter:ADAPTER,validate:validateSpecDraft,sourceType:'technical_pdf',sourceName,
  sourceTitle:r=>r.brand+' '+r.model+' svenska tekniska uppgifter',lockKey:7240016,extraFields:['ac_charge_kw'],
  allowedBodyTypes:['Halvkombi'],modelFacts:r=>r.model_facts,
  supportingSource:(s,r)=>support(r).includes(s.final_url)?{model:s.final_url===mazdaModel?'6e':r.model,shared:false,
    sourceType:s.final_url===mazdaSeats?'price_list_pdf':'manufacturer_page',
    title:r.brand+' '+r.model+(s.final_url===mazdaModel?' svensk modellbeskrivning':' europeiska tillverkaruppgifter'),
    country:s.final_url===mazdaModel?'SE':'DE',language:s.final_url===mazdaModel?'sv':'de',
    sourceName:s.final_url===mazdaModel?'Mazda Sverige':r.brand+' Europa'}:null,
  canonicalFields,
  priceRefresh:(old,r)=>Number(old.price_sek)===r.price_evidence.value&&(!old.price_type||old.price_type==='list_price')&&!old.price_valid_until,
  canonicalExtras:(r,old)=>{
    assert.equal(Number(old.price_sek),r.price_evidence.value,'Separate price reconciliation required');
    assert(!old.price_type||old.price_type==='list_price');assert(!old.price_valid_until);
    return {price_type:'list_price',price_valid_until:null,price_source_url:r.price_evidence.source_url,
      price_source_hash:r.price_evidence.source_hash,price_source_quote:r.price_evidence.quote,
      price_source_name:sourceName(r),price_verified_at:new Date(r.source.fetched_at).toISOString(),
      price_refresh_batch_id:specPlanHash({adapter:ADAPTER,price_evidence:r.price_evidence,fetched_at:r.source.fetched_at})};
  }};
export const buildSpecPlan=(rows,intake,now)=>{
  const plan=build(rows,intake,now,policy);
  assert.equal(plan.targets.length,6,'All six scoped versions must be prepared together');
  for(const t of plan.targets)policy.canonicalExtras(t.draft,t.expected);
  return plan;
};
export const applySpecPlan=(client,plan,hash,now)=>apply(client,plan,hash,now,policy);
// HTML UUIDs and fetch timestamps are transient. Exact facts, scopes and quotes
// must re-parse identically; every new raw source hash is still stored.
export const intakeFingerprint=intake=>intake.drafts.map(r=>JSON.parse(JSON.stringify(r,
  (name,value)=>['content_hash','source_hash','fetched_at'].includes(name)?undefined:value)));
