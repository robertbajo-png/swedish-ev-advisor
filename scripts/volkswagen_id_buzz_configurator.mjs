import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { launchQaBrowser } from './qa_browser.mjs';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const ORIGIN = 'https://www.volkswagen-transportbilar.se';
const PATH = '/sv/bygg-din-bil.html/__app/72006/edition/';
const sha256 = value => createHash('sha256').update(value, 'utf8').digest('hex');
const collapse = text => text.normalize('NFKC').replace(/[\u2060\u200b]/g, ' ').replace(/\s+/g, ' ').trim();
const profiles = [
  ['pro', 'Pro', 'EBBR7R', 210, 286],
  ['pro-4motion', 'Pro 4MOTION', 'EBBR5R', 250, 340],
].map(([slug, trim, motorId, kw, ps]) => ({ slug, trim, motorId, kw, ps,
  url: ORIGIN + PATH + slug + '.app', label: `ID. Buzz ${trim} 5-Seats Sweden Olympic Edition`,
  trimName: `ID. Buzz ${trim} Sweden Olympic Edition`,
}));
const boundedReceipt = receipt => /^[a-f0-9]{64}$/.test(receipt?.html_sha256 ?? '');

export function readConfiguration(slug, finalUrl, renderedText) {
  const profile = profiles.find(row => row.slug === slug);
  if (!profile) throw new Error('unregistered_trim');
  const parsed = new URL(finalUrl);
  const expected = new URL(profile.url);
  if (parsed.origin !== expected.origin || parsed.pathname !== expected.pathname || parsed.username || parsed.password || parsed.hash) {
    throw new Error('unexpected_configurator_route');
  }
  const exact = (key, value) => parsed.searchParams.getAll(key).length === 1 && parsed.searchParams.get(key) === value;
  const engines = parsed.searchParams.getAll('modelId-app');
  if (!exact('carlineId-app', '72006') || !exact('modelYear-app', '2027') || !exact('category-app', 'commercial')
    || !exact('buildabilityStatus-app', 'buildable') || !exact('salesGroupId-app', '74347')
    || !exact('modelVersion-app', '2') || !exact('trimName-app', profile.trimName) || engines.length !== 1
    || !new RegExp(`^${profile.motorId}(?:\\$[A-Z0-9]+)+$`).test(engines[0])) {
    throw new Error('unexpected_configurator_identity');
  }
  const header = profile.label.replace('.', '\\.');
  const pattern = new RegExp(`\\b${header} Hjulbas: 2989 mm Kort Motor: ${profile.kw} kW \\(${profile.ps} PS\\) `
    + 'V\\u00e4xell\\u00e5da: 1 vxl automat \\| El \\| WLTP:\\s*F\\u00f6rbrukning: (\\d{2},\\d{2})\\s*kWh/100 km\\b', 'g');
  const matches = [...collapse(renderedText).matchAll(pattern)];
  if (matches.length !== 1) throw new Error('exact_wltp_configuration_required');
  const value = Number(matches[0][1].replace(',', '.'));
  if (value < 12 || value > 40) throw new Error('consumption_out_of_bounds');
  return { trim: profile.trim, model_year: 2027, seats: 5, wheelbase_mm: 2989, motor_id: profile.motorId,
    configuration_id: engines[0], final_url: parsed.href, observations: {
      configured_wltp_consumption_kwh_100km: { value, quote: matches[0][0] },
    }, rendered_text_sha256: sha256(renderedText), status: 'needs_review' };
}

export function readSummary(slug, selection, proof) {
  const summary = readConfiguration(slug, proof.url, proof.text);
  const before = new URL(selection.final_url);
  const after = new URL(summary.final_url);
  if (summary.configuration_id !== selection.configuration_id || ['exteriorId-app', 'interiorId-app'].some(key => {
    const values = before.searchParams.getAll(key);
    const current = after.searchParams.getAll(key);
    return values.length !== 1 || !values[0].trim() || current.length !== 1 || current[0] !== values[0];
  })) throw new Error('summary_configuration_changed');

  const readRow = (row, label, valuePattern) => {
    if (!Array.isArray(row) || row.length !== 2 || collapse(row[0]) !== label) throw new Error('unexpected_summary_row');
    const value = collapse(row[1]).match(valuePattern)?.[1];
    if (!value) throw new Error('unexpected_summary_value');
    return { value: Number(value.replaceAll(' ', '').replace(',', '.')), quote: `${collapse(row[0])}: ${collapse(row[1])}` };
  };
  const consumption = readRow(proof.wltp.consumption, 'Br\u00e4nslef\u00f6rbrukning blandad k\u00f6rning', /^(\d{2},\d{2}) kWh\/100 km(?: \d+)?$/);
  const range = readRow(proof.wltp.range, 'R\u00e4ckvidd vid blandad k\u00f6rning', /^(\d{3}) km$/);
  if (range.value < 100 || range.value > 900 || consumption.value !== selection.observations.configured_wltp_consumption_kwh_100km.value
    || consumption.value !== summary.observations.configured_wltp_consumption_kwh_100km.value) throw new Error('summary_wltp_conflict');

  const pricePattern = /^([1-9]\d{0,2} \d{3}) kr(?: \d+)?$/;
  const cash = readRow(proof.price.total, 'inkl. moms', pricePattern);
  const base = readRow(proof.price.base, 'Grundpris', pricePattern);
  const beforeVat = readRow(proof.price.before_vat, 'exkl. moms', pricePattern);
  if (proof.price.options?.length !== 2 || collapse(proof.price.options[0]) !== 'Tillval'
    || collapse(proof.price.options[1]) !== 'Inga tillkommande kostnader'
    || cash.value !== base.value || cash.value * 4 !== beforeVat.value * 5 || cash.value < 100000) {
    throw new Error('summary_cash_price_conflict');
  }
  const towing = readRow(proof.towing, 'Max till\u00e5ten dragvikt bromsad vid 12%', /^([1-9] \d{3}) kg$/);
  if (towing.value > 4000) throw new Error('summary_towing_conflict');
  return { final_url: summary.final_url, observations: {
    configured_wltp_consumption_kwh_100km: consumption,
    configured_wltp_range_km: range,
    configured_cash_price_sek_including_vat: cash,
    configured_braked_towing_kg: towing,
  } };
}

export function replayConfiguration(slug, receipt, text, summaryJson, now = new Date()) {
  const profile = profiles.find(row => row.slug === slug);
  assert(profile && receipt.source_url === profile.url && boundedReceipt(receipt.html_access_receipt), 'Exact public access receipt required');
  const captured = Date.parse(receipt.captured_at);
  const access = Date.parse(receipt.html_access_receipt.checked_at);
  assert(Number.isFinite(captured) && Number.isFinite(access) && captured >= access && captured - access <= 300000
    && captured <= now.getTime() + 60000 && now.getTime() - captured <= 86400000, 'Fresh read-only configuration capture required');
  assert.equal(sha256(text), receipt.rendered_text_sha256, 'Rendered engine hash changed');
  const selection = readConfiguration(slug, receipt.final_url, text);
  for (const [key, value] of Object.entries(selection)) assert.deepEqual(receipt[key], value, `Configuration receipt mismatch: ${key}`);
  assert.equal(sha256(summaryJson), receipt.summary?.evidence_sha256, 'Summary evidence hash changed');
  const summary = readSummary(slug, selection, JSON.parse(summaryJson));
  const { evidence_sha256, summary_file, ...saved } = receipt.summary;
  assert.deepEqual(summary, saved, 'Summary facts do not match the raw evidence');
  return { ...selection, source_url: profile.url, captured_at: receipt.captured_at, summary: { ...summary, evidence_sha256 } };
}

async function evidenceRoot() {
  const directory = await realpath(join(ROOT, 'data/local/release-data'));
  if (!directory.toLowerCase().startsWith((await realpath(ROOT)).toLowerCase() + (process.platform === 'win32' ? '\\' : '/'))
    || /[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(directory)) throw new Error('unexpected_evidence_directory');
  return directory;
}

export async function replayCapture(path) {
  const directory = await realpath(path);
  assert.equal(dirname(directory), await evidenceRoot(), 'Use a local configurator capture directory');
  assert.match(basename(directory), /^volkswagen-id-buzz-configurator-[a-z0-9]+$/i);
  const read = async name => {
    const target = join(directory, name);
    assert.equal(await realpath(target), target, 'Capture evidence must be a regular local file');
    return readFile(target, 'utf8');
  };
  const receipt = JSON.parse(await read('observations.json'));
  assert.equal(receipt.publication_approved, false);
  assert.equal(receipt.rows?.length, profiles.length);
  return Promise.all(profiles.map(async profile => {
    const matches = receipt.rows.filter(row => row.source_url === profile.url);
    assert.equal(matches.length, 1, 'Exact unique receipt required per registered version');
    return replayConfiguration(profile.slug, matches[0], await read(`${profile.slug}.txt`), await read(`${profile.slug}-summary.json`));
  }));
}

async function summaryProof(page) {
  await page.getByRole('button', { name: 'Sammanfattning', exact: true }).click({ timeout: 20000 });
  const choices = page.locator('#summary-tab-content-0');
  await choices.waitFor({ timeout: 15000 });
  const showVat = page.getByRole('button', { name: 'Visa inkl. moms', exact: true }).first();
  if (await showVat.isVisible()) {
    await showVat.click({ timeout: 6000 });
    const confirmation = page.getByRole('button', { name: 'OK', exact: true });
    await confirmation.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
    if (await confirmation.isVisible()) await confirmation.click({ timeout: 5000 });
  }
  await page.getByRole('tab', { name: 'Tekniska data', exact: true }).click({ timeout: 8000 });
  const tech = page.locator('#summary-tab-content-2');
  const wltp = tech.locator('[id="0_body"]');
  const weights = tech.locator('[id="3_body"]');
  const row = async (scope, label) => {
    const match = scope.getByRole('row').filter({ has: page.getByText(label, { exact: true }) });
    await match.waitFor({ timeout: 6000 }).catch(() => { throw new Error(`summary_row_unavailable: ${label}`); });
    const cells = await match.locator(':scope > :is(td, th, [role="cell"], [role="rowheader"]):visible').all();
    if (cells.length !== 2) throw new Error(`unexpected_summary_columns: ${label} (${cells.length})`);
    return [await cells[0].innerText(), await cells[1].innerText()];
  };
  const name = 'Max till\u00e5ten dragvikt bromsad vid 12%';
  const proof = { wltp: {
    consumption: await row(wltp, 'Br\u00e4nslef\u00f6rbrukning blandad k\u00f6rning'),
    range: await row(wltp, 'R\u00e4ckvidd vid blandad k\u00f6rning'),
  }, price: {
    base: await row(page, 'Grundpris'), options: await row(page, 'Tillval'),
    total: await row(page, 'inkl. moms'), before_vat: await row(page, 'exkl. moms'),
  } };
  await tech.getByRole('button', { name: 'Vikter', exact: true }).click({ timeout: 6000 });
  proof.towing = await row(weights, name);
  return { ...proof, url: page.url(), text: await page.locator('body').innerText({ timeout: 5000 }) };
}

async function collect(browser, profile) {
  const page = await browser.newPage({ locale: 'sv-SE' });
  try {
    const response = await page.goto(profile.url, { waitUntil: 'domcontentloaded', timeout: 25000 });
    if (response?.status() !== 200 || response.url() !== profile.url
      || (await response.headerValue('tdm-reservation')) === '1'
      || await page.locator('meta[name="tdm-reservation"][content="1" i]').count()) {
      throw new Error('configurator_access_held');
    }
    const deny = page.getByRole('button', { name: 'Enbart nödvändiga', exact: true });
    await deny.waitFor({ timeout: 6000 }).catch(() => {});
    if (await deny.isVisible()) await deny.click({ timeout: 5000 });
    await page.getByRole('button', { name: 'Drivlina', exact: true }).click({ timeout: 20000 });
    await page.getByText(profile.label, { exact: false }).first().waitFor({ timeout: 15000 });
    const text = await page.locator('body').innerText({ timeout: 5000 });
    const observation = readConfiguration(profile.slug, page.url(), text);
    const proof = await summaryProof(page);
    return { text, observation, proof, summary: readSummary(profile.slug, observation, proof) };
  } finally {
    await page.close();
  }
}

async function main() {
  const publicAccess = JSON.parse(execFileSync(process.execPath,
    ['scripts/run_python.mjs', 'scripts/volkswagen_id_buzz_preflight.py', '--check-configurator-access'],
    { cwd: ROOT, encoding: 'utf8', timeout: 45000 }));
  if (!profiles.every(profile => boundedReceipt(publicAccess[profile.url]))) throw new Error('missing_current_access_receipt');
  const output = await mkdtemp(join(await evidenceRoot(), 'volkswagen-id-buzz-configurator-'));
  const rows = [];
  const browser = await launchQaBrowser();
  try {
    for (const profile of profiles) {
      try {
        const { text, observation, proof, summary } = await collect(browser, profile);
        const text_file = `${profile.slug}.txt`;
        const summary_file = `${profile.slug}-summary.json`;
        const evidence = JSON.stringify(proof, null, 2) + '\n';
        await writeFile(join(output, text_file), text, 'utf8');
        await writeFile(join(output, summary_file), evidence, 'utf8');
        rows.push({ ...observation, source_url: profile.url, captured_at: new Date().toISOString(),
          html_access_receipt: publicAccess[profile.url], text_file,
          summary: { ...summary, evidence_sha256: sha256(evidence), summary_file } });
      } catch (error) {
        rows.push({ source_url: profile.url, status: 'held', reason: String(error.message).split('\n')[0] });
      }
    }
  } finally {
    await browser.close();
  }
  await writeFile(join(output, 'observations.json'), JSON.stringify({ publication_approved: false, rows }, null, 2) + '\n');
  console.log(JSON.stringify({ output, captured: rows.filter(row => row.status === 'needs_review').length,
    held: rows.filter(row => row.status === 'held').map(row => ({ source_url: row.source_url, reason: row.reason })) }));
  if (rows.some(row => row.status === 'held')) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2);
  if (args.length === 0) await main();
  else if (args.length === 2 && args[0] === '--replay') console.log(JSON.stringify(await replayCapture(args[1])));
  else throw new Error('Usage: node scripts/volkswagen_id_buzz_configurator.mjs [--replay CAPTURE_DIR]');
}
