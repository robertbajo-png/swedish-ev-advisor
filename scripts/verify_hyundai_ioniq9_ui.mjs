import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {cp,mkdtemp,readFile,realpath,writeFile} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import react from '@vitejs/plugin-react';
import {build,preview} from 'vite';
import {launchQaBrowser} from './qa_browser.mjs';
import {MODEL,VARIANT} from './hyundai_ioniq9_publication.mjs';
import {publicationHash} from './new_model_publication.mjs';
import {catalogHash,normalizeCatalog,variantKey} from './sync_public_catalog.mjs';
import {MANUFACTURER_FROM_PRICE,priceTypeLabel} from '../src/price-evidence.js';
import {vehicleSlug} from '../src/vehicle-names.js';

const {values}=parseArgs({options:{readback:{type:'string'}}});
const json=async file=>JSON.parse(await readFile(file,'utf8'));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const release=await realpath('data/local/release-data');
assert.equal(release,join(await realpath('.'),'data','local','release-data'));
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(release));
const dir=await realpath(values.readback);
assert.equal(dir,resolve(values.readback));
assert.equal(dirname(dir),release);
assert.match(basename(dir),/^hyundai-ioniq9-local-[a-z0-9_]+$/i);
const readback=await json(join(dir,'report.json'));
assert.deepEqual([readback.status,readback.publication_approved,readback.production_writes],['ioniq9_local_insertion_verified',false,0]);
const plan=await json(join(dir,'plan.json'));
assert.equal(publicationHash(plan),readback.plan_sha256);
const archived=join(dir,'main-source');
const original=normalizeCatalog((await json(join(archived,'public/data/public_ev_variants.json'))).records);
const candidate=normalizeCatalog((await json(join(dir,'candidate-catalog.json'))).records);
assert.deepEqual([catalogHash(original),catalogHash(candidate)],[readback.baseline_sha256,readback.candidate_sha256]);
const old=new Set(original.map(variantKey));
assert.deepEqual(candidate.filter(row=>old.has(variantKey(row))),original);
const additions=candidate.filter(row=>!old.has(variantKey(row)));
assert.equal(additions.length,1);
const [row]=additions;
assert.deepEqual([row.brand,row.model,row.variant_name,row.price_type],[MODEL.brand,MODEL.model,VARIANT,MANUFACTURER_FROM_PRICE]);
const output=await mkdtemp(join(dir,'ui-')),root=join(output,'source');
await cp(archived,root,{recursive:true,errorOnExist:true,force:false});
const write=(file,data)=>writeFile(join(root,file),JSON.stringify(data,null,2)+'\n');
const image=plan.image;
assert.equal(row.image_url,image.asset_url);
const policy=(await json('src/press-image-publishers.json'))[image.publisher_id];
const publishers=await json(join(root,'src/press-image-publishers.json'));
assert(!publishers[image.publisher_id]);
publishers[image.publisher_id]=policy;
await write('src/press-image-publishers.json',publishers);
const models=await json(join(root,'src/model-images.json'));
assert(!(image.model_key in models));
models[image.model_key]=image.asset_url;
await write('src/model-images.json',models);
const rights=await json(join(root,'src/image-rights.json'));
assert(!rights.assets.some(asset=>asset.model_key===image.model_key));
rights.assets.push({...image,changes:'Of\u00f6r\u00e4ndrad originalbild och pressrummets helbild.'});
await write('src/image-rights.json',rights);
const position=await json(join(root,'src/image-presentation.json'));
position.models[image.model_key]={asset_url:image.asset_url,content_sha256:image.content_sha256,status:'approved',
  reviewed_at:image.reviewed_at,object_position:'center',object_fit:'contain',style:'manufacturer_press_photo'};
await write('src/image-presentation.json',position);
const web=policy.publisher_responsive_variants[0];
const assetName=basename(image.asset_url,'.jpg');
const verifiedAssets=[
  {name:'ioniq9-reviewed-original.jpg',url:image.asset_url,sha256:image.content_sha256},
  {name:'ioniq9-reviewed-746.webp',url:'/media/responsive/'+assetName+'-746.webp',sha256:web.sha256},
];
for(const asset of verifiedAssets){
  const bytes=await readFile(join(release,asset.name));
  assert.equal(sha(bytes),asset.sha256);
  await writeFile(join(root,'public',asset.url.slice(1)),bytes,{flag:'wx'});
}
await cp('src/spec-qualifications.js',join(root,'src/spec-qualifications.js'),{force:true});
await write('public/data/public_ev_variants.json',{status:'isolated_preview_only',publication_approved:false,records:candidate});
const python=(script,...args)=>JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs',join(root,'scripts',script),...args],
  {encoding:'utf8',timeout:180000,windowsHide:true}));
python('prepare_responsive_images.py','--write');
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
  for(const asset of verifiedAssets){
    const res=await context.request.get(origin+asset.url);
    assert(res.ok());
    assert.equal(sha(await res.body()),asset.sha256);
  }
  const page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  for(const width of [320,390,1440]){
    await page.setViewportSize({width,height:900});
    assert((await page.goto(origin+'/bilar/'+slug(row)+'/',{waitUntil:'networkidle'})).ok());
    const hero=page.locator('.vehicleDetailHero');
    assert.match(flat(await hero.locator('h1').innerText()),/Hyundai Ioniq 9.*Advanced AWD 7-sits MY27/i);
    const photo=await hero.locator('.vehicleHeroMedia img').evaluate(async img=>{
      await img.decode();
      return {path:new URL(img.currentSrc).pathname,fit:getComputedStyle(img).objectFit,width:img.naturalWidth};
    });
    assert(verifiedAssets.some(asset=>asset.url===photo.path)&&photo.fit==='contain'&&photo.width>0,
      'Unexpected rendered IONIQ 9 image: '+JSON.stringify(photo));
    const stats=flat(await hero.locator('.vehicleHeroStats').innerText());
    for(const value of [priceTypeLabel(MANUFACTURER_FROM_PRICE),'850 900 kr','606 km','233 kW','2500 kg'])assert(stats.includes(value),value);
    const schema=JSON.parse(await page.locator('script[data-jsonld="page"]').textContent());
    assert(!schema.offers,'A starting price is not a fixed product offer');
    const detail=flat(await page.locator('#specifikationer').innerText());
    for(const value of ['338 liter','10,5 kW','bromsat'])assert(detail.includes(value),value);
    assert.match(await page.locator('.vehicleSpecNote').first().innerText(),/20-tumshjul/);
    assert.equal(await page.getByRole('link',{name:/^Foto: Hyundai Motor Sweden/}).first().getAttribute('href'),image.source_url);
    const layout=await page.evaluate(()=>{
      const rect=selector=>document.querySelector(selector).getBoundingClientRect();
      return {overflow:document.documentElement.scrollWidth>innerWidth,
        separate:rect('.vehicleHeroCopy').top>=rect('.vehicleHeroMedia').bottom-1};
    });
    assert(!layout.overflow);
    if(width<800)assert(layout.separate,'Mobile copy overlaps the press photo');
    await page.screenshot({path:join(output,'ioniq9-'+width+'.png')});
    checks.push({viewport:width,asset:photo.path});
  }
  await page.getByRole('button',{name:'L\u00e4gg till i j\u00e4mf\u00f6relse',exact:true}).first().click();
  await page.getByRole('button',{name:'J\u00e4mf\u00f6r nu'}).click();
  await page.waitForURL(url=>url.pathname.replace(/\/$/,'')==='/jamfor');
  const ev9=original.find(car=>car.brand==='Kia'&&car.model==='Ev9'&&car.seats===7);
  assert(ev9,'Need an incumbent seven-seat comparison model');
  await page.getByRole('combobox',{name:'L\u00e4gg till en bil'}).selectOption(slug(ev9));
  const table=page.locator('.comparisonTable table');
  assert.match(await table.innerText(),/Hyundai Ioniq 9/i);
  assert.match(await table.innerText(),/Kia EV9/i);
  const ranges=table.getByRole('row').filter({has:page.getByRole('rowheader',{name:/^WLTP-/})});
  assert((await ranges.getByRole('cell').allTextContents()).map(flat).includes('606 km'));
  await page.setViewportSize({width:390,height:900});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:join(output,'comparison-390.png')});
  assert.deepEqual(errors,[]);
}finally{
  await browser?.close();
  await new Promise((done,reject)=>server.httpServer.close(error=>error?reject(error):done()));
}
const report={status:'ioniq9_private_ui_verified',output,checks,comparison:true,existing_records:original.length,
  publication_approved:false,production_writes:0,paid_calls:0};
await writeFile(join(output,'ui-report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(report));
