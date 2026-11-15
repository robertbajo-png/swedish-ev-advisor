import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ev2VersionGuide} from '../src/ev2-version-guide.js';
import {estimateWinterTripStops, winterTripExample} from '../src/winter-trip.js';
import {priceEvidence} from '../src/price-evidence.js';
import {specQualifications} from '../src/spec-qualifications.js';

const records = JSON.parse(readFileSync(new URL('../public/data/public_ev_variants.json', import.meta.url))).records;
const cars = records.filter(row => row.brand === 'Kia' && row.model === 'Ev2').map(row => ({
  id: row.variant_name, brand: row.brand, canonicalModel: row.model, variantName: row.variant_name,
  seatsVerified: row.seats, validationStatus: row.validation_status, price: row.price_sek,
  priceType: row.price_type, priceSource: priceEvidence(row)?.price_source_url, priceVerifiedAt: priceEvidence(row)?.price_verified_at,
  source: row.source_url, rangeVerified: row.wltp_range_km, batteryVerified: row.battery_kwh, ...specQualifications(row),
}));
assert.equal(cars.length, 3);
const guide = ev2VersionGuide(cars[2], [...cars].reverse());
assert.deepEqual(guide.map(x => [x.name, x.priceDifference, x.rangeDifference, x.batteryDifference]), [
  ['Standard Range', null, null, null], ['Long Range', 49100, 136, 18.8], ['GT Line Long Range', 78900, -40, 0],
]);
assert.equal(ev2VersionGuide(cars[0], cars.slice(0, 2)).length, 0, 'Do not compare a partial trim set');
assert.equal(ev2VersionGuide(cars[0], [...cars, cars[0]]).length, 0, 'Do not guess among duplicate trim records');
for (const changed of [{priceType:'campaign_price'}, {priceVerifiedAt:null}, {rangeIsTarget:true}, {rangeInterval:'350–400 km'}, {seatsVerified:4}, {validationStatus:'draft'}]) {
  assert.equal(ev2VersionGuide(cars[0], [{...cars[0], ...changed}, ...cars.slice(1)]).length, 0);
}
assert.equal(ev2VersionGuide({...cars[0], canonicalModel:'Ev3'}, cars).length, 0);
assert.deepEqual(guide.map(x => winterTripExample.comparisonFactors.map(factor => estimateWinterTripStops(x.car.rangeVerified, factor))), [[2,2],[1,1],[2,1]]);
assert.equal(estimateWinterTripStops(500,.8,{...winterTripExample,distanceKm:360}), 0);
assert.equal(estimateWinterTripStops(500,.8,{...winterTripExample,distanceKm:640}), 1);
assert.equal(estimateWinterTripStops(500,.8,{...winterTripExample,distanceKm:641}), 2);
for (const row of [[NaN,.8], [500,0], [500,1.01], [500,.8,{...winterTripExample,chargeToFraction:.1}], [Infinity,.8]]) {
  assert.equal(estimateWinterTripStops(...row), null);
}
console.log('Kia EV2 source-bound upgrade deltas and winter example: passed.');
