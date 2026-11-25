import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import {launchQaBrowser} from './qa_browser.mjs';
import { assertVehiclePhotoFrame } from './qa_vehicle_photo_frame.mjs';
import {vehicleSlug} from '../src/vehicle-names.js';
const base=process.env.EV9_UI_URL||'http://127.0.0.1:5174',origin=new URL(base).origin;
const output=resolve(process.env.EV9_UI_OUTPUT||'data/local/release-data/kia-ev9-completion-2026-11-15/ui');
const catalog=JSON.parse(await readFile('public/data/public_ev_variants.json','utf8'));
const rows=catalog.records.filter(r=>r.brand==='Kia'&&r.model==='Ev9');assert.equal(rows.length,4);
const photo='/media/vehicles/kia-ev9-press-731db0e8f686.jpg';
const hash=createHash('sha256').update(await readFile('public'+photo)).digest('hex');assert(hash.startsWith('731db0e8f686'));
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
   const img=page.locator('.vehicleHeroMedia img');await img.evaluate(e=>e.decode());assert.match(await img.getAttribute('src'),/kia-ev9-press-731db0e8f686/);
   for(const f of ['price_sek','wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','tow_kg','boot_liters','seats','drivetrain'])assert(r[f]!=null);
   assert.equal(r.body_type,'SUV');assert.equal(r.ac_charge_kw,10.5);assert.equal(r.boot_liters,333);
   assert.equal(r.price_type,'list_price');assert.equal(r.price_valid_until,'2026-11-30');
   const text=await page.locator('#specifikationer').innerText();assert(!text.includes('Uppgift saknas'));assert.match(text,/10,5/);assert.match(text,/333/);
   const notice=page.locator('.vehicleContainer > .vehicleImageNotice');
   assert(await notice.isVisible());
   assert.match(await notice.innerText(),/Modellbild: Kia EV9[^.]*\. .*utrustning kan skilja/i);
   assert.doesNotMatch(await notice.innerText(),/Bildkälla|CC[- ]BY|Wikimedia Commons/);
   const layout = await assertVehiclePhotoFrame(page, slug);
   if(r.seats===6&&[390,1440].includes(width)){
    assert.equal(r.price_sek,909900);assert.equal(r.wltp_range_km,505);
    const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();assert.deepEqual(axe.violations,[]);
    await page.screenshot({path:resolve(output,'ev9-six-seats-'+width+'.png'),fullPage:true});
   }
   checks.push({slug,width,...layout});
  }
 }
 await page.setViewportSize({width:1440,height:900});await page.goto(base+'/bilar?brand=Kia&query=EV9',{waitUntil:'networkidle'});
 await page.getByRole('slider',{name:'Maxpris',exact:true}).press('End');
 const picker=page.locator('.vehicleVariantPicker select');await picker.waitFor();
 const selected=[rows.find(r=>r.drivetrain==='RWD'),rows.find(r=>r.variant_name==='EV9 AWD'),rows.find(r=>r.seats===6)];
 for(const r of selected){await picker.selectOption(vehicleSlug(r.brand,r.model,r.variant_name));await page.locator('.homeVehicleActions button').click();await page.locator('.homeVehicleActions button[aria-pressed="true"]').waitFor();}
 await page.locator('.siteHeader').getByRole('link',{name:'Jämför',exact:true}).click();
 const table=await page.locator('table').first().innerText();
 for(const label of ['Kia EV9 RWD','Kia EV9 AWD','6-sits','210 kW','10,5 kW','333'])assert(table.includes(label));
 assert.deepEqual(errors,[]);
 await writeFile(resolve(output,'report.json'),JSON.stringify({origin,checks,axe_audits:2,comparison:true,image_sha256:hash,runtime_errors:errors,paid_calls:0},null,2)+'\n');
 console.log(JSON.stringify({ev9_ui:'passed',origin,pages:checks.length,axe_audits:2,comparison:true,paid_calls:0}));
}finally{await browser.close();}
