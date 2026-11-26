import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { AxeBuilder } from '@axe-core/playwright';
import { launchQaBrowser } from './qa_browser.mjs';
import { isolatePublicDataFixture } from './qa_public_data_fixture.mjs';

const base = process.env.SITE_QA_URL || 'http://127.0.0.1:5174';
const out = new URL('../data/local/advisor-first/', import.meta.url);
await mkdir(out, { recursive: true });
const compact = (str) => str.replace(/\s+/g, ' ');
const browser = await launchQaBrowser();
try {
  for (const [width, height] of [[320, 710], [390, 844], [768, 1024], [1440, 900]]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
    const page = await context.newPage();
    const errors = [];
    let requests = 0;
    page.on('pageerror', error => errors.push(error.message));
    await isolatePublicDataFixture(page);
    await page.route('**/api/advisor', route => {
      requests++;
      return route.fulfill({ status: 503, json: { error: 'Local QA only' } });
    });
    const viewportFits = async () => assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    const capture = (label) => page.screenshot({ path: fileURLToPath(new URL(label + '-' + width + '.png', out)) });
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    const input = page.locator('#home-advisor-query');
    const submit = page.getByRole('button', { name: 'Hitta min elbil', exact: true });
    const toggle = page.getByRole('button', { name: 'Mest räckvidd för pengarna', exact: true });
    const section = page.getByRole('form', { name: 'Din körvecka' });
    await page.locator('.homeVehicleCard').first().waitFor();
    const hero = page.locator('.homeHeroFirst');
    assert.equal(await hero.locator('figure, img, .homeSpotlight').count(), 0, 'The start-page advisor has no replacement hero image');
    assert.equal(await page.getByText('Hyundai Inster Prime', { exact: true }).count(), 0, 'Removed cover caption');
    const heroBox = await hero.boundingBox();
    const formBox = await hero.locator('.homeAdvisorForm').boundingBox();
    assert(heroBox && formBox && Math.abs(heroBox.x - formBox.x) < 1 &&
      Math.abs(heroBox.width - formBox.width) < 1, 'The advisor fills the freed grid column');
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator('h1').count(), 1);
    assert.equal(await section.isVisible(), false);
    for (const item of [input, submit, toggle]) {
      const box = await item.boundingBox();
      assert(box && box.y >= 0 && box.y + box.height <= height, width + 'px: advisor and range shortcut visible before scroll');
    }
    await viewportFits();
    await capture('start');
    await input.fill('En elbil med dragkrok');
    await toggle.focus();
    await page.keyboard.press('Enter');
    await section.waitFor();
    assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
    assert.equal(await input.inputValue(), 'En elbil med dragkrok');
    await page.waitForFunction(() => document.activeElement?.id === 'bil-week-title');
    await page.keyboard.press('Tab');
    const example = section.getByRole('button', { name: 'Fyll i ett exempel' });
    assert(await example.evaluate(el => el === document.activeElement));
    await viewportFits();
    const violations = (await new AxeBuilder({ page }).include('#hitta-elbil').analyze()).violations;
    assert.deepEqual(violations.map(v => [v.id, ...v.nodes.map(n => n.target)]), []);
    await section.locator('#bil-commute').fill('25');
    await section.getByLabel('Var laddar du oftast?').selectOption('home');
    await section.locator('#bil-trip').fill('240');
    await section.getByLabel('Hur ofta?').selectOption('fortnightly');
    assert.match(compact(await section.innerText()), /11 990 km\/år/);
    await section.scrollIntoViewIfNeeded();
    await capture('korvecka');
    await toggle.click();
    assert.equal(await section.isVisible(), false);
    await toggle.click();
    assert.equal(await section.locator('#bil-commute').inputValue(), '25');
    await section.getByRole('button', { name: 'Visa bilurval' }).click();
    await page.waitForURL('**/bilar');
    assert.match(compact(await page.locator('.bilWeekResult').innerText()), /11 990 km\/år · 80 % laddning hemma/);
    assert.match(await page.locator('.bilWeekResult').innerText(), /längst angiven WLTP/);
    await page.locator('.carCard a[href^="/bilar/"]').first().click();
    await page.getByRole('link', { name: 'Ägandekostnad', exact: true }).first().click();
    assert.match(compact(await page.locator('.bilCostVariant').first().innerText()), /35 970 km/);
    await page.locator('.bilCostAssumptions > summary').click();
    assert.equal(await page.getByLabel('Körsträcka, km/år').inputValue(), '11990');
    assert.equal(await page.getByLabel('Jämförelseperiod, månader').inputValue(), '36');
    await page.goBack();
    await page.goBack();
    await page.getByRole('link', { name: 'Ändra körveckan' }).click();
    await section.waitFor();
    assert.equal(await section.locator('#bil-trip').inputValue(), '240');
    await page.getByRole('button', { name: 'Ställ frågan till AI-rådgivaren' }).click();
    assert.match(await input.inputValue(), /räckvidd.*pengarna/);
    assert(await input.evaluate(el => el === document.activeElement));
    assert.equal(requests, 0, 'opening the driving week or preparing a question must not send an AI request');
    await submit.click();
    await page.locator('#dina-forslag').waitFor();
    assert.equal(requests, 1);
    await page.getByRole('navigation', { name: 'Huvudnavigation' }).getByRole('link', { name: 'Rådgivare' }).click();
    await page.waitForURL('**/radgivare');
    assert.equal(await page.locator('#din-korvecka').count(), 0);
    await toggle.click();
    assert.match(await input.inputValue(), /räckvidd.*pengarna/);
    assert.equal(requests, 1);
    assert.deepEqual(errors, []);
    await context.close();
    console.log(width + 'px: adviser visible, keyboard and axe clean, driving week and edit round trip, adviser shortcut, no real AI calls');
  }
} finally {
  await browser.close();
}
