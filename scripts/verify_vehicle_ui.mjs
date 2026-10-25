import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { launchQaBrowser } from './qa_browser.mjs';

const base = process.env.VEHICLE_UI_URL || 'http://127.0.0.1:5174';
const out = new URL('../data/local/design-qa/', import.meta.url);
await mkdir(out, { recursive: true });
const { records } = JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8'));
const browser = await launchQaBrowser();
const failures = [];
try {
  const page = await browser.newPage({ acceptDownloads: true });
  page.on('pageerror', (error) => failures.push(error.message));
  let publicRecords = records;
  await page.route('**/rest/v1/public_ev_variants?**', (route) => route.fulfill({ json: publicRecords }));
  await page.route('**/data/public_ev_variants.json', (route) => route.fulfill({ json: { records: publicRecords } }));
  await page.route('**/rest/v1/public_news_articles?**', (route) => route.fulfill({ json: [] }));
  await page.route('**/data/news_articles.json', (route) => route.fulfill({ json: { records: [] } }));
  await page.route('**/api/compare', (route) => route.fulfill({ status: 503, json: { error: 'Test-only outage' } }));
  const noOverflow = async (name) => assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name + ': no document overflow');
  const photosReady = async (selector) => {
    for (const img of await page.locator(selector).all()) {
      await img.scrollIntoViewIfNeeded().catch(() => {});
      await img.evaluate((element) => element.complete || new Promise((resolve) => { element.addEventListener('load', resolve, { once: true }); element.addEventListener('error', resolve, { once: true }); setTimeout(resolve, 5000); })).catch(() => {});
    }
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
    await photosReady('.vehicleSimilar .homeVehiclePhoto img');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await noOverflow(name + ' detail');
    await page.screenshot({ path: fileURLToPath(new URL(`detail-${name}.png`, out)), fullPage: true });
    await page.screenshot({ path: fileURLToPath(new URL(`detail-hero-${name}.png`, out)) });
    await page.locator('.vehicleHeroActions').getByRole('button', { name: 'Lägg till i jämförelse', exact: true }).click();
    assert.equal(await page.locator('.vehicleHeroActions').getByRole('button', { name: 'Tillagd i jämförelse', exact: true }).getAttribute('aria-pressed'), 'true');
    assert.equal(await page.getByRole('link', { name: 'Öppna källa', exact: true }).getAttribute('target'), '_blank');
  }
  // Explicit canonical zero is distinct from null; no production records are changed.
  publicRecords = [{ ...records[0], price_sek: 600000, price_type: null, dc_charge_kw: null, tow_kg: 0, seats: null }];
  await page.goto(base + '/bilar');
  await page.locator('.carCard').first().waitFor();
  assert.equal(await page.locator('.homeVehiclePrice span').innerText(), 'Prisuppgift', 'Unknown price type is not a list price');
  await page.locator('.carCard').getByRole('link', { name: 'Visa detaljer' }).click();
  assert.match(await page.locator('.vehicleHeroStats').innerText(), /0 kg/);
  assert.match(await page.locator('.vehicleHeroStats').innerText(), /Uppgift saknas/);
  assert.match(await page.locator('.vehicleHeroStats').innerText(), /Prisuppgift/);
  assert.equal(await page.locator('#nyckeltal').getByText('Uppgift saknas', { exact: true }).count(), 3, 'Unknown list price and absent peer data do not produce value metrics');
  assert.equal(await page.locator('.vehicleHeroMedia img').count(), 0, 'No model fallback for missing Audi image');
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
  await page.goto(base + '/compare');
  await page.getByRole('heading', { name: 'Jämför sida vid sida', level: 1 }).waitFor();
  assert.deepEqual(failures, [], 'No client runtime errors');
  console.log(JSON.stringify({ vehicle_ui_ok: true, viewports: ['1440x1000', '820x1180', '390x844', '320x740'], tested: ['filters', 'drawer + keyboard', 'sorting controls', 'card/table view', 'comparison', 'report errors', 'stale report reset', 'CSV', 'cinematic details', 'explicit zero vs null', 'missing photo'], screenshots: fileURLToPath(out) }));
} finally { await browser.close(); }
