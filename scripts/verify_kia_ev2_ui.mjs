import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import {launchQaBrowser} from './qa_browser.mjs';
import {vehicleSlug} from '../src/vehicle-names.js';
import {matchAdvisorVariants,ruleRequirements} from '../src/advisor-matching.js';
import {normalizePublicVariants} from '../functions/_shared/advisor-core.mjs';
const base=process.env.EV2_UI_URL||'http://127.0.0.1:5174',origin=new URL(base).origin;
const output=resolve(process.env.EV2_UI_OUTPUT||'data/local/release-data/kia-ev2-pilot-2026-11-15/ui');
const catalog=JSON.parse(await readFile('public/data/public_ev_variants.json','utf8'));
const rows=catalog.records.filter(r=>r.brand==='Kia'&&r.model==='Ev2');assert.equal(rows.length,3);
const expected=new Map([['EV2 FWD 5-sits',[331900,317,42.2,15.1]],['EV2 FWD Long Range 5-sits',[381000,453,61,14.9]],['EV2 GT Line FWD Long Range 5-sits',[459900,413,61,16.3]]]);
const photo='/media/vehicles/kia-ev2-press-42a663c6e0ce.jpg';
const hash=createHash('sha256').update(await readFile('public'+photo)).digest('hex');
assert.equal(hash,'42a663c6e0ce765ebc59d1865699e61c99909e4a1b3fe6f7b7f20204e63392d9');
const publicRows=normalizePublicVariants(rows),requirements=ruleRequirements({budget:500000,range:300});
const advice=matchAdvisorVariants(publicRows,{...requirements,min_tow_kg:750,min_seats:5});
assert.equal(advice.shortlist.length,3);
assert.equal(matchAdvisorVariants(publicRows,{...requirements,awd_required:true}).shortlist.length,0);
assert.equal(matchAdvisorVariants(publicRows,{...requirements,min_tow_kg:751}).shortlist.length,0);
await mkdir(output,{recursive:true});
const browser=await launchQaBrowser(),checks=[],errors=[];
try{
 const context=await browser.newContext();
 await context.route('**/*',route=>{
  const u=new URL(route.request().url());
  return u.origin!==origin||route.request().method()!=='GET'||u.pathname.startsWith('/api/')?route.abort():route.continue();
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 for(const width of [320,390,768,1440]){
  await page.setViewportSize({width,height:900});
  for(const r of rows){
   const slug=vehicleSlug(r.brand,r.model,r.variant_name),response=await page.goto(base+'/bilar/'+slug,{waitUntil:'networkidle'});assert(response.ok());
   await page.locator('.vehicleDetailHero h1').waitFor();await page.evaluate(()=>document.fonts.ready);
   const img=page.locator('.vehicleHeroMedia img');await img.evaluate(e=>e.decode());assert.match(await img.getAttribute('src'),/kia-ev2-press-42a663c6e0ce/);
   for(const f of ['price_sek','wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','tow_kg','boot_liters','seats','drivetrain'])assert(r[f]!=null);
   assert.deepEqual([r.price_sek,r.wltp_range_km,r.battery_kwh,r.wltp_consumption_kwh_100km],expected.get(r.variant_name));
   assert.equal(r.body_type,'SUV');assert.equal(r.ac_charge_kw,10.5);assert.equal(r.boot_liters,362);assert.equal(r.seats,5);
   assert.equal(r.drivetrain,'FWD');assert.equal(r.tow_kg,750);assert.equal(r.dc_charge_kw,150);assert.equal(r.available_confirmed,false);
   assert.equal(r.price_type,'list_price');assert.equal(r.price_valid_until,'2026-11-30');
   const text=await page.locator('#specifikationer').innerText();assert(!text.includes('Uppgift saknas'));assert.match(text,/10,5/);assert.match(text,/362/);
   const notice=page.locator('.vehicleContainer > .vehicleImageNotice');
   assert(await notice.isVisible());
   assert.match(await notice.innerText(),/Modellbild: Kia EV2 GT Line[^.]*\. .*utrustning kan skilja/i);
   assert.doesNotMatch(await notice.innerText(),/Bildkälla|CC[- ]BY|Wikimedia Commons/);
   const guide=page.getByRole('region',{name:'Vilken version ska jag välja?'});
   assert.equal(await guide.getByRole('article').count(),3);
   assert.equal(await guide.getByRole('link',{name:'Kias prislista'}).count(),3);
   const guideText=(await guide.innerText()).replace(/\s+/g,' ');
   assert.match(guideText,/\+49 100 kr, \+136 km WLTP/);
   assert.match(guideText,/\+78 900 kr, [-−]40 km WLTP/);
   assert.match(guideText,/Uppskattning, inte ett körtest/);
   assert.deepEqual(await guide.getByRole('row',{name:/^GT Line Long Range/}).getByRole('cell').allTextContents(),['2','1']);
   const layout=await page.evaluate(()=>{
    const rect=s=>document.querySelector(s).getBoundingClientRect(),media=rect('.vehicleHeroMedia'),img=document.querySelector('.vehicleHeroMedia img');
    return{overflow:document.documentElement.scrollWidth>innerWidth,gap:rect('.vehicleHeroCopy').top-media.bottom,
     headerGap:media.top-rect('.siteHeader').bottom,ratio:img.getBoundingClientRect().width/img.getBoundingClientRect().height,
     naturalRatio:img.naturalWidth/img.naturalHeight,overlay:getComputedStyle(document.querySelector('.vehicleHeroOverlay')).display};
   });assert(!layout.overflow);
   if(width<=800){assert(layout.gap>=16&&layout.headerGap>=0);assert.equal(layout.overlay,'none');assert(Math.abs(layout.ratio-layout.naturalRatio)<0.01);}
   if(r.variant_name==='EV2 GT Line FWD Long Range 5-sits'&&[390,1440].includes(width)){
    const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();assert.deepEqual(axe.violations,[]);
    for(const related of await page.locator('main img[loading="lazy"]').all()){
     await related.scrollIntoViewIfNeeded();
     await related.evaluate(e=>new Promise((resolve,reject)=>{
      if(e.complete&&e.naturalWidth>0)return resolve();
      const timeout=setTimeout(()=>reject(Error('Related image did not load: '+e.currentSrc)),10000);
      e.addEventListener('load',()=>{clearTimeout(timeout);resolve();},{once:true});
      e.addEventListener('error',()=>{clearTimeout(timeout);reject(Error('Related image failed: '+e.currentSrc));},{once:true});
     }));
     await related.evaluate(e=>e.decode());
    }
    await page.evaluate(()=>scrollTo(0,0));
    await page.screenshot({path:resolve(output,'ev2-gt-line-'+width+'.png'),fullPage:true});
   }
   checks.push({slug,width,...layout});
  }
 }
 await page.setViewportSize({width:1440,height:900});
 await page.goto(base+'/bilar',{waitUntil:'networkidle'});
 const priceSlider=page.getByRole('slider',{name:'Maxpris',exact:true});
 await priceSlider.waitFor();
 const fullCount=catalog.records.length;
 assert.equal(await priceSlider.getAttribute('aria-valuetext'),'Inget pristak');
 assert.equal(await page.locator('.vehicleFilterNote:visible').innerText(),fullCount+' av '+fullCount+' varianter');
 await priceSlider.press('Home');
 assert.notEqual(await page.locator('.vehicleFilterNote:visible').innerText(),fullCount+' av '+fullCount+' varianter');
 await page.getByRole('button',{name:'Återställ',exact:true}).click();
 assert.equal(await priceSlider.getAttribute('aria-valuetext'),'Inget pristak');
 assert.equal(await page.locator('.vehicleFilterNote:visible').innerText(),fullCount+' av '+fullCount+' varianter');
 await page.goto(base+'/bilar?brand=Kia&query=EV2',{waitUntil:'networkidle'});
 assert.equal(await priceSlider.getAttribute('aria-valuetext'),'Inget pristak');
 const picker=page.locator('.vehicleVariantPicker select');await picker.waitFor();
 for(const r of rows){await picker.selectOption(vehicleSlug(r.brand,r.model,r.variant_name));await page.locator('.homeVehicleActions button').click();await page.locator('.homeVehicleActions button[aria-pressed="true"]').waitFor();}
 await page.locator('.siteHeader').getByRole('link',{name:'Jämför',exact:true}).click();
 const table=await page.locator('table').first().innerText();
 for(const label of ['Kia EV2','GT Line','150 kW','10,5 kW','362','317 km','413 km','453 km'])assert(table.includes(label));
 assert.deepEqual(errors,[]);
 await writeFile(resolve(output,'report.json'),JSON.stringify({origin,checks,axe_audits:2,comparison:true,advisor:true,image_sha256:hash,runtime_errors:errors,paid_calls:0},null,2)+'\n');
 console.log(JSON.stringify({ev2_ui:'passed',origin,pages:checks.length,axe_audits:2,comparison:true,advisor:true,paid_calls:0}));
}finally{await browser.close();}
