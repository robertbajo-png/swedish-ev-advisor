
import { MANUFACTURER_FROM_PRICE, priceOfferEnd } from './price-evidence.js';

export const OWNERSHIP_ASSUMPTIONS = Object.freeze({
  months: 36, annualKm: 15000, onceKm: 0, homePercent: 80, homeSek: 2, publicSek: 6,
  consumption: 20, basis: 'metered', lossPercent: 10, resalePercent: 60,
  insurance: 600, service: 2600, tyres: 2200, tax: 360, charger: 0, parking: 0, tolls: 0,
});

function number(value) {
  return value == null || value === '' ? NaN : Number(value);
}

function within(value, min, max) {
  const n = number(value);
  return Number.isFinite(n) && n >= min && n <= max;
}

export function distanceForWeek({ commute, trip, cadence }) {
  const tripsPerYear = { monthly: 12, weekly: 52, once: 0 };
  return {
    annualKm: Number(commute) * 5 * 46 + Number(trip) * tripsPerYear[cadence],
    onceKm: cadence === 'once' ? Number(trip) : 0,
  };
}

export function electricityCost(km, kwhPer100Km, sekPerKwh, basis, lossPercent) {
  const efficiency = basis === 'vehicle' ? 1 - lossPercent / 100 : 1;
  return km * kwhPer100Km / 100 * sekPerKwh / efficiency;
}

export function ownershipPrice(car, today) {
  if (car.priceType === MANUFACTURER_FROM_PRICE) return { reason: 'from-price' };
  if (!['list_price', 'campaign_price', 'dealer_offer'].includes(car.priceType) ||
      !within(car.price, 1, 10000000) || !car.priceSource || !car.priceVerifiedAt || car.priceVerifiedAt > today) return { reason: 'unverified' };
  const offer = car.priceType !== 'list_price';
  const end = priceOfferEnd(car.priceType, car.priceValidUntil);
  if (offer && (!end || end < today)) return { reason: 'offer-date' };
  return { price: Number(car.price) };
}

function compareRow(sek, km, months, cash) {
  return { total: sek, perMonth: sek / months, perMil: sek / (km / 10), cash };
}

// The balloon is paid with the last regular payment if maturity is inside the horizon.
// Before maturity the remaining balance is settled once in the sale cash flow.
export function loanCashFlows(price, sale, operating, months, quote) {
  const [down, term, rate, balloon, opening, fee] =
    ['down', 'term', 'rate', 'balloon', 'opening', 'fee'].map((key) => number(quote[key]));
  if (!within(down, 0, price - 1) || !Number.isInteger(term) || !within(term, 1, 120) ||
      !within(rate, 0, 40) || !within(balloon, 0, price - down) ||
      !within(opening, 0, 1000000) || !within(fee, 0, 1000000)) return null;

  const principal = price - down;
  const monthlyRate = rate / 1200;
  const payment = monthlyRate === 0
    ? (principal - balloon) / term
    : (principal - balloon / (1 + monthlyRate) ** term) * monthlyRate / (1 - (1 + monthlyRate) ** -term);
  const regularMonths = Math.min(term, months);
  let balance = principal;
  let interest = 0;
  for (let paymentIndex = 0; paymentIndex < regularMonths; paymentIndex += 1) {
    const interestThisMonth = balance * monthlyRate;
    interest += interestThisMonth;
    balance += interestThisMonth - payment;
  }
  const mature = months >= term;
  const maturityPayment = mature ? balloon : 0;
  const settlement = mature ? 0 : Math.max(0, balance);
  const fees = opening + fee * regularMonths;
  const total = price - sale + interest + fees + operating;
  return {
    total, interest, fees, start: down + opening, regular: payment + fee, regularMonths,
    maturityPayment, maturityMonth: term, settlement, saleNet: sale - settlement,
    paidToLender: (payment + fee) * regularMonths + maturityPayment + settlement,
  };
}

export function calculateOwnership(car, assumptions, today, loanQuote, leaseQuote) {
  const {
    months, annualKm, onceKm, homePercent, homeSek, publicSek, lossPercent, resalePercent,
    insurance, service, tyres, tax, charger = 0, parking = 0, tolls = 0,
  } = assumptions;
  const consumption = assumptions.overrideConsumption === '' || assumptions.overrideConsumption == null
    ? car.consumptionVerified ?? assumptions.consumption : assumptions.overrideConsumption;
  const basis = assumptions.overrideConsumption === '' || assumptions.overrideConsumption == null
    ? 'metered' : assumptions.basis;
  const valid = Number.isInteger(Number(months)) && within(months, 1, 120)
    && within(annualKm, 100, 60000) && within(onceKm, 0, 60000) && within(homePercent, 0, 100)
    && within(homeSek, 0, 50) && within(publicSek, 0, 50)
    && (basis === 'metered' || basis === 'vehicle' && within(lossPercent, 0, 50))
    && within(resalePercent, 0, 100) && within(consumption, 1, 100)
    && [insurance, service, tyres, tax, charger, parking, tolls].every((value) => within(value, 0, 100000));
  if (!valid) return { reason: 'assumptions' };
  const duration = Number(months);
  const km = annualKm * duration / 12 + Number(onceKm);
  const electricity = electricityCost(km, Number(consumption), (homePercent * homeSek + (100 - homePercent) * publicSek) / 100, basis, Number(lossPercent));
  const operating = {
    electricity, insurance: insurance * duration, service: service * duration / 12,
    tyres: tyres * duration / 12, tax: tax * duration / 12,
    charger: Number(charger), parking: parking * duration, tolls: tolls * duration,
  };
  const operatingTotal = Object.values(operating).reduce((total, item) => total + item, 0);
  const pricing = ownershipPrice(car, today);
  const result = { pricing, km, operating, operatingTotal, consumption, basis, duration };

  if (pricing.price) {
    const sale = pricing.price * resalePercent / 100;
    result.cash = compareRow(pricing.price - sale + operatingTotal, km, duration, { start: pricing.price, sale });
    if (loanQuote) {
      const flows = loanCashFlows(pricing.price, sale, operatingTotal, duration, loanQuote);
      if (flows) result.loan = compareRow(flows.total, km, duration, flows);
    }
  }
  if (leaseQuote) {
    const [term, start, monthly, includedKm, overMil] =
      ['term', 'start', 'monthly', 'includedKm', 'overMil'].map((key) => number(leaseQuote[key]));
    if (!Number.isInteger(term) || !within(term, 1, 120)) result.leaseReason = 'terms';
    else if (term !== duration) result.leaseReason = 'period';
    else if (![start, monthly, includedKm, overMil].every((value) => within(value, 0, 1000000))) result.leaseReason = 'terms';
    else {
      const excess = Math.max(0, km - includedKm) / 10 * overMil;
      const covered = ['service', 'insurance', 'tyres'].reduce((value, key) => value + (leaseQuote[key] ? operating[key] : 0), 0);
      result.lease = compareRow(start + monthly * term + excess + operatingTotal - covered, km, duration,
        { start, monthly, excess, includedKm, covered });
      const increase = number(leaseQuote.monthlyIncrease || 0), wear = number(leaseQuote.wear || 0);
      if ([increase, wear].every(value => within(value, 0, 100000))) {
        result.leaseSensitivity = increase * term + wear;
      }
    }
  }
  return result;
}
