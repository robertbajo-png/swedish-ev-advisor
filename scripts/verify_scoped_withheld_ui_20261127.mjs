import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {spawnSync,spawn} from 'node:child_process';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
import {catalogHash,normalizeCatalog} from './sync_public_catalog.mjs';
import {vehicleSlug} from '../src/vehicle-names.js';
const out='data/local/sandsten-price-review/withheld-ui';
await mkdir(out,{recursive:true});
const file='public/data/public_ev_variants.json',original=await readFile(file);
const live=JSON.parse((await readFile('data/local/sandsten-price-review/catalog.bytes')).toString('utf8'));
const test=structuredClone(live);
const held=test.records.filter(r=>r.brand==='Audi'&&/RRR07B|JCE98Y/.test(r.variant_name));
assert.equal(held.length,2);
for(const row of held){
  for(const key of ['price_sek','price_type','price_valid_until'])row[key]=null;
  for(const key of ['price_source_url','price_source_hash','price_source_quote','price_source_name','price_verified_at'])delete row[key];
  row.price_withheld_reason=row.variant_name.includes('RRR07B')?'source_unavailable':'source_gone';
  row.price_withheld_at='2026-11-27T20:48:37+00:00';
}
test.records=normalizeCatalog(test.records);test.catalog_sha256=catalogHash(test.records);
assert.equal(test.records.length,109);
const env={...process.env,NEWS_BUILD_SYNC:'0',VEHICLE_DATA_MODE:'snapshot',VITE_VEHICLE_DATA_MODE:'snapshot',BILJOURNAL_RENDER_DIST:'1',
  PYTHON:process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'};
const run=args=>{
  const r=spawnSync(process.execPath,args,{env,stdio:'inherit',windowsHide:true,timeout:180000});
  assert.equal(r.status,0,'Local build failed: '+args.join(' '));
};
const urls=held.map(row=>'/bilar/'+vehicleSlug(row.brand,row.model,row.variant_name));
function entities(data,out=[]){
  if(Array.isArray(data))for(const v of data)entities(v,out);
  else if(data&&typeof data==='object'){if(['Vehicle','Product'].includes(data['@type']))out.push(data);if(data['@graph'])entities(data['@graph'],out);}
  return out;
}
function prove(ld){const all=ld.flatMap(data=>entities(data));assert(all.length>0,'Missing Vehicle/Product JSON-LD');for(const v of all)assert(!('offers' in v),'A stale offer remains in structured data');return all.length;}
let browser,server;
const results=[];
try {
  await writeFile(file,JSON.stringify(test,null,2)+'\n');
  await writeFile(out+'/TEST-ONLY-catalog.json',JSON.stringify(test,null,2)+'\n');
  run(['node_modules/vite/bin/vite.js','build','--configLoader','runner']);
  run(['scripts/run_python.mjs','scripts/prerender_static_routes.py']);
  run(['scripts/render_public_pages.mjs']);
  server=spawn(process.execPath,['node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port','4198','--strictPort'],{env,windowsHide:true,stdio:'ignore'});
  const origin='http://127.0.0.1:4198';
  let ready=false;
  for(let i=0;i<40;i++){try{if((await fetch(origin)).ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,250))}
  assert(ready,'Local preview unavailable');
  browser=await chromium.launch({channel:'msedge',headless:true});
  for(const url of urls){
    const res=await fetch(origin+url+'/');assert.equal(res.status,200);const html=await res.text();
    const ld=[...html.matchAll(/<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/ig)].map(m=>JSON.parse(m[1]));
    const staticEntities=prove(ld);
    for(const width of [320,390,768,1440]){
      const page=await browser.newPage({viewport:{width,height:900}});
      await page.route('**/*',route=>{const rq=route.request();return rq.method()==='GET'&&rq.url().startsWith(origin+'/')?route.continue():route.abort()});
      await page.goto(origin+url+'/',{waitUntil:'domcontentloaded'});
      await page.locator('main').waitFor();
      await page.waitForFunction(()=>Array.from(document.querySelectorAll('script[type="application/ld+json"]')).some(s=>s.textContent.includes('Vehicle')));
      // Wait for React hydration/route updates, then check actual final DOM.
      await page.waitForTimeout(1000);
      const dom=await page.evaluate(()=>({ld:Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map(s=>JSON.parse(s.textContent)),text:document.querySelector('main').innerText,overflow:document.documentElement.scrollWidth>innerWidth}));
      const hydratedEntities=prove(dom.ld);
      assert(/Ej verifierat/.test(dom.text),'Missing unpriced UI state');
      assert(!/769\s*950|799\s*800/.test(dom.text),'Historical cash amount visible as live product price');
      assert(!dom.overflow,'Horizontal overflow');
      const slug=url.split('/').pop();
      await page.screenshot({path:out+'/'+slug+'-'+width+'.png',fullPage:false});
      results.push({url,width,staticEntities,hydratedEntities,offers:false,visibleUnpriced:true,overflow:false});
      await page.close();
    }
  }
  const sourcePage=await browser.newPage({viewport:{width:390,height:844}});
  await sourcePage.route('**/*',route=>{const rq=route.request();return rq.method()==='GET'&&rq.url().startsWith(origin+'/')?route.continue():route.abort()});
  await sourcePage.goto(origin+'/kallor/',{waitUntil:'domcontentloaded'});
  const notices=sourcePage.locator('.bilSourceItem').filter({hasText:'Aktuellt pris ej verifierat'});
  await notices.first().waitFor();
  assert.equal(await notices.count(),2);
  for(const item of await notices.all()){
    await item.locator('details summary').click();
    assert((await item.innerText()).includes('Historiskt prisunderlag (inte aktuellt erbjudande)'));
  }
  await sourcePage.close();
  await writeFile(out+'/result.json',JSON.stringify({testOnly:true,results,sourceHistoryLabelVerified:true,productionWrites:0,paidCalls:0},null,2)+'\n');
  console.log(JSON.stringify({testOnly:true,pages:results.length,staticAndHydratedOffersAbsent:true,productionWrites:0,paidCalls:0}));
} finally {
  await browser?.close();server?.kill();
  await writeFile(file,original);
}
