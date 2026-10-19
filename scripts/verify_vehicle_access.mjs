import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';

const root = new URL('../', import.meta.url);
const migration = await readFile(new URL('database/migrations/008_vehicle_access_boundary.sql', root), 'utf8');
const schema = await readFile(new URL('database/schema.sql', root), 'utf8');
const liveProof = await readFile(new URL('database/tests/vehicle_access.sql', root), 'utf8');
assert(schema.includes(migration.trim()), 'Fresh installs must use the same security boundary');
const tables = ['canonical_models', 'canonical_model_variants', 'extracted_variant_drafts', 'manufacturer_sources', 'market_models', 'market_model_monthly_stats', 'model_aliases'];
const views = ['public_ev_models', 'public_ev_variants'];
const privileges = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'];
const db = new PGlite();
let denied = 0;
const asRole = async (role, callback) => {
  await db.exec(`set role ${role}`);
  try { return await callback(); } finally { await db.exec('reset role'); }
};
const deniedQuery = async (sql, accepted = ['42501']) => {
  try { await db.query(sql); }
  catch (error) { assert(accepted.includes(error.code), `Unexpected denial: ${error.code}`); denied++; return; }
  assert.fail(`Operation was not denied: ${sql}`);
};
const fingerprint = async () => JSON.stringify(await Promise.all(tables.map(async (table) => (
  await db.query(`select coalesce(jsonb_agg(to_jsonb(t) order by id), '[]'::jsonb) as rows from public.${table} t`)
).rows[0].rows)));

try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    grant usage on schema public to anon, authenticated, service_role;`);
  // PGlite has core gen_random_uuid(); the production pgcrypto extension is not needed here.
  await db.exec(schema.split('-- Keep the fresh-install access boundary identical to migration 008.')[0]
    .replace('create extension if not exists pgcrypto;', ''));
  await db.exec(`
    insert into canonical_models(id, brand, model, normalized_brand, normalized_model, validation_status) values
      ('00000000-0000-4000-8000-000000000001','Kia','EV3','kia','ev3','validated'),
      ('00000000-0000-4000-8000-000000000002','Rejected','Hidden','rejected','hidden','rejected');
    insert into manufacturer_sources(id, canonical_model_id, brand, model, source_type, url, content_hash) values
      ('00000000-0000-4000-8000-000000000003','00000000-0000-4000-8000-000000000001','Kia','EV3','manufacturer_model_page','https://www.kia.com/se/nya-bilar/ev3/','fixture-hash');
    insert into canonical_model_variants(canonical_model_id, variant_name, price_sek, wltp_range_km, source_url, source_hash, validation_status) values
      ('00000000-0000-4000-8000-000000000001','Published',428900,605,'https://www.kia.com/se/nya-bilar/ev3/','fixture-hash','published'),
      ('00000000-0000-4000-8000-000000000001','Reviewed',450000,600,'https://www.kia.com/se/nya-bilar/ev3/','fixture-hash','published_reviewed'),
      ('00000000-0000-4000-8000-000000000001','Private draft',null,null,'https://www.kia.com/se/nya-bilar/ev3/','fixture-hash','draft'),
      ('00000000-0000-4000-8000-000000000002','Rejected model',400000,500,'https://www.kia.com/se/nya-bilar/ev3/','fixture-hash','published');
    insert into extracted_variant_drafts(canonical_model_id, brand, model, variant_name, source_url, source_hash, extraction_confidence)
      values ('00000000-0000-4000-8000-000000000001','Kia','EV3','Private extraction','https://www.kia.com/se/nya-bilar/ev3/','fixture-hash',0.6);
    insert into market_models(id, brand_raw, model_raw, fuel_type_raw, normalized_brand, normalized_model)
      values ('00000000-0000-4000-8000-000000000004','KIA','EV3','El','kia','ev3');
    insert into market_model_monthly_stats(market_model_id, month, brand_raw, model_raw, fuel_type_raw)
      values ('00000000-0000-4000-8000-000000000004','2026-03-01','KIA','EV3','El');
    insert into model_aliases(canonical_model_id, brand_raw, model_raw, normalized_brand, normalized_model)
      values ('00000000-0000-4000-8000-000000000001','KIA','EV3','kia','ev3');
  `);
  // Reproduce legacy broad grants, including column grants that table REVOKE does not remove.
  for (const table of [...tables, ...views]) {
    await db.exec(`grant all on public.${table} to public, anon, authenticated, service_role;
      grant select(id), update(id) on public.${table} to public, anon, authenticated;`);
  }
  await db.exec('alter default privileges for role postgres in schema public grant all on tables to public, anon, authenticated;');
  await asRole('anon', async () => assert((await db.query('select id from extracted_variant_drafts')).rows.length > 0));
  const before = await fingerprint();
  await db.exec(migration);
  await db.exec(migration);
  await db.exec(liveProof);
  assert.equal(await fingerprint(), before, 'Idempotent migration must not modify any vehicle records');

  for (const role of ['anon', 'authenticated']) {
    for (const table of tables) {
      for (const privilege of privileges) {
        assert.equal((await db.query('select has_table_privilege($1,$2,$3) as allowed', [role, `public.${table}`, privilege])).rows[0].allowed, false);
      }
    }
    await asRole(role, async () => {
      for (const table of tables) {
        await deniedQuery(`select id from public.${table}`);
        await deniedQuery(`insert into public.${table} select * from public.${table} where false`);
        await deniedQuery(`update public.${table} set id=id where false`);
        await deniedQuery(`delete from public.${table} where false`);
        await deniedQuery(`truncate public.${table}`);
      }
      const variants = (await db.query('select variant_name from public.public_ev_variants order by variant_name')).rows;
      assert.deepEqual(variants.map((r) => r.variant_name), ['Published', 'Reviewed']);
      assert.equal((await db.query('select count(*)::int as n from public.public_ev_models')).rows[0].n, 1);
      for (const view of views) {
        for (const privilege of privileges.filter((p) => p !== 'SELECT')) {
          assert.equal((await db.query('select has_table_privilege(current_user,$1,$2) as allowed', [`public.${view}`, privilege])).rows[0].allowed, false);
        }
        await deniedQuery(`update public.${view} set id=id where false`, ['42501', '55000', '0A000']);
        await deniedQuery(`delete from public.${view} where false`, ['42501', '55000', '0A000']);
        await deniedQuery(`insert into public.${view} select * from public.${view} where false`, ['42501', '55000', '0A000']);
      }
    });
  }
  for (const table of tables) {
    assert.equal((await db.query('select relrowsecurity from pg_class where oid=$1::regclass', [`public.${table}`])).rows[0].relrowsecurity, true);
  }
  await asRole('service_role', async () => {
    for (const table of tables) {
      assert((await db.query(`select id from public.${table}`)).rows.length > 0);
      await db.query(`insert into public.${table} select * from public.${table} where false`);
      await db.query(`update public.${table} set id=id where false`);
      await db.query(`delete from public.${table} where false`);
    }
    const { rows } = await db.query(`insert into public.extracted_variant_drafts(brand,model,variant_name,source_url,extraction_confidence)
      values ('Kia','EV3','Server ingestion test','https://www.kia.com/se/nya-bilar/ev3/',0.5) returning id`);
    await db.query('update public.extracted_variant_drafts set price_sek=450000 where id=$1', [rows[0].id]);
    assert.equal((await db.query('delete from public.extracted_variant_drafts where id=$1 returning id', [rows[0].id])).rows.length, 1);
  });
  assert.equal(await fingerprint(), before, 'Tests preserve their original fixture records');
  // Even an accidental future SELECT grant cannot expose rows without an RLS policy.
  await db.exec('grant select on public.extracted_variant_drafts to anon;');
  await asRole('anon', async () => assert.deepEqual((await db.query('select id from public.extracted_variant_drafts')).rows, []));
  await db.exec('revoke select on public.extracted_variant_drafts from anon; create table public.future_private_table(id int);');
  for (const role of ['anon', 'authenticated']) {
    await asRole(role, async () => await deniedQuery('select * from public.future_private_table'));
  }
  // An unexpected invoker view must fail atomically instead of weakening its security.
  await db.exec('alter view public.public_ev_models set (security_invoker=true);');
  await assert.rejects(() => db.exec(migration), /owner-privileged public view/);
  await db.exec('rollback;');
  assert.equal(await fingerprint(), before);
  assert((await db.query("select reloptions from pg_class where oid='public.public_ev_models'::regclass")).rows[0].reloptions.includes('security_invoker=true'));
  console.log(JSON.stringify({ vehicle_access_ok: true, engine: 'PostgreSQL/PGlite', private_tables: tables.length, read_only_public_views: views.length, denied_operations: denied, roles: ['anon', 'authenticated', 'service_role'], idempotent: true, column_grants_removed: true, ingestion_crud_preserved: true, data_unchanged: true, unexpected_configuration_rolls_back: true, remote_requests: 0 }));
} finally { await db.close(); }
