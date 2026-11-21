import assert from 'node:assert/strict';
import { compareCatalogs, variantKey } from './sync_public_catalog.mjs';
import { ADAPTER, assertXpG6PublicVariants } from './xpeng_g6_publication.mjs';

// Validate the exact delta before an export may be used by a G6 release.
export function verifyXpG6CatalogDelta(baseline, rows, plan) {
  assert.equal(plan.adapter, ADAPTER);
  assert.equal(plan.intake.adapter, ADAPTER);
  const model = plan.intake.model;
  assert.deepEqual([model.brand, model.model, plan.image.model_key], ['Xpeng', 'G6', 'xpeng|g6']);
  assert.equal(plan.targets.length, 3);
  assert(!baseline.some(row => variantKey(row).startsWith('xpeng|g6|')), 'Existing public G6 needs separate review');
  const targets = new Set(plan.targets.map(({ draft }) => variantKey({ ...model, variant_name: draft.variant_name })));
  assert.equal(targets.size, 3);
  const difference = compareCatalogs(baseline, rows);
  assert.deepEqual(difference.local_only, [], 'Existing public rows disappeared');
  assert.deepEqual(difference.changed, [], 'Existing public rows changed');
  const added = [...targets].sort();
  assert.deepEqual(difference.remote_only.slice().sort(), added, 'Only the exact G6 additions are allowed');
  assertXpG6PublicVariants(rows.filter(row => targets.has(variantKey(row))), plan);
  return {added, preserved: baseline.length, count: rows.length};
}
