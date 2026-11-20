import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { readConfiguration, readSummary, replayConfiguration } from '../scripts/volkswagen_id_buzz_configurator.mjs';
import { verifyReviewedConfigurations } from '../scripts/prepare_id_buzz_readback.mjs';

function fixture(awd = false) {
  const slug = awd ? 'pro-4motion' : 'pro';
  const trim = awd ? 'Pro 4MOTION' : 'Pro';
  const model = `ID. Buzz ${trim}`;
  const url = new URL('https://www.volkswagen-transportbilar.se/sv/bygg-din-bil.html/__app/72006/edition/' + slug + '.app');
  url.search = new URLSearchParams({ 'modelId-app': (awd ? 'EBBR5R' : 'EBBR7R') + '$OPTION', 'carlineId-app': '72006',
    'category-app': 'commercial', 'modelYear-app': '2027', 'salesGroupId-app': '74347', 'modelVersion-app': '2',
    'trimName-app': model + ' Sweden Olympic Edition', 'buildabilityStatus-app': 'buildable',
    'exteriorId-app': 'F14 EXTERIOR', 'interiorId-app': 'F56 INTERIOR' }).toString();
  const text = `${model} 5-Seats Sweden Olympic Edition Hjulbas: 2989 mm Kort Motor: ${awd ? '250 kW (340 PS)' : '210 kW (286 PS)'} V\u00e4xell\u00e5da: 1 vxl automat | El | WLTP:F\u00f6rbrukning: ${awd ? '22,30' : '19,80'}\u00a0kWh/100 km\u20601\n`
    + 'F\u00f6rbrukning: 21,60\u201320,50 kWh/100 km\nElektrisk r\u00e4ckvidd\n462\u2013489 km';
  return { slug, url, text };
}

test('reads exact five-seat configuration and ignores the family interval', () => {
  for (const [awd, value] of [[false, 19.8], [true, 22.3]]) {
    const { slug, url, text } = fixture(awd);
    const record = readConfiguration(slug, url, text);
    assert.equal(record.observations.configured_wltp_consumption_kwh_100km.value, value);
    assert.equal(record.rendered_text_sha256, createHash('sha256').update(text).digest('hex'));
    assert.equal(record.status, 'needs_review');
    assert.equal(record.wheelbase_mm, 2989);
    assert.equal(record.seats, 5);
  }
});

test('rejects changed year, drivetrain, market, or ambiguous qualifier', () => {
  const { slug, url, text } = fixture();
  for (const [key, different] of [['modelYear-app', '2026'], ['modelId-app', 'EBBR5R$OPTION'],
    ['buildabilityStatus-app', 'unbuildable'], ['category-app', 'private']]) {
    const changed = new URL(url);
    changed.searchParams.set(key, different);
    assert.throws(() => readConfiguration(slug, changed, text), /unexpected_configurator_identity/);
  }
  assert.throws(() => readConfiguration(slug, url + '&modelYear-app=2027', text), /unexpected_configurator_identity/);
  assert.throws(() => readConfiguration(slug, url.href.replace('transportbilar.se', 'transportbilar.example'), text), /unexpected_configurator_route/);
});

test('rejects shell pages, mixed seat counts, non-WLTP and duplicated evidence', () => {
  const { slug, url, text } = fixture();
  for (const other of ['', text.replace('5-Seats', '6-Seats'), text.replace('2989 mm Kort', '3239 mm Lång'),
    text.replace('19,80', '21,60\u201320,50'), text.replace('WLTP:', 'CLTC:'), text + '\n' + text]) {
    assert.throws(() => readConfiguration(slug, url, other), /exact_wltp_configuration_required/);
  }
  assert.throws(() => readConfiguration(slug, url, text.replace('19,80', '99,99')), /consumption_out_of_bounds/);
});

function summaryFixture() {
  const { slug, url, text } = fixture();
  const selection = readConfiguration(slug, url, text);
  const proof = { url: url.href, text,
    wltp: { consumption: ['Br\u00e4nslef\u00f6rbrukning blandad k\u00f6rning', '19,80\u00a0kWh/100 km\u2060\n1'],
      range: ['R\u00e4ckvidd vid blandad k\u00f6rning', '444 km'] },
    price: { base: ['Grundpris', '590 000 kr\u2060\n2'], options: ['Tillval', 'Inga tillkommande kostnader'],
      total: ['inkl. moms', '590\u00a0000 kr'], before_vat: ['exkl. moms', '472 000 kr'] },
    towing: ['Max till\u00e5ten dragvikt bromsad vid 12%', '1 200 kg'] };
  return { slug, selection, proof };
}

test('binds combined range, zero-option VAT-inclusive cash and braked towing to the same configuration', () => {
  const { slug, selection, proof } = summaryFixture();
  const { observations } = readSummary(slug, selection, proof);
  assert.equal(observations.configured_wltp_consumption_kwh_100km.value, 19.8);
  assert.equal(observations.configured_wltp_range_km.value, 444);
  assert.equal(observations.configured_cash_price_sek_including_vat.value, 590000);
  assert.equal(observations.configured_braked_towing_kg.value, 1200);
});

test('holds changed options, paint and interior even when trim and motor match', () => {
  for (const [key, value] of [['modelId-app', 'EBBR7R$NEWOPTION'], ['exteriorId-app', 'F14 RED'], ['interiorId-app', 'F56 OTHER']]) {
    const { slug, selection, proof } = summaryFixture();
    const url = new URL(proof.url);
    url.searchParams.set(key, value);
    assert.throws(() => readSummary(slug, selection, { ...proof, url }), /summary_configuration_changed/);
  }
});

test('holds city range, leasing, mismatched VAT, paid options, non-braked towing and changed consumption', () => {
  const edits = [
    p => { p.wltp.range[0] = 'R\u00e4ckvidd vid stadsk\u00f6rning'; },
    p => { p.price.total[1] = '5 900 kr/m\u00e5n'; },
    p => { p.price.before_vat[1] = '490 000 kr'; },
    p => { p.price.options[1] = '10 000 kr'; },
    p => { p.towing[0] = 'Max till\u00e5ten dragvikt obromsad'; },
    p => { p.wltp.consumption[1] = '19,70 kWh/100 km'; },
  ];
  for (const edit of edits) {
    const { slug, selection, proof } = summaryFixture();
    edit(proof);
    assert.throws(() => readSummary(slug, selection, proof), /summary_/);
  }
});

test('replays fresh raw receipts and rejects edits or stale captures', () => {
  const { slug, selection, proof } = summaryFixture();
  const now = new Date('2026-11-19T10:00:00Z');
  const text = proof.text;
  const raw = JSON.stringify(proof);
  const hash = value => createHash('sha256').update(value).digest('hex');
  const receipt = { ...selection, source_url: new URL(selection.final_url).origin + new URL(selection.final_url).pathname,
    captured_at: '2026-11-19T09:59:00Z', html_access_receipt: { html_sha256: 'a'.repeat(64), checked_at: '2026-11-19T09:58:00Z' },
    summary: { ...readSummary(slug, selection, proof), evidence_sha256: hash(raw), summary_file: 'pro-summary.json' } };
  assert.equal(replayConfiguration(slug, receipt, text, raw, now).summary.observations.configured_wltp_range_km.value, 444);
  assert.throws(() => replayConfiguration(slug, receipt, text + ' ', raw, now), /Rendered engine hash changed/);
  assert.throws(() => replayConfiguration(slug, receipt, text, raw + ' ', now), /Summary evidence hash changed/);
  assert.throws(() => replayConfiguration(slug, { ...receipt, captured_at: '2026-11-17T09:59:00Z' }, text, raw, now), /Fresh read-only/);
  const modified = structuredClone(receipt);
  modified.summary.observations.configured_wltp_range_km.value = 777;
  assert.throws(() => replayConfiguration(slug, modified, text, raw, now), /Summary facts do not match/);
});

test('rejects reworded or cross-version claims after raw configuration replay', () => {
  const { slug, selection, proof } = summaryFixture();
  const configs = [selection, { ...selection, trim: 'Pro 4MOTION', configuration_id: 'EBBR5R$FIXTURE' }].map(config => ({
    ...config, summary: readSummary(slug, selection, proof),
  }));
  const review = { configurations: configs, variants: configs.map(config => {
    const source_url = config.summary.final_url;
    const claim = metric => ({ ...config.summary.observations[metric], source_url });
    return { trim: config.trim, configuration_id: config.configuration_id, facts: {
      wltp_range_km: claim('configured_wltp_range_km'),
      wltp_consumption_kwh_100km: claim('configured_wltp_consumption_kwh_100km'),
    }, price: { manufacturer_base_cash: claim('configured_cash_price_sek_including_vat') },
    observed_configurator_tow: claim('configured_braked_towing_kg') };
  }) };
  verifyReviewedConfigurations(review, configs);
  const changed = structuredClone(review);
  changed.configurations[0].summary.observations.configured_wltp_range_km.value = 555;
  assert.throws(() => verifyReviewedConfigurations(changed, configs), /differ from the raw capture/);
  changed.configurations = configs;
  changed.variants[0].configuration_id = configs[1].configuration_id;
  assert.throws(() => verifyReviewedConfigurations(changed, configs), /different configuration/);
  changed.variants[0].configuration_id = configs[0].configuration_id;
  changed.variants[0].facts.wltp_range_km.quote += ' edited';
  assert.throws(() => verifyReviewedConfigurations(changed, configs), /Configuration quote changed/);
});
