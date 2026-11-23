import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, realpath } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { catalogHash, normalizeCatalog } from './sync_public_catalog.mjs';

const readRepo = file => readFile(new URL('../' + file, import.meta.url), 'utf8');
const distinct = values => [...new Set(values.filter(Boolean))];

export const catalogWithComparableTimes = rows => normalizeCatalog(rows.map(row => ({...row,
  ...Object.fromEntries(['verified_at', 'price_verified_at'].filter(key => row[key]).map(key => [key, new Date(row[key]).toISOString()])),
})));

export async function readPublishedFixture(client) {
  assert.equal((await client.query('SHOW transaction_read_only')).rows[0].transaction_read_only, 'on');
  const rows = async (sql, args) => (await client.query(sql, args)).rows.map(({row}) => row);
  const variants = await rows(`SELECT to_jsonb(cv) AS row FROM public.canonical_model_variants cv
    WHERE cv.id IN (SELECT id FROM public.public_ev_variants) ORDER BY cv.id`);
  assert(variants.length > 0 && variants.length < 10000);
  const sources = await rows(`SELECT to_jsonb(s) AS row FROM public.manufacturer_sources s
    WHERE s.id=ANY($1::uuid[]) ORDER BY s.id`, [distinct(variants.map(r => r.source_id))]);
  const models = await rows(`SELECT to_jsonb(m) AS row FROM public.canonical_models m
    WHERE m.id=ANY($1::uuid[]) ORDER BY m.id`, [distinct([...variants, ...sources].map(r => r.canonical_model_id))]);
  const {rows:[legacy]} = await client.query(`SELECT is_nullable='YES' AS nullable_authority
    FROM information_schema.columns WHERE table_schema='public' AND table_name='manufacturer_sources'
    AND column_name='source_authority'`);
  assert.equal(typeof legacy?.nullable_authority, 'boolean');
  return {models, sources, variants, legacy};
}

export async function seedCatalogFixture(db, {models, sources, variants, legacy}, plans) {
  const schema = (await readRepo('database/schema.sql')).split('-- Keep the fresh-install access boundary identical to migration 008.')[0];
  await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role');
  await db.exec(schema.replace('create extension if not exists pgcrypto;', ''));
  for (const name of ['008_vehicle_access_boundary', '009_public_catalog_contract', '011_exact_toyota_variant_publication', '020_price_only_refresh',
    '021_source_type_alignment', '023_decimal_ac_charging']) {
    await db.exec(await readRepo('database/migrations/' + name + '.sql'));
  }
  if (variants.some(row => row.variant_image_url != null || row.variant_image_source_url != null)) {
    await db.exec(await readRepo('database/migrations/025_variant_photo_override.sql'));
  }
  if (variants.some(row => row.price_type === 'manufacturer_from')) {
    await db.exec(await readRepo('database/migrations/026_manufacturer_from_price.sql'));
  }
  if (variants.some(row => row.dc_charge_kw != null && !Number.isInteger(Number(row.dc_charge_kw)))) {
    await db.exec(await readRepo('database/migrations/027_exact_dc_charging.sql'));
  }
  // Mirror deployed legacy nullability without inventing provenance for old rows.
  if (legacy.nullable_authority) await db.exec('ALTER TABLE public.manufacturer_sources ALTER COLUMN source_authority DROP NOT NULL');
  const insert = async (table, rows) => {
    const unique = new Map();
    for (const row of rows) {
      if (unique.has(row.id)) assert.deepEqual(unique.get(row.id), row, 'Inconsistent scoped fixture row');
      unique.set(row.id, row);
    }
    try {
      await db.query(`INSERT INTO public.${table} SELECT * FROM json_populate_recordset(NULL::public.${table}, $1::json)`,
        [JSON.stringify([...unique.values()])]);
    } catch (error) {
      throw new Error(`${table}: ${error.message.split('\n')[0]}`, {cause: error});
    }
  };
  await insert('canonical_models', [...models, ...plans.map(p => p.expected_model)]);
  await insert('manufacturer_sources', [...sources, ...plans.flatMap(p => p.expected_sources)]);
  await insert('canonical_model_variants', variants);
  await insert('model_aliases', plans.map(p => p.expected_alias));
  await insert('market_models', plans.map(p => p.expected_market));
  await insert('market_model_monthly_stats', plans.flatMap(p => p.expected_monthly));
}

export async function anonymousCatalogRows(db) {
  await db.exec('SET ROLE anon');
  try {
    const {rows} = await db.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id');
    await assert.rejects(db.query('SELECT id FROM public.extracted_variant_drafts'), {code:'42501'});
    await assert.rejects(db.query('SELECT id FROM public.canonical_model_variants'), {code:'42501'});
    return rows.map(r => r.row);
  } finally {await db.exec('RESET ROLE');}
}

export async function readCommittedPublicBaseline(releaseRoot, output, {imageTools = false} = {}) {
  assert.equal(await realpath(output), output);
  assert.equal(dirname(output), releaseRoot);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(releaseRoot));
  const commit = execFileSync('git', ['rev-parse', 'refs/remotes/origin/main'], { encoding: 'utf8' }).trim();
  assert.match(commit, /^[0-9a-f]{40}$/);
  const paths = ['index.html', 'src', 'public', 'functions/_shared'];
  if (imageTools) paths.push('vite.config.mjs', 'scripts/prepare_responsive_images.py', 'scripts/audit_image_rights.py', 'scripts/verify_public_images.py');
  const tree = execFileSync('git', ['ls-tree', '-rl', commit, '--', ...paths], { encoding: 'utf8' }).trim().split('\n');
  assert(tree.length > 10 && tree.length < 10000);
  let size = 0;
  for (const entry of tree) {
    const match = /^100644 blob [a-f0-9]{40}\s+(\d+)\t([a-zA-Z0-9_./-]+)$/.exec(entry);
    assert(match && !match[2].split('/').includes('..'), 'Only ordinary release files may be extracted');
    size += Number(match[1]);
  }
  assert(size < 150 * 1024 * 1024, 'Unexpected release archive size');
  const archive = join(output, 'main.tar'), sourceRoot = join(output, 'main-source');
  await mkdir(sourceRoot);
  execFileSync('git', ['archive', '--format=tar', '--output', archive, commit, '--', ...paths], { timeout: 30000 });
  execFileSync('tar', ['-xf', archive, '-C', sourceRoot], { timeout: 30000 });
  const baseline_url = 'https://elbilsagenten.se/data/public_ev_variants.json';
  const response = await fetch(baseline_url, { redirect: 'error', signal: AbortSignal.timeout(15000) });
  assert(response.ok, 'The public baseline must be readable over HTTPS');
  const live = await response.json();
  const committed = JSON.parse(await readFile(join(sourceRoot, 'public/data/public_ev_variants.json'), 'utf8'));
  const baseline_sha256 = catalogHash(live.records);
  assert.equal(baseline_sha256, catalogHash(committed.records), 'Current local origin/main differs from live');
  const base = normalizeCatalog(committed.records);
  return { sourceRoot, base, proof: { commit, baseline_url, baseline_sha256, baseline_count: base.length,
    checked_at: new Date().toISOString() } };
}
