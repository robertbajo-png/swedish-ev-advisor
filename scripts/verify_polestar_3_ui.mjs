import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cp, mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import react from '@vitejs/plugin-react';
import { build, preview } from 'vite';
import { policy, readPolestar3Image } from './polestar_3_publication.mjs';
import { publicationHash } from './new_model_publication.mjs';
import { launchQaBrowser } from './qa_browser.mjs';
import { catalogHash, normalizeCatalog, variantKey } from './sync_public_catalog.mjs';
import { vehicleSlug } from '../src/vehicle-names.js';

const {values} = parseArgs({options: {readback: {type: 'string'}, 'publisher-media': {type:'string'},
  'short-output': {type:'boolean'}}});
assert(values.readback && values['publisher-media'], 'Supply private --readback and --publisher-media directories');
const repo = await realpath('.');
const evidence = await realpath('data/local/release-data');
assert.equal(evidence, join(repo, 'data', 'local', 'release-data'));
const dir = await realpath(values.readback);
assert.equal(dir, resolve(values.readback));
assert.equal(dirname(dir), evidence);
assert.match(basename(dir), /^polestar-3-local-[a-z0-9]+$/i);
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(dir));
const json = async path => JSON.parse(await readFile(path, 'utf8'));
const hash = body => createHash('sha256').update(body).digest('hex');
const [report, plan, baseline, snapshot] = await Promise.all([
  json(join(dir, 'report.json')), json(join(dir, 'plan.json')),
  json(join(dir, 'main-source/public/data/public_ev_variants.json')), json(join(dir, 'candidate-catalog.json')),
]);
assert.deepEqual([report.status, report.variants, report.publication_approved, report.production_writes],
  ['polestar_3_local_insertion_verified', 1, false, 0]);
assert.equal(publicationHash(plan), report.plan_sha256);
assert.equal(catalogHash(baseline.records), report.baseline_sha256);
assert.equal(catalogHash(snapshot.records), report.candidate_sha256);
const prior = new Set(baseline.records.map(variantKey));
assert.deepEqual(snapshot.records.filter(row => prior.has(variantKey(row))), normalizeCatalog(baseline.records));
const added = snapshot.records.filter(row => !prior.has(variantKey(row)));
assert.equal(added.length, 1);
const row = added[0], photo = readPolestar3Image();
assert.deepEqual(plan.image, photo);
assert.deepEqual([row.brand, row.model, row.variant_name, row.price_sek, row.wltp_range_km, row.image_url, row.price_source_hash],
  ['Polestar', '3', 'Performance', 999000, 601, photo.asset_url, plan.targets[0].draft.price_evidence.source_hash]);
const original = policy.readPrivateImage(photo);
assert.equal(hash(original), photo.content_sha256);
const publisherMedia = await realpath(values['publisher-media']);
assert.equal(publisherMedia, resolve(values['publisher-media']));
const publisherReview = JSON.parse(execFileSync(process.execPath,
  ['scripts/run_python.mjs','scripts/polestar_3_press_web.py','--replay', publisherMedia],
  {encoding:'utf8',timeout:30000,windowsHide:true}));
assert.equal(publisherReview.original_sha256, photo.content_sha256);
assert.equal(publisherReview.publication_approved, false);

const output = await mkdtemp(values['short-output'] ? join(evidence, 'polestar-ui-') : join(dir, 'ui-'));
const root = join(output, 'source');
await cp(join(dir, 'main-source'), root, {recursive:true, force:false, errorOnExist:true});
const uiFiles = ['src/main.jsx','src/vehicle-ui.jsx','src/vehicle-names.js','src/vehicles.css','src/spec-qualifications.js',
  'src/price-evidence.js','src/advisor-matching.js','src/decision-metrics.js','src/tco.js','src/press-image-publishers.json',
  'scripts/prepare_responsive_images.py'];
const uiCode = {};
for (const path of uiFiles) {
  assert.equal(await realpath(join(repo, path)), join(repo, path));
  const bytes = await readFile(path);
  uiCode[path] = hash(bytes);
  await writeFile(join(root, path), bytes);
}
const write = (file, body) => writeFile(join(root, file), JSON.stringify(body, null, 2) + '\n');
const rights = await json(join(root, 'src/image-rights.json'));
const images = await json(join(root, 'src/model-images.json'));
const presentation = await json(join(root, 'src/image-presentation.json'));
assert(!rights.assets.some(asset => asset.model_key === photo.model_key) && !(photo.model_key in images));
await writeFile(join(root, 'public', photo.asset_url.slice(1)), original, {flag:'wx'});
for (const item of publisherReview.variants) {
  const bytes = await readFile(join(publisherMedia, item.file));
  assert.equal(hash(bytes), item.sha256);
  await writeFile(join(root,'public','media','responsive',item.file), bytes, {flag:'wx'});
}
rights.assets.push({...photo, changes:'Originalfilen har inte redigerats.'});
images[photo.model_key] = photo.asset_url;
presentation.models[photo.model_key] = {asset_url:photo.asset_url, content_sha256:photo.content_sha256, status:'approved',
  reviewed_at:photo.reviewed_at, object_position:'center', object_fit:'contain', style:'manufacturer_press_photo'};
await write('src/image-rights.json', rights);
await write('src/model-images.json', images);
await write('src/image-presentation.json', presentation);
await write('public/data/public_ev_variants.json', snapshot);
const python = (script, ...args) => JSON.parse(execFileSync(process.execPath,
  ['scripts/run_python.mjs', join(root, 'scripts', script), ...args], {encoding:'utf8', timeout:120000, windowsHide:true}));
python('prepare_responsive_images.py', '--write');
assert(python('audit_image_rights.py', '--check').all_documented);
assert.equal(python('verify_public_images.py').public_records, snapshot.records.length);
const responsive = (await json(join(root, 'src/image-variants.json')))[photo.asset_url];
assert.deepEqual([responsive.width, responsive.height, responsive.source_sha256], [12302, 9227, photo.content_sha256]);
assert.deepEqual(responsive.variants, publisherReview.variants.map(item =>
  ({url:'/media/responsive/' + item.file,width:item.width,sha256:item.sha256})));

const config = {root, configFile:false, envFile:false, base:'/', logLevel:'silent', build:{outDir:join(output, 'dist')}};
await build({...config, plugins:[react()]});
const server = await preview({...config, preview:{host:'127.0.0.1', port:0, strictPort:true}});
const address = server.httpServer.address();
const checks = [], errors = [];
let browser;
try {
  assert.equal(address.address, '127.0.0.1');
  const origin = 'http://127.0.0.1:' + address.port;
  browser = await launchQaBrowser();
  const context = await browser.newContext({serviceWorkers:'block'});
  await context.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    return url.origin === origin && request.method() === 'GET' && !url.pathname.startsWith('/api/') ? route.continue() : route.abort();
  });
  for (const asset of [{url:photo.asset_url,sha256:photo.content_sha256}, ...responsive.variants]) {
    const imageResponse = await context.request.get(origin + asset.url);
    assert(imageResponse.ok());
    assert.equal(hash(await imageResponse.body()), asset.sha256);
  }
  const page = await context.newPage(), pageImages = [];
  page.on('request', request => { if (request.resourceType() === 'image') pageImages.push(new URL(request.url()).pathname); });
  page.on('pageerror', error => errors.push(error.message));
  const slug = vehicleSlug(row.brand, row.model, row.variant_name);
  for (const width of [390, 1440]) {
    await page.setViewportSize({width, height:900});
    assert((await page.goto(origin + '/bilar/' + slug + '/', {waitUntil:'networkidle'})).ok());
    const hero = page.locator('.vehicleDetailHero');
    assert.match(await hero.locator('h1').innerText(), /Polestar 3\s*Performance/);
    const loaded = await hero.locator('.vehicleHeroMedia img').evaluate(async img => {
      await img.decode();
      return {src:new URL(img.currentSrc).pathname, width:img.naturalWidth, fit:getComputedStyle(img).objectFit};
    });
    assert.equal(loaded.fit, 'contain');
    assert(loaded.width > 0 && responsive.variants.some(asset => asset.url === loaded.src));
    const specs = (await hero.locator('.vehicleHeroStats').innerText()).replace(/\s+/gu, ' ');
    for (const value of ['999 000 kr','524\u2013601 km','350 kW','2200 kg']) assert(specs.includes(value), value);
    assert.match(await page.locator('#specifikationer').innerText(), /20,5\u201323,1 kWh\/100 km/);
    assert.equal(await page.getByRole('link', {name:/^Foto: Polestar/}).first().getAttribute('href'), photo.source_url);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    if (width < 800) assert(await hero.evaluate(element => element.querySelector('.vehicleHeroCopy').getBoundingClientRect().top
      >= element.querySelector('.vehicleHeroMedia').getBoundingClientRect().bottom - 1), 'Mobile hero copy must not overlay the model image');
    await page.screenshot({path:join(output, slug + '-' + width + '.png')});
    checks.push({width, image:loaded.src, exact_image:true, certified_interval:true, no_overflow:true});
  }
  assert(!pageImages.includes(photo.asset_url), 'Page should not fetch the large original when a publisher web size is supported');
  assert.deepEqual(errors, []);
} finally {
  await browser?.close();
  await new Promise((ok, reject) => server.httpServer.close(error => error ? reject(error) : ok()));
}
const result = {status:'polestar_3_private_ui_verified', candidate_sha256:report.candidate_sha256,
  photo_sha256:photo.content_sha256, native_media_evidence:hash(await readFile(join(publisherMedia,'report.json'))),
  ui_code:uiCode, checks, publication_approved:false, production_writes:0};
await writeFile(join(output, 'ui-report.json'), JSON.stringify(result, null, 2) + '\n', {flag:'wx'});
console.log(JSON.stringify({...result, output}));
