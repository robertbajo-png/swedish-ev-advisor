import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { publicationHash } from '../scripts/new_model_publication.mjs';
import { runXpG9Release, verifyRegisteredG9Media } from '../scripts/publish_approved_xpeng_g9.mjs';
import { catalogHash, fetchCatalog } from '../scripts/sync_public_catalog.mjs';
import { ADAPTER } from '../scripts/xpeng_g9_publication.mjs';
import { g9ApprovalHash, prepareG9ReleaseReview, proveFreshG9Release, requirePublishedG6,
  validateG9PostG6Delta } from '../scripts/xpeng_g9_release_review.mjs';

const sha = 'a'.repeat(64);
const g6Source = 'https://store.xpeng.com/se/configurator/new_G6';
const g9Source = 'https://store.xpeng.com/se/configurator/new_G9';
const date = '2026-11-21T12:00:00.000Z';
const jpg = '/media/vehicles/xpeng-g9-press-3872869a55dd.jpg';
const swedishVariants = [
  ['RWD Standard Range 20 tum',719900,502,18.4,79,445,'RWD'],
  ['AWD Performance 21 tum',849900,540,20.1,93.1,525,'AWD'],
];
function fixture() {
  const image = {asset_url:jpg,content_sha256:sha,source_url:'https://www.mynewsdesk.com/se/xpeng-motors-sweden-ab/images/nya-g9-1-punkt-jpeg-3270628'};
  const common = {brand:'Xpeng',body_type:'SUV',validation_status:'published',price_type:'list_price',
    extraction_confidence:1,source_hash:sha,source_quote:'Synthetic technical evidence',
    price_source_hash:sha,price_source_quote:'Synthetic cash price',price_source_name:'Synthetic manufacturer',
    price_verified_at:date,price_valid_until:null,
    available_confirmed:false,coming_or_low_volume:false,discontinued_candidate:false,market_seen:true};
  const baseline = ['AWD Performance 20 tum','RWD Long Range 20 tum','RWD Standard Range 20 tum'].map(variant_name=>({
    ...common,model:'G6',variant_name,price_sek:499900,source_url:g6Source,price_source_url:g6Source,
  }));
  baseline.push({...common,brand:'Toyota',model:'C-HR+',variant_name:'Active 2WD',price_sek:469900,
    source_url:'https://example.com/toyota',price_source_url:'https://example.com/toyota'});
  const additions = swedishVariants.map(([variant_name,price_sek,wltp_range_km,wltp_consumption_kwh_100km,battery_kwh,dc_charge_kw,drivetrain])=>({
    ...common,model:'G9',variant_name,price_sek,wltp_range_km,wltp_consumption_kwh_100km,battery_kwh,dc_charge_kw,drivetrain,
    ac_charge_kw:11,boot_liters:660,tow_kg:1500,seats:5,image_url:jpg,image_source_url:image.source_url,
    source_url:g9Source,price_source_url:g9Source,price_source_quote:`${price_sek} kr`,
  }));
  const candidate = [...baseline,...additions];
  const plan = {adapter:ADAPTER,image,expected_model:common,
    intake:{sources:[{final_url:g9Source,content_hash:sha,fetched_at:date}]},
    targets:additions.map(({variant_name,price_source_quote})=>({draft:{variant_name,extraction_confidence:1,
      price_evidence:{quote:price_source_quote}}}))};
  // Synthetic receipt data only; this test never claims G6 is deployed.
  const report = {status:'xpeng_g9_local_after_g6_passed',g6_evidence:'live_catalog_and_view',
    baseline_count:baseline.length,baseline_sha256:catalogHash(baseline),candidate_sha256:catalogHash(candidate),
    commit:'b'.repeat(40),plan_hashes:[publicationHash(plan)],variants:2,production_writes:0,publication_approved:false,
    anonymous_before_commit:true,late_rollback:true,exact_replay_noop:true,market_history_preserved:true};
  const ui = {status:'g9_private_ui_passed',g6_evidence:report.g6_evidence,source_commit:report.commit,
    candidate_sha256:report.candidate_sha256,private_variants:candidate.length,exact_photos:true,g6_photo_separate:true,
    compared_from_detail:true,no_legacy_badges:true,production_writes:0,publication_approved:false,
    g9_media:[{url:jpg,sha256:sha},...[480,800,1280].map(width=>({
      url:jpg.replace('/vehicles/','/responsive/').replace(/\.jpg$/,`-${width}.webp`),sha256:sha,
    }))],
    responsive_checks:additions.flatMap(({variant_name})=>[320,390,768,1440].map(width=>({variant:variant_name,width})))};
  return {baseline,candidate,plan,report,ui};
}

test('a complete synthetic post-G6 review binds a two-row delta, media and checkout',()=>{
  const f = fixture();
  const receipt = prepareG9ReleaseReview(f);
  assert.equal(receipt.added,2);
  assert.equal(receipt.preserved,4);
  assert.equal(receipt.baseline_sha256,f.report.baseline_sha256);
  assert.notEqual(g9ApprovalHash({...receipt,commit:'c'.repeat(40)}),g9ApprovalHash(receipt));
});

test('a private G6 fixture cannot stand in for a live release baseline',()=>{
  const f = fixture();
  f.report.g6_evidence = 'local_fixture';
  assert.throws(()=>prepareG9ReleaseReview(f),/fixture of G6 is not a live baseline/);
  for(const rows of [[],f.baseline.slice(1),
    f.baseline.map((row,index)=>index===0?{...row,validation_status:'validated'}:row),
    f.baseline.map((row,index)=>index===1?{...row,source_url:g9Source}:row)])
    assert.throws(()=>requirePublishedG6(rows));
});

test('an unrelated edit, missing G9, incorrect price source or G9L is rejected',()=>{
  const f = fixture();
  assert.throws(()=>validateG9PostG6Delta(f.baseline,f.candidate.slice(1),f.plan));
  for(const [index,edit] of [[0,{price_sek:519900}],[3,{variant_name:'wrong Toyota'}],
    [4,{price_source_quote:'5 995 kr/mån'}],[5,{model:'G9L'}]]) {
    const amended = f.candidate.map((row,i)=>i===index?{...row,...edit}:row);
    assert.throws(()=>validateG9PostG6Delta(f.baseline,amended,f.plan));
  }
});

test('a foreign browser run, incomplete viewport set or wrong responsive media cannot be approved',()=>{
  for(const change of [
    ui=>{ui.candidate_sha256='b'.repeat(64);},
    ui=>{ui.no_legacy_badges=false;},
    ui=>{ui.responsive_checks.pop();},
    ui=>{ui.g9_media[3].url='/media/responsive/xpeng-g6-wrong-1280.webp';},
  ]) {
    const f = fixture();
    change(f.ui);
    assert.throws(()=>prepareG9ReleaseReview(f));
  }
});

test('fresh release verification is bound to its exact review and plan hash',()=>{
  const f = fixture();
  const review = prepareG9ReleaseReview(f);
  const hash = g9ApprovalHash(review);
  const fresh = {plan:f.plan,plan_hash:publicationHash(f.plan)};
  assert.throws(()=>proveFreshG9Release(review,fresh,'0'.repeat(64)),/exact approved G9 release hash/);
  assert.throws(()=>proveFreshG9Release(review,{...fresh,plan_hash:'0'.repeat(64)},hash),/Fresh G9 plan changed/);
});

test('catalog drift or an invalid scope hash is rejected before acquiring a snapshot',async()=>{
  const f = fixture();
  const reviewed = prepareG9ReleaseReview(f);
  await assert.rejects(runXpG9Release({mode:'commit',reviewed,approval:'0'.repeat(64)},{}),/Invalid G9 scope hash/);
  const io={assertMain:()=>{},catalog:()=>({records:f.baseline}),siteRows:()=>f.candidate,
    openSnapshot:()=>assert.fail('Opened a snapshot on a changed baseline')};
  await assert.rejects(runXpG9Release({mode:'check',reviewed},io),/Website catalog changed/);
  await assert.rejects(runXpG9Release({mode:'check',reviewed},
    {...io,siteRows:()=>f.baseline,publicRows:()=>f.candidate}),/Live canonical catalog changed/);
});

test('the public reader only returns DB identities on request and rejects duplicated IDs',async()=>{
  const data = fixture().baseline.slice(0,2).map((row,i)=>({...row,id:'12345678-0000-4000-8000-00000000000'+i}));
  const connection = rows=>({url:'https://project.example.com',key:'sb_publishable_synthetic',
    fetchImpl:()=>new Response(JSON.stringify(rows),{headers:{'content-range':'0-1/2'}})});
  const ordinary = await fetchCatalog(connection(data));
  assert(ordinary.every(row=>!Object.hasOwn(row,'id')));
  const withIds = await fetchCatalog({...connection(data),includeIds:true});
  assert.deepEqual(withIds.map(row=>row.id),data.map(row=>row.id));
  const duplicate = [data[0],{...data[1],id:data[0].id}];
  await assert.rejects(fetchCatalog({...connection(duplicate),includeIds:true}),/Duplicate public variant ID/);
});

test('the registered G9 photograph and all three derivatives agree with photographed bytes',async()=>{
  const read = async path=>JSON.parse(await readFile(new URL('../src/'+path+'.json',import.meta.url),'utf8'));
  const [{changes,...image}] = (await read('image-rights')).assets.filter(row=>row.model_key==='xpeng|g9');
  const {variants} = (await read('image-variants'))[image.asset_url];
  const g9_media = [{url:image.asset_url,sha256:image.content_sha256},...variants.map(({url,sha256})=>({url,sha256}))];
  const root = fileURLToPath(new URL('..',import.meta.url));
  await verifyRegisteredG9Media(root,image,{g9_media});
  await assert.rejects(verifyRegisteredG9Media(root,image,{g9_media:g9_media.slice(1)}),/differ from browser QA/);
});
