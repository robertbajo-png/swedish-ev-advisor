import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cp, mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { build, preview } from 'vite';
import react from '@vitejs/plugin-react';
import { launchQaBrowser } from './qa_browser.mjs';
import { FACTS, MODEL, VARIANT, policy, readDriveImage } from './cupra_tavascan_drive_publication.mjs';
import { catalogHash, compareCatalogs, variantKey } from './sync_public_catalog.mjs';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';

const {values}=parseArgs({options:{readback:{type:'string'},'output-root':{type:'string'}}});
assert(values.readback,'Supply the private local readback directory');
const release=await realpath('data/local/release-data');
const folder=await realpath(values.readback);
assert.equal(folder,resolve(values.readback));
assert.equal(dirname(folder),release);
assert.match(basename(folder),/^cupra-tavascan-readback-[a-z0-9]+$/i);
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(folder));
const baselineRoot=join(folder,'main-source');
assert.equal(await realpath(baselineRoot),baselineRoot);
const outputRoot=values['output-root']?await realpath(values['output-root']):folder;
if(values['output-root']){
  assert.equal(outputRoot,resolve(values['output-root']));
  assert.match(outputRoot,/[\\/]data[\\/]local[\\/]release-data$/i);
  const inside=relative(outputRoot,folder);
  assert(inside&&!isAbsolute(inside)&&!inside.startsWith('..'));
}
const output=await mkdtemp(join(outputRoot,'tavascan-ui-'));
const root=join(output,'source');
await cp(baselineRoot,root,{recursive:true,errorOnExist:true,force:false});
const reviewedUi=await readFile(new URL('../src/main.jsx',import.meta.url),'utf8');
assert(!reviewedUi.includes('MarketStatusBadges'),'Reviewed UI still displays market-status badges');
await writeFile(join(root,'src/main.jsx'),reviewedUi);
const json=async path=>JSON.parse(await readFile(path,'utf8'));
const put=async (path,data)=>{
  const file=join(root,path);
  assert.equal(await realpath(file),file);
  await writeFile(file,JSON.stringify(data,null,2)+'\n');
};
const report=await json(join(folder,'report.json'));
assert.deepEqual([report.status,report.production_writes,report.publication_approved],['tavascan_drive_local_only_passed',0,false]);
const image=readDriveImage();
assert.deepEqual(image,report.image);
const candidate=await json(join(folder,'candidate-catalog.json'));
assert.equal(catalogHash(candidate.records),report.candidate_sha256);
const baseline=(await json(join(root,'public/data/public_ev_variants.json'))).records;
assert.equal(catalogHash(baseline),report.baseline_sha256);
const added=candidate.records.filter(row=>row.brand===MODEL.brand && row.model===MODEL.model);
policy.verifyPublic(added,{image,expected_model:{available_confirmed:report.added_variant.available_confirmed}});
const key=variantKey(report.added_variant);
assert.equal(variantKey(added[0]),key);
const retained=candidate.records.filter(row=>variantKey(row)!==key);
assert(compareCatalogs(catalogWithComparableTimes(baseline),catalogWithComparableTimes(retained)).ok,
  'The private candidate must preserve all prior public rows');
const rights=await json(join(root,'src/image-rights.json'));
const lookup=await json(join(root,'src/model-images.json'));
const publishers=await json(join(root,'src/press-image-publishers.json'));
const presentation=await json(join(root,'src/image-presentation.json'));
const reviewedPresentation=(await json('src/image-presentation.json')).models[image.model_key];
assert.deepEqual([reviewedPresentation.asset_url,reviewedPresentation.content_sha256,reviewedPresentation.object_fit],
  [image.asset_url,image.content_sha256,'contain']);
assert(!(image.model_key in presentation.models));
await put('src/image-presentation.json',{...presentation,models:{...presentation.models,[image.model_key]:reviewedPresentation}});
const approved=(await json('src/press-image-publishers.json'))[image.publisher_id];
assert.deepEqual(approved.model_keys,[image.model_key]);
assert.deepEqual(approved.approved_image_paths,[new URL(image.source_url).pathname]);
assert.equal(approved.approved_asset_url,image.downloaded_from);
assert.equal(approved.approved_source_sha256,image.source_content_sha256);
if(image.publisher_id in publishers) assert.deepEqual(publishers[image.publisher_id],approved);
assert(!rights.assets.some(row=>row.model_key===image.model_key));
assert(!(image.model_key in lookup));
await put('src/model-images.json',{...lookup,[image.model_key]:image.asset_url});
await put('src/press-image-publishers.json',{...publishers,[image.publisher_id]:approved});
await put('src/image-rights.json',{...rights,assets:[...rights.assets,{...image,changes:'Hela bildutsnittet bevaras. Endast storlek och format har anpassats.'}]});
await put('public/data/public_ev_variants.json',{...candidate,publication_approved:false});
await writeFile(join(root,'public',image.asset_url.slice(1)),policy.readPrivateImage(image),{flag:'wx'});
const python=(name,...args)=>JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs',join(root,'scripts',name),...args],
  {encoding:'utf8',timeout:90000,windowsHide:true}));
python('prepare_responsive_images.py','--write');
const audit=python('audit_image_rights.py','--check');
assert(audit.all_documented && audit.checks.some(row=>row.model_key===image.model_key && row.documented));
assert.equal(python('verify_public_images.py').public_records,candidate.records.length);
const manifest=(await json(join(root,'src/image-variants.json')))[image.asset_url];
assert.equal(manifest.source_sha256,image.content_sha256);
assert.deepEqual(manifest.variants.map(row=>row.width),[480,800,1280]);

const outDir=join(output,'candidate-build');
const config={root,configFile:false,envFile:false,base:'/',logLevel:'silent',build:{outDir}};
await build({...config,plugins:[react()]});
const server=await preview({...config,preview:{host:'127.0.0.1',port:0,strictPort:true}});
const address=server.httpServer.address();
assert.equal(address.address,'127.0.0.1');
const origin=`http://127.0.0.1:${address.port}`;
const runs=[];
const clean=text=>text.replace(/\s+/gu,' ').trim();
const sha=value=>createHash('sha256').update(value).digest('hex');
let browser;
try {
  const {vehicleSlug}=await import(pathToFileURL(join(root,'src/vehicle-names.js')).href);
  const slug=vehicleSlug(MODEL.brand,MODEL.model,VARIANT);
  browser=await launchQaBrowser();
  const context=await browser.newContext({serviceWorkers:'block'});
  await context.route('**/*',route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==origin || request.method()!=='GET' || url.pathname.startsWith('/api/')) return route.abort();
    return route.continue();
  });
  const renderedCatalog=await context.request.get(origin+'/data/public_ev_variants.json');
  assert(renderedCatalog.ok());
  assert.equal(catalogHash((await renderedCatalog.json()).records),report.candidate_sha256);
  for(const asset of [{url:image.asset_url,sha256:image.content_sha256},...manifest.variants]) {
    const resource=await context.request.get(origin+asset.url);
    assert(resource.ok());assert.equal(sha(await resource.body()),asset.sha256);
  }
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  for(const width of [320,390,768,1440]) {
    await page.setViewportSize({width,height:900});
    const response=await page.goto(`${origin}/bilar/${slug}/`,{waitUntil:'networkidle'});
    assert(response?.ok());
    const hero=page.locator('.vehicleDetailHero');
    await hero.locator('h1').waitFor();
    assert.equal(await page.locator('.marketStatusBadges').count(),0);
    assert.equal(await page.getByText(/Aktuell tillgänglighet är inte separat bekräftad/i).count(),0);
    assert.match(clean(await hero.locator('h1').innerText()),/^Cupra Tavascan\b/i);
    assert.equal(clean(await hero.locator('h1 span').innerText()),VARIANT);
    const stats=clean(await hero.locator('.vehicleHeroStats').innerText());
    for(const label of ['554 900 kr',`${FACTS.wltp_range_km} km`,`${FACTS.dc_charge_kw} kW`,`${FACTS.tow_kg} kg`])
      assert(stats.includes(label),label);
    const loaded=await hero.locator('.vehicleHeroMedia img').evaluate(async node=>{
      await node.decode();return {image:new URL(node.currentSrc).pathname,naturalWidth:node.naturalWidth,fit:getComputedStyle(node).objectFit};
    });
    const source=manifest.variants.find(asset=>asset.url===loaded.image);
    assert(source && loaded.naturalWidth>0,'Responsive press photo did not decode');
    assert.equal(loaded.fit,'contain','Show the whole press photo');
    if(width<=390) assert.equal(source.width,480);
    const credit=page.getByRole('link',{name:/^Foto: SEAT & CUPRA Danmark$/i}).first();
    assert.equal(await credit.getAttribute('href'),image.source_url);
    const layout=await page.evaluate(()=>{
      const box=selector=>document.querySelector(selector).getBoundingClientRect();
      return {overflow:document.documentElement.scrollWidth>innerWidth,
        separate:box('.vehicleHeroCopy').top>=box('.vehicleHeroMedia').bottom-1};
    });
    assert(!layout.overflow);
    if(width<=800) assert(layout.separate,'Mobile copy overlays the press photo');
    if([390,1440].includes(width)) await page.screenshot({path:join(output,`tavascan-${width}.png`)});
    const disclosure=page.locator('#bilkallor');
    await disclosure.locator('summary').click();
    const price=disclosure.getByRole('link',{name:/(?:Pris|Prisk\u00e4lla): CUPRA Sverige/});
    assert.equal(await price.getAttribute('href'),added[0].price_source_url);
    if(width===390) {
      const compare=hero.getByRole('button',{name:'Lägg till i jämförelse'});
      await compare.click();
      const selected=hero.getByRole('button',{name:'Tillagd i jämförelse'});
      assert.equal(await selected.getAttribute('aria-pressed'),'true');
      await selected.click();
      assert.equal(await compare.getAttribute('aria-pressed'),'false');
    }
    runs.push({width,image:loaded.image});
  }
  assert.deepEqual(errors,[]);
} finally {
  await browser?.close();
  await new Promise((done,reject)=>server.httpServer.close(error=>error?reject(error):done()));
}
const result={status:'private_ui_passed',records:candidate.records.length,real_built_catalog:true,real_image_files:true,
  plan_hash:report.plan_hash,candidate_sha256:report.candidate_sha256,
  media:[{url:image.asset_url,sha256:image.content_sha256},...manifest.variants.map(({url,sha256})=>({url,sha256}))],
  exact_editorial_credit:true,full_photo_frame:true,mobile_layout_checked:true,retail_badges_removed:true,
  mobile_comparison_checked:true,runs,production_writes:0,publication_approved:false};
await writeFile(join(output,'ui-report.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({...result,output}));
