import assert from 'node:assert/strict';
import test from 'node:test';
import { inspectDriveConfiguration, publicConfig } from '../scripts/cupra_tavascan_configurator.mjs';

const context = { operation: 'GetConfiguration', market: '013', locale: 'sv-SE', standard: 'wltp' };
const wheel = { name: 'L\u00e4ttmetallf\u00e4lgar 19" Vulcano', selected: true };
const range = { key: 'RANGE_PURE_ELECTRICAL_COMBINED', phase: 'COMBINED', energyManagementType: 'PURE',
  fuelType: 'ELECTRICAL', unit: 'km', value: 552 };
const fuel = { ...range, key: 'CONSUMPTION_PURE_ELECTRICAL_COMBINED', unit: 'kWh/100km', value: 15.8 };

function fixture() {
  return { year: 2027, carlineKey: 'CARLINE-KR1C', carlineName: 'TAVASCAN', wheels: [{ ...wheel }], engines: [{
    selected: true, name: 'Drive 210 kW (286 hk) 2WD Swedish Edition', fuelType: 'El',
    key: 'ALL-KR1BCD_U_0_U_GPF0PF0_U_GPW1PW1_U_GP28P28_U_GYC1YC1_U_GYW3YW3-2027',
    serieEquipment: [{ name: wheel.name, categoryType: 'WHEELS', code: 'MRADF05' },
      { name: 'Ombordladdare Max 11 kW AC', code: 'MBLGKB9' },
      { name: 'Snabbladdning DC Max 135 kW', code: 'MDCBLH2' }],
    prices: [...['basePrice', 'total', 'preDiscountTotal', 'fullPrice'].map(name => ({ name, value: 554900, formatted: '554.900 kr' })),
      { name: 'totalDiscount', value: 0 }, { name: 'optionsPrice', value: 0 }],
    technicalDetail: { transmission: { drive: { formatted: 'Bakhjulsdrift' } }, maxTowingWeight: null,
      battery: { capacity: { name: 'Batterikapacitet netto', formatted: '77 kWh' } },
      vehicleDimensions: { bootCapacity: { name: 'Bagagerumsvolym', formatted: '540 l' } } },
    efficiencyTestData: [{ standard: 'wltp', engineType: 'PEV',
      range: [{ ...range, key: 'RANGE_PURE_ELECTRICAL_CITY', phase: 'CITY', value: 691 }, { ...range }],
      consumptions: [{ ...fuel }],
    }],
  }] };
}

function inspect(model, request = context, visible = '552 km', version = 2) {
  return inspectDriveConfiguration(request, Buffer.from(JSON.stringify({ data: { getModel: model } })), publicConfig, visible, version);
}

test('uses the combined cycle and leaves the MY27 observation private', () => {
  const report = inspect(fixture());
  assert.equal(report.configured_combined_range.value, 552);
  assert.equal(report.configured_combined_consumption.value, 15.8);
  assert.equal(report.model_year, 2027);
  assert.equal(report.model_code, 'KR1BCD');
  assert.equal(report.standard_wheels_inches, 19);
  assert.equal(report.publication_approved, false);
  assert.equal(report.database_writes, 0);
  assert(!('price_sek' in report) && !('wltp_range_km' in report));
  assert.equal(report.configured_base_amount_sek.value, 554900);
  assert.equal(report.configured_hardware.battery_net_kwh.value, 77);
  assert.equal(report.configured_hardware.boot_liters.value, 540);
  assert.equal(report.configured_hardware.ac_charge_kw.value, 11);
  assert.equal(report.configured_hardware.dc_charge_kw.value, 135);
  assert(!report.held.includes('dc_charge_kw'));
  assert(report.held.includes('tow_kg') && !('tow_kg' in report.configured_hardware));
});

test('uses only the selected engine peak DC row and preserves legacy receipt output', () => {
  for (const change of [e => { e.serieEquipment.pop(); },
    e => { e.serieEquipment[2].name = 'Laddstation 135 kW DC'; },
    e => { e.serieEquipment[2].name = 'Snabbladdning DC Max 0 kW'; },
    e => { e.serieEquipment[2].code = 'OTHER'; },
    e => { e.serieEquipment.push({ name: 'Snabbladdning DC Max 175 kW', code: 'OTHER' }); }]) {
    const model = fixture();
    change(model.engines[0]);
    assert.throws(() => inspect(model), /DC/);
  }
  const legacy = inspect(fixture(), context, '552 km', 1);
  assert(legacy.held.includes('dc_charge_kw') && !('dc_charge_kw' in legacy.configured_hardware));
});

test('rejects discounted prices, ambiguous battery basis and charger or drivetrain mismatches', () => {
  for (const change of [e => { e.prices.find(p => p.name === 'totalDiscount').value = 1; },
    e => { e.prices[0].formatted = '5.490 kr/mån'; },
    e => { e.technicalDetail.battery.capacity.name = 'Batterikapacitet brutto'; },
    e => { e.technicalDetail.transmission.drive.formatted = 'Fyrhjulsdrift'; },
    e => { e.serieEquipment[1].name = 'Laddstation 135 kW DC'; }]) {
    const changed = fixture();
    change(changed.engines[0]);
    assert.throws(() => inspect(changed));
  }
});

test('does not accept MY26, another market, a VZ engine or another wheel', () => {
  for (const change of [m => { m.year = 2026; }, m => { m.engines[0].key = m.engines[0].key.replace('2027', '2026'); },
    m => { m.engines[0].name = 'VZ Swedish Edition'; }, m => { m.wheels[0].name = '20" Hekla'; }]) {
    const altered = fixture();
    change(altered);
    assert.throws(() => inspect(altered));
  }
  assert.throws(() => inspect(fixture(), { ...context, market: '012' }), /Exact Swedish WLTP request/);
});

test('refuses a city figure, duplicate combined data, different units or a differing display', () => {
  for (const change of [d => d.range.pop(), d => d.range.push({ ...range }),
    d => { d.consumptions[0].unit = 'Wh/km'; }, d => { d.range[1].value = '552'; }]) {
    const altered = fixture();
    change(altered.engines[0].efficiencyTestData[0]);
    assert.throws(() => inspect(altered), /combined WLTP/);
  }
  assert.throws(() => inspect(fixture(), context, '553 km'), /Rendered range disagrees/);
});
