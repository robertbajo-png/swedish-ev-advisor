import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { PGlite } from '@electric-sql/pglite';
import { normalizePublicVariants } from '../functions/_shared/advisor-core.mjs';
import { applyExactDcMigration } from '../scripts/apply_exact_dc_migration.mjs';
import { anonymousCatalogRows, catalogWithComparableTimes, seedCatalogFixture } from '../scripts/isolated_catalog_review.mjs';
import { catalogHash } from '../scripts/sync_public_catalog.mjs';
import { assertDcChargePower, assertDcStorageForDrafts, assertExactDcInstalled } from '../scripts/verify_exact_dc_migration.mjs';

const migration = name => readFile(new URL('../database/migrations/' + name + '.sql', import.meta.url), 'utf8');
const exactDc = await migration('027_exact_dc_charging');
const MODEL = 'eb000000-0000-4000-8000-000000000000';
const hash = 'a'.repeat(64);
const source = 'https://www.hyundai.com/se/sv/bilar/inster/konfigurator.html';
const tables = ['canonical_model_variants', 'extracted_variant_drafts'];
const dcDraft = dc_charge_kw => ({facts:{dc_charge_kw}});

test('intake accepts exact fractional DC power without rounding or coercion', () => {
  for (const power of [20, 20.01, 85.3, 85.29, 600]) assert.doesNotThrow(() => assertDcChargePower(power));
  for (const power of [0, 19.99, 600.01, 85.301, Infinity, NaN, '85.3', null]) {
    assert.throws(() => assertDcChargePower(power), /at most two decimal places/);
  }
});
const privateState = async db => (await db.query(`
  select jsonb_build_array(
    (select jsonb_agg(to_jsonb(v) order by id) from canonical_model_variants v),
    (select jsonb_agg(to_jsonb(d) order by id) from extracted_variant_drafts d)
  ) as snapshot`)).rows[0].snapshot;
const access = async db => (await db.query(`
  select c.relname,c.relrowsecurity,c.relforcerowsecurity,c.relacl::text, c.reloptions,
    obj_description(c.oid,'pg_class') as comment,
    (select jsonb_agg(to_jsonb(p) order by policyname) from pg_policies p
     where p.schemaname='public' and p.tablename=c.relname) as policies
  from pg_class c where c.oid=any(array['public.canonical_model_variants'::regclass,
    'public.extracted_variant_drafts'::regclass,'public.public_ev_variants'::regclass])
  order by c.relname`)).rows.map(({relacl, ...rest}) => ({...rest, acl:relacl?.slice(1, -1).split(',').sort()}));

async function seed(db) {
  await seedCatalogFixture(db, {models:[], sources:[], variants:[], legacy:{nullable_authority:false}}, []);
  await db.query(`insert into canonical_models(id,brand,model,normalized_brand,normalized_model)
    values($1,'Hyundai','Inster','hyundai','inster')`, [MODEL]);
  await db.query(`insert into canonical_model_variants
    (canonical_model_id,variant_name,wltp_range_km,dc_charge_kw,ac_charge_kw,validation_status,
     source_url,source_hash,source_quote,extraction_confidence)
    values ($1,'Fixture verified value',370,100,10.5,'published',$2,$3,'Fixture only',0.97),
           ($1,'Fixture missing value',370,null,null,'published_reviewed',$2,$3,'Fixture only',0.97),
           ($1,'Fixture held row',370,85,null,'draft',$2,$3,'Fixture only',0.97)`, [MODEL,source,hash]);
  await db.query(`insert into extracted_variant_drafts
    (canonical_model_id,brand,model,variant_name,dc_charge_kw,source_url)
    values($1,'Hyundai','Inster','Fixture validated extraction',100,$2),
          ($1,'Hyundai','Inster','Fixture extraction without DC',null,$2)`,[MODEL,source]);
  await db.exec(`create policy direct_anonymous_draft_denied on extracted_variant_drafts
    for select to anon using (false);
    grant select on public_ev_variants to service_role with grant option;
    comment on view public_ev_variants is 'Existing published catalog metadata';`);
}

for (const mode of ['current catalog', 'catalog after pending image and entry-price migrations']) {
  test(`exact DC through database and public export: ${mode}`, async () => {
    const db = new PGlite();
    try {
      await seed(db);
      if (mode !== 'current catalog') {
        await db.exec(await migration('025_variant_photo_override'));
        await db.exec(await migration('026_manufacturer_from_price'));
      }
      const beforePrivate = await privateState(db);
      const beforePublic = await anonymousCatalogRows(db);
      const originalHash = catalogHash(catalogWithComparableTimes(beforePublic));
      const beforeAccess = await access(db);
      await assert.rejects(assertExactDcInstalled(db), /Migration 027 is required/);
      await assertDcStorageForDrafts(db, [dcDraft(100)]);
      await assert.rejects(assertDcStorageForDrafts(db, [dcDraft(100), dcDraft(85.3)]), /Migration 027 is required/);
      assert.deepEqual(await privateState(db), beforePrivate);
      const counts = [];
      for (let pass = 0; pass < 2; pass++) {
        await db.exec(exactDc);
        await assertExactDcInstalled(db);
        await assertDcStorageForDrafts(db, [dcDraft(100), dcDraft(85.3)]);
        assert.deepEqual(await privateState(db), beforePrivate);
        assert.deepEqual(await anonymousCatalogRows(db), beforePublic);
        assert.deepEqual(await access(db), beforeAccess);
        assert.equal(catalogHash(catalogWithComparableTimes(await anonymousCatalogRows(db))), originalHash);
        counts.push((await db.query(`
          select count(*)::int as n from information_schema.columns where table_schema='public'
          and table_name in ('canonical_model_variants','extracted_variant_drafts','public_ev_variants')
          and column_name='dc_charge_kw' and data_type='numeric' and numeric_scale is null`)).rows[0].n);
      }
      assert.deepEqual(counts,[3,3]);
      for (const table of tables) {
        for (const value of ['19.99','600.01','85.301','NaN','Infinity']) {
          await assert.rejects(db.query(`update ${table} set dc_charge_kw=$1 where dc_charge_kw=100`, [value]), {code:'23514'});
        }
        const result = await db.query(`update ${table} set dc_charge_kw=85.30 where dc_charge_kw=100
          returning dc_charge_kw::text as power`);
        assert.deepEqual(result.rows,[{power:'85.30'}]);
      }
      const rows = await anonymousCatalogRows(db);
      const exported = catalogWithComparableTimes(rows);
      assert.equal(rows.length,2);
      assert.deepEqual(exported.map(r=>r.dc_charge_kw).sort(),[85.3,null]);
      assert.equal(normalizePublicVariants(rows).find(r=>r.variant_name==='Fixture verified value').dc_charge_kw,85.3);
      await db.exec('set role authenticated');
      await assert.rejects(db.query('select dc_charge_kw from canonical_model_variants'), {code:'42501'});
      await assert.rejects(db.query('select dc_charge_kw from extracted_variant_drafts'), {code:'42501'});
      assert.equal((await db.query("select has_any_column_privilege('public_ev_variants','UPDATE') as allowed")).rows[0].allowed,false);
      await assert.rejects(db.query('update public_ev_variants set dc_charge_kw=60'), error => ['42501','55000'].includes(error.code));
      await db.exec('reset role');
    } finally { await db.close(); }
  });
}

test('aborts on unreviewed dependents/metadata without changing storage or public rows', async () => {
  const db = new PGlite();
  try {
    await seed(db);
    const before = await anonymousCatalogRows(db);
    for (const [add, remove, code] of [
      ['create view dependent_catalog as select id from public_ev_variants','drop view dependent_catalog','2BP01'],
      ['comment on column public_ev_variants.dc_charge_kw is \'Preserve me\'',
        'comment on column public_ev_variants.dc_charge_kw is null','P0001'],
    ]) {
      await db.exec(add);
      await assert.rejects(db.exec(exactDc),{code});
      await db.exec('rollback');
      assert.deepEqual(await anonymousCatalogRows(db),before);
      assert.equal((await db.query('select pg_typeof(dc_charge_kw)::text as t from canonical_model_variants limit 1')).rows[0].t,'integer');
      await db.exec(remove);
    }
  } finally { await db.close(); }
});

test('rejects a missing, unvalidated or weaker DC check without modifying data', async () => {
  const db = new PGlite();
  try {
    await seed(db);
    await db.exec(exactDc);
    const before = await privateState(db);
    await db.exec('alter table extracted_variant_drafts drop constraint exact_dc_charge_kw');
    await assert.rejects(assertExactDcInstalled(db), /Require validated exact DC constraint/);
    await db.exec(`alter table extracted_variant_drafts add constraint exact_dc_charge_kw check (
      dc_charge_kw is null or (dc_charge_kw between 20 and 600 and dc_charge_kw=trunc(dc_charge_kw,2))) not valid`);
    await assert.rejects(assertExactDcInstalled(db), /Require validated exact DC constraint/);
    await db.exec(`alter table extracted_variant_drafts drop constraint exact_dc_charge_kw,
      add constraint exact_dc_charge_kw check (dc_charge_kw is null or dc_charge_kw between 20 and 600)`);
    await assert.rejects(assertExactDcInstalled(db), /Unexpected exact DC constraint/);
    await assert.rejects(assertDcStorageForDrafts(db, [dcDraft(85.3)]), /Unexpected exact DC constraint/);
    await db.exec('alter table extracted_variant_drafts alter column dc_charge_kw type numeric(5,2)');
    await assert.rejects(assertExactDcInstalled(db), /Migration 027 is required/);
    assert.deepEqual(await privateState(db), before);
  } finally { await db.close(); }
});

test('operator wrapper rejects late catalog drift, commits exact migration and reruns read-only', async () => {
  const db = new PGlite();
  const client = {query: (sql, args) => sql.startsWith('set local search_path=') ? db.exec(sql) : db.query(sql, args)};
  const source = exactDc.replaceAll('\r\n','\n');
  try {
    await seed(db);
    const before = await privateState(db);
    const readers = await anonymousCatalogRows(db);
    const permissions = await access(db);
    const altered = source.replace("notify pgrst,'reload schema';",
      "UPDATE public.canonical_model_variants SET dc_charge_kw=110 WHERE dc_charge_kw=100;");
    assert.notEqual(altered, source);
    await db.exec('BEGIN READ ONLY');
    await assert.rejects(applyExactDcMigration(client, altered), /Migration would change the catalog/);
    await assert.rejects(assertExactDcInstalled(db), /Migration 027 is required/);
    assert.deepEqual(await privateState(db), before);
    await db.exec('BEGIN READ ONLY');
    assert.deepEqual(await applyExactDcMigration(client, source), {installed:true, applied:true, public_variants:2});
    assert.deepEqual(await applyExactDcMigration(client, source), {installed:true, applied:false, public_variants:2});
    await db.exec('ROLLBACK');
    assert.deepEqual(await anonymousCatalogRows(db), readers);
    assert.deepEqual(await access(db), permissions);
  } finally { await db.close(); }
});
