import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {cp,mkdir,mkdtemp,readFile,realpath,writeFile} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import react from '@vitejs/plugin-react';
import {build,preview} from 'vite';
import {launchQaBrowser} from './qa_browser.mjs';
import {MODEL,VARIANT,facts,policy} from './hyundai_inster_advanced_publication.mjs';
import {catalogWithComparableTimes} from './isolated_catalog_review.mjs';
import {catalogHash,compareCatalogs,normalizeCatalog,variantKey} from './sync_public_catalog.mjs';
import {MANUFACTURER_FROM_PRICE,priceTypeLabel} from '../src/price-evidence.js';
import {vehicleSlug} from '../src/vehicle-names.js';

const {values}=parseArgs({options:{readback:{type:'string'},photo:{type:'string'}}});
const json=async file=>JSON.parse(await readFile(file,'utf8'));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const release=await realpath('data/local/release-data');
assert.equal(release,join(await realpath('.'),'data','local','release-data'));
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
async function privatePacket(value,prefix){
  assert(value);
  const path=await realpath(value);
  assert.equal(path,resolve(value));
  assert.equal(dirname(path),release);
  assert.match(basename(path),new RegExp('^'+prefix+'-[a-z0-9]+$','i'));
  return path;
}
const dir=await privatePacket(values.readback,'inster-advanced-local');
const photoDir=await privatePacket(values.photo,'inster-advanced-licensed-photo');
const report=await json(join(dir,'report.json'));
assert.deepEqual([report.status,report.publication_approved,report.production_writes,report.paid_calls],
  ['inster_advanced_atomic_local_verified',false,0,0]);
const candidateFile=await json(join(dir,'candidate-catalog.json'));
const candidate=normalizeCatalog(candidateFile.records);
assert.deepEqual([candidateFile.status,candidateFile.publication_approved,catalogHash(candidate)],
  ['local_only',false,report.candidate_sha256]);
const original=normalizeCatalog((await json('public/data/public_ev_variants.json')).records);
const old=new Set(original.map(variantKey));
assert(compareCatalogs(catalogWithComparableTimes(original),candidate.filter(row=>old.has(variantKey(row)))).ok,
  'An incumbent catalog entry changed in the Inster readback');
const additions=candidate.filter(row=>!old.has(variantKey(row)));
assert.equal(additions.length,1);
const [row]=additions;
assert.deepEqual([row.brand,row.model,row.variant_name,row.price_sek,row.price_type,row.source_url],
  [MODEL.brand,MODEL.model,VARIANT,377900,MANUFACTURER_FROM_PRICE,policy.primaryUrl]);
for(const [field,value] of Object.entries(facts))assert.equal(row[field],value,field);

const packet=await json(join(photoDir,'manifest.json'));
assert.deepEqual([packet.status,packet.publication_approved,packet.production_writes],
  ['inster_licensed_model_photo_prepared_private',false,0]);
const {image_rights:image,responsive}=packet;
const photoPolicy=await json('src/inster-photo-policy.json');
for(const [key,value] of Object.entries(photoPolicy))assert.deepEqual(image[key],value,key);
assert.equal(image.asset_url,row.image_url);
assert.equal(responsive.source_sha256,policy.imageHash);
assert.deepEqual(responsive.variants.map(asset=>asset.width),[480,800,1280]);
const assets=[{url:image.asset_url,sha256:policy.imageHash},...responsive.variants];
const output=await mkdtemp(join(dir,'ui-')),root=join(output,'source'),archive=join(output,'source.tar');
await mkdir(root);
execFileSync('git',['archive','--format=tar','--output='+archive,'HEAD'],{windowsHide:true});
execFileSync('tar',['-xf',archive,'-C',root],{windowsHide:true});
for(const file of ['src/main.jsx','src/spec-qualifications.js'])await cp(file,join(root,file));
async function edit(file,update){
  const path=join(root,file);
  const data=await json(path);
  update(data);
  await writeFile(path,JSON.stringify(data,null,2)+'\n');
}
await edit('src/model-images.json',data=>{
  assert(!(policy.imageKey in data));
  data[policy.imageKey]=image.asset_url;
});
await edit('src/image-rights.json',data=>{
  assert(!data.assets.some(asset=>asset.model_key===policy.imageKey));
  data.assets.push(image);
});
await edit('src/image-variants.json',data=>{
  assert(!(image.asset_url in data));
  data[image.asset_url]=responsive;
});
await edit('src/image-presentation.json',data=>{
  assert(!(policy.imageKey in data.models));
  data.models[policy.imageKey]={status:'approved',asset_url:image.asset_url,content_sha256:policy.imageHash,
    reviewed_at:image.reviewed_at,object_fit:'contain',object_position:'center',style:'licensed_model_photo'};
});
for(const [index,asset] of assets.entries()){
  assert.equal(asset.url,index===0?photoPolicy.asset_url:
    '/media/responsive/'+basename(photoPolicy.asset_url,'.jpg')+'-'+asset.width+'.webp');
  const relative=asset.url.slice(1);
  const bytes=await readFile(join(photoDir,'public',relative));
  assert.equal(sha(bytes),asset.sha256);
  await writeFile(join(root,'public',relative),bytes,{flag:'wx'});
}
await edit('public/data/public_ev_variants.json',data=>{
  Object.assign(data,{status:'isolated_preview_only',publication_approved:false,records:candidate});
});
const python=(script,...args)=>JSON.parse(execFileSync(process.execPath,
  ['scripts/run_python.mjs',join(root,'scripts',script),...args],{encoding:'utf8',timeout:120000,windowsHide:true}));
assert(python('audit_image_rights.py','--check').all_documented);
assert.equal(python('verify_public_images.py').public_records,candidate.length);
const config={root,configFile:false,envFile:false,base:'/',logLevel:'silent',build:{outDir:join(output,'dist')}};
await build({...config,plugins:[react()]});
const server=await preview({...config,preview:{host:'127.0.0.1',port:0,strictPort:true}});
const origin='http://127.0.0.1:'+server.httpServer.address().port;
const flat=value=>value.replace(/\s+/gu,' ').trim();
const slug=car=>vehicleSlug(car.brand,car.model,car.variant_name);
const checks=[],errors=[];
let browser;
try{
  browser=await launchQaBrowser();
  const context=await browser.newContext({serviceWorkers:'block'});
  await context.route('**/*',route=>{
    const req=route.request(),url=new URL(req.url());
    return url.origin===origin&&req.method()==='GET'&&!url.pathname.startsWith('/api/')?route.continue():route.abort();
  });
  for(const asset of assets){
    const response=await context.request.get(origin+asset.url);
    assert(response.ok());
    assert.equal(sha(await response.body()),asset.sha256);
  }
  const page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  for(const width of [320,390,1440]){
    await page.setViewportSize({width,height:900});
    assert((await page.goto(origin+'/bilar/'+slug(row)+'/',{waitUntil:'networkidle'})).ok());
    const hero=page.locator('.vehicleDetailHero');
    const heading=flat(await hero.locator('h1').innerText());
    assert(heading.includes('Hyundai Inster')&&heading.includes(VARIANT),heading);
    const displayed=await hero.locator('.vehicleHeroMedia img').evaluate(async img=>{
      await img.decode();
      return {path:new URL(img.currentSrc).pathname,fit:getComputedStyle(img).objectFit,width:img.naturalWidth};
    });
    assert(assets.some(asset=>asset.url===displayed.path)&&displayed.fit==='contain'&&displayed.width>0,
      'Unexpected rendered Inster photo: '+JSON.stringify(displayed));
    const stats=flat(await hero.locator('.vehicleHeroStats').innerText());
    for(const value of [priceTypeLabel(MANUFACTURER_FROM_PRICE),'377 900 kr','360 km','85,3 kW','0 kg'])
      assert(stats.includes(value),stats+' lacks '+value);
    assert((await hero.locator('.vehicleHeroDescription').innerText()).includes('85,3 kW'));
    const schema=JSON.parse(await page.locator('script[data-jsonld="page"]').textContent());
    assert(!schema.offers,'A starting price is not a fixed product offer');
    const detail=flat(await page.locator('#specifikationer').innerText());
    for(const value of ['238 liter','351 liter','10,5 kW','15,1 kWh/100 km','85,3 kW','0 kg'])
      assert(detail.includes(value),'Missing spec or qualification: '+value+' in '+detail);
    assert.equal(await page.locator('.vehicleImageNotice').first().innerText(),image.model_image_notice);
    assert.equal(await page.getByRole('link',{name:/^Foto: M 93/}).first().getAttribute('href'),image.source_url);
    const layout=await page.evaluate(()=>{
      const rect=selector=>document.querySelector(selector).getBoundingClientRect();
      return {overflow:document.documentElement.scrollWidth>innerWidth,
        separate:rect('.vehicleHeroCopy').top>=rect('.vehicleHeroMedia').bottom-1};
    });
    assert(!layout.overflow);
    if(width<800)assert(layout.separate,'Mobile copy overlaps the model photo');
    await page.screenshot({path:join(output,'inster-'+width+'.png')});
    checks.push({viewport:width,asset:displayed.path});
  }
  await page.getByRole('button',{name:'L\u00e4gg till i j\u00e4mf\u00f6relse',exact:true}).first().click();
  await page.getByRole('button',{name:'J\u00e4mf\u00f6r nu'}).click();
  await page.waitForURL(url=>url.pathname.replace(/\/$/,'')==='/jamfor');
  const ev2=original.find(car=>car.brand==='Kia'&&car.model==='Ev2');
  assert(ev2,'Need a verified comparison model');
  await page.getByRole('combobox',{name:'L\u00e4gg till en bil'}).selectOption(slug(ev2));
  const table=page.locator('.comparisonTable table');
  assert.match(await table.innerText(),/Hyundai Inster/i);
  assert.match(await table.innerText(),/Kia EV2/i);
  const cells=async name=>table.getByRole('row').filter({has:page.getByRole('rowheader',{name})})
    .getByRole('cell').allTextContents();
  for(const [name,value] of [[/^DC-laddning$/,'85,3 kW'],[/^WLTP-/,'360 km'],[/^Dragvikt$/,'0 kg']])
    assert((await cells(name)).map(flat).includes(value),'Missing comparison metric: '+value);
  await page.setViewportSize({width:390,height:900});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:join(output,'comparison-390.png')});
  assert.deepEqual(errors,[]);
}finally{
  await browser?.close();
  await new Promise((done,reject)=>server.httpServer.close(error=>error?reject(error):done()));
}
const result={status:'inster_private_ui_verified',output,checks,comparison:true,
  existing_records:original.length,catalog_sha256:catalogHash(candidate),publication_approved:false,production_writes:0,paid_calls:0};
await writeFile(join(output,'ui-report.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(result));
