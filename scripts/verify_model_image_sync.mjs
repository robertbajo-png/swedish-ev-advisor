import assert from 'node:assert/strict';
import { PGlite } from '@electric-sql/pglite';
import { applyImagePlan, buildImagePlan, imagePlanHash } from './model_image_sync.mjs';

const db = new PGlite();
try {
  await db.exec(`CREATE TABLE canonical_models (id text primary key, brand text, model text, validation_status text,
    image_url text, image_source_url text, image_verified_at text, updated_at text, market_seen boolean);
    CREATE TABLE canonical_model_variants (id text primary key, price_sek int, source_hash text);
    INSERT INTO canonical_models VALUES ('one','Fixture','One','published','old',null,null,'old',true),
      ('private','Fixture','Private','draft',null,null,null,'old',false);
    INSERT INTO canonical_model_variants VALUES ('variant',400000,'original-proof');`);
  const models = (await db.query('select * from canonical_models order by id')).rows;
  const asset = { model_key: 'fixture|one', asset_url: '/media/vehicles/fixture-one-abcdef123456.jpg', status: 'documented',
    content_sha256: 'a'.repeat(64), source_url: 'https://commons.wikimedia.org/wiki/File:Fixture.jpg', reviewed_at: '2026-10-27' };
  const registry = { schema_version: 1, assets: [asset] };
  const plan = buildImagePlan(models, [models.find(row => row.id === 'one')], registry);
  const old = (await db.query('select * from canonical_models order by id')).rows;
  for (const bad of [{ ...registry, assets: [asset, asset] }, { ...registry, assets: [{ ...asset, model_key: 'other|model' }] },
    { ...registry, assets: [{ ...asset, status: 'candidate' }] }, { ...registry, assets: [{ ...asset, asset_url: 'https://evil.invalid/wrong.jpg' }] }]) {
    assert.throws(() => buildImagePlan(models, [models.find(row => row.id === 'one')], bad));
  }
  await assert.rejects(applyImagePlan(db, plan, '0'.repeat(64)));
  const stale = structuredClone(plan); stale[0].expected.market_seen = false;
  await assert.rejects(applyImagePlan(db, stale, imagePlanHash(stale)));
  assert.deepEqual((await db.query('select * from canonical_models order by id')).rows, old);
  const result = await applyImagePlan(db, plan, imagePlanHash(plan));
  assert.equal(result.models_updated, 1);
  assert.equal((await db.query("select price_sek from canonical_model_variants where id='variant'")).rows[0].price_sek, 400000);
  assert.deepEqual((await db.query("select * from canonical_models where id='private'")).rows[0], old.find(row => row.id === 'private'));
  assert.equal((await db.query("select image_url from canonical_models where id='one'")).rows[0].image_url, asset.asset_url);
  console.log(JSON.stringify({ image_sync: 'passed', scope_and_stale_guards: true, rollback: true, variant_preservation: true, real_database_writes: 0 }));
} finally { await db.close(); }
