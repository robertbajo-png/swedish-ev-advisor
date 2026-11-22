import assert from 'node:assert/strict';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { parseArgs } from 'node:util';
import { PGlite } from '@electric-sql/pglite';
import { applyIoniq5Release, applyNewModelPlan, buildNewModelPlan, CORE_FIELDS, publicationHash, publicationSnapshot } from './new_model_publication.mjs';
import { readIoniq5Capture, readReviewedPhoto } from './hyundai_ioniq5_publication.mjs';
import { ioniq5ReleaseReceipt } from './hyundai_ioniq5_release_scope.mjs';
import { catalogConnectorPath, openCatalogSnapshot } from './local_catalog_connector.mjs';
import { catalogWithComparableTimes } from './isolated_catalog_review.mjs';
import { prepareIoniq5Readback } from './prepare_hyundai_ioniq5_readback.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { catalogHash, normalizeCatalog } from './sync_public_catalog.mjs';

const { values } = parseArgs({ options: { review: { type: 'string' }, 'production-scope': { type: 'boolean' },
  'release-ui': {type: 'string'}, 'client-module': {type:'string'} } });
assert(values.review, 'Supply the private Ioniq 5 source packet');
const { intake, images, capturedAt, reviewHash } = await readIoniq5Capture(values.review);
const now = new Date(capturedAt);
const releaseRoot = await realpath('data/local/release-data');
const read = file => readFile(new URL('../' + file, import.meta.url), 'utf8');
const eligible = intake.drafts.length;

async function readProductionScope() {
  assert(Math.abs(Date.now() - now.getTime()) < 900000, 'Fresh exact evidence required for the production scope check');
  const connection = await catalogConnectorPath(await realpath('.'), values['client-module']);
  const {client, close} = await openCatalogSnapshot(connection);
  try {
    useCalendarDateText(client);
    return await prepareIoniq5Readback(client, intake, images.base, new Date());
  } finally {
    await close();
  }
}

const scope = values['production-scope'] ? await readProductionScope() : null;
const db = new PGlite();
const readPublic = async () => (await db.query('SELECT * FROM public.public_ev_variants ORDER BY id')).rows;
try {
  await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role');
  const schema = (await read('database/schema.sql')).split('-- Keep the fresh-install access boundary identical to migration 008.')[0];
  await db.exec(schema.replace('create extension if not exists pgcrypto;', ''));
  for (const name of ['008_vehicle_access_boundary', '009_public_catalog_contract', '020_price_only_refresh', '023_decimal_ac_charging']) {
    await db.exec(await read('database/migrations/' + name + '.sql'));
  }
  let target;
  if (scope) {
    target = scope.expected_model;
    for (const [table, rows] of [['canonical_models', [target]], ['model_aliases', [scope.expected_alias]],
      ['market_models', [scope.expected_market]], ['market_model_monthly_stats', scope.expected_monthly],
      ['manufacturer_sources', scope.expected_sources]]) {
      for (const row of rows) await db.query(`INSERT INTO public.${table} SELECT * FROM json_populate_record(NULL::public.${table}, $1::json)`, [JSON.stringify(row)]);
    }
  } else {
    ({ rows: [target] } = await db.query(`INSERT INTO canonical_models(brand,model,normalized_brand,normalized_model)
      VALUES ('Hyundai','Ioniq 5','hyundai','ioniq 5') RETURNING id`));
    await db.query(`INSERT INTO model_aliases(canonical_model_id,brand_raw,model_raw,normalized_brand,normalized_model,alias_rule)
      VALUES($1,'HYUNDAI','IONIQ 5','hyundai','ioniq 5','mobility_sweden_exact_raw_name')`, [target.id]);
    const { rows: [market] } = await db.query(`INSERT INTO market_models(brand_raw,model_raw,fuel_type_raw,normalized_brand,normalized_model,first_seen_month,last_seen_month)
      VALUES('HYUNDAI','IONIQ 5','EL','hyundai','ioniq 5','2026-03-01','2026-03-01') RETURNING id`);
    await db.query(`INSERT INTO market_model_monthly_stats(market_model_id,month,brand_raw,model_raw,fuel_type_raw,registrations)
      VALUES($1,'2026-03-01','HYUNDAI','IONIQ 5','EL',51)`, [market.id]);
  }
  const { rows: [toyota] } = await db.query(`INSERT INTO canonical_models(brand,model,normalized_brand,normalized_model)
    VALUES('Toyota','C-Hr+','toyota','c hr') RETURNING id`);
  for (const row of JSON.parse(await read('tests/fixtures/toyota_chr_plus_intake.json')).drafts) {
    const price = row.price_evidence;
    await db.query(`INSERT INTO canonical_model_variants(canonical_model_id,variant_name,price_sek,validation_status,
      source_url,source_hash,source_quote,extraction_confidence)
      VALUES($1,$2,$3,'published',$4,$5,$6,1)`,
      [toyota.id, row.variant_name, price.value, price.source_url, price.source_hash, price.quote]);
  }

  let releaseFixture;
  if (values['release-ui']) {
    assert.equal(eligible, 7, 'Require all seven exact identities for release rehearsal');
    const ui = JSON.parse(await readFile(values['release-ui'], 'utf8'));
    const snapshot = await publicationSnapshot(db);
    const fixturePlan = scope ?? buildNewModelPlan(snapshot, intake, images.base, now);
    const reviewed = ioniq5ReleaseReceipt(fixturePlan, reviewHash);
    if (scope) assert.equal(ui.plan_hash, reviewed.plan_hash);
    const fresh = ioniq5ReleaseReceipt(fixturePlan, publicationHash({fixture_only: true, reviewHash}));
    const fixtureRows=(await db.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')).rows.map(row=>row.row);
    const fixtureUi = {...ui, plan_hash: reviewed.plan_hash, baseline: {...ui.baseline,
      baseline_sha256:catalogHash(fixtureRows),database_baseline_sha256:catalogHash(catalogWithComparableTimes(fixtureRows)),
      baseline_count: 3, candidate_count: 10},
      distribution: {...ui.distribution, preserved: 3, count: 10}};
    releaseFixture = {reviewed, fresh, ui: fixtureUi,
      apply: () => applyIoniq5Release(db, fresh, reviewed, fixtureUi, reviewed.plan_hash, now)};
    await assert.rejects(releaseFixture.apply(), /Both variant image columns must exist/);
    assert.deepEqual(await publicationSnapshot(db), snapshot, 'Missing photo migration must prevent all writes');
  }
  const viewContract = async () => (await db.query(`SELECT c.oid::text, c.relowner::text, c.relacl::text, c.reloptions::text,
    (SELECT array_agg(a.attname::text ORDER BY a.attnum) FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped) AS names
    FROM pg_class c WHERE c.oid='public.public_ev_variants'::regclass`)).rows[0];
  const beforeContract = await viewContract(), beforePhotoMigration = await readPublic();
  const migration = await read('database/migrations/025_variant_photo_override.sql');
  await db.exec(migration);
  const viewSQL = (await db.query("SELECT pg_get_viewdef('public.public_ev_variants'::regclass,true) AS sql")).rows[0].sql;
  await db.exec(migration);
  assert.equal((await db.query("SELECT pg_get_viewdef('public.public_ev_variants'::regclass,true) AS sql")).rows[0].sql, viewSQL);
  assert.deepEqual(await viewContract(), beforeContract, 'View columns, grants, identity and options must stay unchanged');
  assert.deepEqual(await readPublic(), beforePhotoMigration);

  const before = await publicationSnapshot(db);
  const publicBefore = await readPublic();
  assert.equal(publicBefore.length, 3);
  const localPlan = buildNewModelPlan(before, intake, images.base, now);
  if (scope) assert.deepEqual(localPlan, scope);
  const plan = scope ?? localPlan, planHash = publicationHash(plan);
  const apply = () => releaseFixture ? releaseFixture.apply() : applyNewModelPlan(db, plan, planHash, now);
  if (releaseFixture) {
    const {fresh, reviewed, ui} = releaseFixture;
    const remote = {query() { assert.fail('No SQL should run for an invalid approval'); }};
    await assert.rejects(applyIoniq5Release(remote, fresh, reviewed, ui, '0'.repeat(64), now), /Invalid Ioniq 5 approval/);
    await assert.rejects(applyIoniq5Release(remote, fresh, reviewed, ui, reviewed.plan_hash,
      new Date(fresh.evidence_expires_at)), /source window expired/);
    await db.query('UPDATE canonical_model_variants SET price_sek=price_sek+1000 WHERE canonical_model_id=$1', [toyota.id]);
    const drift = await publicationSnapshot(db);
    await assert.rejects(apply(), /Anonymous catalog changed before Ioniq 5 writes/);
    assert.deepEqual(await publicationSnapshot(db), drift);
    await db.query('UPDATE canonical_model_variants SET price_sek=price_sek-1000 WHERE canonical_model_id=$1', [toyota.id]);
    const sql = viewSQL.trim().replace(/;$/, '');
    const changed = sql.replace(/COALESCE\(variant_photo\.variant_image_url, base\.image_url\)/i,
      "CASE WHEN base.variant_name LIKE '% N Line' THEN base.image_url ELSE COALESCE(variant_photo.variant_image_url, base.image_url) END");
    assert.notEqual(changed, sql);
    const replaceView = definition => db.exec('CREATE OR REPLACE VIEW public.public_ev_variants WITH (security_barrier=true) AS ' + definition);
    await replaceView(changed);
    await assert.rejects(apply(), /Unexpected public Ioniq 5 field: image_url/);
    assert.deepEqual(await publicationSnapshot(db), before);
    await replaceView(sql);
  }
  for (const alter of [
    x => { x.drafts[0].variant_name = '84 kWh RWD N Line'; },
    x => { x.drafts[0].identity_evidence.model_year = 2026; },
    x => { x.drafts[0].price_evidence.corroboration.value -= 1000; },
    x => { x.drafts[0].field_evidence.wltp_range_km.wheel_scope = '20 N Line'; },
    x => { x.drafts.at(-1).identity_evidence.reviewed_photo_sha256 = images.base.content_sha256; },
    x => { x.drafts.at(-1).facts.ac_charge_kw = 11; },
    ...(eligible === 7 ? [x => { x.drafts.at(-1).identity_evidence.authorization.value = 'C18AS20016'; }] : []),
  ]) {
    const changed = structuredClone(intake);
    alter(changed);
    assert.throws(() => buildNewModelPlan(before, changed, images.base, now));
  }
  assert.throws(() => buildNewModelPlan(before, intake, images.nLine, now));
  assert.throws(() => buildNewModelPlan(before, intake, images.base, new Date(now.getTime() + 900001)), /Fresh source/);
  await assert.rejects(applyNewModelPlan({ query() { assert.fail('Unexpected remote query'); } }, plan, planHash, now), /restricted to a local PGlite/);
  const primary = intake.sources[0].final_url;
  const { rows: [duplicate] } = await db.query(`INSERT INTO extracted_variant_drafts(canonical_model_id,brand,model,variant_name,source_url)
    VALUES($1,'Hyundai','Ioniq 5',$2,$3) RETURNING id`, [target.id, intake.drafts.at(-1).variant_name, primary]);
  const pending = await publicationSnapshot(db);
  await assert.rejects(apply(), /Staging collision/);
  assert.deepEqual(await publicationSnapshot(db), pending);
  await db.query('DELETE FROM public.extracted_variant_drafts WHERE id=$1', [duplicate.id]);
  await db.exec(`CREATE FUNCTION fixture_ioniq5_late_fail() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Ioniq 5 late failure'; END $$;
    CREATE TRIGGER fixture_ioniq5_late_fail BEFORE UPDATE ON market_models FOR EACH ROW EXECUTE FUNCTION fixture_ioniq5_late_fail();`);
  await assert.rejects(apply(), /Ioniq 5 late failure/);
  assert.deepEqual(await publicationSnapshot(db), before);
  assert.deepEqual(await readPublic(), publicBefore);
  await db.exec('DROP TRIGGER fixture_ioniq5_late_fail ON market_models');
  const result = await apply();
  assert.equal(result.variants_inserted, eligible);
  if (releaseFixture) assert.equal(result.anonymous_before_commit, true);
  const after = await publicationSnapshot(db);
  const edition = after.canonical_model_variants.find(row => row.canonical_model_id === target.id && row.variant_name.endsWith('N Line'));
  assert(edition);
  await assert.rejects(db.query('UPDATE public.canonical_model_variants SET variant_image_source_url=null WHERE id=$1',
    [edition.id]), {code: '23514'});
  await assert.rejects(db.query("UPDATE public.canonical_model_variants SET variant_image_url='https://example.invalid/unrelated.jpg' WHERE id=$1",
    [edition.id]), {code: '23514'});
  await db.exec('BEGIN');
  try {
    const { rows: [renamed] } = await db.query(`UPDATE public.canonical_model_variants SET variant_name='Fixture renamed'
      WHERE id=$1 RETURNING variant_image_url,variant_image_source_url`, [edition.id]);
    assert.deepEqual(renamed, {variant_image_url: null, variant_image_source_url: null});
  } finally {
    await db.exec('ROLLBACK');
  }
  assert.deepEqual(await publicationSnapshot(db), after);
  assert(before.market_model_monthly_stats.every(row => after.market_model_monthly_stats.some(other =>
    publicationHash(row) === publicationHash(other))));
  assert.equal(after.extracted_variant_drafts.length, eligible);
  const last = intake.drafts.at(-1);
  assert(last.variant_name.endsWith('N Line'));
  assert.equal(readReviewedPhoto('nLine').image.content_sha256, last.identity_evidence.reviewed_photo_sha256);
  assert.deepEqual(after.extracted_variant_drafts.find(row => row.variant_name === last.variant_name).extraction_payload.identity_evidence,
    last.identity_evidence);

  let previewRows;
  await db.exec('SET ROLE anon');
  try {
    const visible = await readPublic();
    assert.deepEqual(visible.filter(v => v.canonical_model_id === toyota.id), publicBefore);
    const rows = visible.filter(v => v.canonical_model_id === target.id);
    assert.equal(rows.length, eligible);
    assert.equal(rows.some(row => row.variant_name.endsWith('RWD N Line')), eligible === 7);
    for (const row of rows) {
      const draft = intake.drafts.find(v => v.variant_name === row.variant_name);
      assert(draft);
      for (const field of CORE_FIELDS) assert.equal(field === 'drivetrain' ? row[field] : Number(row[field]), draft.facts[field]);
      assert.equal(row.price_sek, draft.price_evidence.value);
      assert.equal(row.price_type, 'list_price');
      assert.equal(row.price_source_url, draft.price_evidence.source_url);
      assert.equal(row.price_source_hash, draft.price_evidence.source_hash);
      const photo = row.variant_name.endsWith('N Line') ? images.nLine : images.base;
      assert.equal(row.image_url, photo.asset_url);
      assert.equal(row.image_source_url, photo.source_url);
      assert.equal(row.available_confirmed, plan.expected_model.available_confirmed);
    }
    previewRows = normalizeCatalog(JSON.parse(JSON.stringify(rows)).map(row => ({
      ...row, ...Object.fromEntries(CORE_FIELDS.filter(field => field !== 'drivetrain').map(field => [field, Number(row[field])])),
      extraction_confidence: Number(row.extraction_confidence),
    })));
    await assert.rejects(db.query('SELECT id FROM public.extracted_variant_drafts'), {code: '42501'});
    await assert.rejects(db.query('SELECT variant_image_url FROM public.canonical_model_variants'), {code: '42501'});
  } finally {
    await db.exec('RESET ROLE');
  }
  assert((await applyNewModelPlan(db, plan, planHash, now)).already_applied);
  if (releaseFixture) await assert.rejects(apply(), /requires an unpublished canonical model/);
  assert.deepEqual(await publicationSnapshot(db), after);
  const output = await mkdtemp(join(releaseRoot, 'hyundai-ioniq5-local-test-'));
  await writeFile(join(output, 'preview-rows.json'), JSON.stringify(previewRows, null, 2) + '\n', {flag: 'wx'});
  if (scope && eligible === 7) await writeFile(join(output, 'reviewed-scope.json'),
    JSON.stringify(ioniq5ReleaseReceipt(plan, reviewHash), null, 2) + '\n', {flag: 'wx'});
  else if (releaseFixture) await writeFile(join(output, 'rehearsed-scope.json'),
    JSON.stringify(releaseFixture.reviewed, null, 2) + '\n', {flag: 'wx'});
  const report = {status: 'passed_local_only', plan_hash: planHash, source_review_hash: reviewHash,
    database_fixture: scope ? 'isolated PGlite, scoped production readback' : 'isolated PGlite, synthetic scope',
    variants: eligible, technical_fields: eligible * CORE_FIELDS.length, exact_replay: true, rollback: true, staging_collision: true,
    anonymous_readback: true, withheld: intake.model_evidence.identity_holds, preserved_toyota_variants: 3,
    scoped_photos: {base: images.base.content_sha256, n_line: images.nLine.content_sha256},
    variant_photo_projection: true, view_contract_unchanged: true, preview_rows_sha256: publicationHash(previewRows),
    guarded_release_rehearsed: Boolean(releaseFixture),
    production_writes: 0, paid_calls: 0, publication_approved: false};
  await writeFile(join(output, 'transaction.json'), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({...report, output}));
} finally {
  await db.close();
}
