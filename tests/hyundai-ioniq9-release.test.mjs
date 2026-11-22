import assert from 'node:assert/strict';
import test from 'node:test';
import {ADAPTER} from '../scripts/hyundai_ioniq9_publication.mjs';
import {databaseCatalogHash,ioniq9ReleaseHash,runIoniq9Release} from '../scripts/hyundai_ioniq9_release.mjs';
import {catalogHash} from '../scripts/sync_public_catalog.mjs';

const target={commit:'a'.repeat(40),reader_sha256:'b'.repeat(64)};
const baseline=[{brand:'Test',model:'Incumbent',variant_name:'Reference',wltp_range_km:450,
  source_url:'https://manufacturer.example/car',source_quote:'450 km WLTP',source_hash:'1'.repeat(64),
  market_seen:true,available_confirmed:false,coming_or_low_volume:false,discontinued_candidate:false,
  extraction_confidence:1,validation_status:'published'}];
const scope={status:'ioniq9_release_scope_private',publication_approved:false,
  plan:{adapter:ADAPTER},baseline_sha256:catalogHash(baseline),database_baseline_sha256:databaseCatalogHash(baseline)};
const seal=ioniq9ReleaseHash(scope,target);

test('exact source scope, main commit and reader bytes are all part of the release seal',()=>{
  assert.notEqual(seal,ioniq9ReleaseHash(scope,{...target,reader_sha256:'c'.repeat(64)}));
  assert.notEqual(seal,ioniq9ReleaseHash(scope,{...target,commit:'d'.repeat(40)}));
  assert.notEqual(seal,ioniq9ReleaseHash({...scope,candidate_sha256:'e'.repeat(64)},target));
  assert.throws(()=>ioniq9ReleaseHash({...scope,plan:{adapter:'different-model'}},target));
});

test('wrong seal forbids both commit and recovery before IO',async()=>{
  for(const mode of ['commit','export']){
    await assert.rejects(runIoniq9Release({mode,scope,target,seal:'a'.repeat(64)},
      {verifyProduction:()=>assert.fail('Unreviewed production IO')}),/release seal mismatch/);
  }
});

test('changed deployed or database baseline stops before source replay and database connection',async()=>{
  const unchanged={verifyProduction:()=>{},baseline:()=>baseline,liveBaseline:()=>baseline,publicRows:()=>baseline,
    freshSource:()=>assert.fail('Unexpected replay on wrong baseline'),openSnapshot:()=>assert.fail('Unexpected database connection')};
  for(const [key,hash,message] of [
    ['baseline_sha256','f'.repeat(64),/Committed catalog baseline changed/],
    ['database_baseline_sha256','f'.repeat(64),/Anonymous Supabase baseline changed/],
  ]){
    await assert.rejects(runIoniq9Release({mode:'check',scope:{...scope,[key]:hash},target},unchanged),message);
  }
  const wrongLive={...unchanged,liveBaseline:()=>[{...baseline[0],model:'Unexpected'}]};
  await assert.rejects(runIoniq9Release({mode:'check',scope,target},wrongLive),/Deployed catalog baseline changed/);
});

test('export checks its journal before reading canonical variants or writing a file',async()=>{
  await assert.rejects(runIoniq9Release({mode:'export',scope,target,seal},{
    verifyProduction:()=>{},baseline:()=>baseline,liveBaseline:()=>baseline,
    readJournal:()=>({attempt:{seal,target:{...target,commit:'f'.repeat(40)}}}),
    publicRows:()=>assert.fail('Export read did not stop on wrong attempt'),
    saveExport:()=>assert.fail('Unsafe export'),
  }),{code:'ERR_ASSERTION'});
});
