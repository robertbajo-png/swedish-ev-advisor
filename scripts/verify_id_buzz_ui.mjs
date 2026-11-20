import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { parseArgs } from 'node:util';
import { preview } from 'vite';
import { launchQaBrowser } from './qa_browser.mjs';
import { publicationHash } from './new_model_publication.mjs';
import { normalizeCatalog } from './sync_public_catalog.mjs';
import { vehicleSlug } from '../src/vehicle-names.js';
import { priceOfferEnd } from '../src/price-evidence.js';
import { matchAdvisorVariants, ruleRequirements } from '../src/advisor-matching.js';
import { normalizePublicVariants } from '../functions/_shared/advisor-core.mjs';

const { values } = parseArgs({ options: { catalog: { type: 'string' }, build: { type: 'string' } } });
assert(values.catalog && values.build, 'Pass a private test catalog and isolated Vite build');
const json = async path => JSON.parse(await readFile(path, 'utf8'));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const releaseRoot = await realpath('data/local/release-data');
assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(releaseRoot));
const file = await realpath(values.catalog), build = await realpath(values.build);
assert.equal(dirname(dirname(file)), releaseRoot);
assert.match(basename(dirname(file)), /^volkswagen-id-buzz-readback-[a-z0-9]+$/i);
assert.equal(basename(file), 'id-buzz-preview-catalog.json');
assert.equal(dirname(build), releaseRoot);
const catalog = await json(file), base = await json('public/data/public_ev_variants.json');
const proof = await json(join(dirname(file), 'readback.json'));
assert.equal(catalog.source, 'isolated_id_buzz_release_preview');
assert.equal(catalog.publication_approved, false);
assert.equal(catalog.production_writes, 0);
assert.equal(catalog.plan_sha256, proof.plan_hash);
assert.equal(catalog.baseline_sha256, publicationHash(base));
const isBuzz = row => row.brand === 'Volkswagen' && row.model === 'Id. Buzz';
assert.deepEqual(catalog.records.filter(row => !isBuzz(row)), normalizeCatalog(base.records));
const rows = catalog.records.filter(isBuzz);
assert.equal(rows.length, 2);
const photo = await json('src/id-buzz-photo-policy.json');
assert.equal(digest(await readFile(join(build, photo.asset_url))), photo.content_sha256);
const offerEnd = '2026-12-31';
assert.equal(priceOfferEnd('list_price', offerEnd), null);
assert.equal(priceOfferEnd('dealer_offer', '2026-02-30'), null);
const needs = { ...ruleRequirements({ budget: 700000, range: 400 }), min_tow_kg: 1500 };
const shortlist = matchAdvisorVariants(normalizePublicVariants(rows), needs).shortlist;
assert.equal(shortlist.length, 1);
assert.equal(matchAdvisorVariants(normalizePublicVariants(rows), { ...needs, min_tow_kg: 1801 }).shortlist.length, 0);

const output = await mkdtemp(join(releaseRoot, 'volkswagen-id-buzz-ui-'));
const server = await preview({ configFile: false, logLevel: 'silent', build: { outDir: build },
  preview: { host: '127.0.0.1', port: 0, strictPort: true } });
const address = server.httpServer.address();
assert.equal(address.address, '127.0.0.1');
const origin = `http://127.0.0.1:${address.port}`;
const dealer = 'https://mollerbil.se/erbjudanden/id-buzz-pro-sweden-olympic-edition';
const plain = value => value.replace(/\s+/gu, ' ');
const sek = value => plain(new Intl.NumberFormat('sv-SE').format(value));
const runs = [], errors = [];
let browser;
try {
  browser = await launchQaBrowser();
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin || request.method() !== 'GET' || url.pathname.startsWith('/api/')) return route.abort();
    if (url.pathname === '/data/public_ev_variants.json') return route.fulfill({ json: { records: catalog.records } });
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const row of rows) {
      const slug = vehicleSlug(row.brand, row.model, row.variant_name);
      const response = await page.goto(`${origin}/bilar/${slug}/`, { waitUntil: 'networkidle' });
      assert(response?.ok());
      const heading = page.locator('.vehicleDetailHero h1');
      await heading.waitFor();
      assert.match(plain(await heading.innerText()), /Volkswagen ID\. Buzz/);
      assert.match(plain(await heading.innerText()), /Sweden Olympic Edition/);
      assert.equal(row.price_type, 'dealer_offer');
      assert.equal(row.price_valid_until, offerEnd);
      assert.equal(row.price_source_url, dealer);
      const hero = plain(await page.locator('.vehicleHeroStats').innerText());
      for (const value of [sek(row.price_sek) + ' kr', row.wltp_range_km + ' km', row.tow_kg + ' kg']) assert(hero.includes(value), value);
      assert(hero.includes('Pris fr\u00e5n \u00e5terf\u00f6rs\u00e4ljare'));
      assert(!hero.includes('Listpris'));
      const photo = page.locator('.vehicleHeroMedia img');
      await photo.evaluate(element => element.decode());
      assert.match(await photo.evaluate(element => element.currentSrc), /volkswagen-id-buzz-00832a4a6a37/);
      const attribution = page.getByRole('link', { name: /Foto: M 93/ }).first();
      await attribution.waitFor();
      assert.match(await page.locator('main').innerText(), /inte Sweden Olympic Edition/);
      const layout = await page.evaluate(() => {
        const rect = selector => document.querySelector(selector).getBoundingClientRect();
        return { viewport: innerWidth, page: document.documentElement.scrollWidth,
          image_clear_of_text: rect('.vehicleHeroCopy').top >= rect('.vehicleHeroMedia').bottom };
      });
      assert(layout.page <= layout.viewport);
      if (width <= 800) assert(layout.image_clear_of_text, 'Mobile text overlaps photograph');
      if ([390, 1440].includes(width)) await page.screenshot({ path: join(output, `${slug}-${width}.png`) });
      await page.locator('#bilkallor summary').click();
      const details = page.locator('#bilkallor');
      assert.equal(await details.getByRole('link', { name: /^Pris(?:k\u00e4lla)?: M/ }).getAttribute('href'), dealer);
      assert.equal(await details.locator(`time[datetime="${offerEnd}"]`).innerText(), offerEnd);
      assert.match(await details.innerText(), /inte tillverkarens listpris/);
      runs.push({ slug, width, ...layout });
    }
  }
  await page.goto(`${origin}/bilar?brand=Volkswagen&query=ID.%20Buzz`, { waitUntil: 'networkidle' });
  const picker = page.locator('.vehicleVariantPicker select');
  await picker.waitFor();
  const card = page.locator('.vehicleCard').filter({ has: picker });
  for (const row of rows) {
    await picker.selectOption(vehicleSlug(row.brand, row.model, row.variant_name));
    assert.match(await card.locator('.homeVehiclePrice').innerText(), /2026-12-31/);
    await card.locator('.homeVehicleActions button').click();
    await card.locator('.homeVehicleActions button[aria-pressed="true"]').waitFor();
  }
  await page.locator('.siteHeader').getByRole('link', { name: 'J\u00e4mf\u00f6r', exact: true }).click();
  const comparison = plain(await page.locator('.comparisonFacts table').innerText()).replace(/(?<=\d) (?=\d)/g, '');
  for (const value of ['452 km', '416 km', '1200 kg', '1800 kg']) assert(comparison.includes(value), value);
  assert.deepEqual(errors, []);
  const report = { status: 'passed', runs, comparison: true, advisor_towing: true, paid_calls: 0, production_writes: 0, output };
  await writeFile(join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ ...report, runs: runs.length }));
} finally {
  await browser?.close();
  await new Promise(resolve => server.httpServer.close(resolve));
}
