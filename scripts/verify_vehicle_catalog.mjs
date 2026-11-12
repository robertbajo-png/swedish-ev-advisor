import assert from 'node:assert/strict';
import { groupCatalogVariants } from '../src/vehicle-catalog.js';

const variants = [
  { id: 'lr', brand: 'Kia', canonicalModel: 'EV3', model: 'EV3 Long Range', price: 500000 },
  { id: 'base', brand: 'Kia', canonicalModel: 'EV3', model: 'EV3 FWD', price: 400000 },
  { id: 'other', brand: 'Other', canonicalModel: 'EV3', model: 'EV3', price: 450000 },
  { id: 'four', brand: 'Kia', canonicalModel: 'EV4', model: 'EV4 AWD', price: 550000 },
];
const before = structuredClone(variants);
const groups = groupCatalogVariants(variants);
assert.equal(groups.length, 3);
assert.deepEqual(groups[0].variants.map(row => row.id), ['lr', 'base'], 'Preserve matching/sort order');
assert.equal(groups[1].key, 'other|ev3', 'Never merge different manufacturers');
assert.equal(groups.flatMap(group => group.variants).length, variants.length, 'No variants are discarded');
assert.deepEqual(variants, before, 'Do not mutate ranking or verified records');
assert.equal(groupCatalogVariants(variants.filter(row => row.price < 450000))[0].variants.length, 1,
  'A model group must not reintroduce variants excluded by filters');
assert.deepEqual(groupCatalogVariants([]), []);
console.log(JSON.stringify({ model_first_catalog: 'passed', exact_variants_and_filter_order_preserved: true }));
