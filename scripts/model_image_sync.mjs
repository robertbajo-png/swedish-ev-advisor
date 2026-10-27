import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const key = row => [row.brand, row.model].map(value => String(value).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()).join('|');
export const imagePlanHash = plan => createHash('sha256').update(JSON.stringify(plan)).digest('hex');
const retained = row => Object.fromEntries(Object.entries(row).filter(([name]) => !['image_url', 'image_source_url', 'image_verified_at', 'updated_at'].includes(name)));

export function buildImagePlan(models, publicModels, registry) {
  assert.equal(registry.schema_version, 1);
  const scope = new Set(publicModels.map(key));
  assert.equal(registry.assets.length, scope.size, 'One reviewed image per public model');
  const seen = new Set();
  const plan = registry.assets.map(asset => {
    assert(scope.has(asset.model_key) && !seen.has(asset.model_key), 'Unexpected/duplicate model');
    seen.add(asset.model_key);
    assert.equal(asset.status, 'documented');
    assert.match(asset.asset_url, /^\/media\/vehicles\/[a-z0-9-]+-[a-f0-9]{12}\.jpg$/);
    assert.match(asset.content_sha256, /^[a-f0-9]{64}$/);
    assert.match(asset.source_url, /^https:\/\/commons\.wikimedia\.org\/wiki\/File:/);
    const matches = models.filter(model => key(model) === asset.model_key);
    assert.equal(matches.length, 1, 'Exact canonical model required');
    const model = matches[0];
    // Parent records can remain drafts: the public variant view is the publication boundary.
    assert.notEqual(model.validation_status, 'rejected');
    return { id: model.id, model_key: asset.model_key, expected: model,
      image_url: asset.asset_url, image_source_url: asset.source_url, content_sha256: asset.content_sha256,
      reviewed_at: asset.reviewed_at };
  }).sort((a, b) => a.id.localeCompare(b.id));
  assert.equal(seen.size, scope.size);
  return plan;
}

// The caller supplies its existing authenticated TLS client. No new role or RPC is created.
export async function applyImagePlan(client, plan, expectedHash) {
  assert.equal(imagePlanHash(plan), expectedHash, 'Reviewed image plan changed');
  assert(plan.length > 0);
  let committed = false;
  await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE READ WRITE');
  try {
    await client.query("SET LOCAL search_path = pg_catalog");
    await client.query("SET LOCAL lock_timeout = '10s'");
    await client.query("SELECT pg_advisory_xact_lock(7240030)");
    const before = (await client.query('SELECT * FROM public.canonical_models ORDER BY id FOR UPDATE')).rows;
    const variants = (await client.query('SELECT * FROM public.canonical_model_variants ORDER BY id')).rows;
    const byId = new Map(before.map(row => [row.id, row]));
    for (const target of plan) {
      assert.deepEqual(byId.get(target.id), target.expected, 'Concurrent canonical model change');
      const result = await client.query(`UPDATE public.canonical_models
        SET image_url=$1, image_source_url=$2, image_verified_at=$3
        WHERE id=$4 RETURNING id`, [target.image_url, target.image_source_url, target.reviewed_at, target.id]);
      assert.equal(result.rows.length, 1);
    }
    const after = (await client.query('SELECT * FROM public.canonical_models ORDER BY id')).rows;
    const targets = new Map(plan.map(row => [row.id, row]));
    assert.equal(after.length, before.length);
    for (const row of after) {
      const target = targets.get(row.id);
      if (target) {
        assert.deepEqual(retained(row), retained(byId.get(row.id)), 'Non-image model field changed');
        assert.equal(row.image_url, target.image_url);
        assert.equal(row.image_source_url, target.image_source_url);
      } else assert.deepEqual(row, byId.get(row.id), 'Out-of-scope model changed');
    }
    assert.deepEqual((await client.query('SELECT * FROM public.canonical_model_variants ORDER BY id')).rows, variants, 'Variant data changed');
    await client.query('COMMIT');
    committed = true;
    return { committed: true, models_updated: plan.length, variants_changed: 0, news_changed: 0, paid_calls: 0, plan_sha256: expectedHash };
  } finally {
    if (!committed) await client.query('ROLLBACK');
  }
}
