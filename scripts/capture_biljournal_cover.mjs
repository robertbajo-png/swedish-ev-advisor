import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { crc32 } from 'node:zlib';
import { launchQaBrowser } from './qa_browser.mjs';
import { coverPhoto, photoCredit } from '../src/biljournal-images.js';

function creditedPng(png, credit) {
  const type = Buffer.from('iTXt');
  // Uncompressed UTF-8, with empty language and translated keyword.
  const data = Buffer.from('Image credit\0\0\0\0\0' + credit, 'utf8');
  const header = Buffer.alloc(4);
  header.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([type, data])));
  assert.equal(png.subarray(12, 16).toString(), 'IHDR');
  const endOfHeader = 20 + png.readUInt32BE(8);
  return Buffer.concat([png.subarray(0, endOfHeader), header, type, data, checksum, png.subarray(endOfHeader)]);
}

const [htmlPath, outputFolder] = process.argv.slice(2);
assert(htmlPath && outputFolder, 'Usage: node scripts/capture_biljournal_cover.mjs OFFLINE_HTML OUTPUT_DIR');
const file = pathToFileURL(resolve(htmlPath)).href;
const cover = photoCredit(coverPhoto);
const credits = [cover.title, cover.credit, cover.source_url, cover.license_id, cover.license_url,
  'Skärmbild av Elbilsagenten. Fotot återges nedskalat i helbild.'].join('\n');
const browser = await launchQaBrowser();
try {
  for (const [width, height] of [[390, 844], [1440, 800]]) {
    const mobile = width === 390;
    const page = await browser.newPage({ viewport: { width, height }, isMobile: mobile, hasTouch: mobile, offline: true, reducedMotion: 'reduce' });
    await page.goto(file);
    await page.getByRole('heading', { level: 1, name: /^(Få hjälp att välja elbil|Hitta din nästa elbil\.)$/ }).waitFor();
    await page.evaluate(() => document.fonts.ready);
    const image = page.locator('.bilCoverPhoto img');
    const hasCover = await image.count() > 0;
    if (hasCover) await image.evaluate(img => img.decode());
    assert.doesNotMatch(await page.locator('body').innerText(), /M 93|Wikimedia Commons|CC[- ]BY|creativecommons\.org/i);
    const png = await page.screenshot();
    await writeFile(resolve(outputFolder, 'Biljournalen-start-' + width + '.png'), hasCover ? creditedPng(png, credits) : png);
    await page.close();
  }
} finally {
  await browser.close();
}
