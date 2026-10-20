import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const base = process.env.HOME_UI_URL || 'http://127.0.0.1:5174';
const out = new URL('../data/local/design-qa/', import.meta.url);
await mkdir(out, { recursive: true });
const { records: cars } = JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8'));
let browser;
try { browser = await chromium.launch({ headless: true }); }
catch { browser = await chromium.launch({ headless: true, channel: 'msedge' }); }
const errors = [];
const luminance = (hex) => hex.match(/\w\w/g).map((v) => parseInt(v, 16) / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
const contrast = (a, b) => (Math.max(luminance(a), luminance(b)) + .05) / (Math.min(luminance(a), luminance(b)) + .05);
for (const [foreground, background] of [['171b1c', 'f7f7f4'], ['697374', 'f7f7f4'], ['ffffff', '245e5b'], ['245e5b', 'dceae6']]) assert(contrast(foreground, background) >= 4.5, `Contrast ${foreground}/${background}`);
try {
  const page = await browser.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/rest/v1/public_ev_variants?**', (route) => route.fulfill({ json: cars }));
  await page.route('**/data/public_ev_variants.json', (route) => route.fulfill({ json: { records: cars } }));
  await page.route('**/rest/v1/public_news_articles?**', (route) => route.fulfill({ json: [] }));
  await page.route('**/data/news_articles.json', (route) => route.fulfill({ json: { records: [] } }));
  let request;
  let advisorFixtureOverride;
  await page.route('**/api/advisor', async (route) => {
    request = route.request().postDataJSON();
    await route.fulfill({ json: advisorFixtureOverride || {
      mode: 'openai', summary: 'Testsvaret använder publicerade bilposter. Detta är enbart en transportfixtur.',
      interpreted_requirements: { budget_sek: 600000, min_wltp_range_km: 450, need: 'familj' },
      shortlist: [...cars.slice(0, 2).map((car) => ({ brand: car.brand, model: car.model, variant_name: car.variant_name, reasons: ['Verifierade uppgifter finns att jämföra.'], tradeoffs: ['Kontrollera saknade uppgifter innan bilval.'] })), { brand: 'Unknown', model: 'Invented', variant_name: 'Must not render' }],
    } });
  });
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['tablet', { width: 820, height: 1180 }], ['mobile', { width: 390, height: 844 }], ['small', { width: 320, height: 740 }]]) {
    await page.setViewportSize(viewport);
    await page.goto(base);
    await page.locator('.homeVehicleCard').first().waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.locator('.homeSpotlightImage img').evaluate((img) => img.complete || new Promise((resolve) => { img.addEventListener('load', resolve, { once: true }); img.addEventListener('error', resolve, { once: true }); setTimeout(resolve, 8000); })).catch(() => {});
    for (const photo of await page.locator('.homeVehiclePhoto').all()) {
      await photo.scrollIntoViewIfNeeded();
      await photo.locator('img').evaluate((img) => img.complete || new Promise((resolve) => { img.addEventListener('load', resolve, { once: true }); img.addEventListener('error', resolve, { once: true }); setTimeout(resolve, 5000); })).catch(() => {});
    }
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    assert.equal(await page.getByRole('heading', { name: 'Hitta elbilen som passar dig.', level: 1 }).count(), 1);
    assert.equal(await page.locator('.homeVehicleCard').count(), 3);
    assert.equal(await page.locator('.compareSection').count(), 0, 'No full comparison report on homepage');
    assert.equal(await page.locator('.homeAdvisorResults').count(), 0, 'No invented AI output before submitting');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${name} overflow`);
    assert.match(await page.locator('body').evaluate((element) => getComputedStyle(element).fontFamily), /Manrope/);
    const submit = await page.getByRole('button', { name: 'Hitta min elbil', exact: true }).boundingBox();
    assert(submit.y + submit.height <= viewport.height, `${name} search CTA above fold`);
    await page.screenshot({ path: fileURLToPath(new URL(`home-${name}.png`, out)), fullPage: true });
    if (name === 'desktop') await page.screenshot({ path: fileURLToPath(new URL('home-desktop-preview.png', out)) });
    if (name === 'desktop') {
      const left = await page.locator('.homeHeroCopy').boundingBox();
      const right = await page.locator('.homeSpotlight').boundingBox();
      assert(Math.abs(left.y - right.y) < 2, 'Hero columns share a top edge');
    }
    const form = page.locator('.homeAdvisorForm');
    const restingSize = await form.boundingBox();
    const query = page.getByLabel('Vad är viktigt för dig?');
    await query.focus();
    assert(await query.evaluate((node) => node.matches(':focus-visible')), name + ': visible input focus');
    const focusStyle = await form.evaluate((node) => ({ border: getComputedStyle(node).borderColor, shadow: getComputedStyle(node).boxShadow }));
    assert.equal(focusStyle.border, 'rgb(36, 94, 91)');
    assert.match(focusStyle.shadow, /0px 0px 0px 1px/);
    assert.equal(await query.evaluate((node) => getComputedStyle(node).outlineStyle), 'none', name + ': no nested input frame');
    const focusedSize = await form.boundingBox();
    assert.equal(focusedSize.width, restingSize.width, name + ': focus does not resize form');
    assert.equal(focusedSize.height, restingSize.height, name + ': focus does not resize form');
    const label = await form.locator('label').first().boundingBox();
    assert(label.y + label.height <= (await query.boundingBox()).y + 1, name + ': label stays clear of input');
    await form.screenshot({ path: fileURLToPath(new URL(`advisor-focus-${name}.png`, out)) });
    await page.keyboard.press('Tab');
    assert(await page.locator('.homeAdjust').evaluate((node) => node === document.activeElement));
    assert.equal(await page.locator('.homeAdjust').evaluate((node) => getComputedStyle(node).outlineStyle), 'solid', name + ': buttons retain keyboard focus');
  }
  await page.emulateMedia({ forcedColors: 'active' });
  await page.getByLabel('Vad är viktigt för dig?').focus();
  assert.equal(await page.locator('.homeAdvisorForm').evaluate((node) => getComputedStyle(node).outlineWidth), '2px', 'system-color focus survives forced colors');
  await page.emulateMedia({ forcedColors: 'none' });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: 'Bästa familjeelbilen', exact: true }).click();
  assert.match(await page.getByLabel('Vad är viktigt för dig?').inputValue(), /familjeelbil/);
  await page.getByRole('button', { name: 'Anpassa', exact: true }).click();
  assert.equal(await page.getByRole('slider', { name: /Budget/ }).getAttribute('max'), '1200000');
  assert.equal(await page.getByRole('slider', { name: /Minsta räckvidd/ }).getAttribute('max'), '1000');
  await page.getByRole('button', { name: 'Hitta min elbil', exact: true }).click();
  await page.locator('.homeAdvisorResults .homeVehicleCard').first().waitFor();
  assert.match(request.prompt, /familjeelbil/);
  assert.equal(await page.locator('.homeAdvisorResults .homeVehicleCard').count(), 2, 'Unrecognised model is never displayed');
  assert.match(await page.locator('.homeRequirements').innerText(), /600.*000 kr/);
  assert.match(await page.locator('.homeRequirements').innerText(), /450 km/);
  await page.getByRole('button', { name: 'Justera sökningen', exact: true }).click();
  assert.equal(await page.getByLabel('Vad är viktigt för dig?').evaluate((element) => element === document.activeElement), true);
  assert.equal(await page.getByText('Unknown Invented').count(), 0);
  await page.locator('.homeAdvisorResults').getByRole('button', { name: 'Jämför', exact: true }).first().click();
  assert.equal(await page.locator('.homeAdvisorResults').getByRole('button', { name: 'Vald', exact: true }).count(), 1);
  await page.getByLabel('Vad är viktigt för dig?').fill('Jag vill ändra min sökning.');
  assert.equal(await page.locator('.homeRefinementNote').count(), 1);
  await page.screenshot({ path: fileURLToPath(new URL('advisor-desktop.png', out)), fullPage: true });
  await page.getByRole('button', { name: /Jämför valda/ }).click();
  await page.getByRole('heading', { name: 'Jämför sida vid sida', exact: true }).waitFor();
  await page.getByRole('link', { name: 'Alla elbilar', exact: true }).click();
  await page.locator('.carGrid').waitFor();
  assert((await page.locator('.carGrid .carCard').count()) > 0);
  advisorFixtureOverride = {
    mode: 'openai', recommendation_method: 'database_rules', summary: 'Ingen bil kan bekräftas uppfylla kraven.',
    interpreted_requirements: { budget_sek: 400000, min_wltp_range_km: 500, need: 'allround', min_tow_kg: null, awd_required: false, notes: 'Vissa uppgifter saknas för dina krav.' }, shortlist: [],
  };
  await page.goto(base);
  await page.locator('.homeVehicleCard').first().waitFor();
  await page.getByLabel('Vad är viktigt för dig?').fill('Jag behöver inte AWD eller dragkrok.');
  await page.getByRole('button', { name: 'Hitta min elbil', exact: true }).click();
  await page.getByRole('heading', { name: 'Ingen säker rekommendation just nu.' }).waitFor();
  assert.equal(await page.locator('.homeAdvisorResults .homeVehicleCard').count(), 0);
  assert.ok(!(await page.locator('.homeRequirements').innerText()).includes('Fyrhjulsdrift önskas'));
  assert.ok(!(await page.locator('.homeRequirements').innerText()).includes('Dragkrok önskas'));
  assert.equal(await page.getByText('Vissa uppgifter saknas för dina krav.').count(), 1);
  await page.getByRole('button', { name: 'Justera sökningen', exact: true }).click();
  await page.getByRole('slider', { name: /Budget/ }).fill('500000');
  await page.getByRole('button', { name: 'Hitta min elbil', exact: true }).click();
  await page.getByRole('heading', { name: 'Ingen säker rekommendation just nu.' }).waitFor();
  assert.equal(request.explicit_controls.budget, true);
  assert.equal(request.budget, 500000);
  await page.unroute('**/api/advisor');
  await page.route('**/api/advisor', (route) => route.fulfill({ status: 503, json: { error: 'Test-only outage' } }));
  await page.goto(base);
  await page.locator('.homeVehicleCard').first().waitFor();
  await page.getByRole('button', { name: 'Hitta min elbil', exact: true }).click();
  await page.getByText(/Här visas databaserade förslag/).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Mobile results overflow');
  await page.screenshot({ path: fileURLToPath(new URL('advisor-mobile.png', out)), fullPage: true });
  await page.locator('.homeSpotlightImage img').evaluate((img) => img.dispatchEvent(new Event('error'))).catch(() => {});
  assert.equal(await page.locator('.homeSpotlightImage img').count(), 0, 'Failed photo has no replacement vehicle');
  assert.equal(await page.locator('.homeSpotlightImage').getByText('Bild saknas').count(), 1);
  await page.unroute('**/rest/v1/public_ev_variants?**');
  await page.route('**/rest/v1/public_ev_variants?**', (route) => route.fulfill({ json: [...cars, { ...cars[0], brand: 'Private staging row', validation_status: 'draft' }] }));
  await page.route('**/data/public_ev_variants.json', (route) => route.fulfill({ json: { records: [...cars, { ...cars[0], brand: 'Private staging row', validation_status: 'draft' }] } }));
  await page.goto(base);
  await page.locator('.homeVehicleCard').first().waitFor();
  assert.equal(await page.getByText(/Private staging row/).count(), 0);
  await page.unroute('**/rest/v1/public_ev_variants?**');
  await page.route('**/rest/v1/public_ev_variants?**', (route) => route.fulfill({ status: 503 }));
  await page.route('**/data/public_ev_variants.json', (route) => route.fulfill({ status: 503 }));
  await page.goto(base);
  await page.getByText('Biluppgifterna kunde inte hämtas just nu.').waitFor();
  assert.equal(await page.locator('.homeVehicleCard').count(), 0, 'Failed data load never uses mock cars');
  assert.equal(await page.getByRole('button', { name: 'Hitta min elbil', exact: true }).isDisabled(), true);
  assert.deepEqual(errors, [], 'No client runtime errors');
  console.log(JSON.stringify({ home_ui_ok: true, viewports: ['1440x1000', '820x1180', '390x844', '320x740'], flows: ['single focus frame', 'keyboard focus', 'forced colors', 'suggestions', 'refinement', 'verified-only shortlist', 'comparison', 'catalog', 'offline state', 'missing image'], screenshots: fileURLToPath(out) }));
} finally { await browser.close(); }
