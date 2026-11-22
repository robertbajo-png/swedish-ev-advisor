import assert from 'node:assert/strict';
import { test } from 'node:test';
import { PGlite } from '@electric-sql/pglite';
import { planPumaIdentity, pumaIdentitySnapshot, readPumaIdentity,
  stagePumaIdentityLocally } from '../scripts/ford_puma_identity.mjs';
import { anonymousCatalogRows, seedCatalogFixture } from '../scripts/isolated_catalog_review.mjs';

test('stages only the electric Puma in PostgreSQL and preserves all three fuel histories', async () => {
  const db = new PGlite();
  try {
    await seedCatalogFixture(db, {models: [], sources: [], variants: [], legacy: {}}, []);
    const {rows: [puma]} = await db.query("INSERT INTO public.canonical_models(brand,model,normalized_brand,normalized_model) VALUES ('Ford','Puma','ford','puma') RETURNING id");
    await db.query("INSERT INTO public.model_aliases(canonical_model_id,brand_raw,model_raw,normalized_brand,normalized_model,alias_rule) VALUES ($1,'FORD','PUMA','ford','puma','mobility_sweden_exact_raw_name')", [puma.id]);
    const ids = {};
    for (const [fuel, parent] of [['EL', null], ['BENSIN', puma.id], ['ELHYBRID', null]]) {
      const {rows: [model]} = await db.query('INSERT INTO public.market_models ' +
        '(brand_raw,model_raw,fuel_type_raw,normalized_brand,normalized_model,canonical_model_id,first_seen_month,last_seen_month) ' +
        "VALUES ('FORD','PUMA',$1,'ford','puma',$2,'2026-03-01','2026-03-01') RETURNING id", [fuel, parent]);
      ids[fuel] = model.id;
      await db.query('INSERT INTO public.market_model_monthly_stats(market_model_id,month,brand_raw,model_raw,fuel_type_raw,registrations) ' +
        "VALUES ($1,'2026-03-01','FORD','PUMA',$2,10)", [model.id, fuel]);
    }
    const before = await pumaIdentitySnapshot(db);
    await assert.rejects(readPumaIdentity(db), /read-only/);
    await db.exec('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
    const reviewed = await readPumaIdentity(db);
    await db.exec('ROLLBACK');
    assert.deepEqual([reviewed.bev_historical_rows, reviewed.preserved_non_bev_rows], [1, 2]);
    for (const [mutate, error] of [
      [data => { data.market.find(r => r.id === ids.EL).canonical_model_id = puma.id; }, /Exact unlinked/],
      [data => { data.market.find(r => r.id === ids.EL).model_raw = 'PUMA/OTHER'; }, /Exact unlinked/],
      [data => { data.months.find(r => r.market_model_id === ids.EL).fuel_type_raw = 'BENSIN'; }, /Mixed Puma/],
      [data => { data.aliases[0].needs_mapping = true; }, /alias changed/],
      [data => { data.models.push({...data.models[0], normalized_model: 'puma gen e'}); }, /before staging/],
    ]) {
      const unexpected = structuredClone(before);
      mutate(unexpected);
      assert.throws(() => planPumaIdentity(unexpected), error);
    }
    await assert.rejects(stagePumaIdentityLocally(db, {...reviewed, market_id: ids.BENSIN}), /changed since review/);
    assert.deepEqual(await pumaIdentitySnapshot(db), before);
    const result = await stagePumaIdentityLocally(db, reviewed);
    assert.equal(result.market_id, ids.EL);
    const after = await pumaIdentitySnapshot(db);
    assert.deepEqual(after.months, before.months);
    assert.deepEqual(after.market.filter(r => r.id !== ids.EL), before.market.filter(r => r.id !== ids.EL));
    assert.deepEqual(after.models.find(r => r.id === puma.id), before.models[0]);
    assert.deepEqual(after.aliases.find(r => r.canonical_model_id === puma.id), before.aliases[0]);
    assert.equal(after.market.find(r => r.id === ids.EL).canonical_model_id, result.model_id);
    assert.deepEqual(await anonymousCatalogRows(db), [], 'Discovery staging must not publish a vehicle');
    await assert.rejects(stagePumaIdentityLocally(db, reviewed), /before staging/);
    assert.deepEqual(await pumaIdentitySnapshot(db), after);
  } finally { await db.close(); }
});
