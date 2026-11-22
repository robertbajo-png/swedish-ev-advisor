import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile,realpath} from 'node:fs/promises';
import {basename,dirname,join} from 'node:path';
import {parseArgs} from 'node:util';
import {parse} from 'parse5';
import {preview} from 'vite';
import {catalogHash} from './sync_public_catalog.mjs';
import {buildImagePlan,selectImageRegistryForPublic} from './model_image_sync.mjs';
import {launchQaBrowser} from './qa_browser.mjs';

const {values}=parseArgs({options:{'catalog-sha256':{type:'string'},variants:{type:'string'},'news-sha256':{type:'string'}}});
const source=await realpath('.');
assert.equal(basename(source),'source');
assert.match(basename(dirname(source)),/^glb-media-[a-z0-9]+$/i);
assert.equal(basename(dirname(dirname(source))),'release-data');
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(source));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const json=async file=>JSON.parse(await readFile(join(source,file),'utf8'));
const digest=/^[a-f0-9]{64}$/;
assert.match(values['catalog-sha256'],digest);
assert.match(values['news-sha256'],digest);
const original=await readFile('public/data/public_ev_variants.json');
assert.equal(sha(await readFile('dist/data/public_ev_variants.json')),sha(original));
const news=await readFile('dist/data/news_articles.json','utf8');
assert.equal(news,await readFile('public/data/news_articles.json','utf8'));
assert.equal(sha(news.replace(/\r\n/g,'\n')),values['news-sha256'],'Unexpected change to the archived news export');
const baseline=JSON.parse(original).records;
assert.equal(baseline.length,Number(values.variants));
assert.equal(catalogHash(baseline),values['catalog-sha256']);
const key=row=>[row.brand,row.model].map(v=>v.toLowerCase().replace(/[^a-z0-9]+/g,' ').trim()).join('|');
const glbKey='mercedes benz|glb';
assert(!baseline.some(row=>key(row)===glbKey));
const registry=await json('src/image-rights.json');
const rows=registry.assets.filter(asset=>asset.model_key===glbKey);
assert.equal(rows.length,1);
const [image]=rows;
assert.equal(image.author,'Mercedes-Benz AG');
assert.equal((await json('src/model-images.json'))[glbKey],image.asset_url);
const responsive=(await json('src/image-variants.json'))[image.asset_url];
assert.deepEqual([responsive.width,responsive.height,responsive.source_sha256],[5000,3333,image.content_sha256]);
assert.deepEqual(responsive.variants.map(row=>row.width),[746,1782]);
const assets=[{url:image.asset_url,sha256:image.content_sha256},...responsive.variants];
for(const {url,sha256} of assets) {
  assert.match(url,/^\/media\/(?:vehicles|responsive)\/mercedes-benz-glb-press-[a-f0-9]{12}(?:-\d+)?\.(?:jpg|webp)$/);
  assert.equal(sha(await readFile('public'+url)),sha256);
  assert.equal(sha(await readFile('dist'+url)),sha256);
}
const publicModels=[...new Map(baseline.map(row=>[key(row),{...row,id:key(row)}])).values()];
const draft={id:'private-glb',brand:'Mercedes-Benz',model:'Glb',validation_status:'draft'};
const all=[...publicModels,draft];
const before=buildImagePlan(all,publicModels,selectImageRegistryForPublic(publicModels,registry));
const after=buildImagePlan(all,all,selectImageRegistryForPublic(all,registry));
assert(!before.some(row=>row.id===draft.id));
assert.deepEqual(after.filter(row=>row.id!==draft.id),before);
assert.equal(after.find(row=>row.id===draft.id).image_url,image.asset_url);

const sitemap=await readFile('dist/sitemap.xml','utf8');
assert.doesNotMatch(sitemap,/\/bilar\/mercedes-benz-glb-/i);
const homepage=await readFile('dist/index.html','utf8');
const entries=[];
function visit(node){
  if(node.tagName==='script'){
    const attributes=Object.fromEntries(node.attrs.map(({name,value})=>[name,value]));
    if(attributes.type==='module'&&/^\/assets\/index-[a-zA-Z0-9_-]+\.js$/.test(attributes.src??''))entries.push(attributes.src);
  }
  for(const child of node.childNodes??[])visit(child);
}
visit(parse(homepage));
assert.equal(entries.length,1);
const entry=await readFile('dist'+entries[0]);
assert.match(entry.toString('utf8'),/manufacturer_from/,'Starting-price reader is missing');

const server=await preview({root:source,configFile:false,envFile:false,base:'/',logLevel:'silent',
  preview:{host:'127.0.0.1',port:0,strictPort:true}});
const address=server.httpServer.address(),origin='http://127.0.0.1:'+address.port;
let browser;
try {
  assert.equal(address.address,'127.0.0.1');
  browser=await launchQaBrowser();
  const context=await browser.newContext({serviceWorkers:'block'});
  await context.route('**/*',route=>{
    const req=route.request(),url=new URL(req.url());
    return url.origin===origin&&req.method()==='GET'&&!url.pathname.startsWith('/api/')?route.continue():route.abort();
  });
  for(const asset of assets) {
    const result=await context.request.get(origin+asset.url);
    assert.equal(result.status(),200);
    assert.equal(sha(await result.body()),asset.sha256);
  }
  const page=await context.newPage();
  assert((await page.goto(origin+'/bilar/',{waitUntil:'networkidle'})).ok());
  await page.getByRole('heading',{level:1}).waitFor();
  assert.equal(await page.locator('a[href*="/bilar/mercedes-benz-glb-"]').count(),0);
  for(const slug of ['mercedes-benz-glb-250-advanced-edition','mercedes-benz-glb-350-4matic-advanced-edition']){
    await page.goto(origin+'/bilar/'+slug+'/',{waitUntil:'networkidle'});
    await page.getByRole('heading',{name:'Bilen hittades inte.'}).waitFor();
    assert.equal(await page.locator('.vehicleDetailHero').count(),0);
  }
} finally {
  await browser?.close();
  await new Promise((done,reject)=>server.httpServer.close(error=>error?reject(error):done()));
}
console.log(JSON.stringify({status:'glb_media_support_build_verified_locally',catalog_sha256:catalogHash(baseline),
  variants:baseline.length,models:publicModels.length,assets,exact_glb_not_listed:true,glb_routes_not_found:true,
  no_glb_sitemap:true,staged_asset_excluded_from_sync:true,news_preserved:true,
  local_reader:{path:entries[0],sha256:sha(entry)},publication_approved:false,production_writes:0,paid_calls:0}));
