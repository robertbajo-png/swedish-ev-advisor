import assert from 'node:assert/strict';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';
import { AxeBuilder } from '@axe-core/playwright';
import { launchQaBrowser } from './qa_browser.mjs';
import { isolatePublicDataFixture } from './qa_public_data_fixture.mjs';
import { vehicleSlug } from '../src/vehicle-names.js';
import { coverPhoto, photoCredit } from '../src/biljournal-images.js';

const base = process.env.SITE_QA_URL || 'http://127.0.0.1:5174';
const out = new URL('../data/local/design-qa/', import.meta.url);
const carFile = new URL('../public/data/public_ev_variants.json', import.meta.url);
const newsFile = new URL('../public/data/news_articles.json', import.meta.url);
const originalCars = await readFile(carFile, 'utf8');
const originalNews = await readFile(newsFile, 'utf8');
const cars = JSON.parse(originalCars).records;
const vehicleId = row => vehicleSlug(row.brand, row.model, row.variant_name);
const tesla = cars.find(row => vehicleId(row) === 'tesla-model-3-long-range-rwd');
const inster = cars.find(row => row.brand === 'Hyundai' && row.model === 'Inster');
assert(tesla && inster, 'The source and image cases require canonical variants');
// Only browser transport uses this clearly labelled story. No publication occurs.
const articles = [{
  id: 'site-qa-story', slug: 'qa-granskning-inte-en-nyhet', status: 'published',
  title: 'Testartikel: en elbil och ett svenskt perspektiv',
  intro: 'Detta är enbart en testfixtur för tillgänglighet och layout, inte en verklig publicerad nyhet.',
  category: 'modeller', brands: ['Kia'], published_at: '2026-10-15T12:00:00Z', image: null,
  paragraphs: [
    { kind: 'reporting', text: 'Det här stycket testar läsbarheten. Inga nyheter, priser, uttalanden eller tekniska uppgifter hittas på för produktion.' },
    { kind: 'analysis', text: 'Testfixturen visar hur köparperspektiv presenteras åtskilt från rapporterade fakta. Riktiga biluppgifter visas i bilens eget kort.' },
  ],
  sources: [{ publisher: 'Testkälla', title: 'Underlag för gränssnittstest', url: 'https://example.com/qa-source' }],
  related_models: [{ key: 'Kia|Ev6', brand: 'Kia', model: 'EV6', car_slug: 'kia-ev6-rwd' }],
}];
await mkdir(out, { recursive: true });
const browser = await launchQaBrowser();
const report = { pages: [], keyboard: [], responsive: [], bundles: {}, violations: [] };
const errors = [];
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  await isolatePublicDataFixture(page);
  page.on('pageerror', (error) => errors.push(error.message));
  let dataUnavailable = false;
  const carPayload = (route, local = false) => dataUnavailable ? route.fulfill({ status: 503, body: 'QA outage' }) : route.fulfill({ json: local ? { records: cars } : cars });
  await page.route('**/rest/v1/public_ev_variants?**', (route) => carPayload(route));
  await page.route('**/data/public_ev_variants.json', (route) => carPayload(route, true));
  await page.route('**/rest/v1/public_news_articles?**', (route) => route.fulfill({ json: articles }));
  await page.route('**/data/news_articles.json', (route) => route.fulfill({ json: { records: articles } }));
  await page.route('**/api/advisor', (route) => route.fulfill({ status: 503, json: { error: 'QA outage' } }));
  await page.route('**/api/compare', (route) => route.fulfill({ status: 503, json: { error: 'QA outage' } }));
  const go = async (path) => {
    await page.goto(base + path, { waitUntil: 'domcontentloaded' });
    await page.locator('h1').waitFor();
    if (path === '/' || path === '/radgivare') await page.locator('.homeVehicleCard').first().waitFor();
    if (path === '/bilar' || path === '/familj') await page.locator('.carCard').first().waitFor();
    if (path.startsWith('/bilar/')) await page.locator('.vehicleHeroStats').waitFor();
    if (path === '/nyheter') await page.locator('.newsStory').first().waitFor();
    if (path.startsWith('/nyheter/')) await page.locator('.newsArticleBody p').first().waitFor();
    await page.evaluate(() => document.fonts.ready);
  };
  const scan = async (name) => {
    assert.equal(await page.getByRole('main').count(), 1, name + ': one main landmark');
    assert.equal(await page.getByRole('banner').count(), 1, name + ': banner outside main');
    assert.equal(await page.getByRole('contentinfo').count(), 1, name + ': footer outside main');
    assert.equal(await page.locator('h1').count(), 1, name + ': one H1');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), name + ': no document overflow');
    const clippedText = await page.locator('#home-heading, .vehicleCardTitle, .vehicleVariant, .vehiclePageIntro h1, .vehicleHeroCopy h1, .comparisonVehicle h2, .bilCostVariant h2, .newsStoryTitle, .newsArticleHeader h1').evaluateAll((nodes) => nodes.filter((node) => node.scrollWidth > node.clientWidth + 1).map((node) => node.textContent));
    assert.deepEqual(clippedText, [], name + ': no clipped titles');
    const result = await new AxeBuilder({ page }).analyze();
    const violations = result.violations.map((item) => ({ id: item.id, impact: item.impact, help: item.help, nodes: item.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })) }));
    report.pages.push({ name, rulesPassed: result.passes.length, manualChecks: result.incomplete.map((item) => item.id) });
    report.violations.push(...violations.map((violation) => ({ page: name, ...violation })));
    console.log(JSON.stringify({ page: name, violations: violations.length, ...(violations.length ? { details: violations } : {}) }));
  };
  const sourceRegion = page.locator('.bilSources');
  const goToSource = async (link, post) => {
    const target = new URL(await link.getAttribute('href'), base);
    assert.equal(target.pathname, '/kallor');
    assert.equal(target.searchParams.get('post'), post);
    await link.focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(id => document.activeElement?.id === id, post);
    return sourceRegion.locator('[id="' + post + '"]').locator('..');
  };
  const verifyModelSource = async () => {
    const source = await goToSource(page.getByRole('link', { name: 'Källor för modellen', exact: true }), 'bil-' + vehicleId(tesla));
    assert(await source.locator('a[href="' + tesla.source_url + '"]').count());
    if (tesla.price_source_url) assert(await source.locator('a[href="' + tesla.price_source_url + '"]').count());
    await source.getByText('Källbevis', { exact: true }).click();
    assert.match(await source.innerText(), new RegExp(tesla.source_hash));
  };
  const verifyCoverCredit = async () => {
    const cover = photoCredit(coverPhoto);
    const footer = page.getByRole('contentinfo').getByRole('link', { name: 'Källor och bildkrediter', exact: true });
    assert.equal(await page.getByRole('link', { name: 'Källor och bildkrediter', exact: true }).count(), 1);
    await footer.click();
    await goToSource(page.getByRole('link', { name: 'Bildkrediter', exact: true }), 'bilder');
    const credit = sourceRegion.locator('#bilder').locator('..').getByRole('listitem')
      .filter({ has: page.getByRole('heading', { name: cover.title, exact: true }) });
    assert.match(await credit.innerText(), /© M 93 \/ Wikimedia Commons.*CC-BY-SA-3.0-DE/s);
    assert.equal(await credit.getByRole('link', { name: 'Bildkälla', exact: true }).getAttribute('href'), cover.source_url);
    assert.equal(await credit.getByRole('link', { name: 'CC-BY-SA-3.0-DE', exact: true }).getAttribute('href'), cover.license_url);
    assert.match(await credit.innerText(), /Hyundai Inster.*modellvyer/s);
    assert.doesNotMatch(await credit.innerText(), /Startsidan|Omslaget/);
  };
  const routes = [
    ['home', '/'], ['advisor', '/radgivare'], ['catalog', '/bilar'], ['family', '/familj'],
    ['detail', '/bilar/tesla-model-3-long-range-rwd'], ['inster-photo', '/bilar/' + vehicleId(inster)], ['ev6', '/bilar/kia-ev6-rwd'],
    ['compare', '/jamfor'], ['sources', '/kallor'], ['verification', '/verifiering'], ['contact', '/kontakt'], ['privacy', '/integritet'], ['journal', '/nyheter'],
    ['article', '/nyheter/' + articles[0].slug],
  ];
  for (const [viewportName, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
    await page.setViewportSize(viewport);
    for (const [name, path] of routes) {
      await go(path);
      if (name === 'compare') {
        for (let index = 0; index < 3; index++) await page.locator('#comparison-add-car').selectOption({ index: 1 });
        await page.locator('.bilCostAssumptions > summary').click();
        assert.equal(await page.locator('.bilCostVariant').count(), 3);
      }
      await scan(viewportName + '-' + name);
      if (name === 'detail') {
        await verifyModelSource();
        await scan(viewportName + '-expanded-model-evidence');
        await go(path);
      }
      if (name === 'inster-photo') {
        const image = page.locator('.vehicleHeroMedia img');
        await image.evaluate(node => node.decode());
        assert.equal(await image.getAttribute('src'), coverPhoto);
        const notice = page.locator('.vehicleContainer > .vehicleImageNotice');
        assert(await notice.isVisible());
        assert.match(await notice.innerText(), /Hyundai Inster Prime.*utrustningen kan skilja/i);
        assert.doesNotMatch(await notice.innerText(), /Wikimedia|CC[- ]BY|Bildkälla/);
      }
      if (name === 'article') {
        const source = await goToSource(page.getByRole('link', { name: 'Källor för artikeln', exact: true }), 'artikel-' + articles[0].slug);
        assert.equal(await source.locator('a[href="https://example.com/qa-source"]').count(), 1);
        await go(path);
      }
      if (name === 'home') {
        assert.equal(await page.locator('.homeHeroFirst img, .bilCoverPhoto, .homeHeroFirst .homeSpotlight').count(), 0);
        assert.equal(await page.getByText('Hyundai Inster Prime', { exact: true }).count(), 0);
        assert.doesNotMatch(await page.locator('body').innerText(), /Wikimedia Commons|CC[- ]BY|Bildkälla/);
        await verifyCoverCredit();
        await go(path);
      }
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      await page.screenshot({ path: fileURLToPath(new URL(`qa-${viewportName}-${name}-fixtures.png`, out)) });
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await go('/bilar');
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  const dialogResult = await new AxeBuilder({ page }).analyze();
  report.violations.push(...dialogResult.violations.map((item) => ({ page: 'mobile-filter-dialog', id: item.id, nodes: item.nodes.map((node) => node.target) })));
  await page.keyboard.press('Escape');
  assert(await page.getByRole('button', { name: 'Filter', exact: true }).evaluate((node) => node === document.activeElement));
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
  assert.notEqual(await page.evaluate(() => document.body.style.overflow), 'hidden');
  report.responsive.push('filter closes and releases scroll at desktop breakpoint');

  await go('/');
  await page.keyboard.press('Tab');
  assert(await page.getByRole('link', { name: 'Hoppa till innehållet' }).evaluate((node) => node === document.activeElement));
  await page.keyboard.press('Enter');
  assert(await page.getByRole('main').evaluate((node) => node === document.activeElement));
  await page.getByRole('navigation', { name: 'Huvudnavigation' }).getByRole('link', { name: 'Katalog', exact: true }).click();
  await page.locator('.carCard').first().waitFor();
  assert(await page.getByRole('main').evaluate((node) => node === document.activeElement));
  await page.goBack();
  await page.locator('#home-heading').waitFor();
  assert(await page.getByRole('main').evaluate((node) => node === document.activeElement));
  const primaryNav = page.getByRole('navigation', { name: 'Huvudnavigation' });
  const verifyAdvisorFocus = async () => {
    await primaryNav.getByRole('link', { name: 'Rådgivare', exact: true }).focus();
    await page.keyboard.press('Enter');
    await page.locator('#home-advisor-query').waitFor();
    assert(await page.getByRole('main').evaluate(node => node === document.activeElement));
    await page.keyboard.press('Tab');
    await page.waitForFunction(() => document.activeElement?.id === 'home-advisor-query', null, { timeout: 2000 });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert(await page.locator('#home-advisor-query').evaluate(node => node === document.activeElement), 'Route focus must not reclaim input focus');
  };
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (let attempt = 0; attempt < 3; attempt++) {
      await primaryNav.getByRole('link', { name: 'Katalog', exact: true }).click();
      await page.locator('.carCard').first().waitFor();
      await verifyAdvisorFocus();
    }
    await verifyAdvisorFocus();
  }
  report.keyboard.push('skip link', 'SPA route focus', 'back navigation focus', 'advisor navigation and first input focus', 'exact model/article source focus', 'central cover credit');

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.evaluate(() => {
    window.qaScroll = [];
    const scroll = window.scrollTo.bind(window);
    window.scrollTo = (options) => { window.qaScroll.push(options?.behavior); scroll(options); };
    const intoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (options) { window.qaScroll.push(options?.behavior); return intoView.call(this, options); };
  });
  await page.getByRole('button', { name: 'Fyrhjulsdrift', exact: true }).first().click();
  await page.getByRole('button', { name: 'Hitta min elbil', exact: true }).click();
  await page.locator('#advisor-results-title').filter({ hasText: 'Dina rekommendationer' }).waitFor();
  const behaviours = await page.evaluate(() => window.qaScroll);
  assert(behaviours.length > 0 && behaviours.every((value) => value !== 'smooth'));
  report.keyboard.push('reduced motion respected by scripted scrolling');

  for (const width of [640, 320]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [, path] of routes) {
      await go(path);
      const overflow = await page.evaluate(() => ({
        viewport: innerWidth, width: document.documentElement.scrollWidth,
        nodes: [...document.querySelectorAll('main *, header *, footer *')].filter((node) => {
          const rect = node.getBoundingClientRect();
          return rect.right > innerWidth + 1 && getComputedStyle(node).position !== 'absolute';
        }).slice(0, 8).map((node) => ({ className: node.className, width: node.getBoundingClientRect().width })),
      }));
      if (overflow.width > width + 1) await page.screenshot({ path: fileURLToPath(new URL(`qa-overflow-${width}.png`, out)), fullPage: true });
      assert(overflow.width <= overflow.viewport + 1, width + ': ' + path + ' ' + JSON.stringify(overflow));
    }
    await go('/bilar');
    await page.locator('.carCard').first().getByRole('button', { name: 'Jämför', exact: true }).click();
    await page.getByRole('contentinfo').getByRole('button', { name: 'Till toppen' }).focus();
    const waitForRevealedFocus = () => page.waitForFunction(() => {
      const control = document.activeElement?.getBoundingClientRect();
      const bar = document.querySelector('.vehicleCompareBar')?.getBoundingClientRect();
      return control && bar && control.bottom <= bar.top;
    }, null, { timeout: 2000 });
    await waitForRevealedFocus().catch(() => {});
    const footerButton = await page.getByRole('contentinfo').getByRole('button', { name: 'Till toppen' }).boundingBox();
    const compareBar = await page.locator('.vehicleCompareBar').boundingBox();
    if (footerButton.y + footerButton.height > compareBar.y) {
      console.log(JSON.stringify({ footerButton, compareBar, layout: await page.locator('.appShell').evaluate((node) => ({ paddingBottom: getComputedStyle(node).paddingBottom, scrollY, maxScroll: document.documentElement.scrollHeight - innerHeight, focus: document.activeElement?.textContent })) }));
      await page.screenshot({ path: fileURLToPath(new URL(`qa-covered-focus-${width}.png`, out)) });
    }
    assert(footerButton.y + footerButton.height <= compareBar.y, width + ': fixed bar does not hide footer focus');
    // Also exercise focus on a visible control already covered by the overlay.
    const footerControl = page.getByRole('contentinfo').getByRole('button', { name: 'Till toppen' });
    await footerControl.evaluate((node) => {
      node.blur();
      const overlay = document.querySelector('.vehicleCompareBar').getBoundingClientRect();
      window.scrollBy({ top: node.getBoundingClientRect().y - overlay.y - 4, behavior: 'instant' });
      node.focus({ preventScroll: true });
    });
    await waitForRevealedFocus();
    const revealedButton = await footerControl.boundingBox();
    const overlay = await page.locator('.vehicleCompareBar').boundingBox();
    assert(revealedButton.y + revealedButton.height <= overlay.y, width + ': covered focus is revealed');
    report.responsive.push(width + 'px reflow and fixed compare bar');
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await go('/bilar');
  await page.getByRole('button', { name: 'Tabellvy', exact: true }).click();
  const table = page.getByRole('region', { name: 'Bilöversikt, rulla i sidled' });
  await table.focus();
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(() => document.querySelector('.vehicleTableScroll').scrollLeft > 0);
  report.keyboard.push('horizontal table scroll');
  dataUnavailable = true;
  for (const path of ['/bilar', '/bilar/tesla-model-3-long-range-rwd']) {
    await page.goto(base + path, { waitUntil: 'domcontentloaded' });
    await page.getByText('Biluppgifterna kunde inte hämtas.', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Försök igen', exact: true }).count(), 1);
    assert.equal(await page.getByText('Bilen hittades inte.', { exact: true }).count(), 0);
  }
  dataUnavailable = false;
  await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }), page.getByRole('button', { name: 'Försök igen', exact: true }).click()]);
  await page.locator('.vehicleDetailHero').waitFor();
  report.responsive.push('data outage distinguished from missing model, working retry');
  // Metadata must not promote unknown availability, seats or charging as facts.
  await page.route('**/rest/v1/public_ev_variants?**', (route) => route.fulfill({ json: [{ ...cars[0], seats: null, dc_charge_kw: null, tow_kg: 0, available_confirmed: false, price_sek: 600000 }] }));
  await page.route('**/data/public_ev_variants.json', (route) => route.fulfill({ json: { records: [{ ...cars[0], seats: null, dc_charge_kw: null, tow_kg: 0, available_confirmed: false, price_sek: 600000 }] } }));
  await go('/bilar');
  assert.match(await page.title(), /Alla elbilar/);
  await page.locator('.carCard').getByRole('link', { name: 'Visa detaljer' }).click();
  await page.locator('.vehicleDetailHero').waitFor();
  const metadata = await page.locator('script[data-jsonld="page"]').textContent().then(JSON.parse);
  assert.equal(metadata.offers.availability, undefined);
  assert.equal(metadata.vehicleSeatingCapacity, undefined);
  assert(!metadata.additionalProperty.some((item) => item.name === 'DC-laddning'));
  assert(metadata.additionalProperty.some((item) => item.name === 'Dragvikt' && item.value === '0 kg'));
  report.responsive.push('route titles and evidence-bound structured metadata');
  assert.deepEqual(errors, [], 'No browser runtime errors');
  assert.equal(await readFile(carFile, 'utf8'), originalCars, 'Public car export unchanged');
  assert.equal(await readFile(newsFile, 'utf8'), originalNews, 'Public news export unchanged');
  const assets = new URL('../dist/assets/', import.meta.url);
  for (const suffix of ['.js', '.css']) {
    const files = (await readdir(assets)).filter((name) => name.endsWith(suffix));
    const bytes = (await Promise.all(files.map(async (name) => gzipSync(await readFile(new URL(name, assets))).length))).reduce((sum, value) => sum + value, 0);
    report.bundles[suffix] = { gzipBytes: bytes };
    assert(bytes < (suffix === '.js' ? 130 : 30) * 1024, suffix + ': production gzip budget');
  }
  await writeFile(new URL('site-qa-report.json', out), JSON.stringify(report, null, 2));
  assert.deepEqual(report.violations, [], 'No automated accessibility violations; see local QA report');
  console.log(JSON.stringify({ site_qa_ok: true, auditedPages: report.pages.length, keyboard: report.keyboard, responsive: report.responsive, bundles: report.bundles }));
} finally { await browser.close(); }
