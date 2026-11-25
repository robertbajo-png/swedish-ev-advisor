import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { launchQaBrowser } from './qa_browser.mjs';

const base = process.env.SITE_QA_URL || 'http://127.0.0.1:5174';
const out = new URL('../data/local/ui-proportions/', import.meta.url);
await mkdir(out, { recursive: true });
const browser = await launchQaBrowser();
const report = [];
const pageErrors = [];
const routes = [
  ['home', '/'], ['advisor', '/radgivare'], ['catalog', '/bilar'],
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
      if (name === 'home' || name === 'advisor') await page.locator('.homeVehicleCard').first().waitFor();
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
      if (name === 'home') {
        const title = await page.locator('.bilCover h1').evaluate(node => {
          const range = document.createRange();
          range.selectNodeContents(node);
          const lines = [...range.getClientRects()];
          const column = node.closest('.bilCoverText').getBoundingClientRect();
          const description = node.nextElementSibling.getBoundingClientRect();
          return {
            font: getComputedStyle(node).fontFamily,
            fontLoaded: [...document.fonts].some(face => face.family === 'Newsreader' && face.status === 'loaded'),
            lines: new Set(lines.map(line => Math.round(line.top))).size,
            contained: lines.every(line => line.left >= column.left && line.right <= Math.min(column.right, innerWidth) + 1 && line.bottom <= description.top + 1),
          };
        });
        assert.match(title.font, /^Newsreader/);
        assert(title.fontLoaded, `${width}: Newsreader is loaded for the cover title`);
        assert(h1Size >= 36 && h1Size <= 106, `${width}: approved cover type scale (${h1Size}px)`);
        assert(title.lines > 0 && title.lines <= 2 && title.contained, `${width}: fully visible title with no overlapping description`);
        const firstStop = await page.locator('.bilWeekRoute summary').first().boundingBox();
        const submit = await page.getByRole('button', { name: 'Visa bilurval' }).boundingBox();
        assert(firstStop.y + firstStop.height <= height, `${width}: first route control visible in the opening viewport`);
        assert(submit.y + submit.height <= height, `${width}: route action visible in the opening viewport`);
        assert(await page.locator('.bilWeekRoute summary').evaluateAll(nodes => nodes.length === 3 && nodes.every(node => node.getBoundingClientRect().height >= 44)));
      } else {
        assert(h1Size <= (width <= 560 ? 36 : name === 'advisor' ? 56 : name === 'detail' ? 52 : 40), `${name}/${width}: controlled heading scale`);
      }
      if (name === 'advisor') {
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
        if (width <= 360) {
          const nav = await page.locator('.bilHeader nav a').evaluateAll(links => links.map(link => {
            const { top, right, left, height } = link.getBoundingClientRect();
            return { name: link.textContent.trim(), top, right, left, height };
          }));
          assert(nav.length === 5 && nav.every(({ top, left, right, height }) => top === nav[0].top && left >= 0 && right <= width && height >= 44),
            `${width}: compact, visible catalog navigation (${JSON.stringify(nav)})`);
        }
        assert(firstCard.y < firstCardLimit, `${width}: actual cars appear promptly (${Math.round(firstCard.y)}px)`);
        assert(await fontSize('.vehicleCard .homeVehicleSpecs dt') >= 13);
        assert(await fontSize('.vehicleCard .homeVehicleActions a') >= 14);
        if (width > 560) {
          const cards = await page.locator('.carCard').evaluateAll((nodes) => nodes.map((node) => ({
            top: node.getBoundingClientRect().top,
            price: node.querySelector('.homeVehiclePrice').getBoundingClientRect().top,
            title: node.querySelector('.vehicleCardTitle').textContent,
          })));
          let pairs = 0;
          for (let i = 1; i < cards.length; i++) {
            const previous = cards[i - 1], current = cards[i];
            if (Math.abs(current.top - previous.top) < 2) {
              pairs++;
              assert(Math.abs(current.price - previous.price) < 2, `${width}: card prices share a baseline (${previous.title}, ${current.title})`);
            }
          }
          assert(pairs > 0, `${width}: multicolumn catalog rows are exercised`);
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
        const prices = await page.locator('.comparisonVehicle > div:last-child > p').evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().bottom));
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
