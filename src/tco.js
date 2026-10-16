export const DEFAULT_TCO_ASSUMPTIONS = Object.freeze({
  annualKm: 15000,
  years: 5,
  annualInterestPercent: 5.5,
  residualPercent: 45,
  homeChargingPercent: 80,
  homeElectricitySekKwh: 2,
  publicElectricitySekKwh: 6,
  assumedConsumptionKwh100Km: 20,
  insuranceSekMonth: 900,
  serviceSekYear: 4000,
  taxSekYear: 360,
});

function finiteNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function normalizeTcoAssumptions(input = {}) {
  return {
    annualKm: clamp(finiteNumber(input.annualKm, DEFAULT_TCO_ASSUMPTIONS.annualKm), 1000, 60000),
    years: clamp(finiteNumber(input.years, DEFAULT_TCO_ASSUMPTIONS.years), 1, 10),
    annualInterestPercent: clamp(finiteNumber(input.annualInterestPercent, DEFAULT_TCO_ASSUMPTIONS.annualInterestPercent), 0, 20),
    residualPercent: clamp(finiteNumber(input.residualPercent, DEFAULT_TCO_ASSUMPTIONS.residualPercent), 0, 90),
    homeChargingPercent: clamp(finiteNumber(input.homeChargingPercent, DEFAULT_TCO_ASSUMPTIONS.homeChargingPercent), 0, 100),
    homeElectricitySekKwh: clamp(finiteNumber(input.homeElectricitySekKwh, DEFAULT_TCO_ASSUMPTIONS.homeElectricitySekKwh), 0, 20),
    publicElectricitySekKwh: clamp(finiteNumber(input.publicElectricitySekKwh, DEFAULT_TCO_ASSUMPTIONS.publicElectricitySekKwh), 0, 20),
    assumedConsumptionKwh100Km: clamp(finiteNumber(input.assumedConsumptionKwh100Km, DEFAULT_TCO_ASSUMPTIONS.assumedConsumptionKwh100Km), 5, 50),
    insuranceSekMonth: clamp(finiteNumber(input.insuranceSekMonth, DEFAULT_TCO_ASSUMPTIONS.insuranceSekMonth), 0, 10000),
    serviceSekYear: clamp(finiteNumber(input.serviceSekYear, DEFAULT_TCO_ASSUMPTIONS.serviceSekYear), 0, 50000),
    taxSekYear: clamp(finiteNumber(input.taxSekYear, DEFAULT_TCO_ASSUMPTIONS.taxSekYear), 0, 20000),
  };
}

export function calculateTco(car, rawAssumptions = {}) {
  const assumptions = normalizeTcoAssumptions(rawAssumptions);
  const price = finiteNumber(car?.price, 0);
  if (price <= 0) {
    return {
      calculable: false,
      reason: 'missing_price',
      carId: car?.id || null,
      monthlySek: null,
      totalSek: null,
      components: null,
      assumptions,
    };
  }

  const verifiedConsumption = finiteNumber(car?.consumptionVerified, 0);
  const consumptionKwh100Km = verifiedConsumption > 0
    ? verifiedConsumption
    : assumptions.assumedConsumptionKwh100Km;
  const consumptionSource = verifiedConsumption > 0 ? 'verified' : 'assumption';
  const months = assumptions.years * 12;
  const homeShare = assumptions.homeChargingPercent / 100;
  const weightedElectricityPrice =
    assumptions.homeElectricitySekKwh * homeShare +
    assumptions.publicElectricitySekKwh * (1 - homeShare);

  const depreciationSek = price * (1 - assumptions.residualPercent / 100);
  const averageFinancedBalance = price * 0.8 * 0.55;
  const financingSek = averageFinancedBalance * (assumptions.annualInterestPercent / 100) * assumptions.years;
  const electricitySek =
    assumptions.annualKm * assumptions.years * (consumptionKwh100Km / 100) * weightedElectricityPrice;
  const insuranceSek = assumptions.insuranceSekMonth * months;
  const serviceSek = assumptions.serviceSekYear * assumptions.years;
  const taxSek = assumptions.taxSekYear * assumptions.years;

  const components = {
    depreciationSek: Math.round(depreciationSek),
    financingSek: Math.round(financingSek),
    electricitySek: Math.round(electricitySek),
    insuranceSek: Math.round(insuranceSek),
    serviceSek: Math.round(serviceSek),
    taxSek: Math.round(taxSek),
  };
  const totalSek = Object.values(components).reduce((sum, value) => sum + value, 0);

  return {
    calculable: true,
    carId: car.id,
    priceSek: price,
    monthlySek: totalSek / months,
    totalSek,
    costPerKmSek: totalSek / (assumptions.annualKm * assumptions.years),
    residualValueSek: price * (assumptions.residualPercent / 100),
    weightedElectricityPrice,
    consumptionKwh100Km,
    consumptionSource,
    components,
    assumptions,
  };
}
