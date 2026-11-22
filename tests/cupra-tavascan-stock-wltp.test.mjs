import assert from 'node:assert/strict';
import test from 'node:test';
import { completeDriveProfile, inspectDriveStock, samples } from '../scripts/cupra_tavascan_stock_wltp.mjs';

function fixture(sample) {
  const order = sample.id.slice(-13);
  const items = Object.entries({ numberplate: sample.plate, knr: order, manuf: 'CUPRA',
    model: 'Tavascan', modelyear: '2026', smod: 'Endurance', preuse: 'Nybil', drive: 'Bakhjulsdrift' })
    .map(([key, value]) => ({ key, value }));
  items.push({ key: 'cartitle', mbv: { code: 'KR1BCD' } }, { key: 'motor', values: [
    { key: 'fuel', value: 'El' }, { key: 'power.kw', value: '210', unit: 'kW' },
  ] });
  const group = (key, dataKey, value, unit) => ({ key, techDataGroup: { key, data: [{ key: dataKey,
    techData: { key: dataKey, values: [{ key: 'PURE_ELECTRICAL', items: [
      { key: 'energy_management', value: 'PURE' }, { key: 'fuel', value: 'ELECTRICAL' },
    ], values: [{ key: 'CITY', value: '692,0', unit }, { key: 'COMBINED', value, unit }] }] },
  }] } });
  const payload = { key: sample.token, carid: sample.id, items,
    serie_equip: [{ key: 'serieequip.wheels', values: [{ value: 'L\u00e4ttmetallf\u00e4lgar 8J x 19' },
      { value: 'D\u00e4ck 235/55 R19 fram och 255/50 R19 bak(polymerskikt)' }] },
    { key: 'serieequip.engine', values: [{ value: 'H\u00f6gvoltsbatteri 77 kWh (netto)' }] }],
    tyreLabels: [{ labels: ['235/55 R19', '255/50 R19'].map(size => ({ sizeDesignation_tyreSizeDesignation: size })) }],
    hypermediatechdata: [{ key: 'WLTP', techDataType: { key: 'WLTP', groups: [
      group('range', 'range', '553,0', 'km'), group('consumption', 'fuel', '15,8', 'kWh/100km'),
    ] } }],
  };
  const importer = { order, equipment_codes: ['P80', 'PF0', 'YC1'], importer_drive_type_reference: 'Framhjulsdrift',
    identity: { edition: 'Drive', model_year: 2026, stock_reference: sample.plate,
      model_code: { value: 'KR1BCD', source_url: sample.importer, source_hash: 'a'.repeat(64) } } };
  return { payload, importer };
}

function inspect(sample, change = () => {}, rendered = '553,0 km') {
  const { payload, importer } = fixture(sample);
  change(payload, importer);
  return inspectDriveStock(sample, Buffer.from(JSON.stringify(payload)), importer, rendered);
}

function base() {
  return { edition: 'Drive Swedish Edition', market: 'SE', model_year: 2026, model_code: 'KR1BCD',
    standard_wheel_inches: { value: 19 }, publication_approved: false, price: { value: 554900 },
    separate_dealer_price_proof: { value: 554900 }, held: ['wltp_range_km'], advertised_max_range_only: { value: 550 },
    technical_fields: Object.fromEntries(Object.entries({ac_charge_kw: 11, battery_kwh: 77, boot_liters: 540,
      dc_charge_kw: 135, drivetrain: 'RWD', seats: 5, tow_kg: 1000, wltp_consumption_kwh_100km: 15.3})
      .map(([key, value]) => [key, { value }])),
  };
}

test('admits the exact paired technical figures while retaining the separate cash price and advertised alternative', () => {
  assert.deepEqual(samples.map(s => s.token), ['U1dFNDAwNjAyMjIyMDI2ODY3NTU2=', 'U1dFNDA2OTUyMjIyMDI2ODY3NTY2=']);
  const original = base();
  const result = completeDriveProfile(original, samples.map(s => inspect(s)));
  assert.equal(result.technical_fields.wltp_range_km.value, 553);
  assert.equal(result.technical_fields.wltp_consumption_kwh_100km.value, 15.8);
  assert.equal(result.technical_fields.wltp_range_km.corroboration.source_url, samples[1].page);
  assert.equal(result.price.value, 554900);
  assert.equal(result.advertised_max_range_only.value, 550);
  assert.equal(result.alternative_manufacturer_offer_consumption.value, 15.3);
  assert.equal(Object.keys(result.technical_fields).length, 9);
  assert.deepEqual(result.held, []);
  assert.equal(result.publication_approved, false);
  assert.deepEqual(original, base());
});

test('rejects a different unit, ambiguous model year, incorrect edition and other tyres', () => {
  for (const [field, value] of [['numberplate', 'EWB33D'], ['modelyear', '2027'], ['drive', 'Fyrhjulsdrift'], ['knr', '2222026867557']]) {
    assert.throws(() => inspect(samples[0], p => { p.items.find(row => row.key === field).value = value; }));
  }
  assert.throws(() => inspect(samples[0], (_p, i) => { i.equipment_codes[0] = 'P28'; }));
  assert.throws(() => inspect(samples[0], p => { p.tyreLabels[0].labels[0].sizeDesignation_tyreSizeDesignation = '235/50 R20'; }), /Tyre labels/);
});

test('rejects wrong measurement phase, unit, display and a disagreement between the two cars', () => {
  const values = p => p.hypermediatechdata[0].techDataType.groups[0].techDataGroup.data[0].techData.values[0].values;
  assert.throws(() => inspect(samples[0], p => values(p).pop()), /COMBINED/);
  assert.throws(() => inspect(samples[0], p => { values(p)[1].unit = 'mi'; }), /Invalid combined/);
  assert.throws(() => inspect(samples[0], () => {}, '692,0 km'), /Rendered combined/);
  assert.throws(() => completeDriveProfile(base(), [inspect(samples[0]), inspect(samples[1], p => { values(p)[1].value = '552,0'; }, '552,0 km')]), /disagree on range/);
  assert.throws(() => completeDriveProfile(base(), [inspect(samples[0]), inspect(samples[0])]), /distinct stock units/);
});
