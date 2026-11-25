import assert from 'node:assert/strict';
import { test } from 'node:test';
import { calculateOwnership, distanceForWeek, loanCashFlows, OWNERSHIP_ASSUMPTIONS } from '../src/ownership-cost.js';

const today = '2026-11-25';
const car = {
  price: 400000, priceType: 'list_price',
  priceSource: 'https://example.com/exact-variant', priceVerifiedAt: '2026-11-24',
  consumptionVerified: 20,
};
const loan = { down: 80000, term: 36, rate: 0, balloon: 120000, opening: 600, fee: 40 };
const lease = { term: 36, start: 10000, monthly: 3990, includedKm: 36000, overMil: 18, service: true };
const input = { ...OWNERSHIP_ASSUMPTIONS, homePercent: 80, homeSek: 2, publicSek: 6 };
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 0.00001, actual + ' != ' + expected);

test('46 pendlarveckor plus en återkommande eller enstaka helgresa', () => {
  assert.deepEqual(distanceForWeek({ commute: '32', trip: '180', cadence: 'once' }), { annualKm: 7360, onceKm: 180 });
  assert.deepEqual(distanceForWeek({ commute: '32', trip: '180', cadence: 'monthly' }), { annualKm: 9520, onceKm: 0 });
  assert.deepEqual(distanceForWeek({ commute: '25', trip: '240', cadence: 'fortnightly' }), { annualKm: 11990, onceKm: 0 });
});

test('en enda helgresa räknas en gång även utan pendling', () => {
  const distance = distanceForWeek({ commute: '', trip: '240', cadence: 'once' });
  const result = calculateOwnership(car, { ...input, ...distance }, today);
  assert.equal(result.km, 240);
  near(result.operating.electricity, 134.4);
  assert.equal(calculateOwnership(car, { ...input, annualKm: 0, onceKm: 0 }, today).reason, 'assumptions');
});

test('45 000 km och 2,80 kr/kWh skiljer laddförluster från WLTP vid elmätare', () => {
  assert.equal(calculateOwnership(car, input, today).operating.electricity, 25200);
  near(calculateOwnership(car, { ...input, basis: 'vehicle', overrideConsumption: 20 }, today).operating.electricity, 28000);
  assert.equal(calculateOwnership(car, { ...input, homePercent: 0 }, today).operating.electricity, 54000);
  assert.equal(calculateOwnership(car, { ...input, basis: 'vehicle', lossPercent: '', overrideConsumption: 20 }, today).reason, 'assumptions');
  assert.equal(calculateOwnership(car, { ...input, basis: 'vehicle', lossPercent: '' }, today).operating.electricity, 25200);
});

test('exakt variant utan offerter och frånpris utan fabrikation', () => {
  const exact = calculateOwnership(car, input, today);
  assert.equal(exact.cash.total, 222280);
  assert.equal(exact.loan, undefined);
  assert.equal(exact.lease, undefined);
  for (const [row, reason] of [
    [{ ...car, priceType: 'manufacturer_from' }, 'from-price'],
    [{ ...car, priceType: 'campaign_price', priceValidUntil: '2026-11-24' }, 'offer-date'],
    [{ ...car, priceVerifiedAt: '2026-11-26' }, 'unverified'],
    [{ ...car, priceSource: '' }, 'unverified'],
  ]) {
    const result = calculateOwnership(row, input, today, loan, lease);
    assert.equal(result.pricing.reason, reason);
    assert.equal(result.cash, undefined);
    assert.equal(result.loan, undefined);
    assert.ok(result.lease.total > 0, 'separat inmatat leasingavtal får beräknas');
  }
});

test('lånet stängs exakt en gång före, vid och efter förfall', () => {
  for (const months of [18, 36, 48]) {
    const result = loanCashFlows(400000, 240000, 62280, months, { ...loan, rate: 6 });
    const viaCash = result.start + result.regular * result.regularMonths + result.maturityPayment + result.settlement + 62280 - 240000;
    near(result.total, viaCash);
    if (months < 36) {
      assert.equal(result.maturityPayment, 0);
      assert.ok(result.settlement > 120000);
    } else {
      assert.equal(result.maturityPayment, 120000);
      assert.equal(result.maturityMonth, 36);
      assert.equal(result.settlement, 0);
    }
  }
});

test('leasing: övermil, inkluderad service och period måste matcha', () => {
  const result = calculateOwnership(car, input, today, null, { ...lease, monthlyIncrease: 100, wear: 2000 });
  assert.equal(result.lease.cash.covered, 7800);
  assert.equal(result.lease.cash.excess, 16200);
  assert.equal(result.lease.total, 224320);
  assert.equal(result.leaseSensitivity, 5600);
  assert.equal(calculateOwnership(car, input, today, null, { ...lease, term: 24 }).leaseReason, 'period');
});
