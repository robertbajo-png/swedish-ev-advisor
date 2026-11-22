import assert from 'node:assert/strict';
import { catalogHash, compareCatalogs, variantKey } from './sync_public_catalog.mjs';

const prefix = 'hyundai|ioniq 5|';
export const isIoniq5 = row => variantKey(row).startsWith(prefix);
export const isIoniq5NLine = row => row.variant_name.endsWith(' N Line');

export function verifyIoniq5CatalogDelta(baseline, catalog, reviewed, assets) {
  assert(!baseline.some(isIoniq5), 'An existing Ioniq 5 requires separate review');
  assert.equal(reviewed.length, 7);
  assert(reviewed.every(isIoniq5));
  const nLine = reviewed.filter(isIoniq5NLine);
  assert.equal(nLine.length, 2);
  assert.equal(assets.length, 2);
  const [base, edition] = assets;
  assert.equal(base.model_key, 'hyundai|ioniq 5');
  assert.equal(edition.model_key, base.model_key);
  assert.notEqual(base.asset_url, edition.asset_url);
  assert.notEqual(base.source_url, edition.source_url);
  assert(!Object.hasOwn(base, 'variant_names'), 'Only the base photo may enter the model lookup');
  assert(Array.isArray(edition.variant_names), 'Require the exact N Line scope');
  assert.deepEqual(edition.variant_names.slice().sort(), nLine.map(row => row.variant_name).sort(), 'Require the exact N Line scope');
  const difference = compareCatalogs(baseline, catalog);
  assert.deepEqual(difference.local_only, [], 'Existing public rows disappeared');
  assert.deepEqual(difference.changed, [], 'Existing public rows changed');
  const added = reviewed.map(variantKey).sort();
  assert.deepEqual(difference.remote_only.slice().sort(), added, 'Only the seven reviewed Ioniq 5 variants are allowed');
  const rows = catalog.filter(isIoniq5);
  assert.equal(rows.length, 7);
  for (const row of rows) {
    const expected = isIoniq5NLine(row) ? edition : base;
    assert.equal(row.image_url, expected.asset_url, 'Wrong Ioniq 5 edition photo');
    assert.equal(row.image_source_url, expected.source_url, 'Wrong Ioniq 5 photo source');
  }
  assert.equal(catalogHash(rows), catalogHash(reviewed), 'Ioniq 5 fields differ from the reviewed anonymous projection');
  return { added, preserved: baseline.length, count: catalog.length };
}
