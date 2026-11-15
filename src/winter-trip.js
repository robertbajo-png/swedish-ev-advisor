export const winterTripExample = Object.freeze({
  distanceKm: 400,
  startFraction: 1,
  reserveFraction: 0.1,
  chargeToFraction: 0.8,
  comparisonFactors: Object.freeze([0.60, 0.75]),
});

export function estimateWinterTripStops(wltpRangeKm, rangeFactor, scenario = winterTripExample) {
  const { distanceKm, startFraction, reserveFraction, chargeToFraction } = scenario;
  if (![wltpRangeKm, rangeFactor, distanceKm, startFraction, reserveFraction, chargeToFraction].every(Number.isFinite)
    || wltpRangeKm <= 0 || rangeFactor <= 0 || rangeFactor > 1 || distanceKm <= 0
    || reserveFraction < 0 || startFraction <= reserveFraction || startFraction > 1
    || chargeToFraction <= reserveFraction || chargeToFraction > 1) return null;
  const fullRange = wltpRangeKm * rangeFactor;
  const firstLeg = fullRange * (startFraction - reserveFraction);
  const onwards = fullRange * (chargeToFraction - reserveFraction);
  if (!Number.isFinite(firstLeg) || !Number.isFinite(onwards) || onwards <= 0) return null;
  const stops = Math.max(0, Math.ceil((distanceKm - firstLeg) / onwards - 1e-10));
  return Number.isSafeInteger(stops) ? stops : null;
}
