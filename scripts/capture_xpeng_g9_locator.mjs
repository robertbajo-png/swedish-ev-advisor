import assert from 'node:assert/strict';
import { launchQaBrowser } from './qa_browser.mjs';

// The public locator is rendered in the browser; do not submit any forms.
const url = 'https://www.xpeng.com/se/find-us';
const name = 'XPENG Experience Center Sweden Karlstad';
const allowedDomains = ['xpeng.com', 'xiaopeng.com'];
const browser = await launchQaBrowser();
try {
  const context = await browser.newContext({ serviceWorkers: 'block', locale: 'sv-SE' });
  await context.route('**/*', route => {
    const request = route.request();
    const host = new URL(request.url()).hostname;
    if (!['GET', 'OPTIONS'].includes(request.method())
        || !allowedDomains.some(domain => host === domain || host.endsWith('.' + domain))) return route.abort();
    return route.continue();
  });
  const page = await context.newPage();
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
  assert.equal(response?.status(), 200);
  assert.notEqual(response.headers()['tdm-reservation'], '1', 'Respect the locator text-mining reservation');
  assert.equal(page.url(), url);
  await page.getByText(name, { exact: true }).first().waitFor({ state: 'attached', timeout: 15000 });
  const blocks = await page.evaluate(label => {
    const titles = [...document.querySelectorAll('h3')]
      .filter(el => el.textContent.trim() === label && !el.querySelector('*'));
    return [...new Set(titles.map(el => el.parentElement).filter(el =>
      el?.textContent.includes('Blockgatan 5') && el.textContent.includes('info@lecab.se')).map(el => el.outerHTML))];
  }, name);
  assert(blocks.length === 1 && blocks[0].length < 16000, 'Expected one exact official Karlstad outlet card');
  console.log(JSON.stringify({ final_url: url, http_status: 200, rendered_html: blocks[0],
    fetched_at: new Date().toISOString(), body_kind: 'rendered_official_outlet_card' }));
} finally {
  await browser.close();
}
