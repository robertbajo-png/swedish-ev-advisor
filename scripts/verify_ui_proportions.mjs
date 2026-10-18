import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const base = process.env.SITE_QA_URL || 'http://127.0.0.1:5174';
const out = new URL('../data/local/ui-proportions/', import.meta.url);
await mkdir(out, { recursive: true });
let browser;
try { browser = await chromium.launch({ headless: true }); }
catch { browser = await chromium.launch({ headless: true, channel: 'msedge' }); }
const report = [];
const pageErrors = [];
const routes = [
  ['home', '/'], ['catalog', '/bilar'],
  ['detail', '/bilar/tesla-model-3-long-range-rwd'], ['compare', '/jamfor'],
];
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on('pageerror', (error) => pageErrors.push(error.message));
  const fontSize = (selector) => page.locator(selector).first().evaluate((node) => parseFloat(getComputedStyle(node).fontSize));
  for (const [width, height] of [[1440, 900], [1280, 800], [1024, 768], [768, 1024], [390, 844], [320, 800]]) {
    await page.setViewportSize({ width, height });
    for (const [name, path] of routes) {
      await page.goto(base + path, { waitUntil: 'domcontentloaded' });
      await page.locator('h1').waitFor();
      if (name === 'home') await page.locator('.homeVehicleCard').first().waitFor();
      if (name === 'catalog') await page.locator('.carCard').first().waitFor();
      if (name === 'compare' && await page.locator('#comparison-add-car').count()) {
        for (let index = 0; index < 3; index++) {
          if (!await page.locator('#comparison-add-car').count()) break;
          await page.locator('#comparison-add-car').selectOption({ index: 1 });
        }
      }
      if (name === 'compare') assert.equal(await page.locator('.comparisonVehicle').count(), 3);
      await page.evaluate(() => document.fonts.ready);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name}/${width}: no horizontal overflow`);
      const h1Size = await fontSize('h1');
      assert(h1Size <= (width <= 560 ? 36 : name === 'home' ? 56 : name === 'detail' ? 52 : 40), `${name}/${width}: controlled heading scale`);
      if (name === 'home') {
        const button = page.getByRole('button', { name: 'Hitta min elbil', exact: true });
        assert((await button.boundingBox()).y + (await button.boundingBox()).height <= height, `${width}: advisor action visible without scrolling`);
        assert(await fontSize('.homeAdvisorForm > label') >= 13);
        if (width <= 800) {
          const targets = await page.locator('.homeSuggestions button').evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height));
          assert(targets.every((size) => size >= 44), `${width}: suggestion touch targets`);
        }
        if (width >= 1280) assert((await page.locator('.homeHero').boundingBox()).height < 720, `${width}: compact desktop hero`);
      }
      if (name === 'catalog') {
        const firstCard = await page.locator('.carCard').first().boundingBox();
        const firstCardLimit = width <= 360 ? 560 : width <= 560 ? 510 : width <= 800 ? 480 : 460;
        assert(firstCard.y < firstCardLimit, `${width}: actual cars appear promptly (${Math.round(firstCard.y)}px)`);
        assert(await fontSize('.vehicleCard .homeVehicleSpecs dt') >= 13);
        assert(await fontSize('.vehicleCard .homeVehicleActions a') >= 14);
        if (width > 560) {
          const prices = await page.locator('.carCard .homeVehiclePrice').evaluateAll((nodes) => nodes.slice(0, 2).map((node) => node.getBoundingClientRect().y));
          assert(Math.abs(prices[0] - prices[1]) < 2, `${width}: card prices share a baseline`);
        }
        if (width <= 800) {
          const sizes = await page.locator('.catalogViewToggle button, .catalogFilterTrigger, .catalogSort select').evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height));
          assert(sizes.every((size) => size >= 44), `${width}: catalog touch targets`);
        }
      }
      if (name === 'detail') {
        const stats = await page.locator('.vehicleHeroStats').boundingBox();
        if (width <= 800) {
          const actions = await page.locator('.vehicleHeroActions').boundingBox();
          assert(stats.y - actions.y - actions.height <= 48, `${width}: no artificial void before specifications`);
        } else assert(stats.y + stats.height <= height, `${width}: hero facts visible without scrolling`);
        const clipped = await page.locator('.vehicleHeroStats strong').evaluateAll((nodes) => nodes.filter((node) => node.scrollWidth > node.clientWidth + 1).map((node) => node.textContent));
        assert.deepEqual(clipped, [], `${width}: missing values fit spec panel`);
      }
      if (name === 'compare' && width > 800) {
        const prices = await page.locator('.comparisonVehicle p').evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().bottom));
        assert(Math.max(...prices) - Math.min(...prices) < 2, `${width}: comparison prices align`);
      }
      if (name === 'compare' && width <= 560) {
        const heights = await page.locator('.comparisonVehicle').evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height));
        assert(heights.every((size) => size <= 176), `${width}: compact comparison selections`);
      }
      if (width === 1440 || width === 390) {
        await page.waitForFunction(() => [...document.images].filter((image) => {
          const rect = image.getBoundingClientRect();
          return rect.top < innerHeight && rect.bottom > 0;
        }).every((image) => image.complete), null, { timeout: 15000 }).catch(() => {});
        await page.screenshot({ path: fileURLToPath(new URL(`after-${width}-${name}.png`, out)) });
      }
      report.push({ page: name, width, h1Size });
      console.log(JSON.stringify(report.at(-1)));
    }
  }
  assert.deepEqual(pageErrors, [], 'no browser runtime errors');
  console.log(JSON.stringify({ ui_proportions_ok: true, layouts: report.length, productionWrites: false, aiRequests: false }));
} finally {
  await browser.close();
  await writeFile(new URL('report.json', out), JSON.stringify(report, null, 2));
}
