import assert from 'node:assert/strict';
import {test} from 'node:test';
import {ADAPTER} from '../scripts/mercedes_glb_publication.mjs';
import {glbApprovalHash,runGlbRelease} from '../scripts/mercedes_glb_release.mjs';
import {fetchCatalog,normalizeCatalog} from '../scripts/sync_public_catalog.mjs';

const scope={status:'glb_release_scope_private',publication_approved:false,plan:{adapter:ADAPTER}};
const target={commit:'a'.repeat(40),reader_sha256:'b'.repeat(64)};

test('the approval covers the scope, exact commit and live reader',()=>{
  const original=glbApprovalHash(scope,target);
  assert.notEqual(glbApprovalHash(scope,{...target,reader_sha256:'9'.repeat(64)}),original);
  assert.notEqual(glbApprovalHash(scope,{...target,commit:'1'.repeat(40)}),original);
  assert.notEqual(glbApprovalHash({...scope,plan:{...scope.plan,marker:'changed'}},target),original);
  assert.throws(()=>glbApprovalHash({...scope,publication_approved:true},target));
});

test('bad approval fails before IO and check fails closed on production proof',async()=>{
  await assert.rejects(runGlbRelease({mode:'commit',scope,target,approval:'c'.repeat(64)},
    {verifyProduction:()=>assert.fail('Wrong approval must not touch external state')}),/explicit approved hash/);
  await assert.rejects(runGlbRelease({mode:'check',scope,target},{verifyProduction:()=>{throw new Error('Live GLB reader mismatch');},
    openSnapshot:()=>assert.fail('Do not open a database without production proof')}),/reader mismatch/);
});

test('private raw verification can retain IDs while the public export stays unchanged',async()=>{
  const row={id:'00000000-0000-4000-8000-000000000001',canonical_model_id:'00000000-0000-4000-8000-000000000002',
    brand:'Test',model:'Sample',variant_name:'5-door',
    wltp_range_km:450,source_url:'https://manufacturer.example/electric',source_hash:'f'.repeat(64),
    source_quote:'Combined range: 450 km',extraction_confidence:1,validation_status:'published',
    market_seen:true,available_confirmed:false,coming_or_low_volume:false,discontinued_candidate:false};
  const options={url:'https://example.supabase.co',key:'sb_publishable_synthetic_only',
    fetchImpl:()=>new Response(JSON.stringify([row]),{headers:{'content-range':'0-0/1'}})};
  assert.equal((await fetchCatalog(options))[0].id,undefined);
  assert.deepEqual(await fetchCatalog({...options,includeIds:true}),
    [{...normalizeCatalog([row])[0],id:row.id,canonical_model_id:row.canonical_model_id}]);
  await assert.rejects(fetchCatalog({...options,includeIds:true,
    fetchImpl:()=>new Response(JSON.stringify([{...row,validation_status:'draft'}]),{headers:{'content-range':'0-0/1'}})}),/Non-published/);
});
