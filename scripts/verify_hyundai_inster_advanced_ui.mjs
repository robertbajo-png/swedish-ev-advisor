import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {cp,mkdir,mkdtemp,readFile,realpath,writeFile} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import react from '@vitejs/plugin-react';
import {build,preview} from 'vite';
import {launchQaBrowser} from './qa_browser.mjs';
import * as inster from './hyundai_inster_advanced_publication.mjs';
import * as macan from './porsche_macan_publication.mjs';
import * as lexus from './lexus_rz_publication.mjs';
import * as touring from './toyota_bz4x_touring_publication.mjs';
import {MACAN_MODEL} from './porsche_macan_scope.mjs';
import {catalogWithComparableTimes} from './isolated_catalog_review.mjs';
import {catalogHash,compareCatalogs,normalizeCatalog,variantKey} from './sync_public_catalog.mjs';
import {MANUFACTURER_FROM_PRICE,priceTypeLabel} from '../src/price-evidence.js';
import {vehicleSlug} from '../src/vehicle-names.js';

const {values}=parseArgs({options:{readback:{type:'string'},photo:{type:'string'},macan:{type:'boolean'},lexus:{type:'boolean'},touring:{type:'boolean'}}});
assert([values.macan,values.lexus,values.touring].filter(Boolean).length<=1);
const isMacan=values.macan===true;
const isLexus=values.lexus===true;
const isTouring=values.touring===true;
const registeredPhoto=isTouring||isLexus||isMacan;
const profile=isTouring?{
  ...touring,id:'touring',name:'Toyota bZ4X Touring',price:569900,range:'591 km',dc:'150 kW',tow:'750 kg',
  formattedPrice:'569 900 kr',specs:['669 liter','11 kW','14 kWh/100 km','74,7 kWh','bruttokapacitet','bromsat sl'],
  reportPrefix:'toyota-touring-local',localStatus:'touring_local_atomic_rehearsal_verified',verifiedStatus:'touring_private_ui_verified',
}:isLexus?{
  ...lexus,id:'lexus',name:'Lexus RZ',price:599000,range:'567 km',dc:'150 kW',tow:'750 kg',
  formattedPrice:'599 000 kr',specs:['586 liter','22 kW','14,5 kWh/100 km','150 kW','bruttokapacitet','draganordning'],
  reportPrefix:'lexus-rz-local',localStatus:'lexus_local_atomic_rehearsal_verified',verifiedStatus:'lexus_private_ui_verified',
}:isMacan?{
  MODEL:MACAN_MODEL,VARIANT:macan.variant,facts:macan.facts,policy:macan.policy,
  id:'macan',name:'Porsche Macan',price:970000,range:'642 km',dc:'270 kW',tow:'2000 kg',
  formattedPrice:'970 000 kr',specs:['518 liter','11 kW','16,7 kWh/100 km','270 kW','bruttokapacitet','tillvald dragkrok'],
  reportPrefix:'porsche-macan-local',photoPrefix:'macan-licensed-model-photo',
  localStatus:'macan_local_atomic_rehearsal_verified',verifiedStatus:'macan_private_ui_verified',
}:{
  ...inster,id:'inster',name:'Hyundai Inster',price:377900,range:'360 km',dc:'85,3 kW',tow:'0 kg',
  formattedPrice:'377 900 kr',specs:['238 liter','351 liter','10,5 kW','15,1 kWh/100 km','85,3 kW','0 kg'],
  reportPrefix:'inster-advanced-local',photoPrefix:'inster-advanced-licensed-photo',
  localStatus:'inster_advanced_atomic_local_verified',verifiedStatus:'inster_private_ui_verified',
};
const {MODEL,VARIANT,facts,policy}=profile;
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
const dir=await privatePacket(values.readback,profile.reportPrefix);
assert(!(isLexus||isTouring)||!values.photo);
const photoDir=isLexus||isTouring?null:await privatePacket(values.photo,profile.photoPrefix);
const report=await json(join(dir,'report.json'));
assert.deepEqual([report.status,report.publication_approved,report.production_writes,report.paid_calls],
  [profile.localStatus,false,0,0]);
const candidateFile=await json(join(dir,'candidate-catalog.json'));
const candidate=normalizeCatalog(candidateFile.records);
assert.deepEqual([candidateFile.status,candidateFile.publication_approved,catalogHash(candidate)],
  ['local_only',false,report.candidate_sha256]);
const original=normalizeCatalog((await json('public/data/public_ev_variants.json')).records);
const old=new Set(original.map(variantKey));
assert(compareCatalogs(catalogWithComparableTimes(original),catalogWithComparableTimes(candidate.filter(row=>old.has(variantKey(row))))).ok,
  'An incumbent catalog entry changed in the test readback');
const additions=candidate.filter(row=>!old.has(variantKey(row)));
assert.equal(additions.length,1);
const [row]=additions;
assert.deepEqual([row.brand,row.model,row.variant_name,row.price_sek,row.price_type,row.source_url],
  [MODEL.brand,MODEL.model,VARIANT,profile.price,MANUFACTURER_FROM_PRICE,policy.primaryUrl]);
for(const [field,value] of Object.entries(facts))assert.equal(row[field],value,field);

const packet=photoDir?await json(join(photoDir,'manifest.json')):null;
if(packet)assert.deepEqual([packet.status,packet.publication_approved,packet.production_writes],
  [isMacan?'private_reviewed_model_asset':'inster_licensed_model_photo_prepared_private',false,0]);
const photoPolicy=await json(isTouring?'src/toyota-touring-photo-policy.json':isLexus?'src/lexus-rz-photo-policy.json':isMacan?
  'src/porsche-macan-photo-policy.json':'src/inster-photo-policy.json');
const image=registeredPhoto
  ? (await json('src/image-rights.json')).assets.find(asset=>asset.model_key===policy.imageKey)
  : packet.image_rights;
const responsive=registeredPhoto?(await json('src/image-variants.json'))[image.asset_url]:packet.responsive;
for(const [key,value] of Object.entries(photoPolicy))assert.deepEqual(image[key],value,key);
assert.equal(image.asset_url,row.image_url);
assert.equal(responsive.source_sha256,policy.imageHash);
assert.deepEqual(responsive.variants.map(asset=>asset.width),[480,800,1280]);
const assets=[{url:image.asset_url,sha256:policy.imageHash},...responsive.variants];
const output=await mkdtemp(join(dir,'ui-')),root=join(output,'source'),archive=join(output,'source.tar');
await mkdir(root);
execFileSync('git',['archive','--format=tar','--output='+archive,'HEAD'],{windowsHide:true});
execFileSync('tar',['-xf',archive,'-C',root],{windowsHide:true});
for(const file of ['src/main.jsx','src/spec-qualifications.js','src/vehicle-names.js'])await cp(file,join(root,file));
async function edit(file,update){
  const path=join(root,file);
  const data=await json(path);
  update(data);
  await writeFile(path,JSON.stringify(data,null,2)+'\n');
}
function include(data,key,value){
  if(key in data)assert.deepEqual(data[key],value,'Registered Inster media differs from the reviewed packet');
  else data[key]=value;
}
await edit('src/model-images.json',data=>include(data,policy.imageKey,image.asset_url));
await edit('src/image-rights.json',data=>{
  const entries=data.assets.filter(asset=>asset.model_key===policy.imageKey);
  if(entries.length)assert.deepEqual(entries,[image]);
  else data.assets.push(image);
});
await edit('src/image-variants.json',data=>include(data,image.asset_url,responsive));
const touringPresentation=isTouring?(await json('src/image-presentation.json')).models[policy.imageKey]:null;
if(touringPresentation||!registeredPhoto)await edit('src/image-presentation.json',data=>{
  if(touringPresentation){include(data.models,policy.imageKey,touringPresentation);return;}
  include(data.models,policy.imageKey,{status:'approved',asset_url:image.asset_url,content_sha256:policy.imageHash,
    reviewed_at:image.reviewed_at,object_fit:'contain',object_position:'center',style:'licensed_model_photo'});
});
for(const [index,asset] of assets.entries()){
  assert.equal(asset.url,index===0?photoPolicy.asset_url:
    '/media/responsive/'+basename(photoPolicy.asset_url,'.jpg')+'-'+asset.width+'.webp');
  const relative=asset.url.slice(1);
  const bytes=await readFile(join(photoDir??'.','public',relative));
  assert.equal(sha(bytes),asset.sha256);
  const dest=join(root,'public',relative);
  try{await writeFile(dest,bytes,{flag:'wx'});}
  catch(error){
    if(error.code!=='EEXIST')throw error;
    assert.equal(sha(await readFile(dest)),asset.sha256,'Registered Inster image bytes changed');
  }
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
    assert(heading.includes(profile.name)&&heading.includes(VARIANT),heading);
    const displayed=await hero.locator('.vehicleHeroMedia img').evaluate(async img=>{
      await img.decode();
      return {path:new URL(img.currentSrc).pathname,fit:getComputedStyle(img).objectFit,width:img.naturalWidth};
    });
    assert(assets.some(asset=>asset.url===displayed.path)&&displayed.fit==='contain'&&displayed.width>0,
      'Unexpected rendered vehicle photo: '+JSON.stringify(displayed));
    const stats=flat(await hero.locator('.vehicleHeroStats').innerText());
    for(const value of [priceTypeLabel(MANUFACTURER_FROM_PRICE),profile.formattedPrice,profile.range,profile.dc,profile.tow])
      assert(stats.includes(value),stats+' lacks '+value);
    assert((await hero.locator('.vehicleHeroDescription').innerText()).includes(profile.dc));
    const schema=JSON.parse(await page.locator('script[data-jsonld="page"]').textContent());
    assert(!schema.offers,'A starting price is not a fixed product offer');
    const detail=flat(await page.locator('#specifikationer').innerText());
    for(const value of profile.specs)
      assert(detail.includes(value),'Missing spec or qualification: '+value+' in '+detail);
    assert.equal(await page.locator('.vehicleImageNotice').first().innerText(),image.model_image_notice);
    const attribution=page.getByRole('link').filter({hasText:'Foto: '+image.author});
    assert.equal(await attribution.first().getAttribute('href'),image.source_url);
    const layout=await page.evaluate(()=>{
      const rect=selector=>document.querySelector(selector).getBoundingClientRect();
      return {overflow:document.documentElement.scrollWidth>innerWidth,
        separate:rect('.vehicleHeroCopy').top>=rect('.vehicleHeroMedia').bottom-1};
    });
    assert(!layout.overflow);
    if(width<800)assert(layout.separate,'Mobile copy overlaps the model photo');
    await page.screenshot({path:join(output,profile.id+'-'+width+'.png')});
    checks.push({viewport:width,asset:displayed.path});
  }
  await page.getByRole('button',{name:'L\u00e4gg till i j\u00e4mf\u00f6relse',exact:true}).first().click();
  await page.getByRole('button',{name:'J\u00e4mf\u00f6r nu'}).click();
  await page.waitForURL(url=>url.pathname.replace(/\/$/,'')==='/jamfor');
  const ev2=original.find(car=>car.brand==='Kia'&&car.model==='Ev2');
  assert(ev2,'Need a verified comparison model');
  await page.getByRole('combobox',{name:'L\u00e4gg till en bil'}).selectOption(slug(ev2));
  const table=page.locator('.comparisonTable table');
  assert((await table.innerText()).includes(profile.name));
  assert.match(await table.innerText(),/Kia EV2/i);
  const cells=async name=>table.getByRole('row').filter({has:page.getByRole('rowheader',{name})})
    .getByRole('cell').allTextContents();
  for(const [name,value] of [[/^DC-laddning$/,profile.dc],[/^WLTP-/,profile.range],[/^Dragvikt$/,profile.tow]])
    assert((await cells(name)).map(flat).includes(value),'Missing comparison metric: '+value);
  await page.setViewportSize({width:390,height:900});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:join(output,'comparison-390.png')});
  assert.deepEqual(errors,[]);
}finally{
  await browser?.close();
  await new Promise((done,reject)=>server.httpServer.close(error=>error?reject(error):done()));
}
const result={status:profile.verifiedStatus,output,checks,comparison:true,
  existing_records:original.length,catalog_sha256:catalogHash(candidate),publication_approved:false,production_writes:0,paid_calls:0};
await writeFile(join(output,'ui-report.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(result));
