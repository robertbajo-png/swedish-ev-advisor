import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const pressPublishers = JSON.parse(readFileSync(new URL('../src/press-image-publishers.json', import.meta.url), 'utf8'));

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
    if (asset.license_id === 'Polestar-editorial') {
      assert(['polestar|2', 'polestar|4'].includes(asset.model_key));
      const match = /^https:\/\/media\.polestar\.com\/gallery\/images\/([0-9]+)$/.exec(asset.source_url);
      assert(match, 'Exact public pressroom photo required');
      assert.equal(asset.evidence_url, 'https://media.polestar.com/copyright');
      assert.equal(asset.license_url, asset.evidence_url);
      assert.equal(asset.usage_scope, 'independent_vehicle_editorial');
      assert.deepEqual(asset.prohibited_uses, ['advertising', 'commercial_promotion', 'endorsement']);
      assert.match(asset.metadata_sha256, /^[a-f0-9]{64}$/);
      assert(new RegExp('^https://media\\.polestar\\.com/assets/images/(?:original|small)/' + match[1] + '-[a-zA-Z0-9._-]+\\.jpe?g$').test(asset.downloaded_from));
    } else if (asset.license_id === 'Toyota-editorial') {
      assert.equal(asset.model_key, 'toyota|bz4x');
      const source = 'https://media.toyota.co.uk/images/bz4x-fwd-exterior-static-european-spec-2025/';
      for (const field of ['source_url','evidence_url','license_url']) assert.equal(asset[field], source);
      assert.equal(asset.downloaded_from, 'https://media.toyota.co.uk/wp-content/uploads/sites/5/2025/12/2026_bZ4X-FWD_Deep-Blue-Metallic_Static_001-scaled.jpg');
      assert.equal(asset.evidence_quote, 'Images are copyright free for editorial purposes only');
      assert.equal(asset.usage_scope, 'independent_vehicle_editorial'); assert.equal(asset.full_frame, true);
      assert.deepEqual(asset.prohibited_uses, ['advertising','commercial_promotion','endorsement']);
      for (const field of ['metadata_sha256','source_content_sha256']) assert.match(asset[field], /^[a-f0-9]{64}$/);
    } else if (asset.license_id === 'Manufacturer-media-use') {
      const policy = pressPublishers[asset.publisher_id];
      assert(policy?.model_keys.includes(asset.model_key), 'Registered exact press model required');
      const source = new URL(asset.source_url);
      assert.equal(source.origin, policy.origin);
      const prefix = policy.image_path_prefix || '/images/';
      assert(source.pathname.startsWith(prefix));
      assert.match(source.pathname.slice(prefix.length), /^[a-z0-9-]+-[0-9]+$/);
      assert(!policy.approved_image_paths || policy.approved_image_paths.includes(source.pathname), 'Reviewed exact-model photo required');
      assert(asset.model_key !== 'skoda|enyaq' || !source.pathname.includes('coup'), 'Enyaq SUV is not Enyaq Coupe');
      assert(!source.search && !source.hash);
      assert.equal(asset.evidence_url, asset.source_url);
      assert.equal(asset.license_url, asset.source_url);
      assert.equal(asset.evidence_quote, policy.permission_excerpt + ' | ' + policy.condition_excerpt);
      assert.equal(asset.usage_scope, 'independent_vehicle_editorial');
      assert.equal(asset.full_frame, true);
      for (const field of ['metadata_sha256', 'source_content_sha256']) assert.match(asset[field], /^[a-f0-9]{64}$/);
      const download = new URL(asset.downloaded_from);
      assert.equal(download.origin, policy.asset_origin);
      assert.match(download.pathname, /^\/image\/upload\/fl_attachment\/[a-zA-Z0-9_-]+$/);
      assert(!download.search && !download.hash);
    } else assert.match(asset.source_url, /^https:\/\/commons\.wikimedia\.org\/wiki\/File:/);
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
  return plan.filter(row => row.expected.image_url !== row.image_url || row.expected.image_source_url !== row.image_source_url);
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
