import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { launchQaBrowser } from './qa_browser.mjs';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const modelPage = 'https://www.cupraofficial.se/bilar/tavascan';
export const publicConfig = 'https://www.cupraofficial.se/carshop/w/configuration'
  + '?id=ePl9IIpVw_Cws2OQj6efq653kKEziucdfXxAgk7OLvoG-u4BbgZABKTDDYEISBtZAJG-e6SzIRAB6XBjIIIlAyyh5uii62fgCJRzMzRRMHQydAIxTc0UQMDRRSm2FgAeFiki'
  + '&carline=CARLINE-GROUP-KR1';
const gateway = 'https://gateway.prod.pcc.seat.cloud.vwgroup.com/ecosystem/v1/graphql';
const driveName = 'Drive 210 kW (286 hk) 2WD Swedish Edition';
const wheelName = 'L\u00e4ttmetallf\u00e4lgar 19" Vulcano';
const motorKey = /^ALL-KR1BCD_U_0_U_GPF0PF0_U_GPW1PW1_U_GP28P28_U_GYC1YC1_U_GYW3YW3-2027$/;
const sha256 = raw => createHash('sha256').update(raw).digest('hex');
const encode = data => JSON.stringify(data, null, 2) + '\n';

function one(rows, message) {
  assert.equal(rows.length, 1, message);
  return rows[0];
}

export function inspectDriveConfiguration(request, raw, source, renderedRange, version = 2) {
  assert(version === 1 || version === 2, 'Unknown configuration receipt version');
  assert.equal(source, publicConfig, 'Unregistered CUPRA configuration');
  assert.deepEqual(request, { operation: 'GetConfiguration', market: '013', locale: 'sv-SE', standard: 'wltp' },
    'Exact Swedish WLTP request required');
  assert(raw.length > 0 && raw.length < 250_000, 'Invalid configuration response length');
  const payload = JSON.parse(raw);
  assert(payload.errors === undefined, 'Manufacturer returned configuration errors');
  const model = payload.data?.getModel;
  assert.deepEqual([model?.year, model?.carlineKey, model?.carlineName], [2027, 'CARLINE-KR1C', 'TAVASCAN'],
    'Expected a MY27 Tavascan, never reuse it for MY26');
  const engine = one(model.engines.filter(row => row.selected === true), 'Exact selected engine required');
  assert(engine.name === driveName && engine.fuelType === 'El' && motorKey.test(engine.key), 'Selected drive edition changed');
  const wheel = one(model.wheels.filter(row => row.selected === true), 'Exact selected wheel required');
  const standardWheel = one(engine.serieEquipment.filter(row => row.categoryType === 'WHEELS'), 'Exact standard wheel required');
  assert(wheel.name === wheelName && standardWheel.name === wheelName && standardWheel.code === 'MRADF05',
    'Standard 19-inch Vulcano scope changed');
  const price = name => one(engine.prices.filter(row => row.name === name), `Missing configured price: ${name}`);
  const base = price('basePrice');
  const amount = base.value;
  assert(Number.isInteger(amount) && amount >= 100_000 && amount <= 3_000_000
    && /^\d{1,3}(?:\.\d{3})+ kr$/.test(base.formatted)
    && Number(base.formatted.replaceAll('.', '').replace(' kr', '')) === amount
    && ['total', 'preDiscountTotal', 'fullPrice'].every(name => price(name).value === amount)
    && ['optionsPrice', 'totalDiscount'].every(name => price(name).value === 0), 'Expected undiscounted configured amount in SEK');
  const technical = engine.technicalDetail;
  assert(technical.transmission.drive.formatted === 'Bakhjulsdrift', 'Expected rear wheel drive');

  function technicalValue(row, label, pattern, min, max) {
    const match = pattern.exec(row?.formatted ?? '');
    const value = Number(match?.[1]);
    assert(row?.name === label && Number.isInteger(value) && value >= min && value <= max, `Invalid ${label} observation`);
    return { value, quote: `${label}: ${row.formatted}` };
  }

  const net = technicalValue(technical.battery.capacity, 'Batterikapacitet netto', /^(\d+) kWh$/, 20, 180);
  const boot = technicalValue(technical.vehicleDimensions.bootCapacity, 'Bagagerumsvolym', /^(\d+) l$/, 80, 1500);
  const ac = one(engine.serieEquipment.filter(row => row.code === 'MBLGKB9'), 'Onboard AC charger not confirmed');
  const acKw = technicalValue({ name: 'Ombordladdare', formatted: ac.name }, 'Ombordladdare', /^Ombordladdare Max (\d+) kW AC$/, 3, 43);
  let dcKw;
  if (version >= 2) {
    const dc = one(engine.serieEquipment.filter(row => row.code === 'MDCBLH2' || /^Snabbladdning DC Max\b/.test(row.name)),
      'Unique maximum DC charging equipment required');
    assert.equal(dc.code, 'MDCBLH2', 'Maximum DC charging equipment code changed');
    dcKw = technicalValue({ name: 'Maximal DC-effekt', formatted: dc.name }, 'Maximal DC-effekt', /^Snabbladdning DC Max (\d+) kW$/, 20, 600);
  }
  const data = one(engine.efficiencyTestData, 'Unique WLTP data required');
  assert(data.standard === 'wltp' && data.engineType === 'PEV', 'Wrong measurement standard or motor');

  function combined(rows, key, unit, min, max) {
    const row = one(rows.filter(row => row.phase === 'COMBINED' || row.key === key), 'Unique combined WLTP value required');
    assert(row.key === key && row.phase === 'COMBINED' && row.energyManagementType === 'PURE'
      && row.fuelType === 'ELECTRICAL' && row.unit === unit && Number.isFinite(row.value)
      && row.value >= min && row.value <= max, 'Invalid combined WLTP evidence');
    return { value: row.value, unit, quote: `${key}: ${row.value} ${unit}` };
  }

  const range = combined(data.range, 'RANGE_PURE_ELECTRICAL_COMBINED', 'km', 50, 1200);
  const consumption = combined(data.consumptions, 'CONSUMPTION_PURE_ELECTRICAL_COMBINED', 'kWh/100km', 5, 60);
  assert(Number.isInteger(range.value) && renderedRange === `${range.value} km`, 'Rendered range disagrees with configured range');
  return { status: 'private_configurator_wltp_observation', source_url: source, source_hash: sha256(raw),
    market: 'SE', variant: 'Drive Swedish Edition', model_year: 2027, model_code: 'KR1BCD',
    configuration_key: engine.key, standard_wheels_inches: 19, configured_combined_range: range,
    configured_combined_consumption: consumption, configured_base_amount_sek: { value: amount, quote: base.formatted },
    configured_hardware: { battery_net_kwh: net, boot_liters: boot, ac_charge_kw: acKw,
      drivetrain: { value: 'RWD', quote: technical.transmission.drive.formatted },
      ...(dcKw ? { dc_charge_kw: dcKw } : {}) },
    held: ['independent MY27 list-price basis', 'certified WLTP', ...(dcKw ? [] : ['dc_charge_kw']), 'tow_kg', 'seats'],
    scope: 'MY27 public configurator figures; not certified MY26 facts',
    publication_approved: false, database_writes: 0 };
}

async function evidenceRoot() {
  const expected = join(await realpath(root), 'data', 'local', 'release-data');
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(expected));
  assert.equal(await realpath(expected), expected, 'Require local evidence directory');
  return expected;
}

function publicAccess() {
  const check = [
    'import json,sys; sys.path.insert(0,"scripts")',
    'from audit_catalog_sources import SourceFetcher',
    'from hashlib import sha256',
    'from urllib.parse import urljoin',
    'from variant_refresh import parse_document',
    'url, model = sys.argv[1:]',
    'fetcher = SourceFetcher(timeout=20, url_policy=lambda u, b: u in (url, model),',
    '    document_parser=lambda raw, typ: raw, text_parser=lambda *_: "")',
    'page = fetcher.fetch(model, {"Cupra"})',
    'assert (page["status"], page.get("http_status"), page.get("final_url")) == ("reachable", 200, model)',
    'links = parse_document(page["document"], "text/html").nodes("a")',
    'assert any(urljoin(model, link.attrs.get("href", "")) == url for link in links), "Published Drive configuration link changed"',
    'config = fetcher.fetch(url, {"Cupra"})',
    'assert (config["status"], config.get("http_status"), config.get("final_url")) == ("reachable", 200, url)',
    'print(json.dumps({"model_html_sha256": sha256(page["document"]).hexdigest(),',
    '    "config_html_sha256": sha256(config["document"]).hexdigest()}))',
  ].join('\n');
  return JSON.parse(execFileSync(process.execPath, ['scripts/run_python.mjs', '-c', check, publicConfig, modelPage],
    { cwd: root, timeout: 80000, encoding: 'utf8', windowsHide: true }));
}

async function capture(directory) {
  const access = publicAccess();
  const browser = await launchQaBrowser();
  let raw, request, renderedRange;
  try {
    const page = await browser.newPage();
    const incoming = page.waitForResponse(response => response.url() === gateway
      && response.request().postDataJSON()?.operationName === 'GetConfiguration', { timeout: 35000 });
    const [navigation, response] = await Promise.all([page.goto(publicConfig, { waitUntil: 'domcontentloaded', timeout: 25000 }), incoming]);
    assert(navigation?.ok() && response.ok() && page.url() === publicConfig, 'Public configuration is not reachable');
    assert([navigation, response].every(r => !r.headers()['tdm-reservation'] || r.headers()['tdm-reservation'] === '0'),
      'Manufacturer reserved automated extraction');
    const body = response.request().postDataJSON();
    request = { operation: body.operationName, market: body.variables.marketContextInput.marketCode,
      locale: body.variables.marketContextInput.languageKey, standard: body.variables.efficiencyStandard };
    raw = await response.body();
    const selected = JSON.parse(raw).data.getModel.engines.find(row => row.selected === true);
    const expected = `${selected.efficiencyTestData[0].range.find(row => row.phase === 'COMBINED').value} km`;
    const visible = page.getByText(expected, { exact: true }).first();
    await visible.waitFor({ timeout: 10000 });
    renderedRange = (await visible.innerText()).trim();
  } finally { await browser.close(); }
  const report = inspectDriveConfiguration(request, raw, publicConfig, renderedRange);
  const folder = await mkdtemp(join(directory, 'cupra-tavascan-configurator-'));
  const receipt = { version: 2, captured_at: new Date().toISOString(), access, request, rendered_range: renderedRange, report };
  await writeFile(join(folder, 'configuration.json'), raw, { flag: 'wx' });
  await writeFile(join(folder, 'review.json'), encode(receipt), { flag: 'wx' });
  return { folder, report };
}

async function replay(directory, path) {
  const folder = await realpath(path);
  assert.equal(dirname(folder), directory);
  assert.match(basename(folder), /^cupra-tavascan-configurator-[a-z0-9]+$/i);
  async function read(name) {
    const file = join(folder, name);
    assert.equal(await realpath(file), file);
    return readFile(file);
  }
  const saved = JSON.parse(await read('review.json'));
  assert.match(saved.access.model_html_sha256, /^[0-9a-f]{64}$/);
  assert.match(saved.access.config_html_sha256, /^[0-9a-f]{64}$/);
  const version = saved.version === undefined ? 1 : saved.version;
  const report = inspectDriveConfiguration(saved.request, await read('configuration.json'), publicConfig, saved.rendered_range, version);
  assert.deepEqual(report, saved.report, 'Configuration bytes or derived proof changed');
  return { folder, report };
}

async function main() {
  const [mode, path, extra] = process.argv.slice(2);
  assert(!extra && ((mode === '--capture' && !path) || (mode === '--replay' && path)), 'Use --capture or --replay <private-folder>');
  const directory = await evidenceRoot();
  const { folder, report } = mode === '--capture' ? await capture(directory) : await replay(directory, path);
  console.log(JSON.stringify({ output: join(folder, 'review.json'), ...report }));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) await main();
