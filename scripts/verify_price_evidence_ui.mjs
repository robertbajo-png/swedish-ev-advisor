import assert from 'node:assert/strict';
import {mkdir,readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {preview} from 'vite';
import AxeBuilder from '@axe-core/playwright';
import {launchQaBrowser} from './qa_browser.mjs';

const out=new URL('../data/local/design-qa/',import.meta.url);
await mkdir(out,{recursive:true});
const snapshot=JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json',import.meta.url),'utf8'));
const original=snapshot.records.find(row=>row.brand==='Skoda'&&row.model==='Enyaq'&&row.variant_name==='Solid Edition 85');
assert(original,'Canonical variant required for a clearly isolated transport fixture');
const fixture={...original,price_sek:501000,price_type:'campaign_price',price_valid_until:'2026-12-15',verified_at:'2026-07-01T00:00:00Z',
  price_source_url:original.source_url,price_source_hash:'b'.repeat(64),price_source_name:'Skoda Sverige',
  price_source_quote:'Synthetic transport fixture for price evidence; not a published price.',price_verified_at:'2026-10-27T12:00:00Z'};
let server,browser;
try {
  let base=process.env.PRICE_EVIDENCE_UI_URL||'http://127.0.0.1:5174';
  if(process.argv.includes('--isolated-server')) {
    server=await preview({configLoader:'runner',preview:{host:'127.0.0.1',port:0,strictPort:true,open:false}});
    base='http://127.0.0.1:'+server.httpServer.address().port;
  }
  browser=await launchQaBrowser();
  const errors=[];
  for(const [name,viewport]of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
    const context=await browser.newContext({viewport});
    const page=await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',route=>{
      const request=route.request(),url=new URL(request.url());
      if(url.pathname.endsWith('/data/public_ev_variants.json'))return route.fulfill({json:{...snapshot,records:[fixture]}});
      if(url.pathname.includes('/rest/v1/public_ev_variants'))return route.fulfill({json:[fixture]});
      if(url.pathname.includes('/api/'))return route.fulfill({status:503,json:{error:'Offline UI fixture: providers disabled'}});
      if(request.resourceType()==='image')return route.abort();
      return route.continue();
    });
    await page.goto(base+'/bilar');
    const card=page.locator('.carCard').first();
    await card.waitFor();
    assert.match(await card.locator('.homeVehiclePrice').innerText(),/501\s000 kr/);
    assert.match(await card.innerText(),/Kampanjpris.*2026-12-15/);
    assert.equal(await card.getByRole('link',{name:'Priskälla'}).getAttribute('href'),fixture.price_source_url);
    assert.deepEqual(await card.locator('.vehicleSourceLine time').allTextContents(),['2026-07-01','2026-10-27']);
    await card.getByRole('link',{name:/Visa detaljer/}).click();
    await page.locator('.vehicleDetailHero h1').waitFor();
    const drivetrain=page.locator('.detailInfoCard').filter({has:page.getByRole('heading',{name:'Grunden i bilen'})});
    assert.match(await drivetrain.innerText(),/Pris verifierat 2026-10-27/);
    assert.match(await drivetrain.innerText(),/Övriga uppgifter verifierade 2026-07-01/);
    await page.locator('#bilkallor summary').click();
    const sources=page.locator('#bilkallor');
    assert.match(await sources.innerText(),/Biluppgifter verifierade 2026-07-01/);
    assert.match(await sources.innerText(),/Pris verifierat 2026-10-27/);
    assert.equal(await sources.getByRole('link',{name:/Priskälla: Skoda Sverige/}).getAttribute('href'),fixture.price_source_url);
    assert(!/Listpris 569\s?900/.test(await page.locator('body').innerText()),'An old price quote must not become the new vehicle summary');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'No horizontal page overflow');
    assert.deepEqual((await new AxeBuilder({page}).analyze()).violations.map(v=>v.id),[],name+' accessibility');
    await page.evaluate(()=>document.activeElement?.blur());
    await page.screenshot({path:fileURLToPath(new URL('price-evidence-'+name+'.png',out)),fullPage:true});
    await context.close();
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({price_evidence_ui_ok:true,viewports:['1440x1000','390x844'],separate_dates_and_sources:true,stale_price_summary_absent:true,accessibility_violations:0,synthetic_transport_fixture:true,production_writes:0,provider_calls:0}));
}finally {
  await browser?.close();
  if(server)await new Promise(resolve=>server.httpServer.close(resolve));
}
