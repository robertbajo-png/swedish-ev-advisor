import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
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
  for (const [width, height] of [[320, 710], [390, 844], [768, 1024], [1440, 900], [1536, 864]]) {
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
    // First keyboard navigation must start in a fresh document, not after
    // scrolling the card images (which can change sequential focus origin).
    await page.evaluate(() => scrollTo(0, 0));
    const skip = page.locator('.skipLink');
    const skipState = () => skip.evaluate(el => ({ focused: el === document.activeElement, rect: el.getBoundingClientRect().toJSON() }));
    const initialSkip = await skipState();
    assert(!initialSkip.focused && initialSkip.rect.bottom <= 0);
    await page.keyboard.press('Tab');
    await page.waitForFunction(() => { const el = document.querySelector('.skipLink'), r = el.getBoundingClientRect();
      return el === document.activeElement && r.top >= 0 && r.bottom <= innerHeight; });
    const focusedSkip = await skipState();
    assert(focusedSkip.focused && focusedSkip.rect.top >= 0 && focusedSkip.rect.bottom <= height);
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => {
      const el = document.querySelector('.skipLink');
      return document.activeElement?.id === 'main-content' && document.activeElement !== el && el.getBoundingClientRect().bottom <= 0;
    });
    const activatedSkip = await skipState();
    assert(!activatedSkip.focused && activatedSkip.rect.bottom <= 0);
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.locator('.homeVehicleCard').first().waitFor();
    const featured = page.locator('.homeExploreStart');
    const note = featured.locator('#home-featured-image-notice');
    assert.equal(await note.innerText(), 'Pressbilder. Utrustning kan skilja mellan versioner.');
    assert.equal(await featured.locator('.vehicleImageNotice').count(), 0);
    const photos = featured.locator('.homeVehiclePhoto');
    assert.equal(await photos.count(), 3);
    assert.deepEqual(await photos.evaluateAll(nodes => nodes.map(node => node.getAttribute('aria-describedby'))), Array(3).fill('home-featured-image-notice'));
    assert.match(await featured.locator('.vehicleSpecNote').innerText(), /631 km/);
    const gridBounds = await featured.locator('.homeVehicleGrid').boundingBox();
    const noteBounds = await note.boundingBox();
    const headingBounds = await featured.locator('#explore-title').boundingBox();
    assert(gridBounds && noteBounds && headingBounds && Math.abs(headingBounds.x-noteBounds.x)<1
      && noteBounds.y>=headingBounds.y+headingBounds.height-1 && noteBounds.y+noteBounds.height < gridBounds.y,
      'Shared notice fits into the section heading, not floating below the cards');
    const creditLink = featured.getByRole('link', {name:'Bildkrediter',exact:true});
    assert.equal(await creditLink.getAttribute('href'), '/kallor?post=bilder');
    assert((await creditLink.boundingBox()).height >=44);
    assert.deepEqual(await photos.locator('img').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('src'))), [
      '/media/vehicles/bmw-i4-press-0f228bbc4a06.jpg',
      '/media/vehicles/cupra-born-press-7b71951e205b.jpg',
      '/media/vehicles/ford-explorer-press-96d1dbd59dc4.jpg'
    ]);
    assert.equal(await featured.locator(".vehiclePhotoLabel").count(), 0);
    assert.match(await featured.locator(".homeVehicleCard").filter({hasText:"Ford Explorer"}).locator(".homeVehicleSpecs").innerText(), /2200 kg/);
    const observed = [];
    for (const photo of await photos.all()) {
      const img = photo.locator('img');
      await img.evaluate(async el => { el.loading = 'eager'; await el.decode(); });
      const frame = await photo.boundingBox(), image = await img.boundingBox();
      const style = await img.evaluate(el => ({ fit: getComputedStyle(el).objectFit, transform: getComputedStyle(el).transform }));
      assert.equal(style.fit, 'contain');
      assert.equal(style.transform, 'none');
      assert(frame && image && image.x >= frame.x - 1 && image.x + image.width <= frame.x + frame.width + 1 &&
        image.y >= frame.y - 1 && image.y + image.height <= frame.y + frame.height + 1, 'Whole image visible');
      // Approximate visible-car centres marked on the three original image frames.
      // Keep this source-specific: do not centre by clipping an editorial asset.
      const centres = {
        'bmw-i4-press-0f228bbc4a06.jpg': [.56, .63],
        'cupra-born-press-7b71951e205b.jpg': [.505, .565],
        'ford-explorer-press-96d1dbd59dc4.jpg': [.50, .58],
      };
      const { name, nw, nh } = await img.evaluate(el => ({ name: new URL(el.currentSrc).pathname.split('/').pop(), nw: el.naturalWidth, nh: el.naturalHeight }));
      const centre = centres[name];
      assert(centre && nw && nh);
      const scale = Math.min(image.width / nw, image.height / nh);
      const x = (image.x + (image.width - nw * scale) / 2 + nw * scale * centre[0] - frame.x) / frame.width;
      const y = (image.y + (image.height - nh * scale) / 2 + nh * scale * centre[1] - frame.y) / frame.height;
      // Natural compositions differ; equal top line, no clipping, and small
      // mobile gaps matter more than an exact artificial subject midpoint.
      assert(Math.abs(x - .5) < .06 && y > .35 && y < .76, name + ' natural motif alignment');
      const visibleW = nw * scale, visibleH = nh * scale;
      const visibleY = image.y + (image.height - visibleH) / 2;
      const title = await photo.locator('..').locator('.vehicleCardTitle').boundingBox();
      assert(title && Math.abs(visibleY - frame.y - 8) < 1.5 && visibleW <= frame.width * .92 + 1, name + ' common visible photo frame');
      if (width <= 560) assert(title.y - (visibleY + visibleH) <= 38, name + ' compact mobile image-to-title gap');
      const card = photo.locator('..');
      const price = await card.locator('.homeVehiclePrice').boundingBox();
      const identity = await card.locator('.vehicleCardIdentity').boundingBox();
      const actions = await card.locator('.homeVehicleActions').boundingBox();
      assert(price && identity && actions && price.y - identity.y - identity.height <= 13);
      observed.push({ w: frame.width, h: frame.height, visibleH, y: visibleY, title: title.y, price: price.y, actions: actions.y });
    }
    assert(observed.every(v => Math.abs(v.w - observed[0].w) < 1));
    assert(observed.every(v => Math.abs(v.visibleH - observed[0].visibleH) < 1.5), 'Actual visible photo heights, not just img boxes, agree');
    if (width >= 768) assert(observed.every(v => Math.abs(v.h - observed[0].h) < 1));
    if (width >= 1440) for (const key of ['y','title','price','actions']) assert(observed.every(v => Math.abs(v[key] - observed[0][key]) < 1), 'Aligned desktop row: '+key);
    if (width === 768) assert(Math.abs(observed[1].y - observed[0].y) < 1);
    assert.deepEqual((await new AxeBuilder({page}).include('.homeExploreStart').analyze()).violations.map(v => v.id), []);
    const sourceNotes = await featured.locator('.vehicleSpecNote').evaluateAll(nodes=>nodes.map(el=>({text:el.innerText, visible:el.getBoundingClientRect().height>0, size:parseFloat(getComputedStyle(el).fontSize)})));
    assert(sourceNotes.some(note=>note.visible && note.size>=12 && note.text.includes('631 km')));
    await creditLink.focus();
    await page.keyboard.press('Enter');
    await page.waitForURL('**/kallor?post=bilder');
    await page.waitForFunction(()=>document.activeElement?.id==='bilder');
    const credits = page.getByRole('region',{name:'Bildkrediter',exact:true});
    const firstThree = await credits.locator('.bilSourcesList > li').evaluateAll(nodes=>nodes.slice(0,3).map(el=>el.innerText));
    assert(firstThree[0].includes('Nye BMW i4 eDrive40.jpg') && firstThree[1].includes('Cupra Born') && firstThree[2].includes('2023_FORD_NewElectricExplorer_6'));
    await page.screenshot({path:fileURLToPath(new URL('home-credits-'+width+'.png',out))});
    for (const [title,author,link] of [
      ['Nye BMW i4 eDrive40.jpg','Fabian Kirchbauer','https://www.mynewsdesk.com/no/bmw-no/images/nye-bmw-i4-edrive40-dot-jpg-3037471'],
      ['2023_FORD_NewElectricExplorer_6','Ford Sverige / Hedin HMC Motor Company AB','https://www.mynewsdesk.com/se/ford/images/2023-ford-newelectricexplorer-6-2732259']
    ]) {
      const entry=credits.getByRole('listitem').filter({has:page.getByRole('heading',{name:title,exact:true})});
      assert.equal(await entry.count(),1);
      assert((await entry.innerText()).includes(author));
      assert((await entry.innerText()).includes('startsidans bilurval'));
      assert.equal(await entry.getByRole('link',{name:'Bildkälla',exact:true}).getAttribute('href'),link);
      assert.equal(await entry.getByRole('link',{name:'Manufacturer-media-use',exact:true}).getAttribute('href'),link);
    }
    await page.goto(base, {waitUntil:'domcontentloaded'});
    await page.locator('.homeVehicleCard').first().waitFor();
    await page.evaluate(()=>scrollTo(0,0));

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
    // The result panel opens before the async mock transport necessarily runs.
    // Wait for the actual intercepted response, then still require exactly one request.
    await Promise.all([
      page.waitForResponse(response => new URL(response.url()).pathname === '/api/advisor' && response.status() === 503),
      submit.click(),
    ]);
    await page.locator('#dina-forslag').waitFor();
    assert.equal(requests, 1);
    await page.getByRole('navigation', { name: 'Huvudnavigation' }).getByRole('link', { name: 'Rådgivare' }).click();
    await page.waitForURL('**/radgivare');
    assert.equal(await page.locator('#din-korvecka').count(), 0);
    assert.equal(await page.locator('#home-featured-image-notice').count(), 0);
    assert(await page.locator('.homeExplore .vehicleImageNotice').count() > 0, 'Advisor route still has individual notices');
    await toggle.click();
    assert.match(await input.inputValue(), /räckvidd.*pengarna/);
    assert.equal(requests, 1);
    assert.deepEqual(errors, []);
    await context.close();
    console.log(width + 'px: adviser visible, keyboard and axe clean, driving week and edit round trip, adviser shortcut, no real AI calls');
  }
  const exactContext = await browser.newContext({viewport:{width:1440,height:900}});
  const exactPage = await exactContext.newPage();
  await exactContext.route('**/api/**',route=>route.abort());
  await exactPage.goto(base+'/bilar',{waitUntil:'domcontentloaded'});
  await exactPage.locator('.vehicleCatalog .carGrid > .vehicleCard').first().waitFor();
  for (const [title,asset] of [['BMW i4','bmw-i4-press-497a46b16ded.jpg'],['Ford Explorer','ford-explorer-press-050047452e4e.jpg']]) {
    const card=exactPage.locator('.vehicleCatalog .carGrid > .vehicleCard').filter({has:exactPage.locator('.vehicleCardTitle').filter({hasText:title})});
    assert.equal(await card.count(),1);
    assert((await card.locator('img').getAttribute('src')).endsWith(asset));
    await exactPage.goto(base+await card.locator('.homeVehiclePhoto').getAttribute('href'),{waitUntil:'domcontentloaded'});
    assert((await exactPage.locator('.vehicleHeroMedia img').getAttribute('src')).endsWith(asset));
    await exactPage.goto(base+'/bilar',{waitUntil:'domcontentloaded'});
    await exactPage.locator('.vehicleCatalog .carGrid > .vehicleCard').first().waitFor();
  }
  await exactPage.goto(base+'/radgivare',{waitUntil:'domcontentloaded'});
  await exactPage.locator('.homeExplore .homeVehicleCard').first().waitFor();
  assert.equal(await exactPage.locator('img[src*="0f228bbc4a06"],img[src*="96d1dbd59dc4"]').count(),0);
  await exactContext.close();
  // A different, individually qualified photo must not be swept into the shared note.
  const data = JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json', import.meta.url), 'utf8'));
  const rows = ['bmw-i4-press-497a46b16ded.jpg', 'cupra-born-press-7b71951e205b.jpg', 'hyundai-ioniq-9-press-4556561b89d9.jpg'].map(asset =>
    data.records.find(row => row.image_url?.endsWith(asset)));
  assert(rows.every(Boolean));
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  await isolatePublicDataFixture(page);
  await page.route('**/data/public_ev_variants.json', route => route.fulfill({ json: { ...data, records: rows } }));
  await page.goto(base);
  const featured = page.locator('.homeExploreStart');
  await featured.locator('.homeVehicleCard').first().waitFor();
  assert.equal(await featured.locator('#home-featured-image-notice').count(), 0);
  assert.equal(await featured.locator('.homeVehiclePhoto[aria-describedby]').count(), 0);
  assert.equal(await featured.locator('.vehicleImageNotice').count(), 3);
  assert.match(await featured.innerText(), /Pressbild av IONIQ 9. Utrustningen kan skilja mellan versioner/);
  await ctx.close();
  console.log('mixed image rights and model-specific notices stay on each card');
} finally {
  await browser.close();
}
