import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import {launchQaBrowser} from './qa_browser.mjs';
import { assertVehiclePhotoFrame } from './qa_vehicle_photo_frame.mjs';
import {vehicleSlug} from '../src/vehicle-names.js';
import {matchAdvisorVariants,ruleRequirements} from '../src/advisor-matching.js';
import {normalizePublicVariants} from '../functions/_shared/advisor-core.mjs';
import {profiles} from './toyota_chr_plus_publication.mjs';
const base=process.env.CHR_UI_URL||'http://127.0.0.1:5174',origin=new URL(base).origin;
const output=resolve(process.env.CHR_UI_OUTPUT||'data/local/release-data/toyota-chr-plus-pilot-2026-11-15/ui');
const catalog=JSON.parse(await readFile('public/data/public_ev_variants.json','utf8'));
const rows=catalog.records.filter(r=>r.brand==='Toyota'&&r.model==='C-Hr+');assert.equal(rows.length,3);
const expected=new Map(profiles.map(p=>[p[0],p]));
const photo='/media/vehicles/toyota-c-hr-press-39c5e82ee449.jpg';
const hash=createHash('sha256').update(await readFile('public'+photo)).digest('hex');
assert.equal(hash,'39c5e82ee449b0b4424d5f8ddda24922ff80eadba6a54a90de9348d9e3788e1a');
const publicRows=normalizePublicVariants(rows),requirements=ruleRequirements({budget:650000,range:500});
assert.equal(matchAdvisorVariants(publicRows,requirements).shortlist.length,3);
assert.equal(matchAdvisorVariants(publicRows,{...requirements,awd_required:true,min_tow_kg:1500}).shortlist.length,2);
assert.equal(matchAdvisorVariants(publicRows,{...requirements,min_tow_kg:1501}).shortlist.length,0);
assert.equal(matchAdvisorVariants(publicRows,{...requirements,min_wltp_range_km:600}).shortlist.length,1);
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
   const p=expected.get(r.variant_name);assert(p);
   const slug=vehicleSlug(r.brand,r.model,r.variant_name),response=await page.goto(base+'/bilar/'+slug,{waitUntil:'networkidle'});assert(response.ok());
   await page.locator('.vehicleDetailHero h1').waitFor();await page.evaluate(()=>document.fonts.ready);
   assert.match(await page.locator('.vehicleDetailHero h1').innerText(),/Toyota C-HR\+/);
   const img=page.locator('.vehicleHeroMedia img');await img.evaluate(e=>e.decode());assert.match(await img.getAttribute('src'),/toyota-c-hr-press-39c5e82ee449/);
   for(const f of ['price_sek','wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','tow_kg','boot_liters','seats','drivetrain'])assert(r[f]!=null);
   assert.deepEqual([r.price_sek,r.wltp_range_km,r.wltp_consumption_kwh_100km,r.ac_charge_kw,r.tow_kg],[p[7],p[8],p[9],p[10],p[11]]);
   assert.equal(r.body_type,'SUV');assert.equal(r.battery_kwh,77);assert.equal(r.boot_liters,416);assert.equal(r.seats,5);assert.equal(r.dc_charge_kw,150);
   assert.equal(r.drivetrain,p[4]);assert.equal(r.available_confirmed,false);assert.equal(r.price_type,'list_price');assert.equal(r.price_valid_until,null);
   const text=await page.locator('#specifikationer').innerText();assert(!text.includes('Uppgift saknas'));assert(text.includes(p[10]+' kW'));assert.match(text,/416/);
   const notice=page.locator('.vehicleContainer > .vehicleImageNotice');
   assert(await notice.isVisible());
   assert.match(await notice.innerText(),/Modellbild: Toyota C-HR\+ i brittiskt Design[^.]*\. .*utrustning kan skilja/i);
   assert.doesNotMatch(await notice.innerText(),/Bildkälla|CC[- ]BY|Wikimedia Commons/);
   const layout = await assertVehiclePhotoFrame(page, slug);
   if(p[2]==='Executive'&&[390,1440].includes(width)){
    for(const related of await page.locator('main img[loading="lazy"]').all()){
     await related.scrollIntoViewIfNeeded();await related.evaluate(e=>new Promise((resolve,reject)=>{
      if(e.complete&&e.naturalWidth>0)return resolve();
      const timer=setTimeout(()=>reject(Error('Related image did not load: '+e.currentSrc)),10000);
      e.addEventListener('load',()=>{clearTimeout(timer);resolve();},{once:true});
      e.addEventListener('error',()=>{clearTimeout(timer);reject(Error('Related image failed: '+e.currentSrc));},{once:true});
     }));await related.evaluate(e=>e.decode());
    }
    await page.evaluate(()=>{document.activeElement?.blur();scrollTo({top:0,behavior:'instant'});});
    await page.waitForFunction(()=>scrollY===0);
    await page.screenshot({path:resolve(output,'chr-plus-executive-'+width+'.png'),fullPage:true});
    const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();assert.deepEqual(axe.violations,[]);
   }
   checks.push({slug,width,...layout});
  }
 }
 // Catalog-only progressive disclosure: same complete model qualifier, photo and
 // facts, visible keyboard focus, and no change to the detail-page qualifier.
 for(const width of [320,390,768,1440]){
  await page.setViewportSize({width,height:900});
  await page.goto(base+'/bilar?brand=Toyota&query=C-HR%2B',{waitUntil:'networkidle'});
  const card=page.locator('.vehicleCatalog .vehicleCard').filter({has:page.locator('img[src*="toyota-c-hr-press-39c5e82ee449"]')});
  await card.waitFor();assert.equal(await card.count(),1);
  const picker=card.locator('.vehicleVariantPicker select');
  for(const r of rows){
   await picker.selectOption(vehicleSlug(r.brand,r.model,r.variant_name));
   const details=card.locator('details.vehicleImageNoticeDisclosure'),summary=details.locator('summary'),note=details.locator('.vehicleImageNotice');
   assert.equal(await details.count(),1);
   assert.equal(await summary.innerText(),'Om modellbilden');
   assert.equal(await details.getAttribute('open'),null);assert(!await note.isVisible());
   assert.equal(await note.textContent(),'Modellbild: Toyota C-HR+ i brittiskt Design-utförande. Färg, hjul och utrustning kan skilja från den svenska versionen.');
   const photoLink=card.locator('.homeVehiclePhoto'),id=await photoLink.getAttribute('aria-describedby');
   assert(id);assert.equal(await card.locator('#'+id).textContent(),await note.textContent());
   const cdp=await context.newCDPSession(page);
   const root=await cdp.send('DOM.getDocument');
   const dom=await cdp.send('DOM.querySelector',{nodeId:root.root.nodeId,selector:'[aria-describedby="'+id+'"]'});
   const ax=await cdp.send('Accessibility.getPartialAXTree',{nodeId:dom.nodeId,fetchRelatives:false});
   assert.equal(ax.nodes.find(n=>n.role?.value==='link')?.description?.value,await note.textContent());
   await cdp.detach();
   assert((await summary.boundingBox()).height>=44);
   await summary.focus();await page.keyboard.press('Enter');assert(await note.isVisible());
   assert(await summary.evaluate(e=>document.activeElement===e&&getComputedStyle(e).outlineWidth!=='0px'));
   const axe=await new AxeBuilder({page}).include('.vehicleImageNoticeDisclosure').analyze();assert.deepEqual(axe.violations,[]);
   await page.keyboard.press('Space');assert(!await note.isVisible());
  }
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 }

 await page.setViewportSize({width:1440,height:900});await page.goto(base+'/bilar?brand=Toyota&query=C-HR%2B',{waitUntil:'networkidle'});
 await page.getByRole('slider',{name:'Maxpris',exact:true}).press('End');
 const picker=page.locator('.vehicleVariantPicker select');await picker.waitFor();
 for(const r of rows){await picker.selectOption(vehicleSlug(r.brand,r.model,r.variant_name));await page.locator('.homeVehicleActions button').click();await page.locator('.homeVehicleActions button[aria-pressed="true"]').waitFor();}
 await page.locator('.siteHeader').getByRole('link',{name:'Jämför',exact:true}).click();
 const table=await page.locator('table').first().innerText();
 for(const label of ['Toyota C-HR+','Executive AWD','150 kW','11 kW','22 kW','416','607 km','548 km','507 km'])assert(table.includes(label));
 assert.deepEqual(errors,[]);
 await writeFile(resolve(output,'report.json'),JSON.stringify({origin,checks,axe_audits:14,catalog_disclosure_checks:12,comparison:true,advisor:true,image_sha256:hash,runtime_errors:errors,paid_calls:0},null,2)+'\n');
 console.log(JSON.stringify({toyota_chr_plus_ui:'passed',origin,pages:checks.length,axe_audits:14,catalog_disclosure_checks:12,comparison:true,advisor:true,paid_calls:0}));
}finally{await browser.close();}
