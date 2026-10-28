import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import AxeBuilder from '@axe-core/playwright';
import { launchQaBrowser } from './qa_browser.mjs';
import { retiredSlug } from './current_variant_sync.mjs';

const base = process.env.VEHICLE_UI_URL || 'http://127.0.0.1:5174';
const snapshot = JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8'));
const registry = JSON.parse(await readFile(new URL('../src/vehicle-redirects.json', import.meta.url), 'utf8'));
const output = new URL('../data/local/design-qa/', import.meta.url);
await mkdir(output, { recursive: true });
const browser = await launchQaBrowser();
const errors = [], posts = [];
let checked = 0;
try {
  for (const [name, viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {
      const request = route.request(), url = new URL(request.url());
      if (request.method() !== 'GET') { posts.push(url.pathname); return route.abort(); }
      if (url.pathname.endsWith('/data/public_ev_variants.json')) return route.fulfill({json:snapshot});
      if (url.pathname.includes('/rest/v1/public_ev_variants')) return route.fulfill({json:snapshot.records});
      if (url.pathname.includes('/api/')) return route.fulfill({status:503,json:{error:'Providers disabled in UI verification'}});
      return route.continue();
    });
    for (const entry of registry.redirects) {
      await page.goto(base + '/bilar/' + entry.slug + '/');
      await page.waitForURL(url => url.pathname === '/bilar' && url.searchParams.get('brand') === entry.brand && url.searchParams.get('query') === entry.model);
      const card = page.locator('.carCard').first();
      await card.waitFor().catch(error => { throw new Error('Retired link has no current model cards: '+entry.slug, {cause:error}); });
      assert.equal(await page.locator('#desktop-price').inputValue(),'1200000');
      assert.equal(await page.getByRole('searchbox',{name:'Sök bilmodell'}).inputValue(),entry.model);
      const titles = await page.locator('.carCard .vehicleCardTitle').allTextContents();
      assert(titles.length && titles.every(title => title.includes(entry.brand)), 'Retired link must remain within the same manufacturer');
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      checked++;
    }
    const basic = snapshot.records.find(row => row.brand === 'Kia' && row.model === 'Ev3' && row.variant_name === 'EV3 FWD');
    assert(basic && basic.wltp_range_km === null && basic.dc_charge_kw === null);
    await page.goto(base + '/bilar/' + retiredSlug(basic.brand,basic.model,basic.variant_name));
    await page.locator('.vehicleDetailHero h1').waitFor();
    const hero = await page.locator('.vehicleDetailHero').innerText();
    assert(hero.replace(/\s/g,' ').includes(basic.price_sek.toLocaleString('sv-SE').replace(/\s/g,' ') + ' kr'));
    assert.match(hero,/Uppgift saknas/);
    assert(!/\b0 (?:km|kW|kg)\b/.test(hero), 'Unknown technical values are not zeros');
    assert.deepEqual((await new AxeBuilder({page}).analyze()).violations.map(v=>v.id),[]);
    await page.screenshot({path:fileURLToPath(new URL('current-basic-profile-'+name+'.png',output)),fullPage:true});
    const longest=[...snapshot.records].sort((a,b)=>b.variant_name.length-a.variant_name.length)[0];
    await page.goto(base+'/bilar/'+retiredSlug(longest.brand,longest.model,longest.variant_name));
    await page.locator('.vehicleDetailHero h1').waitFor();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Long exact stock identities must fit');
    assert.deepEqual(await page.locator('.vehicleHeroCopy h1, .vehicleHeroCopy p').evaluateAll(nodes=>nodes.filter(node=>node.scrollWidth>node.clientWidth+1).map(node=>node.textContent)),[]);
    assert.deepEqual((await new AxeBuilder({page}).analyze()).violations.map(v=>v.id),[]);
    await page.screenshot({path:fileURLToPath(new URL('current-long-stock-profile-'+name+'.png',output)),fullPage:true});
    // Exercise the SPA resolver separately from the static HTML redirect fallback.
    const first = registry.redirects[0];
    await page.evaluate(slug => {history.pushState({},'', '/bilar/'+slug); dispatchEvent(new PopStateEvent('popstate'));}, first.slug);
    await page.waitForURL(url => url.pathname === '/bilar' && url.searchParams.get('brand') === first.brand);
    await page.locator('.carCard').first().waitFor();
    await context.close();
  }
  assert.deepEqual(errors,[]);
  assert.deepEqual(posts,[]);
  console.log(JSON.stringify({vehicle_redirect_ui_ok:true,retired_links_checked:checked,spa_and_static_fallback:true,
    basic_profile_nulls:true,accessibility_violations:0,viewports:['1440x1000','390x844'],paid_calls:0}));
} finally {await browser.close();}
