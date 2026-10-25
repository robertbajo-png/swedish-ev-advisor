import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { launchQaBrowser } from './qa_browser.mjs';

const calls = [];
const launch = async options => { calls.push(options); return 'fixture-browser'; };
for (const channel of ['chrome', 'msedge']) {
  assert.equal(await launchQaBrowser({ env: { PLAYWRIGHT_CHANNEL: channel }, launch }), 'fixture-browser');
  assert.deepEqual(calls.pop(), { headless: true, channel });
}
await assert.rejects(launchQaBrowser({ env: { PLAYWRIGHT_CHANNEL: 'unknown' }, launch }));
assert.equal(calls.length, 0);
const failure = new Error('fixture browser unavailable');
await assert.rejects(launchQaBrowser({ env: { PLAYWRIGHT_CHANNEL: 'chrome' }, launch: async () => { throw failure; } }), failure);
await assert.rejects(launchQaBrowser({ env: {}, platform: 'linux', launch: async () => { throw failure; } }), failure);
await launchQaBrowser({ env: {}, platform: 'win32', launch: async options => {
  if (!options.channel) throw failure;
  assert.equal(options.channel, 'msedge');
} });
for (const name of ['site_qa', 'ui_proportions', 'home_ui', 'vehicle_ui', 'journal_ui', 'news_ui']) {
  const source = await readFile(new URL(`./verify_${name}.mjs`, import.meta.url), 'utf8');
  assert(source.includes('await launchQaBrowser()'));
}
const workflow = await readFile(new URL('../.github/workflows/ci.yml', import.meta.url), 'utf8');
assert(workflow.includes('google-chrome --version') && workflow.includes('PLAYWRIGHT_CHANNEL=chrome'));
assert(workflow.includes('bunx playwright install --with-deps chromium'));
for (const command of ['site-qa', 'ui-proportions', 'home-ui', 'vehicle-ui', 'journal-ui', 'news-ui']) assert(workflow.includes(`bun run verify:${command}`));
console.log(JSON.stringify({ qa_browser_contract_ok: true, browser_failures_not_hidden: true, all_six_ui_suites_required: true }));
