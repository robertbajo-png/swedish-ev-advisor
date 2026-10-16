import assert from 'node:assert/strict';
import {
  DEFAULT_TCO_ASSUMPTIONS,
  calculateTco,
  normalizeTcoAssumptions,
} from '../src/tco.js';

const assumptions = {
  ...DEFAULT_TCO_ASSUMPTIONS,
  annualKm: 10000,
  years: 5,
  annualInterestPercent: 5,
  residualPercent: 50,
  homeChargingPercent: 100,
  homeElectricitySekKwh: 2,
  publicElectricitySekKwh: 8,
  assumedConsumptionKwh100Km: 20,
  insuranceSekMonth: 1000,
  serviceSekYear: 4000,
  taxSekYear: 360,
};

const calculated = calculateTco({ id: 'example', price: 500000, consumptionVerified: null }, assumptions);
assert.equal(calculated.calculable, true);
assert.equal(calculated.consumptionSource, 'assumption');
assert.equal(calculated.consumptionKwh100Km, 20);
assert.equal(calculated.components.depreciationSek, 250000);
assert.equal(calculated.components.electricitySek, 20000);
assert.equal(calculated.components.insuranceSek, 60000);
assert.equal(calculated.components.serviceSek, 20000);
assert.equal(calculated.components.taxSek, 1800);
assert.equal(calculated.components.financingSek, 55000);
assert.equal(calculated.totalSek, 406800);
assert.equal(calculated.monthlySek, 6780);

const verifiedConsumption = calculateTco({ id: 'verified', price: 500000, consumptionVerified: 15 }, assumptions);
assert.equal(verifiedConsumption.consumptionSource, 'verified');
assert.equal(verifiedConsumption.consumptionKwh100Km, 15);
assert.equal(verifiedConsumption.components.electricitySek, 15000);

const missingPrice = calculateTco({ id: 'missing', price: null }, assumptions);
assert.equal(missingPrice.calculable, false);
assert.equal(missingPrice.reason, 'missing_price');
assert.equal(missingPrice.monthlySek, null);

const normalized = normalizeTcoAssumptions({ years: 99, residualPercent: -20, annualKm: 0 });
assert.equal(normalized.years, 10);
assert.equal(normalized.residualPercent, 0);
assert.equal(normalized.annualKm, 1000);

console.log(JSON.stringify({ tco_contract_ok: true, monthly_example_sek: calculated.monthlySek }, null, 2));
