import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { launchQaBrowser } from './qa_browser.mjs';
import { isolatePublicDataFixture } from './qa_public_data_fixture.mjs';
import { vehicleSlug } from '../src/vehicle-names.js';

const base = process.env.VEHICLE_UI_URL || 'http://127.0.0.1:5174';
const out = new URL('../data/local/design-qa/', import.meta.url);
await mkdir(out, { recursive: true });
const { records } = JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8'));
const browser = await launchQaBrowser();
const failures = [];
try {
  const page = await browser.newPage({ acceptDownloads: true });
  await isolatePublicDataFixture(page);
  page.on('pageerror', (error) => failures.push(error.message));
  let publicRecords = records;
  await page.route('**/rest/v1/public_ev_variants?**', (route) => route.fulfill({ json: publicRecords }));
  await page.route('**/data/public_ev_variants.json', (route) => route.fulfill({ json: { records: publicRecords } }));
  await page.route('**/rest/v1/public_news_articles?**', (route) => route.fulfill({ json: [] }));
  await page.route('**/data/news_articles.json', (route) => route.fulfill({ json: { records: [] } }));
  await page.route('**/api/compare', (route) => route.fulfill({ status: 503, json: { error: 'Test-only outage' } }));
  const noOverflow = async (name) => assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name + ': no document overflow');
  const mobilePhotoClear = async () => {
    if (page.viewportSize().width > 800) return;
    const layout = await page.evaluate(() => {
      const media = document.querySelector('.vehicleHeroMedia');
      const rect = media.getBoundingClientRect();
      const copy = document.querySelector('.vehicleHeroCopy').getBoundingClientRect();
      const stats = document.querySelector('.vehicleHeroStats').getBoundingClientRect();
      const header = document.querySelector('.siteHeader').getBoundingClientRect();
      const img = media.querySelector('img');
      return { height: rect.height, width: rect.width, headerGap: rect.top - header.bottom, copyGap: copy.top - rect.bottom,
        statsGap: stats.top - rect.bottom, overlay: getComputedStyle(document.querySelector('.vehicleHeroOverlay')).display,
        frameRatio: img ? img.getBoundingClientRect().width / img.getBoundingClientRect().height : null,
        sourceRatio: img ? img.naturalWidth / img.naturalHeight : null };
    });
    assert(layout.height >= 160, 'Mobile model photo has a real, reserved area');
    assert(layout.headerGap >= 0, 'Mobile navigation cannot cover the top of the photograph');
    assert(layout.copyGap >= 16 && layout.statsGap >= 16, 'No vehicle text, badges, actions or specifications over the mobile photo');
    assert.equal(layout.overlay, 'none', 'Mobile model photo is not darkened for overlaid copy');
    if (layout.sourceRatio) assert(Math.abs(layout.frameRatio - layout.sourceRatio) < 0.01, 'Mobile photograph preserves its full original frame');
  };
  const photosReady = async (selector) => {
    for (const img of await page.locator(selector).all()) {
      await img.scrollIntoViewIfNeeded();
      await img.evaluate(async element => {
        if (!element.complete) await new Promise((resolve, reject) => {
          element.addEventListener('load', resolve, { once: true });
          element.addEventListener('error', () => reject(new Error('Exact-model image failed to load: ' + element.currentSrc)), { once: true });
        });
        await element.decode();
      });
      assert(await img.evaluate(element => element.complete && element.naturalWidth > 0), 'Exact model photo must actually decode');
    }
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  };
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['tablet', { width: 820, height: 1180 }], ['mobile', { width: 390, height: 844 }], ['small', { width: 320, height: 740 }]]) {
    await page.setViewportSize(viewport);
    await page.goto(base + '/bilar');
    await page.locator('.carGrid .carCard').first().waitFor();
    await page.getByRole('searchbox', { name: 'Sök bilmodell' }).fill('Polestar');
    assert((await page.locator('.carCard').count()) > 0);
    assert(await page.locator('.carCard').evaluateAll((cards) => cards.every((card) => card.innerText.includes('Polestar'))));
    await page.getByRole('combobox', { name: 'Sortera bilar' }).selectOption('price');
    assert.match(await page.locator('.carCard').first().innerText(), /599.*000 kr/);
    await page.getByRole('combobox', { name: 'Sortera bilar' }).selectOption('range');
    assert.match(await page.locator('.carCard').first().innerText(), /659 km/);
    await page.getByRole('combobox', { name: 'Sortera bilar' }).selectOption('match');
    const modelTitles = await page.locator('.carCard .vehicleCardTitle').allTextContents();
    assert.equal(new Set(modelTitles).size, modelTitles.length, 'One card per exact model, not repeated trim photos');
    const versionPicker = page.locator('.carCard').first().locator('.vehicleVariantPicker select');
    if (await versionPicker.count()) {
      const ids = await versionPicker.locator('option').evaluateAll(options => options.map(option => option.value));
      const selectedId = ids.at(-1);
      await versionPicker.focus();
      await versionPicker.selectOption(selectedId);
      assert.equal(await versionPicker.inputValue(), selectedId, 'Version choice is stable');
      assert.equal(await versionPicker.evaluate(element => element === document.activeElement), true, 'Changing a version keeps keyboard focus');
      assert((await page.locator('.carCard').first().getByRole('link', { name: 'Visa detaljer' }).getAttribute('href')).endsWith('/' + selectedId));
      await page.locator('.carCard').first().getByRole('button', { name: 'Jämför', exact: true }).click();
      assert.equal(await page.locator('.carCard').first().getByRole('button', { name: 'Vald', exact: true }).count(), 1);
      await page.locator('.carCard').first().getByRole('button', { name: 'Vald', exact: true }).click();
    }
    if (viewport.width <= 800) {
      await page.getByRole('button', { name: 'Filter', exact: true }).click();
      const drawer = page.getByRole('dialog');
      await drawer.getByRole('combobox', { name: 'Märke', exact: true }).selectOption('Volvo');
      await page.keyboard.press('Escape');
      assert.equal(await drawer.count(), 0);
      assert.equal(await page.getByRole('button', { name: 'Filter', exact: true }).evaluate((e) => e === document.activeElement), true);
      assert.equal(await page.locator('.carCard').count(), 0, 'Search and brand filters combine');
      await page.getByRole('button', { name: 'Återställ filter', exact: true }).click();
      await page.getByRole('searchbox', { name: 'Sök bilmodell' }).fill('Polestar');
    }
    await photosReady('.carCard .homeVehiclePhoto img');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await noOverflow(name + ' catalog');
    await page.screenshot({ path: fileURLToPath(new URL(`catalog-${name}.png`, out)), fullPage: true });
    await page.getByRole('button', { name: 'Tabellvy', exact: true }).click();
    assert.equal(await page.getByRole('table').count(), 1);
    assert(await page.locator('.catalogTable tbody tr').count() > modelTitles.length, 'Table retains the individual matching variants');
    await noOverflow(name + ' table');
    await page.getByRole('button', { name: 'Kortvy', exact: true }).click();
    await page.locator('.carCard').first().getByRole('button', { name: 'Jämför', exact: true }).click();
    await page.locator('.carCard').nth(1).getByRole('button', { name: 'Jämför', exact: true }).click();
    await page.getByRole('complementary', { name: 'Din jämförelse' }).getByRole('button', { name: 'Jämför', exact: true }).click();
    await page.getByRole('heading', { name: 'Jämför sida vid sida', level: 1 }).waitFor();
    assert.equal(await page.locator('.comparisonVehicle').count(), 2);
    assert.equal(await page.getByRole('table').count(), 1);
    assert.equal(await page.locator('.comparisonTable tbody tr').filter({ hasText: 'Batteri' }).count(), 1);
    await photosReady('.comparisonVehiclePhoto img');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await noOverflow(name + ' compare');
    await page.screenshot({ path: fileURLToPath(new URL(`compare-${name}.png`, out)), fullPage: true });
    if (name === 'desktop') {
      await page.getByRole('button', { name: 'Skapa rapport', exact: true }).click();
      await page.getByText(/Rapporten kunde inte hämtas/).waitFor();
      const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Exportera CSV' }).click()]);
      assert.match(download.suggestedFilename(), /elbilsguiden-jamforelse.*\.csv$/);
      await page.unroute('**/api/compare');
      await page.route('**/api/compare', (route) => route.fulfill({ json: { mode: 'deterministic_fallback', summary: 'Transportfixtur för rapportens gränssnitt.', winner: { variant_key: 'fixture', name: 'Rapportens testbil' }, compared: [], reasons: ['Endast testdata.'], tradeoffs: ['Ingen personlig prioritering.'] } }));
      await page.getByRole('button', { name: 'Skapa rapport', exact: true }).click();
      await page.getByText('Högst i rapportens viktning').waitFor();
      await page.locator('.comparisonVehiclePhoto button').first().click();
      await page.getByText('Högst i rapportens viktning').waitFor({ state: 'hidden' });
      assert.equal(await page.getByText('Högst i rapportens viktning').count(), 0, 'Changed selection clears stale report');
    }
    await page.goto(base + '/bilar/tesla-model-3-long-range-rwd');
    await page.locator('.vehicleDetailHero h1').waitFor();
    assert.match(await page.locator('.vehicleDetailHero h1').innerText(), /Tesla Model 3/);
    assert.equal(await page.locator('.vehicleHeroStats > div').count(), 4);
    const tesla = records.find((record) => record.brand === 'Tesla' && /long range rwd/i.test(record.variant_name) && /3/.test(record.model));
    if (tesla?.dc_charge_kw == null) assert.match(await page.locator('.vehicleHeroStats').innerText(), /Uppgift saknas/);
    assert.equal(await page.getByText('Familjepoäng').count(), 0);
    assert.equal(await page.getByText('Vinterpoäng').count(), 0);
    await photosReady('.vehicleHeroMedia img');
    await mobilePhotoClear();
    await photosReady('.vehicleSimilar .homeVehiclePhoto img');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await noOverflow(name + ' detail');
    await page.screenshot({ path: fileURLToPath(new URL(`detail-${name}.png`, out)), fullPage: true });
    await page.screenshot({ path: fileURLToPath(new URL(`detail-hero-${name}.png`, out)) });
    await page.locator('.vehicleHeroActions').getByRole('button', { name: 'Lägg till i jämförelse', exact: true }).click();
    assert.equal(await page.locator('.vehicleHeroActions').getByRole('button', { name: 'Tillagd i jämförelse', exact: true }).getAttribute('aria-pressed'), 'true');
    assert.equal(await page.getByRole('link', { name: 'Öppna källa', exact: true }).getAttribute('target'), '_blank');
  }
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    await page.setViewportSize(viewport);
    await page.goto(base + '/bilar?brand=Kia&query=EV');
    await page.locator('.carGrid .carCard').first().waitFor();
    await page.waitForFunction(() => document.querySelector('#desktop-brand')?.value === 'Kia');
    assert(await page.locator('.carCard').evaluateAll(cards => cards.every(card => card.innerText.includes('Kia'))));
    await photosReady('.carCard .homeVehiclePhoto img');
    assert(await page.locator('.carCard .homeVehiclePhoto img').evaluateAll(images => images.some(image => getComputedStyle(image).objectFit === 'contain')), 'Manufacturer full-frame conditions affect actual rendering');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await noOverflow(name + ' Kia press photos');
    await page.screenshot({ path: fileURLToPath(new URL(`catalog-kia-viewport-${name}.png`, out)) });
    await page.screenshot({ path: fileURLToPath(new URL(`catalog-kia-${name}.png`, out)), fullPage: true });
    await page.goto(base + '/bilar/kia-ev6-rwd');
    await page.locator('.vehicleDetailHero h1').waitFor();
    await photosReady('.vehicleHeroMedia img');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await noOverflow(name + ' Kia cinematic photo');
    await page.screenshot({ path: fileURLToPath(new URL(`detail-kia-hero-${name}.png`, out)) });
  }
  for (const width of [320, 375, 390, 430, 768]) {
    await page.setViewportSize({ width, height: 844 });
    for (const slug of ['kia-ev5-fwd', 'kia-ev6-rwd', 'skoda-elroq-60-selection-explore-edition', 'skoda-enyaq-solid-edition-rs']) {
      await page.goto(base + '/bilar/' + slug);
      await page.locator('.vehicleDetailHero h1').waitFor();
      await photosReady('.vehicleHeroMedia img');
      await mobilePhotoClear();
      await noOverflow(width + ' ' + slug + ' separated photo');
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      await page.screenshot({ path: fileURLToPath(new URL(`detail-${slug}-${width}.png`, out)), fullPage: true });
      await page.locator('.vehicleDetailHero').screenshot({ path: fileURLToPath(new URL(`detail-hero-${slug}-${width}.png`, out)) });
    }
  }
  const skoda = records.filter(row => row.brand === 'Skoda');
  assert.equal(skoda.length, 11);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const row of skoda) {
    assert.equal(row.body_type, 'SUV');
    for (const field of ['price_sek', 'wltp_range_km', 'wltp_consumption_kwh_100km', 'battery_kwh', 'dc_charge_kw', 'ac_charge_kw', 'boot_liters', 'tow_kg', 'seats', 'drivetrain'])
      assert(row[field] != null, 'Current Skoda profile is complete: ' + row.variant_name + ' / ' + field);
    await page.goto(base + '/bilar/' + vehicleSlug(row.brand, row.model, row.variant_name));
    await page.locator('.vehicleDetailHero h1').waitFor();
    await photosReady('.vehicleHeroMedia img');
    await mobilePhotoClear();
    const img = page.locator('.vehicleHeroMedia img');
    const originalStem = row.image_url.split('/').at(-1).replace(/\.jpg$/, '');
    assert.match(await img.getAttribute('src'), new RegExp('^/media/(?:vehicles/' + originalStem + '\\.jpg|responsive/' + originalStem + '-(?:480|800|1280)\\.webp)$'), 'Detail derivative belongs to this exact canonical photograph');
    assert.match(row.image_url, /skoda-(elroq|enyaq)-press-/);
    assert.match(await page.locator('.vehicleHeroStats').innerText(), new RegExp(row.wltp_range_km + ' km'));
    await page.getByText('Förbrukning, grundutförande', { exact: true }).waitFor();
    assert.equal(await page.locator('#nyckeltal').getByText('Uppgift saknas', { exact: true }).count(), 0, 'Verified current campaign prices support explicitly labelled value metrics');
    assert.match(await page.locator('#nyckeltal').innerText(), /Kampanjpris, giltigt till 2026-12-15/);
    await noOverflow('Complete Skoda profile ' + row.variant_name);
  }
  const completedProfiles = records.filter(row => row.brand === 'Toyota' && row.model === 'bZ4X' || row.brand === 'Polestar' && ['2','4'].includes(row.model));
  assert.equal(completedProfiles.length, 6);
  const mazdaRenaultProfiles = records.filter(row => row.brand === 'Mazda' && row.model === '6E' || row.brand === 'Renault' && row.model === '5');
  assert.equal(mazdaRenaultProfiles.length, 6);
  const claProfiles = records.filter(row => row.brand === 'Mercedes-Benz' && row.model === 'Cla');
  assert.equal(claProfiles.length, 3);
  const fordProfiles = records.filter(row => row.brand === 'Ford' && row.model === 'Explorer');
  assert.equal(fordProfiles.length, 2);
  for (const row of [...completedProfiles, ...mazdaRenaultProfiles, ...claProfiles, ...fordProfiles]) {
    await page.goto(base + '/bilar/' + vehicleSlug(row.brand, row.model, row.variant_name));
    await page.locator('.vehicleDetailHero h1').waitFor();
    await photosReady('.vehicleHeroMedia img'); await mobilePhotoClear();
    assert(!(await page.locator('#specifikationer').innerText()).includes('Uppgift saknas'));
    if (row.brand === 'Polestar') assert.match(await page.locator('#specifikationer').innerText(), /WLTP-intervall/);
    if (mazdaRenaultProfiles.includes(row)) {
      assert.equal(row.body_type, 'Halvkombi');
      assert.match(row.image_url, /(?:mazda-6e|renault-5)-press-/);
      for (const field of ['price_sek','wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','tow_kg','boot_liters','seats','drivetrain'])
        assert(row[field] != null, 'Completed Mazda/Renault profile: ' + field);
      if (row.brand === 'Renault' && row.battery_kwh === 52)
        assert.match(await page.locator('#specifikationer').innerText(), /gemensamma WLTP-intervall/);
    }
    if (claProfiles.includes(row)) {
      assert.equal(row.body_type, 'Sedan');
      assert.equal(row.price_type, 'dealer_offer');
      assert.match(row.image_url, /mercedes-benz-cla-press-/);
      for (const field of ['price_sek','wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','tow_kg','boot_liters','seats','drivetrain'])
        assert(row[field] != null, 'Completed CLA profile: ' + field);
      assert.match(await page.locator('.vehicleDetailHero').innerText(), /beställningsbil/);
      assert.match(await page.locator('#specifikationer').innerText(), /Monterad dragkrok ingår inte automatiskt/);
      assert.match(new URL(page.url()).pathname, /-lagerbil\/?$/);
    }
    if (fordProfiles.includes(row)) {
      for (const field of ['price_sek','wltp_range_km','wltp_consumption_kwh_100km','battery_kwh','dc_charge_kw','ac_charge_kw','tow_kg','boot_liters','seats','drivetrain'])
        assert(row[field] != null, 'Completed Ford profile: ' + field);
      assert.equal(row.body_type, 'SUV');assert.equal(row.price_type, 'campaign_price');
      assert.equal(row.price_valid_until, '2026-12-30');assert.match(row.variant_name, /Premium Edition.*MY27\.25/);
      assert.match(row.image_url, /ford-explorer-press-/);
      assert.match(await page.locator('#specifikationer').innerText(), /Fords danska/);
      assert.match(await page.locator('#nyckeltal').innerText(), /Kampanjpris, giltigt till 2026-12-30/);
      assert(!(await page.locator('#nyckeltal').innerText()).includes('Uppgift saknas'));
      await page.locator('#bilkallor summary').click();
      assert.equal(await page.locator('#bilkallor a[href="https://www.ford.dk/koeb/kampagner/explorer-og-capri"]').count(), 1);
    }
    await noOverflow('Complete manufacturer profile ' + row.variant_name);
  }
  await page.goto(base + '/bilar?brand=Polestar&query=4%20Dual');
  await page.getByRole('button', { name: 'Tabellvy', exact: true }).click();
  const targetRow = page.locator('.catalogTable tbody tr').filter({ hasText: 'Polestar 4 Dual motor' });
  await targetRow.waitFor();
  assert.match(await targetRow.innerText(), /Tillverkarens mål/);
  const compareTarget = targetRow.getByRole('button');
  if (await compareTarget.getAttribute('aria-pressed') !== 'true') await compareTarget.click();
  await page.locator('.siteHeader').getByRole('link', { name: 'Jämför', exact: true }).click();
  const [targetCsv] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Exportera CSV', exact: true }).click()]);
  const csvText = await readFile(await targetCsv.path(), 'utf8');
  assert(csvText.includes('Räckviddens status') && csvText.includes('inte ett slutligt certifierat värde'));
  // Explicit canonical zero is distinct from null; no production records are changed.
  await page.route('**/media/vehicles/qa-missing.jpg', (route) => route.abort());
  publicRecords = [{ ...records[0], price_sek: 600000, price_type: null, wltp_range_km: 600, dc_charge_kw: null, tow_kg: 0, seats: null,
    image_url: '/media/vehicles/qa-missing.jpg' }];
  await page.goto(base + '/bilar');
  await page.locator('.carCard').first().waitFor();
  assert.equal(await page.locator('.homeVehiclePrice span').innerText(), 'Prisuppgift', 'Unknown price type is not a list price');
  await page.locator('.carCard').getByRole('link', { name: 'Visa detaljer' }).click();
  assert.match(await page.locator('.vehicleHeroStats').innerText(), /0 kg/);
  assert.match(await page.locator('.vehicleHeroStats').innerText(), /Uppgift saknas/);
  assert.match(await page.locator('.vehicleHeroStats').innerText(), /Prisuppgift/);
  assert.equal(await page.locator('#nyckeltal').getByText('Uppgift saknas', { exact: true }).count(), 3, 'Unknown list price and absent peer data do not produce value metrics');
  await page.locator('.vehicleHeroMedia .missingCarImage').waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await mobilePhotoClear();
  assert.equal(await page.locator('.vehicleHeroMedia img').count(), 0, 'Failed exact image never becomes a replacement model photo');
  for (const [type, label] of [['list_price', 'Listpris'], ['campaign_price', 'Kampanjpris'], ['dealer_offer', 'Återförsäljarerbjudande']]) {
    publicRecords = [{ ...publicRecords[0], price_type: type }];
    await page.goto(base + '/bilar');
    await page.locator('.carCard').first().waitFor();
    assert.equal(await page.locator('.homeVehiclePrice span').innerText(), label, 'Verified price type stays distinct');
    if (type === 'list_price') {
      await page.locator('.carCard').getByRole('link', { name: 'Visa detaljer' }).click();
      assert.equal(await page.locator('#nyckeltal').getByText('Uppgift saknas', { exact: true }).count(), 1, 'Known list price enables only the two supported value metrics');
    }
  }
  publicRecords = [{ ...publicRecords[0], brand: 'QA', model: 'Unknown model fixture', image_url: null, image_source_url: null }];
  await page.goto(base + '/bilar');
  await page.locator('.carCard').getByRole('link', { name: 'Visa detaljer' }).click();
  await page.locator('.vehicleHeroMedia .missingCarImage').waitFor();
  assert.equal(await page.locator('.vehicleHeroMedia img').count(), 0, 'Unmapped model has no lookalike fallback');
  await page.goto(base + '/compare');
  await page.getByRole('heading', { name: 'Jämför sida vid sida', level: 1 }).waitFor();
  assert.deepEqual(failures, [], 'No client runtime errors');
  console.log(JSON.stringify({ vehicle_ui_ok: true, viewports: ['1440x1000', '820x1180', '390x844', '320x740'], tested: ['filters', 'drawer + keyboard', 'sorting controls', 'card/table view', 'comparison', 'report errors', 'stale report reset', 'CSV', 'cinematic details', 'explicit zero vs null', 'missing photo'], screenshots: fileURLToPath(out) }));
} finally { await browser.close(); }
