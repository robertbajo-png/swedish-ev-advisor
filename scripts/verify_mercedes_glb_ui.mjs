import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {cp, mkdtemp, readFile, realpath, writeFile} from 'node:fs/promises';
import {basename, dirname, join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import react from '@vitejs/plugin-react';
import {build, preview} from 'vite';
import {readGlbImage, readPrivateGlbImage} from './mercedes_glb_publication.mjs';
import {publicationHash} from './new_model_publication.mjs';
import {launchQaBrowser} from './qa_browser.mjs';
import {catalogHash, normalizeCatalog, variantKey} from './sync_public_catalog.mjs';
import {MANUFACTURER_FROM_PRICE, priceTypeLabel} from '../src/price-evidence.js';

const {values}=parseArgs({options:{readback:{type:'string'},'press-web':{type:'string'}}});
assert(values.readback&&values['press-web'],'Supply --readback and --press-web private directories');
const repo=await realpath('.'), release=await realpath('data/local/release-data');
assert.equal(release,join(repo,'data','local','release-data'));
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
async function folder(request,prefix) {
  const dir=await realpath(request);
  assert.equal(dir,resolve(request));
  assert.equal(dirname(dir),release);
  assert.match(basename(dir),new RegExp('^'+prefix+'[a-z0-9_]+$','i'));
  return dir;
}
const dir=await folder(values.readback,'mercedes-glb-local-');
const media=await folder(values['press-web'],'mercedes-glb-press-web-');
const json=async file=>JSON.parse(await readFile(file,'utf8'));
const sha=body=>createHash('sha256').update(body).digest('hex');
const readback=await json(join(dir,'report.json'));
assert.deepEqual([readback.status,readback.variants,readback.publication_approved,readback.production_writes],
  ['glb_local_insertion_verified',2,false,0]);
const plan=await json(join(dir,'plan.json'));
assert.equal(publicationHash(plan),readback.plan_sha256);
const archived=join(dir,'main-source');
assert.equal(await realpath(archived),archived);
const old=normalizeCatalog((await json(join(archived,'public/data/public_ev_variants.json'))).records);
const candidate=normalizeCatalog((await json(join(dir,'candidate-catalog.json'))).records);
assert.equal(catalogHash(old),readback.baseline_sha256);
assert.equal(catalogHash(candidate),readback.candidate_sha256);
const keys=new Set(old.map(variantKey));
assert.deepEqual(candidate.filter(row=>keys.has(variantKey(row))),old);
const variants=candidate.filter(row=>!keys.has(variantKey(row)));
const image=readGlbImage(), original=readPrivateGlbImage(image);
assert.deepEqual(plan.image,image);
assert.equal(sha(original),image.content_sha256);
assert.equal(variants.length,2);
assert(variants.every(r=>r.brand==='Mercedes-Benz'&&r.model==='Glb'&&r.image_url===image.asset_url
  &&r.image_source_url===image.source_url&&r.price_type===MANUFACTURER_FROM_PRICE&&r.price_source_url!==r.source_url));
const output=await mkdtemp(join(dir,'ui-')), root=join(output,'source');
await cp(archived,root,{recursive:true,errorOnExist:true,force:false});
const overlays=['src/price-evidence.js','src/main.jsx','src/vehicle-ui.jsx','src/advisor-matching.js','src/decision-metrics.js',
  'src/tco.js','src/vehicle-names.js','src/spec-qualifications.js','scripts/audit_image_rights.py','scripts/prepare_responsive_images.py'];
const codeHashes={};
for(const file of overlays) {
  assert.equal(await realpath(join(repo,file)),join(repo,file));
  const bytes=await readFile(join(repo,file));
  await writeFile(join(root,file),bytes);
  codeHashes[file]=sha(bytes);
}
const publishers=await json(join(root,'src/press-image-publishers.json'));
const policy=(await json(join(repo,'src/press-image-publishers.json')))[image.publisher_id];
assert.equal(policy.approved_source_sha256,image.content_sha256);
publishers[image.publisher_id]=policy;
const pictures=await json(join(root,'src/model-images.json'));
assert(!(image.model_key in pictures));
pictures[image.model_key]=image.asset_url;
const rights=await json(join(root,'src/image-rights.json'));
assert(!rights.assets.some(asset=>asset.model_key===image.model_key));
rights.assets.push({...image,changes:'Originalfilen och pressrummets helbilder visas utan egen bearbetning.'});
const position=await json(join(root,'src/image-presentation.json'));
position.models[image.model_key]={asset_url:image.asset_url,content_sha256:image.content_sha256,status:'approved',
  reviewed_at:image.reviewed_at,object_position:'center',object_fit:'contain',style:'manufacturer_press_photo'};
const copy=async (file,bytes)=>writeFile(join(root,'public',file),bytes,{flag:'wx'});
await copy(image.asset_url.slice(1),original);
const web=(await json(join(media,'report.json'))).variants;
assert.deepEqual(web.map(({width,height,sha256,source_url})=>({width,height,sha256,source_url})),policy.publisher_responsive_variants);
for(const variant of web) {
  assert.equal(variant.file,basename(image.asset_url,'.jpg')+'-'+variant.width+'.webp');
  const path=join(media,variant.file);
  assert.equal(await realpath(path),path);
  const bytes=await readFile(path);
  assert.equal(sha(bytes),variant.sha256);
  await copy('media/responsive/'+variant.file,bytes);
}
const write=(file,body)=>writeFile(join(root,file),JSON.stringify(body,null,2)+'\n');
await write('src/press-image-publishers.json',publishers);
await write('src/model-images.json',pictures);
await write('src/image-rights.json',rights);
await write('src/image-presentation.json',position);
await write('public/data/public_ev_variants.json',{status:'isolated_preview_only',publication_approved:false,records:candidate});
const python=(script,...args)=>JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs',join(root,'scripts',script),...args],
  {encoding:'utf8',timeout:180000,windowsHide:true}));
const replay=JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs','scripts/mercedes_glb_press_web.py','--replay',media],
  {encoding:'utf8',timeout:90000,windowsHide:true}));
assert.equal(replay.original_sha256,image.content_sha256);
python('prepare_responsive_images.py','--write');
assert(python('audit_image_rights.py','--check').all_documented);
assert.equal(python('verify_public_images.py').public_records,candidate.length);
const responsive=(await json(join(root,'src/image-variants.json')))[image.asset_url];
assert.equal(responsive.source_sha256,image.content_sha256);
assert.deepEqual(responsive.variants.map(r=>r.width),[746,1782]);
const {vehicleSlug}=await import(pathToFileURL(join(root,'src/vehicle-names.js')).href);
const {vehicleSlug:oldSlug}=await import(pathToFileURL(join(archived,'src/vehicle-names.js')).href);
const slug=row=>vehicleSlug(row.brand,row.model,row.variant_name);
assert.equal(new Set(candidate.map(slug)).size,candidate.length);
for(const row of old)assert.equal(slug(row),oldSlug(row.brand,row.model,row.variant_name));
const config={root,configFile:false,envFile:false,base:'/',logLevel:'silent',build:{outDir:join(output,'dist')}};
await build({...config,plugins:[react()]});
const server=await preview({...config,preview:{host:'127.0.0.1',port:0,strictPort:true}});
const address=server.httpServer.address(),origin='http://127.0.0.1:'+address.port;
const flat=value=>value.replace(/\s+/gu,' ').trim();
const money=value=>flat(new Intl.NumberFormat('sv-SE').format(value))+' kr';
const label=priceTypeLabel(MANUFACTURER_FROM_PRICE);
const checks=[],errors=[];
let browser;
try {
  assert.equal(address.address,'127.0.0.1');
  browser=await launchQaBrowser();
  const context=await browser.newContext({serviceWorkers:'block',deviceScaleFactor:1});
  await context.route('**/*',route=>{
    const req=route.request(),url=new URL(req.url());
    return url.origin===origin&&req.method()==='GET'&&!url.pathname.startsWith('/api/')?route.continue():route.abort();
  });
  for(const asset of [{url:image.asset_url,sha256:image.content_sha256},...responsive.variants]) {
    const response=await context.request.get(origin+asset.url);
    assert(response.ok());
    assert.equal(sha(await response.body()),asset.sha256);
  }
  const page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  for(const width of [390,1440]) {
    await page.setViewportSize({width,height:900});
    for(const row of variants) {
      assert((await page.goto(origin+'/bilar/'+slug(row)+'/',{waitUntil:'networkidle'})).ok());
      const hero=page.locator('.vehicleDetailHero'),title=hero.locator('h1');
      assert.equal(flat((await title.innerText()).replace(row.variant_name.slice(4),'')),'Mercedes-Benz GLB');
      assert.equal(flat(await title.locator('span').innerText()),row.variant_name.slice(4));
      const loaded=await hero.locator('.vehicleHeroMedia img').evaluate(async img=>{
        await img.decode();
        return {path:new URL(img.currentSrc).pathname,width:img.naturalWidth,fit:getComputedStyle(img).objectFit};
      });
      assert.equal(loaded.path,responsive.variants[width===390?0:1].url);
      assert(loaded.width>0&&loaded.fit==='contain');
      const stats=flat(await hero.locator('.vehicleHeroStats').innerText());
      for(const value of [label,money(row.price_sek),row.wltp_range_km+' km','320 kW',row.tow_kg+' kg'])assert(stats.includes(value),value);
      assert.doesNotMatch(stats,/listpris|kampanjpris/i);
      const schema=JSON.parse(await page.locator('script[data-jsonld="page"]').textContent());
      assert(schema.additionalProperty?.some(p=>p.name===label&&p.value===row.price_sek));
      assert(!schema.offers,'A starting price must not be a product offer');
      const details=flat(await page.locator('#specifikationer').innerText());
      for(const value of ['85 kWh','11 kW','540 liter','bromsat','standardladdaren'])assert(details.includes(value),value);
      assert.match(await page.locator('.vehicleSpecNote').first().innerText(),/svenska grundversionen/);
      assert.equal(await page.getByRole('link',{name:/^Foto: Mercedes-Benz AG/}).first().getAttribute('href'),image.source_url);
      const layout=await page.evaluate(()=>{
        const rect=selector=>document.querySelector(selector).getBoundingClientRect();
        return {overflow:document.documentElement.scrollWidth>innerWidth,
          separate:rect('.vehicleHeroCopy').top>=rect('.vehicleHeroMedia').bottom-1};
      });
      assert(!layout.overflow);
      if(width===390)assert(layout.separate,'Mobile copy overlaps the press image');
      await page.screenshot({path:join(output,slug(row)+'-'+width+'.png')});
      checks.push({variant:row.variant_name,viewport:width,asset:loaded.path});
    }
  }
  await page.getByRole('button',{name:'L\u00e4gg till i j\u00e4mf\u00f6relse',exact:true}).first().click();
  await page.getByRole('button',{name:'J\u00e4mf\u00f6r nu'}).click();
  await page.waitForURL(url=>url.pathname.replace(/\/$/,'')==='/jamfor');
  await page.getByRole('combobox',{name:'L\u00e4gg till en bil'}).selectOption(slug(variants[0]));
  const table=page.locator('.comparisonTable table');
  for(const row of variants)assert.equal(await table.getByRole('columnheader',{name:'Mercedes-Benz '+row.variant_name,exact:true}).count(),1);
  const ranges=table.getByRole('row').filter({has:page.getByRole('rowheader',{name:/^WLTP-/})});
  assert.deepEqual((await ranges.getByRole('cell').allTextContents()).map(flat).sort(),['614 km','631 km']);
  const prices=table.getByRole('row').filter({has:page.getByRole('rowheader',{name:'Pris',exact:true})});
  assert.equal(await prices.locator('.bestCell').count(),0);
  assert.deepEqual((await prices.getByRole('cell').allTextContents()).map(flat).sort(),
    [619000,659000].map(price=>label+': '+money(price)));
  await page.getByRole('button',{name:'Skapa rapport',exact:true}).click();
  assert.match(await page.locator('.reportWinner').innerText(),/bara tekniska v\u00e4rden/);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:join(output,'comparison-1440.png')});
} finally {
  await browser?.close();
  await new Promise((done,reject)=>server.httpServer.close(error=>error?reject(error):done()));
}
const report={status:'glb_private_ui_verified',checks,catalog_sha256:readback.candidate_sha256,code_sha256:codeHashes,
  comparison:true,existing_routes_preserved:old.length,publication_approved:false,production_writes:0,paid_calls:0};
await writeFile(join(output,'ui-report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({...report,output}));
