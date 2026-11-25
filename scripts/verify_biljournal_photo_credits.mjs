import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { launchQaBrowser } from './qa_browser.mjs';
import { vehicleSlug } from '../src/vehicle-names.js';
import { coverPhoto, photoCredit } from '../src/biljournal-images.js';

const [server, offlineFile] = process.argv.slice(2);
assert(server && offlineFile, 'Usage: node scripts/verify_biljournal_photo_credits.mjs LOCAL_URL OFFLINE_HTML');
assert.equal(new URL(server).hostname, '127.0.0.1');
const localOrigin = new URL(server).origin;
const offline = pathToFileURL(resolve(offlineFile)).href;
const cover = photoCredit(coverPhoto);
const rightsText = /Bildkälla|Bildvillkor|M 93|Alexander-93|Wikimedia Commons|CC[- ]BY|creativecommons\.org/i;

async function checkEntry(page, mobile) {
  const footerLink = page.getByRole('contentinfo').getByRole('link', {name:'Källor och bildkrediter', exact:true});
  assert.equal(await page.getByRole('link', {name:'Källor och bildkrediter', exact:true}).count(), 1);
  assert.doesNotMatch(await page.locator('body').innerText(), rightsText);
  await (mobile ? footerLink.tap() : footerLink.click());
  const nav = page.getByRole('navigation', {name:'På källsidan'});
  await nav.getByRole('link', {name:'Bildkrediter', exact:true}).focus();
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.activeElement.id === 'bilder');
  const photos = page.getByRole('region', {name:'Bildkrediter', exact:true});
  const hero = photos.getByRole('listitem').filter({has:page.getByRole('heading',{name:cover.title, exact:true})});
  assert.equal(await hero.count(),1);
  assert.match(await hero.innerText(), /© M 93 \/ Wikimedia Commons.*CC-BY-SA-3.0-DE/s);
  assert.equal(await hero.getByRole('link',{name:'Bildkälla'}).getAttribute('href'),cover.source_url);
  assert.equal(await hero.getByRole('link',{name:'CC-BY-SA-3.0-DE'}).getAttribute('href'),cover.license_url);
  assert.match(await hero.innerText(), /Startsidan.*helbild/s);
}
const browser = await launchQaBrowser();
try {
  for (const file of [false,true]) {
    for (const width of [390,1440]) {
      const mobile = width === 390;
      const url = path => file ? offline + '#' + path : localOrigin + path;
      const page = await browser.newPage({viewport:{width,height:844},isMobile:mobile,hasTouch:mobile,offline:file,reducedMotion:'reduce'});
      const outside = [];
      page.on('request', req => {
        if (/^https?:/.test(req.url()) && (file || new URL(req.url()).origin !== localOrigin)) outside.push(req.url());
      });
      if (!file) await page.route('**/*',r => new URL(r.request().url()).origin === localOrigin ? r.continue() : r.abort());
      await page.goto(url('/'));
      await page.getByRole('heading',{level:1,name:'Din körvecka'}).waitFor();
      await page.locator('.bilCover img').evaluate(image => image.decode());
      assert.equal(await page.locator('.bilCover figcaption').innerText(),'Hyundai Inster Prime');
      const { records, articles } = JSON.parse(await page.locator('#public-page-data').textContent());
      const car = records.find(row => row.brand === 'Hyundai' && row.model === 'Inster');
      assert.ok(car);
      const id = vehicleSlug(car.brand,car.model,car.variant_name);
      await checkEntry(page,mobile);
      await page.goto(url('/bilar/'+id));
      await page.locator('.vehicleDetailHero h1').waitFor();
      await page.locator('.vehicleHeroMedia img').evaluate(image=>image.decode());
      assert.match(await page.locator('.vehicleDetailHero + .vehicleContainer .vehicleImageNotice, .vehicleContainer > .vehicleImageNotice').first().innerText(), /Hyundai Inster Prime.*Utrustningen kan skilja/s);
      await checkEntry(page,mobile);
      await page.goto(url('/jamfor'));
      await page.locator('#comparison-add-car').selectOption(id);
      assert.match(await page.locator('.comparisonVehicle .vehicleImageNotice').innerText(),/Utrustningen kan skilja/);
      await checkEntry(page,mobile);
      const lead = articles.find(article => article.title.includes('Renault 5 bakom'));
      assert(lead);
      await page.goto(url('/nyheter'));
      await page.getByRole('heading',{name:lead.title,exact:true}).waitFor();
      assert.match(await page.locator('.newsStory--lead figcaption').innerText(),/Arkivbild.*Genève 2024/s);
      await checkEntry(page,mobile);
      await page.goto(url('/nyheter/'+lead.slug));
      await page.getByRole('heading',{level:1,name:lead.title,exact:true}).waitFor();
      assert.match(await page.locator('.journalArticle > .journalImage figcaption').innerText(),/Arkivbild.*Genève 2024/s);
      await checkEntry(page,mobile);
      assert.deepEqual(outside,[]);
      console.log((file?'Offline':'Lokal produkt')+' '+width+' px: start, modell, jämförelse, nyhetslista och artikel passerade');
      await page.close();
    }
  }
} finally { await browser.close(); }
