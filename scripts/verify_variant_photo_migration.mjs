import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile, realpath } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { catalogHash } from './sync_public_catalog.mjs';

const view = 'public.public_ev_variants';
const variants = 'public.canonical_model_variants';
const digest = value => createHash('sha256').update(value).digest('hex');
const migrationFile = new URL('../database/migrations/025_variant_photo_override.sql', import.meta.url);
const roles = ['anon', 'authenticated'];

async function contract(client) {
  const { rows: [flags] } = await client.query(`SELECT
    (SELECT relrowsecurity FROM pg_class WHERE oid=$2::regclass) AS protected_rows,
    (SELECT r.rolsuper OR r.rolbypassrls FROM pg_class c JOIN pg_roles r ON c.relowner=r.oid
     WHERE c.oid=$1::regclass) AS owner_can_read,
    (SELECT coalesce(reloptions,ARRAY[]::text[]) FROM pg_class WHERE oid=$1::regclass) AS view_options,
    (SELECT obj_description(oid,'pg_class') FROM pg_class WHERE oid=$1::regclass) AS view_comment,
    pg_get_viewdef($1::regclass,true) AS definition,
    (SELECT count(*)::integer FROM pg_attribute WHERE attrelid=$2::regclass AND attnum>0 AND NOT attisdropped
      AND attname IN ('variant_image_url','variant_image_source_url')) AS override_columns,
    (SELECT convalidated FROM pg_constraint WHERE conrelid=$2::regclass AND conname='canonical_variant_photo_complete') AS constraint_validated,
    (SELECT tgenabled IN ('O','A') FROM pg_trigger WHERE tgrelid=$2::regclass AND NOT tgisinternal
      AND tgname='invalidate_variant_photo_on_identity_change') AS trigger_enabled,
    to_regprocedure('public.invalidate_variant_photo_on_identity_change()') IS NOT NULL AS trigger_function_present`, [view, variants]);
  const { rows: columns } = await client.query(`SELECT attname AS name,format_type(atttypid,atttypmod) AS type
    FROM pg_attribute WHERE attrelid=$1::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum`, [view]);
  const { rows: access } = await client.query(`SELECT role,
    has_table_privilege(role,$1::regclass,'SELECT') AS view_select,
    has_table_privilege(role,$1::regclass,'INSERT,UPDATE,DELETE') AS view_write,
    has_any_column_privilege(role,$2::regclass,'SELECT') AS direct_select,
    has_any_column_privilege(role,$2::regclass,'INSERT,UPDATE') OR has_table_privilege(role,$2::regclass,'DELETE') AS direct_write
    FROM unnest($3::text[]) role ORDER BY role`, [view, variants, roles]);
  const { rows: grants } = await client.query(`SELECT acl.grantor,acl.grantee,acl.privilege_type,acl.is_grantable
    FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) acl
    WHERE c.oid=$1::regclass ORDER BY acl.grantor,acl.grantee,acl.privilege_type,acl.is_grantable`, [view]);
  return { ...flags, columns, access, grants };
}

function assertBoundary(state) {
  assert.equal(state.protected_rows, true, 'Canonical variants must keep RLS');
  assert.equal(state.owner_can_read, true, 'Expected the owner-privileged compatibility view');
  assert(state.view_options.includes('security_barrier=true') && !state.view_options.includes('security_invoker=true'));
  for (const name of ['id', 'image_url', 'image_source_url', 'price_source_url']) {
    assert(state.columns.some(column => column.name === name), 'Missing required public column: ' + name);
  }
  for (const row of state.access) assert.deepEqual(row, {
    role: row.role, view_select: true, view_write: false, direct_select: false, direct_write: false,
  }, 'Unexpected catalog grant for ' + row.role);
  assert.equal(state.access.length, roles.length);
}

function assertMigrationState(state, installed) {
  if (!installed) {
    assert.equal(state.override_columns, 0, 'Unexpected existing variant image columns; review before applying 025');
    assert(state.constraint_validated === null && state.trigger_enabled === null && !state.trigger_function_present,
      'Unexpected existing migration objects; review before applying 025');
    assert(!state.definition.includes('variant_photo.'), 'Unexpected existing variant-photo view');
    return;
  }
  assert.equal(state.override_columns, 2, 'Both variant image columns must exist');
  assert(state.constraint_validated && state.trigger_enabled && state.trigger_function_present, 'Incomplete variant-photo safeguards');
  for (const field of ['image_url','image_source_url']) {
    assert(state.definition.toLowerCase().includes('coalesce(variant_photo.variant_' + field + ', base.' + field + ')'),
      'Missing variant-photo projection: ' + field);
  }
}

export async function assertVariantPhotoInstalled(client) {
  const state = await contract(client);
  assertBoundary(state);
  assertMigrationState(state, true);
}

export async function hasVariantPhotoMigration(client) {
  const state = await contract(client);
  assertBoundary(state);
  const installed = state.override_columns !== 0;
  assertMigrationState(state, installed);
  return installed;
}

async function readOnlyProduction(installed) {
  const root = await realpath('.');
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(root));
  const connector = join(root, 'data', 'local', 'db-tools', 'source-client.mjs');
  assert.equal(await realpath(connector), connector);
  const { openSourceSnapshot, closeSourceSnapshot } = await import(pathToFileURL(connector).href);
  const commit = execFileSync('git', ['rev-parse', 'refs/remotes/origin/main'], {encoding: 'utf8'}).trim();
  const remote = execFileSync('git', ['ls-remote', 'origin', 'refs/heads/main'], {encoding: 'utf8', timeout: 20000}).trim();
  assert.equal(remote, commit + '\trefs/heads/main', 'Refresh the main reference first');
  const { records: baseline } = JSON.parse(execFileSync('git', ['show', commit + ':public/data/public_ev_variants.json'],
    {encoding: 'utf8', maxBuffer: 5000000}));
  const base = await openSourceSnapshot();
  try {
    assert.equal((await base.query('SHOW transaction_read_only')).rows[0].transaction_read_only, 'on');
    const state = await contract(base);
    assertBoundary(state);
    assertMigrationState(state, installed);
    await base.query('SET LOCAL ROLE anon');
    const { rows } = await base.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id');
    assert.equal(catalogHash(rows.map(entry => entry.row)), catalogHash(baseline), 'Canonical anonymous catalog changed since main');
    await base.query('RESET ROLE');
    console.log(JSON.stringify({ status: installed ? 'installed_and_catalog_unchanged' : 'ready_for_review',
      mode: 'production_read_only', base_commit: commit,
      current_public_rows: rows.length, current_catalog_sha256: catalogHash(baseline),
      public_view_sha256: digest(state.definition), public_columns_preserved_target: state.columns.length,
      migration_sha256: digest(await readFile(migrationFile)), production_writes: 0 }));
  } finally {
    await closeSourceSnapshot(base);
  }
}

async function localFixture() {
  const { PGlite } = await import('@electric-sql/pglite');
  const db = new PGlite();
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
    GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;
    CREATE TABLE canonical_models(id integer PRIMARY KEY, image_url text, image_source_url text);
    CREATE TABLE canonical_model_variants(id integer PRIMARY KEY, canonical_model_id integer NOT NULL REFERENCES canonical_models(id),
      variant_name text NOT NULL, price_source_url text, price_sek integer, validation_status text NOT NULL);
    ALTER TABLE canonical_model_variants ENABLE ROW LEVEL SECURITY;
    CREATE POLICY deny_public_read ON canonical_model_variants FOR SELECT TO anon,authenticated USING (false);
    CREATE VIEW public_ev_variants WITH (security_barrier=true) AS
      SELECT v.id,v.canonical_model_id,v.variant_name,v.price_source_url,v.price_sek,m.image_url,m.image_source_url
      FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id
      WHERE v.validation_status='published';
    REVOKE ALL ON canonical_model_variants FROM PUBLIC,anon,authenticated;
    GRANT SELECT ON public_ev_variants TO anon,authenticated;
    GRANT SELECT ON public_ev_variants TO service_role WITH GRANT OPTION;
    COMMENT ON VIEW public_ev_variants IS 'Consumer catalogue';
    CREATE VIEW public_catalog_dependency AS SELECT id,price_sek FROM public_ev_variants;
    INSERT INTO canonical_models VALUES(1,'/media/vehicles/base.jpg','https://example.invalid/base'),(2,null,null);
    INSERT INTO canonical_model_variants VALUES
      (1,1,'Essential','https://example.invalid/base',550000,'published'),
      (2,1,'N Line','https://example.invalid/n-line',650000,'published'),
      (3,1,'Draft',null,null,'draft');`);
  return db;
}

async function localProof() {
  const sql = await readFile(migrationFile, 'utf8');
  const db = await localFixture();
  const readPublic = async client => (await client.query('SELECT * FROM public.public_ev_variants ORDER BY id')).rows;
  try {
    const original = await readPublic(db);
    const before = await contract(db);
    assertBoundary(before);
    assertMigrationState(before, false);
    assert.throws(() => assertMigrationState(before, true), /Both variant image columns/);
    await db.exec(sql);
    const after = await contract(db);
    assertBoundary(after);
    for (const key of ['view_options', 'view_comment', 'columns', 'access', 'grants']) {
      assert.deepEqual(after[key], before[key], 'Migration changed existing view contract: ' + key);
    }
    assertMigrationState(after, true);
    assert.throws(() => assertMigrationState(after, false), /Unexpected existing variant image columns/);
    assert.throws(() => assertMigrationState({...after, trigger_enabled: false}, true), /Incomplete variant-photo safeguards/);
    assert.deepEqual(await readPublic(db), original);
    await db.exec(sql);
    assert.deepEqual(await contract(db), after);
    assert.deepEqual(await readPublic(db), original);
    assert.equal((await db.query('SELECT * FROM public_catalog_dependency')).rows.length, 2);

    const photo = '/media/vehicles/hyundai-ioniq-5-n-line-123456789abc.jpg';
    const source = 'https://example.invalid/verified-exact-n-line';
    await assert.rejects(db.query('UPDATE canonical_model_variants SET variant_image_url=$1 WHERE id=2', [photo]), {code: '23514'});
    await assert.rejects(db.query('UPDATE canonical_model_variants SET variant_image_url=$1,variant_image_source_url=$2 WHERE id=2',
      [photo, 'http://example.invalid/not-https']), {code: '23514'});
    const setPhoto = () => db.query('UPDATE canonical_model_variants SET variant_image_url=$1,variant_image_source_url=$2 WHERE id=2',
      [photo, source]);
    await setPhoto();
    for (const role of roles) {
      await db.exec('SET ROLE ' + role);
      try {
        const [base, nLine] = await readPublic(db);
        assert.deepEqual(base, original[0]);
        assert.deepEqual(nLine, { ...original[1], image_url: photo, image_source_url: source });
        await assert.rejects(db.query('SELECT id FROM public.canonical_model_variants'), {code: '42501'});
        const {rows: [{allowed}]} = await db.query(`SELECT
          has_function_privilege(current_user,'public.invalidate_variant_photo_on_identity_change()','EXECUTE') AS allowed`);
        assert.equal(allowed, false);
      } finally {
        await db.exec('RESET ROLE');
      }
    }
    await db.exec('UPDATE canonical_model_variants SET variant_name=\'Different grade\' WHERE id=2');
    assert.equal((await readPublic(db))[1].image_url, original[1].image_url);
    await setPhoto();
    await db.exec('UPDATE canonical_model_variants SET canonical_model_id=2 WHERE id=2');
    assert.equal((await readPublic(db))[1].image_url, null);
  } finally {
    await db.close();
  }
  const conflicts = [
    ['ALTER TABLE public.canonical_model_variants DISABLE ROW LEVEL SECURITY', /private canonical/],
    ['GRANT SELECT (id) ON public.canonical_model_variants TO anon', /private canonical/],
    ['ALTER VIEW public.public_ev_variants SET (security_invoker=true)', /owner-privileged/],
    ['ALTER VIEW public.public_ev_variants RENAME COLUMN price_source_url TO old_price_url', /price contracts/],
  ];
  for (const [extra, reason] of conflicts) {
    const blocked = await localFixture();
    try {
      await blocked.exec(extra);
      const before = await contract(blocked);
      await assert.rejects(blocked.exec(sql), reason);
      await blocked.exec('ROLLBACK');
      assert.deepEqual(await contract(blocked), before, 'Rejected migration changed the fixture');
    } finally {
      await blocked.close();
    }
  }
  console.log(JSON.stringify({ status: 'passed_local_only', migration_sha256: digest(sql), idempotent: true,
    grants_and_view_columns_preserved: true, edition_projection: true, identity_invalidation: true,
    rejected_migration_cases: conflicts.length, production_writes: 0 }));
}

async function main() {
  const { values } = parseArgs({ options: { 'production-check': { type: 'boolean' }, 'verify-installed': { type: 'boolean' } } });
  assert(!values['verify-installed'] || values['production-check'], 'Installed check must explicitly be production read-only');
  if (values['production-check']) await readOnlyProduction(Boolean(values['verify-installed']));
  else await localProof();
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) main().catch(error => {
  console.error(JSON.stringify({ status: 'held', code: /^[A-Z0-9_]{1,32}$/.test(error.code ?? '') ? error.code : null,
    reason: error.code === 'ERR_ASSERTION' ? error.message.split('\n')[0] : 'Variant-photo verification failed',
    production_writes: 0 }));
  process.exitCode = 1;
});
