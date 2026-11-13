import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { launchQaBrowser } from './qa_browser.mjs';

// Called only after the collector's robots, HTTP and TDM preflight succeeds.
const url = 'https://www.toyota.se/bilar/bz4x/specifications';
assert(process.argv.length === 3, 'One private output path required');
const browser = await launchQaBrowser();
try {
  const page = await browser.newPage();
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  assert.equal(response.status(), 200);
  assert.equal(page.url(), url);
  assert.notEqual(response.headers()['tdm-reservation'], '1');
  await page.waitForFunction(() => [...document.querySelectorAll('div[id$="-data"]')]
    .some(node => node.textContent.includes('carConfigMotorization')), null, { timeout: 20000 });
  assert.equal(await page.locator('meta[name="tdm-reservation"][content="1"]').count(), 0);
  await writeFile(resolve(process.argv[2]), await page.content());
} finally { await browser.close(); }
