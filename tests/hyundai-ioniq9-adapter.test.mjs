import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {ADAPTER,MODEL,VARIANT,policy} from '../scripts/hyundai_ioniq9_publication.mjs';
import {newModelAdapter} from '../scripts/new_model_adapters.mjs';
import {selectImageRegistryForPublic} from '../scripts/model_image_sync.mjs';
import {specQualifications} from '../src/spec-qualifications.js';

const url='https://dmassets.hyundai.com/is/content/hyundaiautoever/Hyundai_Sverige_Prislista_20261102pdf';
const source={final_url:url,content_hash:'a'.repeat(64)};
const old={canonical_model_id:'prior',brand:'Hyundai',model:'Ioniq 5',url,final_url:url,
  source_type:'price_list_pdf',source_authority:'manufacturer',country:'SE',language:'sv',http_status:200,
  content_hash:source.content_hash,source_validation:'reachable_official_model_source'};
const snapshot={canonical_models:[{id:'prior',brand:'Hyundai',model:'Ioniq 5',normalized_brand:'hyundai',normalized_model:'ioniq 5'}]};

test('IONIQ 9 is a registered single-variant rehearsal, not an enabled remote publisher',()=>{
  assert.equal(newModelAdapter(ADAPTER),policy);
  assert.deepEqual([policy.maxVariants,policy.localOnly,policy.imageKey],[1,true,'hyundai|ioniq 9']);
});

test('the national price PDF can be reused without changing its existing owner or metadata',()=>{
  const before=structuredClone({source,old,snapshot});
  assert.equal(policy.reuseEvidenceSource(source,old,snapshot),true);
  assert.deepEqual({source,old,snapshot},before);
  assert.equal(policy.reuseEvidenceSource({...source,final_url:policy.primaryUrl},old,snapshot),false);
});

test('the national price PDF rejects a wrong owner, changed bytes or unverified status',()=>{
  for(const edit of [{canonical_model_id:'different'},{content_hash:'b'.repeat(64)},
    {country:'NO'},{source_authority:'authorized_dealer'},{http_status:403},{source_validation:'needs_discovery'}]){
    assert.throws(()=>policy.reuseEvidenceSource(source,{...old,...edit},snapshot),/IONIQ 9 scope changed/);
  }
  assert.throws(()=>policy.reuseEvidenceSource(source,undefined,snapshot),/IONIQ 9 scope changed/);
});

test('model-level statistics cannot be joined via a different market row',()=>{
  const exact={id:'official-bev'};
  policy.scopedDiscovery.check({market_models:[exact,{id:'other',canonical_model_id:'untouched'}]},{id:'pilot'},exact);
  assert.throws(()=>policy.scopedDiscovery.check({market_models:[exact,{id:'wrong',canonical_model_id:'pilot'}]},{id:'pilot'},exact),
    /Only the exact BEV market row/);
});

test('public qualifications apply only to the exact seven-seat Swedish car',()=>{
  const row={...MODEL,variant_name:VARIANT,source_url:policy.primaryUrl,seats:7,wltp_range_km:606,
    image_url:'/media/vehicles/hyundai-ioniq-9-press-4556561b89d9.jpg'};
  const notes=specQualifications(row);
  assert.match(notes.imageNotice,/Pressbild av IONIQ 9/);
  assert.match(notes.rangeNote,/20-tumshjul/);
  assert.match(notes.consumptionNote,/10,5 kW AC/);
  assert.match(notes.practicalNote,/338 liter bakom tredje/);
  assert.match(notes.practicalNote,/bromsat/);
  for(const change of [{seats:6},{wltp_range_km:600},{variant_name:'Calligraphy'},{source_url:'https://www.hyundai.com/'}]){
    const wrong=specQualifications({...row,...change});
    assert.equal(wrong.rangeNote,null);
    assert.equal(wrong.practicalNote,null);
    assert.equal(wrong.imageNotice,null);
  }
});

test('the staged press photo is exact, intact and does not add a public model',()=>{
  const repo=file=>new URL('../'+file,import.meta.url);
  const json=file=>JSON.parse(readFileSync(repo(file),'utf8'));
  const registry=json('src/image-rights.json');
  const asset=registry.assets.find(item=>item.model_key===policy.imageKey);
  const media=json('src/image-variants.json')[asset.asset_url];
  assert.deepEqual([media.width,media.height,media.source_sha256],[11324,7923,policy.imageHash]);
  assert.deepEqual(media.variants.map(v=>v.width),[746]);
  for(const [url,hash] of [[asset.asset_url,asset.content_sha256],...media.variants.map(v=>[v.url,v.sha256])]){
    assert.equal(createHash('sha256').update(readFileSync(repo('public'+url))).digest('hex'),hash);
  }
  const scoped={schema_version:1,assets:[asset]};
  assert.deepEqual(selectImageRegistryForPublic([],scoped).assets,[]);
  assert.deepEqual(selectImageRegistryForPublic([MODEL],scoped).assets,[asset]);
  assert.throws(()=>selectImageRegistryForPublic([],{...scoped,assets:[{...asset,full_frame:false}]}));
});
