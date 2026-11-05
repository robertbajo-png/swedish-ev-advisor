import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { launchQaBrowser } from './qa_browser.mjs';

const base = process.env.PUBLIC_CONTENT_QA_URL || 'http://127.0.0.1:5174';
const origin = new URL(base).origin;
const out = 'data/local/seo-qa';
await mkdir(out, { recursive: true });
const browser = await launchQaBrowser();
const result = [], errors = [];
try {
  for (const javascript of [false, true]) {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, javaScriptEnabled: javascript });
    await context.route('**/*', (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== origin || route.request().method() !== 'GET' || url.pathname.startsWith('/api/')) return route.abort();
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => { if (/hydration|hydrating|server rendered/i.test(message.text())) errors.push(message.text()); });
    if (javascript) await page.addInitScript(() => {
      window.__labVitals = { lcp: null, cls: 0 };
      new PerformanceObserver((list) => { for (const entry of list.getEntries()) window.__labVitals.lcp = entry.startTime; }).observe({ type: 'largest-contentful-paint', buffered: true });
      new PerformanceObserver((list) => { for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__labVitals.cls += entry.value; }).observe({ type: 'layout-shift', buffered: true });
    });
    for (const path of ['/', '/familj', '/under-500000', '/bilar/tesla-model-3-long-range-rwd']) {
      const response = await page.goto(base + path, { waitUntil: 'networkidle' });
      assert(response.ok());
      assert.equal(await page.locator('h1').count(), 1);
      const expected = { '/': 'Hitta elbilen', '/familj': 'familj', '/under-500000': '500 000', '/bilar/tesla-model-3-long-range-rwd': 'Tesla Model 3' }[path];
      assert((await page.locator('h1').innerText()).includes(expected), path + ': correct route, not a generic SPA fallback');
      assert.equal(await page.locator('#main-content').count(), 1);
      assert(await page.locator('a[href="/bilar"]').count());
      assert(!/Hämtar bilar|Hämtar bilen/.test(await page.locator('main').innerText()));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, path + ': no mobile overflow');
      if (javascript) {
        await page.waitForFunction(() => !document.querySelector('script[data-prerender="page"]'));
        await page.evaluate(() => document.fonts.ready);
        result.push({ path, mode: 'isolated_local_lab_not_field_data', ...await page.evaluate(() => window.__labVitals) });
        if (path === '/familj') {
          const before = await page.locator('.vehicleCard').count();
          await page.getByLabel('Sök bilmodell').fill('not-a-real-car');
          assert(before > 0); assert.equal(await page.locator('.vehicleCard').count(), 0);
        }
      }
      await page.screenshot({ path: `${out}/${path.replaceAll('/', '-') || 'home'}-${javascript ? 'hydrated' : 'no-js'}.png`, fullPage: false });
    }
    if (javascript) {
      await page.goto(base + '/bilar?brand=Tesla&query=Model');
      await page.waitForFunction(() => !document.querySelector('script[data-prerender="page"]'));
      assert.equal(await page.locator('#desktop-brand').inputValue(), 'Tesla', 'Deep-link filters survive hydration');
    }
    await context.close();
  }
  assert.deepEqual(errors, [], 'Hydration or runtime errors');
  await writeFile(out + '/mobile-lab.json', JSON.stringify({ checked_at: new Date().toISOString(), base, observations: result, field_data_available: false, paid_calls: 0 }, null, 2));
  console.log(JSON.stringify({ static_and_hydrated_mobile_routes: 8, errors, paid_calls: 0, lab: result }));
} finally { await browser.close(); }
