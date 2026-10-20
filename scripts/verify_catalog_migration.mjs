import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';

const root = new URL('../', import.meta.url);
const migration = await readFile(new URL('database/migrations/009_public_catalog_contract.sql', root), 'utf8');
const boundary = await readFile(new URL('database/migrations/008_vehicle_access_boundary.sql', root), 'utf8');
const legacy = await readFile(new URL('database/migrations/001_ev_database.sql', root), 'utf8');
const schema = await readFile(new URL('database/schema.sql', root), 'utf8');
for (const [name, source] of [['legacy', legacy], ['current', schema.split('-- Keep the fresh-install access boundary identical to migration 008.')[0]]]) {
  const db = new PGlite();
  try {
    await db.exec('create role anon; create role authenticated; create role service_role bypassrls; grant usage on schema public to anon, authenticated, service_role');
    await db.exec(source.replace('create extension if not exists pgcrypto;', ''));
    await db.exec("alter type validation_status add value if not exists 'published_reviewed'");
    // Legacy deployments already received these traceability fields before hardening.
    await db.exec(`alter table canonical_model_variants add column if not exists source_url text,
      add column if not exists source_hash text, add column if not exists review_approved_by text,
      add column if not exists review_reason text, add column if not exists review_promoted_at timestamptz;
      insert into canonical_models(id,brand,model,normalized_brand,normalized_model) values
      ('00000000-0000-4000-8000-000000000001','Kia','EV3','kia','ev3');
      insert into canonical_model_variants(canonical_model_id,variant_name,price_sek,wltp_range_km,validation_status)
      values ('00000000-0000-4000-8000-000000000001','Base',400000,500,'published');`);
    await db.exec(boundary);
    const before = (await db.query('select variant_name,price_sek,wltp_range_km,updated_at from canonical_model_variants')).rows;
    const aclBefore = (await db.query("select relacl::text from pg_class where oid='public_ev_variants'::regclass")).rows;
    await db.exec('create view dependent_catalog as select id from public_ev_variants');
    await db.exec(migration);
    await db.exec(migration);
    assert.deepEqual((await db.query('select variant_name,price_sek,wltp_range_km,updated_at from canonical_model_variants')).rows, before);
    assert.deepEqual((await db.query("select relacl::text from pg_class where oid='public_ev_variants'::regclass")).rows, aclBefore);
    assert.equal((await db.query('select count(*)::int as n from dependent_catalog')).rows[0].n, 1);
    const row = (await db.query('select * from public_ev_variants')).rows[0];
    for (const field of ['price_type','price_valid_until','wltp_consumption_kwh_100km','image_url','verified_at']) assert.equal(row[field], null);
    assert.equal(row.source_name, 'Kia');
    for (const role of ['anon','authenticated']) {
      await db.exec(`set role ${role}`);
      assert.equal((await db.query('select count(*)::int as n from public_ev_variants')).rows[0].n, 1);
      await assert.rejects(db.query('select * from canonical_model_variants'), (e) => e.code === '42501');
      await assert.rejects(db.query('update public_ev_variants set price_sek=1'), (e) => ['42501','55000'].includes(e.code));
      await db.exec('reset role');
    }
    console.log(JSON.stringify({ catalog_migration_ok: true, configuration: name, idempotent: true, acl_unchanged: true, facts_unchanged: true, dependencies_preserved: true }));
  } finally { await db.close(); }
}
