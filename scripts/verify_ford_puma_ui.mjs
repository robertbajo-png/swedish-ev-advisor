import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cp, mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import react from '@vitejs/plugin-react';
import { build, preview } from 'vite';
import { readPrivatePumaImage, readPumaImage } from './ford_puma_gen_e_publication.mjs';
import { publicationHash } from './new_model_publication.mjs';
import { launchQaBrowser } from './qa_browser.mjs';
import { catalogHash, normalizeCatalog, variantKey } from './sync_public_catalog.mjs';
import { MANUFACTURER_FROM_PRICE, priceTypeLabel } from '../src/price-evidence.js';

const {values, positionals} = parseArgs({options: {readback: {type: 'string'}}, allowPositionals: true});
assert(values.readback && !positionals.length, 'Supply one private --readback directory');
const repo = await realpath('.');
const evidence = await realpath('data/local/release-data');
assert.equal(evidence, join(repo, 'data', 'local', 'release-data'));
const dir = await realpath(values.readback);
assert.equal(dir, resolve(values.readback));
assert.equal(dirname(dir), evidence);
assert.match(basename(dir), /^ford-puma-local-[a-z0-9]+$/i);
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(dir));
const json = async path => JSON.parse(await readFile(path, 'utf8'));
const report = await json(join(dir, 'report.json'));
assert.deepEqual([report.status, report.variants, report.publication_approved, report.production_writes, report.atomic_identity],
  ['puma_local_insertion_verified', 2, false, 0, true]);
assert.equal(report.starting_price_migration_local, true);
const packet = await json(join(dir, 'atomic-packet.json'));
assert.equal(publicationHash(packet), report.plan_sha256, 'Atomic catalog rehearsal packet changed');
assert.deepEqual([packet.status, packet.publication_approved], ['puma_atomic_rehearsal_only', false]);
const committed = join(dir, 'main-source');
assert.equal(await realpath(committed), committed);
const prior = normalizeCatalog((await json(join(committed, 'public/data/public_ev_variants.json'))).records);
const candidate = normalizeCatalog((await json(join(dir, 'candidate-catalog.json'))).records);
assert.equal(catalogHash(prior), report.baseline_sha256);
assert.equal(catalogHash(candidate), report.candidate_sha256);
const keys = new Set(prior.map(variantKey));
assert.deepEqual(candidate.filter(row => keys.has(variantKey(row))), prior);
const variants = candidate.filter(row => !keys.has(variantKey(row)));
assert.equal(variants.length, 2);
const image = readPumaImage();
assert.deepEqual(packet.image, image);
assert(variants.every(row => row.brand === 'Ford' && row.model === 'Puma Gen-E'
  && row.image_url === image.asset_url && row.image_source_url === image.source_url
  && row.price_type === MANUFACTURER_FROM_PRICE && row.price_source_url === row.source_url));
assert.deepEqual(variants.map(row => row.price_sek).sort(), [389000, 409000]);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const original = readPrivatePumaImage(image);
assert.equal(hash(original), image.content_sha256);
const output = await mkdtemp(join(dir, 'ui-'));
const root = join(output, 'source');
await cp(committed, root, {recursive: true, errorOnExist: true, force: false});
const priceUiFiles = ['src/price-evidence.js', 'src/main.jsx', 'src/vehicle-ui.jsx', 'src/advisor-matching.js',
  'src/decision-metrics.js', 'src/tco.js', 'src/vehicle-names.js'];
const priceUiHashes = {};
for (const file of priceUiFiles) {
  const path = join(repo, file);
  assert.equal(await realpath(path), path);
  const body = await readFile(path);
  priceUiHashes[file] = hash(body);
  await writeFile(join(root, file), body);
}
const write = (file, body) => writeFile(join(root, file), JSON.stringify(body, null, 2) + '\n');
const rights = await json(join(root, 'src/image-rights.json'));
const registry = await json(join(root, 'src/model-images.json'));
const publishers = await json(join(root, 'src/press-image-publishers.json'));
const presentation = await json(join(root, 'src/image-presentation.json'));
assert(!rights.assets.some(row => row.model_key === image.model_key));
assert(!(image.model_key in registry));
const currentPublisher = (await json('src/press-image-publishers.json'))[image.publisher_id];
assert.deepEqual(currentPublisher.model_keys, [image.model_key]);
assert.equal(currentPublisher.approved_source_sha256, image.content_sha256);
publishers[image.publisher_id] = currentPublisher;
registry[image.model_key] = image.asset_url;
rights.assets.push({...image, changes: 'Originalfilen har inte redigerats. Responsiva kopior har endast anpassats i storlek och format.'});
presentation.models[image.model_key] = {asset_url: image.asset_url, content_sha256: image.content_sha256,
  status: 'approved', reviewed_at: image.reviewed_at, object_position: 'center', object_fit: 'contain', style: 'manufacturer_press_photo'};
await writeFile(join(root, 'public', image.asset_url.slice(1)), original, {flag: 'wx'});
await write('src/image-rights.json', rights);
await write('src/model-images.json', registry);
await write('src/press-image-publishers.json', publishers);
await write('src/image-presentation.json', presentation);
await write('public/data/public_ev_variants.json', {status: 'isolated_preview_only', publication_approved: false, records: candidate});
const python = (script, ...args) => JSON.parse(execFileSync(process.execPath,
  ['scripts/run_python.mjs', join(root, 'scripts', script), ...args], {encoding: 'utf8', timeout: 120000, windowsHide: true}));
python('prepare_responsive_images.py', '--write');
assert(python('audit_image_rights.py', '--check').all_documented);
assert.equal(python('verify_public_images.py').public_records, candidate.length);
const responsive = (await json(join(root, 'src/image-variants.json')))[image.asset_url];
assert.equal(responsive.source_sha256, image.content_sha256);
assert.deepEqual(responsive.variants.map(row => row.width), [480, 800, 1280]);
const {vehicleSlug} = await import(pathToFileURL(join(root, 'src/vehicle-names.js')).href);
const {vehicleSlug: originalSlug} = await import(pathToFileURL(join(committed, 'src/vehicle-names.js')).href);
const slug = row => vehicleSlug(row.brand, row.model, row.variant_name);
assert.equal(new Set(candidate.map(slug)).size, candidate.length);
for (const row of prior) assert.equal(slug(row), originalSlug(row.brand, row.model, row.variant_name));
const config = {root, configFile: false, envFile: false, base: '/', logLevel: 'silent', build: {outDir: join(output, 'dist')}};
await build({...config, plugins: [react()]});
const server = await preview({...config, preview: {host: '127.0.0.1', port: 0, strictPort: true}});
const address = server.httpServer.address();
const origin = 'http://127.0.0.1:' + address.port;
const text = value => value.replace(/\s+/gu, ' ').trim();
const checks = [], errors = [];
let browser;
try {
  assert.equal(address.address, '127.0.0.1');
  browser = await launchQaBrowser();
  const context = await browser.newContext({serviceWorkers: 'block'});
  await context.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    return url.origin === origin && request.method() === 'GET' && !url.pathname.startsWith('/api/') ? route.continue() : route.abort();
  });
  for (const asset of [{url: image.asset_url, sha256: image.content_sha256}, ...responsive.variants]) {
    const response = await context.request.get(origin + asset.url);
    assert(response.ok());
    assert.equal(hash(await response.body()), asset.sha256);
  }
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  for (const width of [390, 1440]) {
    for (const row of variants) {
      await page.setViewportSize({width, height: 900});
      assert((await page.goto(origin + '/bilar/' + slug(row) + '/', {waitUntil: 'networkidle'})).ok());
      const hero = page.locator('.vehicleDetailHero');
      const title = hero.locator('h1');
      assert.match(text(await title.innerText()), /^Ford Puma Gen-E\b/i);
      assert.equal(text(await title.locator('span').innerText()), row.variant_name);
      const loaded = await hero.locator('.vehicleHeroMedia img').evaluate(async img => {
        await img.decode();
        return {src: new URL(img.currentSrc).pathname, width: img.naturalWidth, fit: getComputedStyle(img).objectFit};
      });
      assert(responsive.variants.some(asset => asset.url === loaded.src));
      assert(loaded.width > 0 && loaded.fit === 'contain');
      const price = text(new Intl.NumberFormat('sv-SE').format(row.price_sek)) + ' kr';
      const stats = text(await hero.locator('.vehicleHeroStats').innerText());
      for (const value of [price, row.wltp_range_km + ' km', '100 kW', '750 kg']) assert(stats.includes(value), value);
      assert(stats.includes(priceTypeLabel(row.price_type)));
      assert.doesNotMatch(stats, /listpris|kampanjpris/i);
      const priceSchema = JSON.parse(await page.locator('script[data-jsonld="page"]').textContent());
      assert(priceSchema.additionalProperty?.some(p => p.name === priceTypeLabel(row.price_type) && p.value === row.price_sek));
      assert(!priceSchema.offers);
      const layout = await page.evaluate(() => {
        const box = selector => document.querySelector(selector).getBoundingClientRect();
        return {overflow: document.documentElement.scrollWidth > innerWidth,
          separate: box('.vehicleHeroCopy').top >= box('.vehicleHeroMedia').bottom - 1};
      });
      assert(!layout.overflow);
      if (width < 800) assert(layout.separate, 'Mobile text overlaps the Puma press image');
      assert.equal(await page.getByRole('link', {name: /^Foto: Ford Sverige/i}).first().getAttribute('href'), image.source_url);
      await page.screenshot({path: join(output, slug(row) + '-' + width + '.png')});
      checks.push({variant: row.variant_name, viewport: width, asset: loaded.src});
    }
  }
  await page.getByRole('button', {name: 'L\u00e4gg till i j\u00e4mf\u00f6relse', exact: true}).first().click();
  await page.getByRole('button', {name: 'J\u00e4mf\u00f6r nu'}).click();
  await page.waitForURL(url => url.pathname.replace(/\/$/, '') === '/jamfor');
  const table = page.locator('.comparisonTable table');
  await table.waitFor();
  await page.getByRole('combobox', {name: 'L\u00e4gg till en bil'}).selectOption(slug(variants[0]));
  for (const row of variants) {
    assert.equal(await table.getByRole('columnheader', {name: 'Ford Puma Gen-E ' + row.variant_name, exact: true}).count(), 1);
  }
  const rangeRow = table.getByRole('row').filter({has: page.getByRole('rowheader', {name: /^WLTP-/})});
  assert.deepEqual((await rangeRow.getByRole('cell').allTextContents()).map(text).sort(), ['404 km', '417 km']);
  const priceRow = table.getByRole('row').filter({has: page.getByRole('rowheader', {name: 'Pris', exact: true})});
  assert.equal(await priceRow.locator('.bestCell').count(), 0);
  assert.deepEqual((await priceRow.getByRole('cell').allTextContents()).map(text).sort(),
    ['389 000 kr', '409 000 kr'].map(value => priceTypeLabel(MANUFACTURER_FROM_PRICE) + ': ' + value));
  await page.getByRole('button', {name: 'Skapa rapport', exact: true}).click();
  assert.match(await page.locator('.reportWinner').innerText(), /bara tekniska v\u00e4rden/);
  assert((await page.locator('.reportCompared small').allTextContents()).every(value => text(value).startsWith('Fr\u00e5n ')));
  assert.deepEqual(errors, []);
} finally {
  await browser?.close();
  await new Promise((done, reject) => server.httpServer.close(error => error ? reject(error) : done()));
}
const result = {status: 'puma_private_ui_verified', candidate_sha256: report.candidate_sha256, checks,
  atomic_plan_sha256: report.plan_sha256,
  publisher_starting_price_checked: true, price_ui_sha256: priceUiHashes,
  compared_from_detail: true, photo_sha256: image.content_sha256, production_writes: 0, publication_approved: false};
await writeFile(join(output, 'ui-report.json'), JSON.stringify(result, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({...result, output}));
