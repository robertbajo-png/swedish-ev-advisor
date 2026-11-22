import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {buildImagePlan,selectImageRegistryForPublic} from '../scripts/model_image_sync.mjs';

const publisher='mercedes-glb-se-private-review';
const policy=JSON.parse(readFileSync(new URL('../src/press-image-publishers.json',import.meta.url),'utf8'))[publisher];
const url=policy.origin+policy.approved_image_paths[0], digest=policy.approved_source_sha256;
const glb={id:'glb',brand:'Mercedes-Benz',model:'Glb',validation_status:'draft'};
const asset={model_key:policy.model_keys[0],publisher_id:publisher,license_id:policy.license_id,status:'documented',
  source_url:url,evidence_url:url,license_url:url,downloaded_from:policy.approved_asset_url,
  evidence_quote:policy.permission_excerpt+' | '+policy.condition_excerpt,usage_scope:'independent_vehicle_editorial',
  asset_url:'/media/vehicles/mercedes-benz-glb-press-'+digest.slice(0,12)+'.jpg',content_sha256:digest,source_content_sha256:digest,
  full_frame:true,author:policy.asset_author,credit:policy.asset_author+' / pressbild',metadata_sha256:'a'.repeat(64),
  reviewed_at:'2026-11-21'};
const registry=assets=>({schema_version:1,assets});

test('parks only the reviewed GLB asset before publication and resumes normal matching after',()=>{
  assert.deepEqual(buildImagePlan([glb],[],selectImageRegistryForPublic([],registry([asset]))),[]);
  const [plan]=buildImagePlan([glb],[glb],selectImageRegistryForPublic([glb],registry([asset])));
  assert.deepEqual([plan.id,plan.image_url,plan.image_source_url],[glb.id,asset.asset_url,asset.source_url]);
});

test('rejects an unreviewed or duplicate staged GLB asset rather than hiding it',()=>{
  for(const changed of [{publisher_id:'different'},{full_frame:false},{author:'different'},
    {content_sha256:'b'.repeat(64)},{asset_url:'/media/vehicles/other-01ba09303394.jpg'},
    {variant_names:['any trim']},{downloaded_from:'https://example.com/other.jpg'}]){
    assert.throws(()=>selectImageRegistryForPublic([],registry([{...asset,...changed}])));
  }
  assert.throws(()=>selectImageRegistryForPublic([],registry([asset,asset])),/Duplicate/);
  assert.throws(()=>buildImagePlan([],[],selectImageRegistryForPublic([],registry([{...asset,model_key:'mercedes benz|other'}]))),
    /One reviewed image per public model/);
});
