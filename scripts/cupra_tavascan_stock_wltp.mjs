import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { launchQaBrowser } from './qa_browser.mjs';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const stockPage = 'https://www.cupraofficial.se/kopa/bilar-i-lager';
const api = 'https://vtpapi.seat.com/restapi/v1/cusenwb/datastore/cars/';
const importer = 'https://bilarilager.vwgroup.se/cupra/';
const rangeLabel = 'Elektrisk r\u00e4ckvidd, blandad k\u00f6rning';
const encode = body => JSON.stringify(body, null, 2) + '\n';
const hash = body => createHash('sha256').update(body).digest('hex');
export const samples = Object.entries({ MJB63M: 'SWE400602222026867556', UON91J: 'SWE406952222026867566' })
  .map(([plate, id]) => {
    const token = `${Buffer.from(id).toString('base64')}=`;
    return { plate, id, token, page: `${stockPage}/w/offer/new/${token}`, api: api + token, importer: importer + plate };
  });

function row(rows, key) {
  const matches = rows?.filter(item => item.key === key);
  assert.equal(matches?.length, 1, `Expected one ${key} row`);
  return matches[0];
}

export function inspectDriveStock(sample, raw, identityProof, displayedRange) {
  const registered = samples.find(s => s.plate === sample.plate);
  assert.deepEqual(sample, registered, 'Unregistered stock sample');
  assert(raw.length > 0 && raw.length <= 512_000, 'Invalid stock payload size');
  const identity = identityProof.identity;
  assert.deepEqual([identity.edition, identity.model_year, identity.model_code.value, identity.stock_reference,
    identity.model_code.source_url], ['Drive', 2026, 'KR1BCD', sample.plate, sample.importer], 'Wrong importer identity');
  assert.match(identity.model_code.source_hash, /^[0-9a-f]{64}$/);
  assert.deepEqual(identityProof.equipment_codes, ['P80', 'PF0', 'YC1']);
  assert.match(identityProof.order, /^\d{13}$/);
  assert(sample.id.endsWith(identityProof.order), 'Factory order does not match the public offer');
  const body = JSON.parse(raw);
  const item = key => row(body.items, key).value;
  assert.deepEqual([body.key, body.carid, item('numberplate'), item('knr')],
    [sample.token, sample.id, sample.plate, identityProof.order], 'Offer does not match the importer unit');
  assert.deepEqual([item('manuf'), item('model'), item('modelyear'), item('smod'), item('preuse'), item('drive'),
    row(body.items, 'cartitle').mbv?.code], ['CUPRA', 'Tavascan', '2026', 'Endurance', 'Nybil', 'Bakhjulsdrift', 'KR1BCD'],
  'Not the exact Swedish MY26 Drive powertrain');
  const motor = row(body.items, 'motor').values;
  assert.deepEqual([row(motor, 'fuel').value, row(motor, 'power.kw').value, row(motor, 'power.kw').unit], ['El', '210', 'kW']);
  const wheels = row(body.serie_equip, 'serieequip.wheels').values.map(entry => entry.value);
  const tireQuote = 'D\u00e4ck 235/55 R19 fram och 255/50 R19 bak(polymerskikt)';
  assert(wheels.includes('L\u00e4ttmetallf\u00e4lgar 8J x 19') && wheels.includes(tireQuote), 'Expected standard 19-inch wheel set');
  const tireSizes = body.tyreLabels.flatMap(t => (t.labels ?? []).map(x => x.sizeDesignation_tyreSizeDesignation));
  assert(tireSizes.length >= 2 && tireSizes.every(s => typeof s === 'string' && /^\s*(?:235\s*\/\s*55|255\s*\/\s*50)\s*R\s*19\s*$/i.test(s)),
    'Tyre labels conflict with the 19-inch edition');
  assert(row(body.serie_equip, 'serieequip.engine').values.some(x => x.value === 'H\u00f6gvoltsbatteri 77 kWh (netto)'),
    'Net battery identity changed');
  const wltp = row(body.hypermediatechdata, 'WLTP').techDataType;
  assert.equal(wltp.key, 'WLTP');
  const sourceHash = hash(raw);
  function combined(group, dataKey, unit, label, min, max) {
    const section = row(wltp.groups, group).techDataGroup;
    assert.equal(section.key, group);
    const technical = row(section.data, dataKey).techData;
    assert.equal(technical.key, dataKey);
    const electric = row(technical.values, 'PURE_ELECTRICAL');
    assert.deepEqual([row(electric.items, 'energy_management').value, row(electric.items, 'fuel').value], ['PURE', 'ELECTRICAL']);
    const result = row(electric.values, 'COMBINED');
    assert(result.unit === unit && /^\d{1,4},\d$/.test(result.value), `Invalid combined WLTP ${group}`);
    const value = Number(result.value.replace(',', '.'));
    assert(value >= min && value <= max, `Out of bounds combined WLTP ${group}`);
    return { value, source_url: sample.page, source_hash: sourceHash, source_quote: `${label}: ${result.value} ${unit}` };
  }
  const range = combined('range', 'range', 'km', rangeLabel, 50, 1200);
  assert(Number.isInteger(range.value) && displayedRange === `${range.value},0 km`, 'Rendered combined range disagrees');
  const consumption = combined('consumption', 'fuel', 'kWh/100km', 'Kombinerad elforbrukning (WLTP)', 5, 60);
  return { plate: sample.plate, model_year: 2026, model_code: 'KR1BCD', market: 'SE', standard_wheels_inches: 19,
    wheel_quote: tireQuote, range, consumption, importer_identity: identityProof };
}

export function completeDriveProfile(base, observations) {
  const fields = base.technical_fields;
  assert.deepEqual([base.edition, base.market, base.model_year, base.model_code, base.standard_wheel_inches.value,
    base.publication_approved, base.price.value, base.separate_dealer_price_proof.value],
  ['Drive Swedish Edition', 'SE', 2026, 'KR1BCD', 19, false, 554900, 554900], 'Wrong starting profile');
  assert.deepEqual(base.held, ['wltp_range_km']);
  assert.deepEqual(Object.keys(fields).sort(), ['ac_charge_kw', 'battery_kwh', 'boot_liters', 'dc_charge_kw', 'drivetrain',
    'seats', 'tow_kg', 'wltp_consumption_kwh_100km']);
  assert.deepEqual(observations.map(o => o.plate), samples.map(s => s.plate), 'Require both distinct stock units');
  const [first, second] = observations;
  for (const key of ['range', 'consumption']) {
    assert.equal(first[key].value, second[key].value, `The matching stock cars disagree on ${key}`);
    assert.notEqual(first[key].source_hash, second[key].source_hash, 'Require distinct stock payloads');
  }
  const anchor = field => ({ ...first[field], corroboration: second[field], basis: 'swedish_my26_drive_19_inch_stock_combined_wltp' });
  return { ...base, technical_fields: { ...fields, wltp_range_km: anchor('range'),
    wltp_consumption_kwh_100km: anchor('consumption') },
  alternative_manufacturer_offer_consumption: fields.wltp_consumption_kwh_100km,
  decision: 'Prefer the paired combined WLTP data of two matching Swedish MY26 manufacturer stock units, not a mix with the offer maximum.',
  held: [], publication_approved: false };
}

function python(code, args, input) {
  return JSON.parse(execFileSync(process.execPath, ['scripts/run_python.mjs', '-c', code, ...args],
    { cwd: root, timeout: 65000, encoding: 'utf8', maxBuffer: 2 * 1024 * 1024, windowsHide: true, input }));
}

const pySetup = 'import json, sys; sys.path.insert(0,"scripts")\nfrom cupra_tavascan_review import drive_wltp_importer_context\n';
function verifyAccess(sample) {
  return python(pySetup + [
    'from base64 import b64encode',
    'from audit_catalog_sources import SourceFetcher',
    'page, data, importer = sys.argv[1:]',
    'fetcher = SourceFetcher(timeout=15, url_policy=lambda url, brands: url in (page, importer),',
    '    document_parser=lambda body, _: body, text_parser=lambda *_: "")',
    'assert fetcher.robots_allowed(data), "Manufacturer API policy disallows access"',
    'p, i = (fetcher.fetch(url, {"Cupra"}) for url in (page, importer))',
    'assert all((r["status"], r.get("http_status"), r.get("final_url")) == ("reachable", 200, url)',
    '    for r, url in ((p, page), (i, importer))), "Public vehicle sources held"',
    'print(json.dumps({"page_hash": p["content_hash"], "importer_b64": b64encode(i["document"]).decode()}))',
  ].join('\n'), [sample.page, sample.api, sample.importer]);
}

function importerProof(sample, raw) {
  return python(pySetup + 'print(json.dumps(drive_wltp_importer_context(sys.stdin.buffer.read(), sys.argv[1])))', [sample.importer], raw);
}

async function artifact(folder, file) {
  const path = join(folder, file);
  assert.equal(await realpath(path), path, 'Require a local regular evidence file');
  return readFile(path);
}

async function baseProfile(directory, name) {
  assert.match(name, /^cupra-tavascan-review-[a-z0-9_]+$/);
  const folder = join(directory, name);
  assert.equal(await realpath(folder), folder);
  execFileSync(process.execPath, ['scripts/run_python.mjs', 'scripts/cupra_tavascan_review.py', '--replay', folder],
    { cwd: root, timeout: 65000, windowsHide: true });
  const raw = await artifact(folder, 'review.json');
  return { profile: JSON.parse(raw).private_my26_drive_profile, base_hash: hash(raw) };
}

async function capture(directory, baseName, base) {
  const access = samples.map(verifyAccess);
  const browser = await launchQaBrowser();
  const packet = [];
  try {
    const tab = await browser.newPage();
    for (const [index, sample] of samples.entries()) {
      const incoming = tab.waitForResponse(r => r.url() === sample.api && r.ok() && r.request().method() === 'GET', { timeout: 35000 });
      const [nav, response] = await Promise.all([tab.goto(sample.page, { waitUntil: 'domcontentloaded' }), incoming]);
      assert(nav?.ok() && tab.url() === sample.page,
        `Unexpected stock source navigation: page ${nav?.status()}, data ${response.status()}, at ${tab.url()}`);
      assert([nav, response].every(r => !r.headers()['tdm-reservation'] || r.headers()['tdm-reservation'] === '0'),
        'Manufacturer has reserved automated extraction');
      const raw = await response.body();
      await tab.getByText(rangeLabel, { exact: true }).first().waitFor({ timeout: 10000 });
      const label = tab.getByText(rangeLabel, { exact: true }).first();
      const display = await label.evaluate(node => node.nextElementSibling?.textContent.trim() ?? '');
      const importerRaw = Buffer.from(access[index].importer_b64, 'base64');
      const observation = inspectDriveStock(sample, raw, importerProof(sample, importerRaw), display);
      packet.push({ raw, importerRaw, display, page_hash: access[index].page_hash, observation });
    }
  } finally { await browser.close(); }
  const profile = completeDriveProfile(base.profile, packet.map(p => p.observation));
  const folder = await mkdtemp(join(directory, 'cupra-tavascan-stock-wltp-'));
  for (const [i, sample] of samples.entries()) {
    await writeFile(join(folder, `${sample.plate}.json`), packet[i].raw, { flag: 'wx' });
    await writeFile(join(folder, `${sample.plate}.html`), packet[i].importerRaw, { flag: 'wx' });
  }
  const receipt = { base: baseName, base_hash: base.base_hash, captured_at: new Date().toISOString(),
    status: 'private_my26_profile_complete', publication_approved: false, database_writes: 0,
    inputs: packet.map(({ display, page_hash, observation }) => ({ display, page_hash, observation })), profile };
  await writeFile(join(folder, 'review.json'), encode(receipt), { flag: 'wx' });
  return { folder, receipt };
}

async function replay(directory, input) {
  const folder = await realpath(input);
  assert.equal(folder, resolve(input));
  assert.equal(dirname(folder), directory);
  assert.match(basename(folder), /^cupra-tavascan-stock-wltp-[a-z0-9]+$/i);
  const receiptBytes = await artifact(folder, 'review.json');
  const receipt = JSON.parse(receiptBytes);
  assert.deepEqual([receipt.status, receipt.publication_approved, receipt.database_writes, receipt.inputs.length],
    ['private_my26_profile_complete', false, 0, samples.length]);
  const base = await baseProfile(directory, receipt.base);
  assert.equal(base.base_hash, receipt.base_hash);
  const observations = [];
  for (const [index, sample] of samples.entries()) {
    const { display, page_hash, observation } = receipt.inputs[index];
    assert.match(page_hash, /^[0-9a-f]{64}$/);
    const actual = inspectDriveStock(sample, await artifact(folder, `${sample.plate}.json`),
      importerProof(sample, await artifact(folder, `${sample.plate}.html`)), display);
    assert.deepEqual(actual, observation);
    observations.push(actual);
  }
  assert.deepEqual(completeDriveProfile(base.profile, observations), receipt.profile);
  return { folder, receipt, capture_sha256: hash(receiptBytes) };
}

async function evidenceDirectory() {
  const directory = join(await realpath(root), 'data', 'local', 'release-data');
  assert.equal(await realpath(directory), directory);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(directory));
  return directory;
}

export async function readDriveWltpEvidence(input) {
  const directory = await evidenceDirectory();
  const { receipt, capture_sha256 } = await replay(directory, input);
  const raw = await artifact(join(directory, receipt.base), 'review.json');
  assert.equal(hash(raw), receipt.base_hash, 'Base proof changed after replay');
  return { receipt, base: JSON.parse(raw), capture_sha256 };
}

async function main() {
  const [mode, input, extra] = process.argv.slice(2);
  assert(!extra && input && ['--capture', '--replay'].includes(mode), 'Use --capture <base-folder-name> or --replay <private-folder>');
  const directory = await evidenceDirectory();
  const { folder, receipt } = mode === '--capture' ? await capture(directory, input, await baseProfile(directory, input))
    : await replay(directory, input);
  console.log(JSON.stringify({ output: join(folder, 'review.json'), status: receipt.status,
    technical_fields: Object.fromEntries(Object.entries(receipt.profile.technical_fields).map(([key, fact]) => [key, fact.value])),
    price_sek: receipt.profile.price.value, publication_approved: false, database_writes: 0 }));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) await main();
