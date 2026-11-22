import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import react from '@vitejs/plugin-react';
import { build, preview } from 'vite';
import { readReviewedPhoto } from './hyundai_ioniq5_publication.mjs';
import { isIoniq5, isIoniq5NLine as isNLine, verifyIoniq5CatalogDelta } from './hyundai_ioniq5_distribution.mjs';
import { catalogWithComparableTimes, readCommittedPublicBaseline } from './isolated_catalog_review.mjs';
import { publicationHash } from './new_model_publication.mjs';
import { launchQaBrowser } from './qa_browser.mjs';
import { catalogHash, normalizeCatalog, variantKey } from './sync_public_catalog.mjs';

const { values } = parseArgs({ options: { transaction: { type: 'string' } } });
assert(values.transaction, 'Supply an isolated Ioniq 5 transaction receipt');
const root = await realpath('data/local/release-data');
assert.equal(root, join(await realpath('.'), 'data', 'local', 'release-data'));
const receiptPath = await realpath(values.transaction);
assert.equal(dirname(dirname(receiptPath)), root);
assert.match(basename(dirname(receiptPath)), /^hyundai-ioniq5-local-test-[a-z0-9]+$/i);
assert.equal(basename(receiptPath), 'transaction.json');
const rowsPath = join(dirname(receiptPath), 'preview-rows.json');
assert.equal(await realpath(rowsPath), rowsPath);
const json = async file => JSON.parse(await readFile(file, 'utf8'));
const receipt = await json(receiptPath);
for (const [key, wanted] of Object.entries({ status: 'passed_local_only', variants: 7, technical_fields: 63,
  database_fixture: 'isolated PGlite, scoped production readback', variant_photo_projection: true,
  view_contract_unchanged: true, anonymous_readback: true, publication_approved: false, production_writes: 0, paid_calls: 0 })) {
  assert.equal(receipt[key], wanted, 'Unexpected transaction evidence: ' + key);
}
assert.deepEqual(receipt.withheld, {});
const rows = normalizeCatalog(await json(rowsPath));
assert.equal(publicationHash(rows), receipt.preview_rows_sha256);
assert.equal(rows.length, 7);
assert(rows.every(isIoniq5));
assert.equal(rows.filter(isNLine).length, 2);

const photos = { base: readReviewedPhoto('base'), nLine: readReviewedPhoto('nLine') };
const photoFor = row => isNLine(row) ? photos.nLine.image : photos.base.image;
for (const [key, indexed] of Object.entries({base: photos.base, n_line: photos.nLine})) {
  const digest = createHash('sha256').update(indexed.body).digest('hex');
  assert.equal(digest, indexed.image.content_sha256);
  assert.equal(digest, receipt.scoped_photos[key]);
}
for (const row of rows) {
  assert.equal(row.image_url, photoFor(row).asset_url, 'Wrong image in the actual anonymous catalog projection');
  assert.equal(row.image_source_url, photoFor(row).source_url);
}

const output = await mkdtemp(join(root, 'hyundai-ioniq5-ui-'));
const {sourceRoot, base, proof} = await readCommittedPublicBaseline(root, output, {imageTools: true});
assert(!base.some(isIoniq5), 'An existing public model must not be replaced by a test');
const catalog = normalizeCatalog([...base, ...rows]);
assert.deepEqual(catalog.filter(row => !isIoniq5(row)), base);
const rights = await json(join(sourceRoot, 'src/image-rights.json'));
for (const shot of Object.values(photos)) assert(!rights.assets.some(row => row.asset_url === shot.image.asset_url));
const assets = Object.values(photos).map(shot => ({ ...shot.image, changes: 'Hela originalmotivet. Storlek och format anpassade.' }));
assets[1].variant_names = rows.filter(isNLine).map(row => row.variant_name);
const delta = verifyIoniq5CatalogDelta(base, catalog, rows, assets);
const edited = (match, changes) => catalog.map(row => match(row) ? {...row, ...changes} : row);
const sameVariant = exact => row => variantKey(row) === variantKey(exact);
const isEdition = row => isIoniq5(row) && isNLine(row);
const alteredExports = [
  [catalog.filter(row => !sameVariant(base[0])(row)), assets, /Existing public rows disappeared/],
  [edited(sameVariant(base[0]), {available_confirmed: !base[0].available_confirmed}), assets, /Existing public rows changed/],
  [catalog.filter(row => !sameVariant(rows[0])(row)), assets, /Only the seven reviewed/],
  [edited(isIoniq5, {dc_charge_kw: 22}), assets, /fields differ/],
  [edited(isEdition, {image_url: assets[0].asset_url, image_source_url: assets[0].source_url}), assets, /Wrong Ioniq 5 edition photo/],
  [edited(row => isIoniq5(row) && !isNLine(row), {image_url: assets[1].asset_url, image_source_url: assets[1].source_url}),
    assets, /Wrong Ioniq 5 edition photo/],
  [edited(isEdition, {image_source_url: assets[0].source_url}), assets, /Wrong Ioniq 5 photo source/],
  [catalog, [assets[0], {...assets[1], variant_names: [...assets[1].variant_names, rows.find(row => !isNLine(row)).variant_name]}],
    /Require the exact N Line scope/],
];
for (const [candidate, registry, error] of alteredExports) assert.throws(() => verifyIoniq5CatalogDelta(base, candidate, rows, registry), error);

const put = (name, data) => writeFile(join(sourceRoot, name), JSON.stringify(data, null, 2) + '\n');
const publishers = await json(join(sourceRoot, 'src/press-image-publishers.json'));
const key = photos.base.image.publisher_id;
assert.equal(key, photos.nLine.image.publisher_id);
const publisher = (await json('src/press-image-publishers.json'))[key];
assert.deepEqual(publisher.model_keys, ['hyundai|ioniq 5']);
assert.deepEqual(publisher.approved_image_paths, assets.map(asset => new URL(asset.source_url).pathname));
assert.equal(publishers[key], undefined);
const lookup = await json(join(sourceRoot, 'src/model-images.json'));
assert.equal(lookup['hyundai|ioniq 5'], undefined);
assert(!rights.assets.some(asset => asset.model_key === 'hyundai|ioniq 5'));
await put('src/press-image-publishers.json', {...publishers, [key]: publisher});
await put('src/image-rights.json', {...rights, assets: [...rights.assets, ...assets]});
await put('src/model-images.json', {...lookup, 'hyundai|ioniq 5': assets[0].asset_url});
for (const {image, body} of Object.values(photos)) await writeFile(join(sourceRoot, 'public', image.asset_url.slice(1)), body, {flag: 'wx'});
const dryRunSource = 'isolated_ioniq5_distribution_rehearsal';
await put('public/data/public_ev_variants.json', {source: dryRunSource, publication_approved: false, records: catalog});
const python = (name, ...args) => JSON.parse(execFileSync(process.execPath, ['scripts/run_python.mjs',
  join(sourceRoot, 'scripts', name), ...args], {encoding: 'utf8', timeout: 90000, windowsHide: true}));
python('prepare_responsive_images.py', '--write');
const rightsAudit = python('audit_image_rights.py', '--check');
assert.equal(rightsAudit.all_documented, true);
for (const asset of assets) assert(rightsAudit.checks.some(check => check.asset_url === asset.asset_url && check.documented));
assert.equal(python('verify_public_images.py').public_records, catalog.length);
const manifest = await json(join(sourceRoot, 'src/image-variants.json'));
const shipped = new Map(assets.map(asset => {
  const responsive = manifest[asset.asset_url];
  assert.equal(responsive.source_sha256, asset.content_sha256);
  assert.deepEqual(responsive.variants.map(image => image.width), [480, 800, 1280]);
  return [asset.asset_url, [{url: asset.asset_url, sha256: asset.content_sha256}, ...responsive.variants]];
}));
const outDir = join(output, 'dist');
await build({root: sourceRoot, configFile: false, envFile: false, base: '/', logLevel: 'silent', build: {outDir},
  plugins: [react()],
});
const { vehicleSlug } = await import(pathToFileURL(join(sourceRoot, 'src/vehicle-names.js')).href);
const slug = row => vehicleSlug(row.brand, row.model, row.variant_name);
const server = await preview({root: sourceRoot, configFile: false, envFile: false, logLevel: 'silent', build: {outDir},
  preview: {host: '127.0.0.1', port: 0, strictPort: true}});
const address = server.httpServer.address();
assert.equal(address.address, '127.0.0.1');
const origin = `http://127.0.0.1:${address.port}`;
const compact = text => text.replace(/\s+/gu, ' ').trim();
const formatSEK = value => compact(new Intl.NumberFormat('sv-SE').format(value)) + ' kr';
const errors = [], runs = [];
let browser;
try {
  browser = await launchQaBrowser();
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin || request.method() !== 'GET' || url.pathname.startsWith('/api/')) return route.abort();
    return route.continue();
  });
  for (const asset of [...shipped.values()].flat()) {
    const response = await context.request.get(origin + asset.url);
    assert(response.ok());
    assert.equal(createHash('sha256').update(await response.body()).digest('hex'), asset.sha256);
    assert.match(response.headers()['content-type'], asset.width ? /^image\/webp\b/ : /^image\/jpeg\b/);
  }
  const response = await context.request.get(origin + '/data/public_ev_variants.json');
  assert(response.ok());
  const builtCatalog = await response.json();
  assert.equal(builtCatalog.source, dryRunSource);
  assert.equal(builtCatalog.publication_approved, false);
  verifyIoniq5CatalogDelta(base, builtCatalog.records, rows, assets);
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  function matchPhoto(loaded, expected, phone = false) {
    const file = shipped.get(expected.asset_url).find(asset => asset.url === loaded.path);
    assert(file?.width && loaded.width > 0, 'A responsive file for the exact edition must load');
    if (phone) assert.equal(file.width, 480, 'Phone must use the 480 px file');
  }
  async function checkPhoto(container, row) {
    const expected = photoFor(row);
    const photo = container.locator('img');
    await photo.scrollIntoViewIfNeeded();
    const actual = await photo.evaluate(async element => {
      await element.decode();
      return {path: new URL(element.currentSrc).pathname, width: element.naturalWidth};
    });
    matchPhoto(actual, expected);
    assert.equal(await container.getByRole('link', { name: 'Foto: Hyundai Motor Sweden', exact: true })
      .getAttribute('href'), expected.source_url);
  }
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({width, height: 900});
    for (const row of rows) {
      assert((await page.goto(`${origin}/bilar/${slug(row)}/`, { waitUntil: 'networkidle' }))?.ok());
      const hero = page.locator('.vehicleDetailHero');
      const heading = hero.locator('h1');
      await heading.waitFor();
      assert.match(compact(await heading.innerText()), /^Hyundai Ioniq 5\b/i);
      assert.equal(compact(await heading.locator('span').innerText()), row.variant_name);
      const stats = compact(await hero.locator('.vehicleHeroStats').innerText());
      for (const val of ['Listpris', formatSEK(row.price_sek), row.wltp_range_km + ' km', row.dc_charge_kw + ' kW']) {
        assert(stats.includes(val), val);
      }
      const expected = photoFor(row);
      const loaded = await hero.locator('.vehicleHeroMedia img').evaluate(async element => {
        await element.decode();
        return {path: new URL(element.currentSrc).pathname, width: element.naturalWidth};
      });
      matchPhoto(loaded, expected, width <= 390);
      assert.equal(await page.getByRole('link', {name: 'Foto: Hyundai Motor Sweden', exact: true}).first()
        .getAttribute('href'), expected.source_url);
      const layout = await page.evaluate(() => {
        const rect = selector => document.querySelector(selector).getBoundingClientRect();
        return {viewport: innerWidth, scroll: document.documentElement.scrollWidth,
          photo_clear_of_copy: rect('.vehicleHeroCopy').top >= rect('.vehicleHeroMedia').bottom - 1};
      });
      assert(layout.scroll <= width);
      if (width <= 800) assert(layout.photo_clear_of_copy, 'Text overlaps the photo on mobile');
      if ([390, 1440].includes(width) && (isNLine(row) || row.battery_kwh === 63)) {
        await page.screenshot({path: join(output, `${slug(row)}-${width}.png`)});
      }
      runs.push({slug: slug(row), width, photo: loaded.path, ...layout});
    }
  }
  const baseline = rows.find(row => row.battery_kwh === 63);
  const compare = [baseline, ...rows.filter(isNLine)];
  await page.goto(`${origin}/bilar?brand=Hyundai&query=Ioniq%205`, {waitUntil: 'networkidle'});
  const picker = page.locator('.vehicleVariantPicker select');
  await picker.waitFor();
  for (const row of rows) {
    await picker.selectOption(slug(row));
    const card = page.locator('.vehicleCard').filter({has: page.locator(`a.homeVehiclePhoto[href="/bilar/${slug(row)}"]`)});
    await card.waitFor();
    await checkPhoto(card, row);
    if (compare.includes(row)) {
      await card.locator('.homeVehicleActions button').click();
      await card.locator('.homeVehicleActions button[aria-pressed="true"]').waitFor();
    }
  }
  await page.locator('.siteHeader').getByRole('link', {name: 'J\u00e4mf\u00f6r', exact: true}).click();
  for (const row of compare) {
    const item = page.locator('.comparisonVehicle').filter({has: page.locator(`h2 a[href="/bilar/${slug(row)}"]`)});
    await checkPhoto(item, row);
  }
  assert.deepEqual(errors, []);
  const report = {status: 'passed_local_only', runs, listing: true, comparison: true,
    photos: receipt.scoped_photos, plan_hash: receipt.plan_hash, transaction_rows_sha256: receipt.preview_rows_sha256,
    baseline: {...proof, database_baseline_sha256: catalogHash(catalogWithComparableTimes(base)),
      candidate_count: catalog.length, candidate_sha256: catalogHash(catalog)},
    distribution: {...delta, static_assets: [...shipped.values()].flat(), intercepted_catalog: false,
      intercepted_images: false, rejected_export_mutations: alteredExports.length, approved_for_deployment: false},
    production_writes: 0, paid_calls: 0, publication_approved: false};
  await writeFile(join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
  await writeFile(join(output, 'reviewed-photo-registration.json'), JSON.stringify({assets, publication_approved: false}, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({...report, runs: runs.length, output}));
} finally {
  await browser?.close();
  await new Promise(resolve => server.httpServer.close(resolve));
}
