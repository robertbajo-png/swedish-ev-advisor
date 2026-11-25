import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import {launchQaBrowser} from './qa_browser.mjs';
import { assertVehiclePhotoFrame } from './qa_vehicle_photo_frame.mjs';
import {vehicleSlug} from '../src/vehicle-names.js';

const base=process.env.EV6_UI_URL||'http://127.0.0.1:5174';
const origin=new URL(base).origin;
const output=resolve(process.env.EV6_UI_OUTPUT||'data/local/release-data/kia-ev6-completion-2026-11-15/ui');
const snapshot=JSON.parse(await readFile('public/data/public_ev_variants.json','utf8'));
const rows=snapshot.records.filter(r=>r.brand==='Kia'&&r.model==='Ev6');
assert.equal(rows.length,3);
const image='/media/vehicles/kia-ev6-press-5e19a7dc0d49.jpg';
assert.equal(createHash('sha256').update(await readFile('public'+image)).digest('hex'),'5e19a7dc0d49f06143132458fb1322a88a573fa0c4e15139725eec2ea63d2756');
await mkdir(output,{recursive:true});
const browser=await launchQaBrowser(),checks=[],errors=[];
try{
 const context=await browser.newContext();
 // Inspect real rendered public data without counting QA traffic or buying AI.
 await context.route('**/*',route=>{
  const u=new URL(route.request().url());
  return u.origin!==origin||route.request().method()!=='GET'||u.pathname.startsWith('/api/')?route.abort():route.continue();
 });
 const page=await context.newPage();
 page.on('pageerror',error=>errors.push(error.message));
 for(const width of [320,390,768,1440]){
  await page.setViewportSize({width,height:900});
  for(const row of rows){
   const slug=vehicleSlug(row.brand,row.model,row.variant_name);
   const response=await page.goto(base+'/bilar/'+slug,{waitUntil:'networkidle'});assert(response.ok());
   await page.locator('.vehicleDetailHero h1').waitFor();
   await page.evaluate(()=>document.fonts.ready);
   const img=page.locator('.vehicleHeroMedia img');
   await img.evaluate(async element=>{await element.decode();});
   assert(await img.evaluate(element=>element.complete&&element.naturalWidth>0));
   assert.match(await img.getAttribute('src'),/kia-ev6-press-5e19a7dc0d49/);
   for(const field of ['price_sek','wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','tow_kg','boot_liters','seats','drivetrain'])
    assert(row[field]!=null,slug+': complete '+field);
   assert.equal(row.body_type,'Crossover');assert.equal(row.ac_charge_kw,10.5);assert.equal(row.dc_charge_kw,258);
   assert.equal(row.price_type,'list_price');assert.equal(row.price_valid_until,'2026-11-30');
   const specs=await page.locator('#specifikationer').innerText();
   assert(!specs.includes('Uppgift saknas'));assert.match(specs,/10,5/);assert.match(specs,/480/);
   if(row.variant_name==='EV6 GT'){assert.equal(row.drivetrain,'AWD');assert.match(specs,/609 hk/);assert.match(specs,/450 km/);}
   else assert.match(specs,/19 tum/);
   const notice=page.locator('.vehicleContainer > .vehicleImageNotice');
   assert(await notice.isVisible());
   assert.match(await notice.innerText(),/Modellbild: Kia EV6 Baseline[^.]*\. .*utrustning kan skilja/i);
   assert.doesNotMatch(await notice.innerText(),/Bildkälla|CC[- ]BY|Wikimedia Commons/);
   assert.match(await page.locator('.vehicleHeroStats').innerText(),new RegExp(row.wltp_range_km+' km'));
   const layout = await assertVehiclePhotoFrame(page, slug);
   if(row.variant_name==='EV6 GT'&&[390,1440].includes(width)){
    const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();assert.deepEqual(axe.violations,[]);
    await page.screenshot({path:resolve(output,'ev6-gt-'+width+'.png'),fullPage:true});
   }
   checks.push({slug,width,...layout,complete:true});
  }
 }
 await page.setViewportSize({width:1440,height:900});
 await page.goto(base+'/bilar?brand=Kia&query=EV6',{waitUntil:'networkidle'});
 await page.getByRole('slider',{name:'Maxpris',exact:true}).press('End');
 const picker=page.locator('.vehicleVariantPicker select');
 await picker.waitFor();
 for(const row of rows){
  await picker.selectOption(vehicleSlug(row.brand,row.model,row.variant_name));
  const add=page.locator('.homeVehicleActions button');
  await add.click();
  await page.locator('.homeVehicleActions button[aria-pressed="true"]').waitFor();
 }
 await page.locator('.siteHeader').getByRole('link',{name:'Jämför',exact:true}).click();
 const table=await page.locator('table').first().innerText();
 assert.match(table,/Kia EV6 RWD/);assert.match(table,/Kia EV6 AWD/);assert.match(table,/Kia EV6 GT/);
 assert.match(table,/258 kW/);assert.match(table,/10,5 kW/);assert.match(table,/480/);
 assert.deepEqual(errors,[]);
 await writeFile(resolve(output,'report.json'),JSON.stringify({origin,checks,axe_audits:2,comparison:true,runtime_errors:errors,paid_calls:0,external_analytics_requests:0},null,2)+'\n');
 console.log(JSON.stringify({ev6_ui:'passed',origin,pages:checks.length,axe_audits:2,comparison:true,paid_calls:0}));
}finally{await browser.close();}
