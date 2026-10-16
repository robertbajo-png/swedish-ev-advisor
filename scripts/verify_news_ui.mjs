import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';

// Test-only transport fixtures. These are never written to the public news export.
const base = process.env.NEWS_UI_URL || 'http://127.0.0.1:5174';
const out = new URL('../data/local/news-qa/', import.meta.url);
await mkdir(out, { recursive: true });
const records = [
  { id: 'test-one', slug: 'testartikel-om-elbilar', title: 'Testartikel: en uppdaterad elbil för Europa', intro: 'Detta är testdata för att kontrollera nyhetssidans layout, läsbarhet och navigation. Texten publiceras aldrig i den riktiga nyhetsdatabasen.', category: 'modeller', brands: ['Testmärke'], published_at: '2026-10-15T12:00:00Z',
    paragraphs: [{ text: 'Den här artikeln används endast i ett automatiserat gränssnittstest. Vi kontrollerar rubriker, källänkar och att längre stycken får plats på både små och stora skärmar.', kind: 'reporting' }, { text: 'För dig som läser nyheter är det viktigt att kunna gå vidare till bilens uppgifter och jämföra relevanta alternativ. Även denna text är en testfixtur.', kind: 'analysis' }],
    related_models: [{ key: 'Kia|Ev6', brand: 'Kia', model: 'EV6', car_slug: 'kia-ev6-rwd' }],
    sources: [{ item_id: 'source', url: 'https://example.com/news', publisher: 'Testkälla', title: 'Test source article', published_at: '2026-10-15T10:00:00Z', kind: 'primary' }], editorial_method: 'Testfixtur', image: null },
  { id: 'test-two', slug: 'testartikel-om-laddning', title: 'Testartikel: laddning och nya möjligheter', intro: 'En andra testartikel för att verifiera att filtrering efter både bilmärke och kategori fungerar.', category: 'laddning', brands: ['Annat testmärke'], published_at: '2026-10-14T12:00:00Z', paragraphs: [], related_models: [], sources: [], editorial_method: 'Testfixtur', image: null }
];
let browser;
try { browser = await chromium.launch({ headless: true }); }
catch { browser = await chromium.launch({ headless: true, channel: 'msedge' }); }
const errors = [];
try {
  const page = await browser.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  const cars = JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8'));
  await page.route('**/rest/v1/public_ev_variants?**', (route) => route.fulfill({ json: cars.records }));
  await page.route('**/rest/v1/public_news_articles?**', (route) => route.fulfill({ json: records.map((r) => ({ id: r.id, slug: r.slug, published_at: r.published_at, payload: r })) }));
  await page.route('**/data/news_articles.json', (route) => route.fulfill({ json: { records } }));
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    await page.setViewportSize(viewport);
    await page.goto(base + '/nyheter');
    await page.getByRole('heading', { name: records[0].title }).waitFor();
    await page.screenshot({ path: fileURLToPath(new URL(`listing-${name}.png`, out)), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${name} listing overflow`);
    await page.getByLabel('Märke', { exact: true }).selectOption('Testmärke');
    assert.equal(await page.getByRole('heading', { name: records[1].title }).count(), 0);
    await page.getByRole('link', { name: records[0].title, exact: true }).click();
    await page.getByRole('heading', { name: records[0].title, level: 1 }).waitFor();
    await page.getByRole('heading', { name: 'Vad betyder detta för dig som bilköpare?' }).waitFor();
    assert.equal(await page.getByRole('link', { name: /Testkälla:/ }).getAttribute('href'), 'https://example.com/news');
    assert.equal(await page.locator('.newsRelated').getByRole('link', { name: 'Kia EV6', exact: true }).getAttribute('href'), '/bilar/kia-ev6-rwd');
    const ld = JSON.parse(await page.locator('script[data-jsonld="page"]').textContent());
    assert.equal(ld['@type'], 'NewsArticle');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${name} article overflow`);
    await page.screenshot({ path: fileURLToPath(new URL(`article-${name}.png`, out)), fullPage: true });
  }
  await page.goto(base + '/');
  await page.getByRole('heading', { name: 'Det senaste i elbilsvärlden' }).waitFor();
  await page.goto(base + '/bilar/kia-ev6-rwd');
  await page.getByRole('heading', { name: 'Senaste nytt om denna bil' }).waitFor();
  await page.unroute('**/data/news_articles.json');
  await page.unroute('**/rest/v1/public_news_articles?**');
  await page.route('**/data/news_articles.json', (route) => route.fulfill({ json: { records: [] } }));
  await page.route('**/rest/v1/public_news_articles?**', (route) => route.fulfill({ json: [] }));
  await page.goto(base + '/nyheter');
  await page.getByRole('heading', { name: 'Snart mer från elbilsvärlden' }).waitFor();
  assert.deepEqual(errors, [], 'No client runtime errors');
  console.log(JSON.stringify({ news_ui_ok: true, viewports: ['1440x1000', '390x844'], screenshots: out.pathname, fixture_only: true }));
} finally { await browser.close(); }
