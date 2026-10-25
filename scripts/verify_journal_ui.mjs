import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { launchQaBrowser } from './qa_browser.mjs';

const base = process.env.NEWS_UI_URL || 'http://127.0.0.1:5174';
const out = new URL('../data/local/news-qa/', import.meta.url);
const publicPath = new URL('../public/data/news_articles.json', import.meta.url);
const originalExport = await readFile(publicPath, 'utf8');
await mkdir(out, { recursive: true });
const titles = [
  'Testartikel: en uppdaterad elbil för Europa',
  'Testartikel: laddning längs de långa resorna',
  'Testartikel: nästa steg för batterierna',
  'Testartikel: nya perspektiv på elbilsmarknaden',
  'Testartikel: ett svenskt prisbesked',
  'Testartikel: ett oberoende vintertest',
  'Testartikel: förändringar i modellprogrammet',
  'Testartikel: säkerhet och ny teknik',
];
// Browser transport only. These stories/images are never saved to production data.
const records = titles.map((title, index) => ({
  id: 'journal-fixture-' + index, slug: 'qa-testartikel-' + index, title,
  intro: 'Detta är testdata för den redaktionella förhandsvisningen. Artikeln används endast för att granska layout och funktioner och är inte en publicerad nyhet.',
  published_at: new Date(Date.UTC(2026, 9, 15 - index, 12)).toISOString(),
  brands: [[ 'Kia' ], [ 'Annat testmärke' ], [ 'Kia' ], [ 'Volvo' ], [ 'Volvo' ], [ 'Annat testmärke' ], [ 'Kia' ], [ 'Volvo' ]][index],
  category: ['modeller', 'laddning', 'batterier', 'marknad', 'priser', 'tester', 'uppdateringar', 'sakerhet'][index],
  paragraphs: [
    { kind: 'reporting', text: 'Den här texten är en testfixtur, inte en verklig nyhet. Den kontrollerar läsbredd, radavstånd och hur en artikel följer med mellan dator, surfplatta och mobil.' },
    { kind: 'reporting', text: 'Originaltextens ordning ska bevaras. Källhänvisningar och publiceringsdatum ska finnas kvar även när artikelns visuella form förändras. Inga värden eller uttalanden läggs till av gränssnittet.' },
    { kind: 'analysis', text: 'Detta stycke testar hur ett köparperspektiv skiljs från rapporterade fakta. Innehållet är fortfarande en testfixtur, utan någon faktisk rekommendation om bilköp.' },
    { kind: 'analysis', text: 'Bilarnas riktiga publicerade poster visas separat. En nyhetsartikel får inte ändra ett verifierat pris eller en specifikation, och inte heller ersätta bilens egen faktakälla.' },
  ],
  sources: [{ item_id: 'source-' + index, publisher: 'Testkälla', title: 'Originalrapport för gränssnittstest', url: 'https://example.com/qa-news-' + index, published_at: '2026-10-10T12:00:00Z', kind: 'primary' }],
  related_models: index === 0 ? [{ key: 'Kia|Ev6', brand: 'Kia', model: 'EV6', car_slug: 'kia-ev6-rwd' }] : [],
  image: null, editorial_method: 'Testfixtur, inte publicerad',
}));
const draft = { ...records[0], id: 'private-draft', slug: 'privat-utkast', title: 'Hemligt testutkast', status: 'quarantined' };
const browser = await launchQaBrowser();
const errors = [];
try {
  const page = await browser.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  const cars = JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8'));
  await page.route('**/rest/v1/public_ev_variants?**', (route) => route.fulfill({ json: cars.records }));
  const newsPayload = () => [...records, draft];
  const apiPattern = '**/rest/v1/public_news_articles?**';
  const staticPattern = '**/data/news_articles.json';
  await page.route(apiPattern, (route) => route.fulfill({ json: newsPayload().map((article) => ({ id: article.id, slug: article.slug, published_at: article.published_at, payload: article })) }));
  await page.route(staticPattern, (route) => route.fulfill({ json: { records: newsPayload() } }));
  const noOverflow = async (name) => {
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), name + ': document overflow');
    assert(await page.locator('h1, .newsStoryTitle').evaluateAll((items) => items.every((item) => item.scrollWidth <= item.clientWidth + 1)), name + ': clipped headline');
  };
  for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['tablet', { width: 820, height: 1180 }], ['mobile', { width: 390, height: 844 }], ['small', { width: 320, height: 740 }]]) {
    await page.setViewportSize(viewport);
    await page.goto(base + '/nyheter');
    await page.getByRole('heading', { name: records[0].title }).waitFor();
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator('.newsStory--lead').count(), 1);
    assert.equal(await page.locator('.newsStory--secondary').count(), 2);
    assert.equal(await page.locator('.newsStory--recent').count(), 5);
    assert.equal(await page.getByText('Hemligt testutkast').count(), 0);
    assert.equal(await page.locator('.newsStory img').count(), 0, 'No borrowed vehicle photos as article images');
    await noOverflow(name + ' listing');
    await page.screenshot({ path: fileURLToPath(new URL('journal-listing-' + name + '-fixtures.png', out)), fullPage: true });
    if (name === 'desktop') await page.screenshot({ path: fileURLToPath(new URL('journal-preview-desktop-fixtures.png', out)) });
    await page.getByRole('combobox', { name: 'Märke', exact: true }).selectOption('Kia');
    assert.equal(await page.locator('.newsStory').count(), 3);
    await page.getByRole('button', { name: 'Teknik & batterier', exact: true }).click();
    assert.equal(await page.locator('.newsStory').count(), 1);
    assert.equal(await page.locator('.journalSecondary').count(), 0);
    await page.getByRole('button', { name: 'Priser & marknad', exact: true }).click();
    await page.getByRole('heading', { name: 'Inga nyheter matchar ditt val' }).waitFor();
    await page.getByRole('button', { name: 'Visa alla nyheter', exact: true }).click();
    assert.equal(await page.locator('.newsStory').count(), 8);
    await page.getByRole('link', { name: records[0].title, exact: true }).click();
    await page.getByRole('heading', { name: records[0].title, level: 1 }).waitFor();
    assert.equal(await page.getByRole('heading', { name: 'Vad betyder detta för dig som bilköpare?', exact: true }).count(), 1);
    assert.deepEqual(await page.locator('.newsArticleBody p').allTextContents(), records[0].paragraphs.map((paragraph) => paragraph.text));
    assert.equal(await page.getByRole('link', { name: /Testkälla:/ }).getAttribute('href'), records[0].sources[0].url);
    await page.locator('.newsRelated .vehicleCard').waitFor();
    assert.equal(await page.locator('.newsRelated').getByRole('link', { name: 'Kia EV6', exact: true }).getAttribute('href'), '/bilar/kia-ev6-rwd');
    const structured = JSON.parse(await page.locator('script[data-jsonld="page"]').textContent());
    assert.equal(structured['@type'], 'NewsArticle');
    assert.deepEqual(structured.citation, [records[0].sources[0].url]);
    assert.equal(structured.image, undefined);
    assert.match(await page.getByRole('heading', { name: records[0].title, level: 1 }).evaluate((element) => getComputedStyle(element).fontFamily), /Newsreader/);
    await noOverflow(name + ' article');
    const image = page.locator('.newsRelated .vehicleCard img');
    if (await image.count()) {
      await image.scrollIntoViewIfNeeded();
      await image.evaluate((element) => element.complete || new Promise((resolve) => { element.addEventListener('load', resolve, { once: true }); element.addEventListener('error', resolve, { once: true }); setTimeout(resolve, 5000); }));
    }
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.screenshot({ path: fileURLToPath(new URL('journal-article-' + name + '-fixtures.png', out)), fullPage: true });
    if (name === 'desktop') {
      await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (text) => { window.__testCopiedLink = text; } } }));
      await page.getByRole('button', { name: 'Kopiera länk', exact: true }).click();
      await page.getByRole('button', { name: 'Länk kopierad', exact: true }).waitFor();
      assert.equal(await page.evaluate(() => window.__testCopiedLink), base + '/nyheter/' + records[0].slug);
      await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async () => { throw new Error('Test-only clipboard failure'); } } }));
      await page.getByRole('button', { name: 'Länk kopierad', exact: true }).click();
      await page.getByText('Länken kunde inte kopieras.', { exact: true }).waitFor();
    }
  }
  const testImage = 'https://example.com/journal-test-image.png';
  await page.route(testImage, (route) => route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=', 'base64') }));
  records[0].image = { url: testImage, alt: 'En bild endast för test', credit: 'Testbild, inte publicerad', source_url: 'https://example.com/press', license_url: 'https://example.com/rights', rights_status: 'approved' };
  await page.goto(base + '/nyheter/' + records[0].slug);
  await page.locator('.journalArticle > .journalImage img').waitFor();
  assert.equal(await page.getByRole('link', { name: 'Bildvillkor', exact: true }).getAttribute('href'), records[0].image.license_url);
  assert.equal(JSON.parse(await page.locator('script[data-jsonld="page"]').textContent()).image, testImage);
  await page.locator('.journalArticle > .journalImage img').evaluate((image) => image.dispatchEvent(new Event('error')));
  assert.equal(await page.locator('.journalArticle > .journalImage').count(), 0, 'Failed image becomes text-only, no replacement');
  records[0].image.rights_status = 'unknown';
  await page.goto(base + '/nyheter');
  await page.getByRole('heading', { name: records[0].title }).waitFor();
  assert.equal(await page.locator('.newsStory img').count(), 0, 'No image without approved rights');
  await page.goto(base + '/');
  await page.getByRole('heading', { name: 'Det senaste i elbilsvärlden' }).waitFor();
  assert.equal(await page.locator('.journalPreview .newsStory').count(), 3);
  await page.goto(base + '/bilar/kia-ev6-rwd');
  await page.getByRole('heading', { name: 'Senaste nytt om denna bil' }).waitFor();
  assert.equal(await page.locator('.journalPreview .newsStory').count(), 1);
  await page.unroute(apiPattern);
  await page.unroute(staticPattern);
  let release;
  let signalStarted;
  const started = new Promise((resolve) => { signalStarted = resolve; });
  const delay = () => new Promise((resolve) => { release = resolve; signalStarted(); });
  await page.route(apiPattern, async (route) => { await delay(); await route.fulfill({ json: [] }); });
  await page.route(staticPattern, async (route) => { await delay(); await route.fulfill({ json: { records: [] } }); });
  await page.goto(base + '/nyheter');
  await page.getByText('Hämtar nyheter...', { exact: true }).waitFor();
  assert.equal(await page.locator('.newsSkeletons').count(), 1);
  await started;
  release();
  await page.getByRole('heading', { name: 'Snart mer från elbilsvärlden' }).waitFor();
  await page.unroute(apiPattern);
  await page.route(apiPattern, (route) => route.fulfill({ status: 503 }));
  await page.unroute(staticPattern);
  await page.route(staticPattern, (route) => route.fulfill({ status: 503 }));
  await page.goto(base + '/nyheter');
  await page.getByRole('heading', { name: 'Nyheterna kunde inte hämtas' }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Försök igen', exact: true }).count(), 1);
  await page.unroute(staticPattern);
  await page.route(staticPattern, (route) => route.fulfill({ json: { records: [] } }));
  await page.getByRole('button', { name: 'Försök igen', exact: true }).click();
  await page.getByRole('heading', { name: 'Snart mer från elbilsvärlden' }).waitFor();
  await page.screenshot({ path: fileURLToPath(new URL('journal-empty-mobile.png', out)), fullPage: true });
  await page.goto(base + '/nyheter/finns-inte');
  await page.getByRole('heading', { name: 'Nyheten hittades inte' }).waitFor();
  assert.deepEqual(errors, [], 'No client runtime errors');
  assert.equal(await readFile(publicPath, 'utf8'), originalExport, 'Test fixtures never change public news');
  console.log(JSON.stringify({ journal_ui_ok: true, fixture_only: true, viewports: ['1440x1000', '820x1180', '390x844', '320x740'], checks: ['lead + secondary + recent', 'brand/topic filters', 'original paragraph order', 'sources', 'canonical vehicle card', 'JSON-LD', 'copy link', 'image rights/failure', 'home/detail previews', 'loading/empty/error/404'], screenshots: fileURLToPath(out) }));
} finally { await browser.close(); }
