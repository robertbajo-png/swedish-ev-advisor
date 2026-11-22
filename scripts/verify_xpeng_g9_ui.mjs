import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cp, mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import react from '@vitejs/plugin-react';
import { build, preview } from 'vite';
import { applyPrivateInventoryCopy, inventoryBadge } from './private_inventory_copy_patch.mjs';
import { launchQaBrowser } from './qa_browser.mjs';
import { catalogHash, normalizeCatalog, variantKey } from './sync_public_catalog.mjs';
import { readReviewedImage, readReviewedImageBytes } from './xpeng_g6_publication.mjs';
import { readG9Image, readPrivateG9Image } from './xpeng_g9_publication.mjs';
import { requirePublishedG6 } from './xpeng_g9_release_review.mjs';

const {values} = parseArgs({options:{readback:{type:'string'},'inventory-patch':{type:'string'}}});
assert(values.readback,'Supply the private XPENG G9 readback directory');
const evidence = await realpath('data/local/release-data');
const folder = await realpath(values.readback);
assert.equal(folder,resolve(values.readback));
assert.equal(dirname(folder),evidence);
assert.match(basename(folder),/^xpeng-g9-readback-[a-z0-9]+$/i);
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(folder));
const json = async file=>JSON.parse(await readFile(file,'utf8'));
const report = await json(join(folder,'report.json'));
assert.equal(report.status,'xpeng_g9_local_after_g6_passed');
assert.deepEqual([report.publication_approved,report.production_writes,report.variants,report.g6_variants],[false,0,2,3]);
const g6Evidence = report.g6_evidence??'local_fixture';
assert(['live_catalog_and_view','local_fixture'].includes(g6Evidence));
const liveG6 = g6Evidence==='live_catalog_and_view';
const candidate = normalizeCatalog((await json(join(folder,'candidate-catalog.json'))).records);
assert.equal(catalogHash(candidate),report.candidate_sha256);
const base = join(folder,'main-source');
assert.equal(await realpath(base),base);
const baseline = normalizeCatalog((await json(join(base,'public','data','public_ev_variants.json'))).records);
assert.equal(catalogHash(baseline),report.baseline_sha256);
const existing = new Set(baseline.map(variantKey));
assert.deepEqual(candidate.filter(row=>existing.has(variantKey(row))),baseline);
if(liveG6) requirePublishedG6(baseline);
const models = Object.fromEntries([
  ['G6',readReviewedImage(),readReviewedImageBytes],
  ['G9',readG9Image(),readPrivateG9Image],
].map(([key,image,read])=>[key,{image,bytes:read(image),rows:candidate.filter(row=>
  (key==='G6'&&liveG6?existing.has(variantKey(row)):!existing.has(variantKey(row)))&&row.model===key&&row.brand==='Xpeng')}]));
assert.equal(candidate.length,baseline.length+(liveG6?2:5));
assert.deepEqual([models.G6.rows.length,models.G9.rows.length],[3,2]);
for(const {image,rows} of Object.values(models)) for(const row of rows) {
  assert.equal(row.image_url,image.asset_url);
  assert.equal(row.image_source_url,image.source_url);
}

const output = await mkdtemp(join(folder,'ui-'));
const root = join(output,'source');
await cp(base,root,{recursive:true,errorOnExist:true,force:false});
const {inventoryPatchHash,baselineNames} = values['inventory-patch']
  ? await applyPrivateInventoryCopy(root,report.commit,values['inventory-patch']) : {};
const put = async (file,data)=>writeFile(join(root,file),JSON.stringify(data,null,2)+'\n');
const rights = await json(join(root,'src/image-rights.json'));
const lookup = await json(join(root,'src/model-images.json'));
const publishers = await json(join(root,'src/press-image-publishers.json'));
const presentation = await json(join(root,'src/image-presentation.json'));
const currentPublishers = await json('src/press-image-publishers.json');
const sha = bytes=>createHash('sha256').update(bytes).digest('hex');
for(const {image,bytes} of Object.values(models)) {
  const approved = currentPublishers[image.publisher_id];
  assert.deepEqual(approved.model_keys,[image.model_key]);
  assert.deepEqual(approved.approved_image_paths,[new URL(image.source_url).pathname]);
  assert.equal(approved.approved_asset_url,image.downloaded_from);
  assert.equal(approved.approved_source_sha256,image.source_content_sha256);
  const registered = image.model_key in lookup;
  if(liveG6&&image.model_key==='xpeng|g6') assert(registered,'The deployed G6 image must be registered');
  if(registered) {
    assert.deepEqual(publishers[image.publisher_id],approved);
    assert.equal(lookup[image.model_key],image.asset_url);
    const entries = rights.assets.filter(row=>row.model_key===image.model_key);
    assert.equal(entries.length,1);
    assert.equal(entries[0].asset_url,image.asset_url);
    assert.equal(entries[0].source_url,image.source_url);
    assert.equal(entries[0].content_sha256,image.content_sha256);
    const fit = presentation.models[image.model_key];
    assert.deepEqual([fit?.asset_url,fit?.content_sha256,fit?.status,fit?.object_fit],
      [image.asset_url,image.content_sha256,'approved','contain']);
    assert.equal(sha(await readFile(join(root,'public',image.asset_url.slice(1)))),image.content_sha256);
    continue;
  }
  assert(!rights.assets.some(row=>row.model_key===image.model_key));
  if(image.publisher_id in publishers) assert.deepEqual(publishers[image.publisher_id],approved);
  publishers[image.publisher_id] = approved;
  lookup[image.model_key] = image.asset_url;
  rights.assets.push({...image,changes:image.model_image_notice+' Endast storlek och format har anpassats.'});
  presentation.models[image.model_key] = {asset_url:image.asset_url,content_sha256:image.content_sha256,
    status:'approved',reviewed_at:image.reviewed_at,object_position:'center',object_fit:'contain',style:'manufacturer_press_photo'};
  await writeFile(join(root,'public',image.asset_url.slice(1)),bytes,{flag:'wx'});
}
await put('src/press-image-publishers.json',publishers);
await put('src/image-rights.json',rights);
await put('src/model-images.json',lookup);
await put('src/image-presentation.json',presentation);
await put('public/data/public_ev_variants.json',{status:'isolated_preview_only',publication_approved:false,records:candidate});
const python = (name,...args)=>JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs',join(root,'scripts',name),...args],
  {encoding:'utf8',timeout:90000,windowsHide:true}));
python('prepare_responsive_images.py','--write');
assert(python('audit_image_rights.py','--check').all_documented);
assert.equal(python('verify_public_images.py').public_records,candidate.length);
const manifest = await json(join(root,'src/image-variants.json'));
const {vehicleSlug} = await import(pathToFileURL(join(root,'src/vehicle-names.js')).href);
const slug = row=>vehicleSlug(row.brand,row.model,row.variant_name);
assert.equal(new Set(candidate.map(slug)).size,candidate.length);
if(baselineNames) for(const row of candidate)
  assert.equal(slug(row),baselineNames.vehicleSlug(row.brand,row.model,row.variant_name));

const config = {root,configFile:false,envFile:false,base:'/',logLevel:'silent',build:{outDir:join(output,'dist')}};
await build({...config,plugins:[react()]});
const server = await preview({...config,preview:{host:'127.0.0.1',port:0,strictPort:true}});
const address = server.httpServer.address();
const origin = `http://127.0.0.1:${address.port}`;
const clean = text=>text.replace(/\s+/gu,' ').trim();
const sek = value=>clean(new Intl.NumberFormat('sv-SE').format(value))+' kr';
const number = value=>String(value).replace('.',',');
const attempts = [], errors = [];
const g9Media = [];
let noLegacyBadges = true;
let browser;
try {
  assert.equal(address.address,'127.0.0.1');
  browser = await launchQaBrowser();
  const context = await browser.newContext({serviceWorkers:'block'});
  await context.route('**/*',route=>{
    const request = route.request(), url = new URL(request.url());
    return url.origin===origin&&request.method()==='GET'&&!url.pathname.startsWith('/api/')?route.continue():route.abort();
  });
  const localCatalog = await context.request.get(origin+'/data/public_ev_variants.json');
  assert(localCatalog.ok());
  assert.equal(catalogHash((await localCatalog.json()).records),report.candidate_sha256);
  for(const {image} of Object.values(models)) {
    const files = manifest[image.asset_url];
    assert.equal(files.source_sha256,image.content_sha256);
    assert.deepEqual(files.variants.map(row=>row.width),[480,800,1280]);
    for(const asset of [{url:image.asset_url,sha256:image.content_sha256},...files.variants]) {
      const res = await context.request.get(origin+asset.url);
      assert(res.ok());
      assert.equal(sha(await res.body()),asset.sha256);
      if(image.model_key==='xpeng|g9') g9Media.push({url:asset.url,sha256:asset.sha256});
    }
  }
  const page = await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  const loadVariant = async(row,width)=>{
    await page.setViewportSize({width,height:900});
    const res = await page.goto(origin+'/bilar/'+slug(row)+'/',{waitUntil:'networkidle'});
    assert(res?.ok());
    const hero = page.locator('.vehicleDetailHero');
    const title = hero.locator('h1');
    await title.waitFor();
    assert.match(clean(await title.innerText()),new RegExp('^XPENG '+row.model+'\\b','i'));
    assert.equal(clean(await title.locator('span').innerText()),row.variant_name);
    const rendered = await hero.locator('.vehicleHeroMedia img').evaluate(async img=>{
      await img.decode();
      return {src:new URL(img.currentSrc).pathname,width:img.naturalWidth,fit:getComputedStyle(img).objectFit};
    });
    const image = models[row.model].image;
    const actual = manifest[image.asset_url].variants.find(asset=>asset.url===rendered.src);
    assert(actual && rendered.width>0,'Wrong or missing vehicle image: '+row.variant_name);
    assert.equal(rendered.fit,'contain');
    if(width<=390) assert.equal(actual.width,480);
    return {hero,loaded:rendered.src};
  };
  await loadVariant(models.G6.rows[0],390);
  for(const row of models.G9.rows) for(const width of [320,390,768,1440]) {
    const {hero,loaded} = await loadVariant(row,width);
    const stats = clean(await hero.locator('.vehicleHeroStats').innerText());
    for(const text of [sek(row.price_sek),`${row.wltp_range_km} km`,`${row.dc_charge_kw} kW`,`${row.tow_kg} kg`])
      assert(stats.includes(text),'Missing exact hero value: '+text);
    const layout = await page.evaluate(()=>{
      const box = selector=>document.querySelector(selector).getBoundingClientRect();
      return {overflow:document.documentElement.scrollWidth>innerWidth,
        separate:box('.vehicleHeroCopy').top>=box('.vehicleHeroMedia').bottom-1};
    });
    assert(!layout.overflow,'Horizontal page overflow');
    if(width<=800) assert(layout.separate,'Mobile text overlaps the press image');
    if(width===390||width===1440) await page.screenshot({path:join(output,`${slug(row)}-${width}.png`)});
    const fullText = clean(await page.locator('main').innerText());
    noLegacyBadges &&= !inventoryBadge.test(fullText);
    if(inventoryPatchHash) assert.doesNotMatch(fullText,inventoryBadge);
    for(const text of [`${number(row.battery_kwh)} kWh`,`${number(row.wltp_consumption_kwh_100km)} kWh/100 km`])
      assert(fullText.includes(text),'Missing exact technical detail: '+text);
    const details = page.locator('#bilkallor');
    await details.locator('summary').click();
    noLegacyBadges &&= !inventoryBadge.test(await details.innerText());
    if(inventoryPatchHash) assert.doesNotMatch(await details.innerText(),inventoryBadge);
    assert.equal(await details.getByRole('link',{name:/(?:Pris|Prisk\u00e4lla): XPENG Sverige/i}).getAttribute('href'),row.price_source_url);
    assert.match(await details.innerText(),/Pressbild av G9 Black Edition/);
    assert.equal(await page.getByRole('link',{name:/^Foto: XPENG Sverige$/i}).first().getAttribute('href'),models.G9.image.source_url);
    attempts.push({variant:row.variant_name,width,photo:loaded});
  }
  const compareRow = models.G9.rows[0];
  await loadVariant(compareRow,390);
  await page.getByRole('button',{name:'L\u00e4gg till i j\u00e4mf\u00f6relse',exact:true}).first().click();
  await page.getByRole('button',{name:'J\u00e4mf\u00f6r nu'}).click();
  await page.waitForURL(url=>url.pathname.replace(/\/$/,'')==='/jamfor');
  await page.getByText(compareRow.variant_name,{exact:false}).first().waitFor();
  assert.deepEqual(errors,[]);
} finally {
  await browser?.close();
  await new Promise((done,reject)=>server.httpServer.close(error=>error?reject(error):done()));
}
const result = {status:'g9_private_ui_passed',source_commit:report.commit,private_variants:candidate.length,
  candidate_sha256:report.candidate_sha256,g6_evidence:g6Evidence,g9_media:g9Media,no_legacy_badges:noLegacyBadges,
  previous_variants_preserved:baseline.length,exact_photos:true,g6_photo_separate:true,
  ...(inventoryPatchHash?{inventory_patch_sha256:inventoryPatchHash,unchanged_vehicle_urls:candidate.length}:{}),
  responsive_checks:attempts,compared_from_detail:true,production_writes:0,publication_approved:false};
await writeFile(join(output,'ui-report.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({...result,output}));
