import assert from 'node:assert/strict';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { parseArgs } from 'node:util';
import { PGlite } from '@electric-sql/pglite';
import { applyNewModelPlan, applyXpG6Release, buildNewModelPlan, CORE_FIELDS, publicationHash, publicationSnapshot, rollingRegistrations } from './new_model_publication.mjs';
import { prepareXpG6Readback } from './prepare_xpeng_g6_readback.mjs';
import { readReviewedImage, readXpG6Capture } from './xpeng_g6_publication.mjs';
import { catalogHash, normalizeCatalog } from './sync_public_catalog.mjs';

const { values } = parseArgs({options: {review: {type: 'string'}, readback: {type: 'string'},
  'release-review': {type: 'string'}, 'release-ui': {type: 'string'}}});
assert(values.review, 'Supply the private G6 source capture directory');
const {intake, reviewHash, capturedAt} = readXpG6Capture(values.review);
const image = readReviewedImage();
const now = new Date(capturedAt);
const evidence = await realpath(new URL('../data/local/release-data', import.meta.url));
let liveScope;
let freshRecord;
async function privateReceipt(path, fileName, directoryPattern) {
  const file = await realpath(path);
  assert.equal(basename(file), fileName);
  assert.match(basename(dirname(file)), directoryPattern);
  assert.equal(dirname(dirname(file)), evidence);
  return JSON.parse(await readFile(file, 'utf8'));
}
if (values.readback) {
  const record = await privateReceipt(values.readback, 'readback.json', /^xpeng-g6-readback-[a-z0-9]+$/i);
  assert.equal(record.status, 'ready_for_review');
  assert.equal(record.apply_allowed, false);
  assert.equal(record.production_writes, 0);
  assert.equal(record.review_hash, reviewHash);
  assert.equal(record.plan_hash, publicationHash(record.plan));
  liveScope = record.plan;
  freshRecord = record;
}
let approvedRoute;
if (values['release-review'] || values['release-ui']) {
  assert(freshRecord && values['release-review'] && values['release-ui'], 'Require all three historical release receipts');
  const reviewed = await privateReceipt(values['release-review'], 'readback.json', /^xpeng-g6-readback-[a-z0-9]+$/i);
  const ui = await privateReceipt(values['release-ui'], 'report.json', /^xpeng-g6-ui-[a-z0-9]+$/i);
  approvedRoute = {reviewed, ui};
}
const db = new PGlite();
const publicRows = async () => (await db.query('SELECT * FROM public.public_ev_variants ORDER BY id')).rows;
const read = name => readFile(new URL('../' + name, import.meta.url), 'utf8');

try {
  await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role');
  const schema = (await read('database/schema.sql')).split('-- Keep the fresh-install access boundary identical to migration 008.')[0];
  await db.exec(schema.replace('create extension if not exists pgcrypto;', ''));
  for (const name of ['008_vehicle_access_boundary', '009_public_catalog_contract', '020_price_only_refresh', '023_decimal_ac_charging']) {
    await db.exec(await read('database/migrations/' + name + '.sql'));
  }
  let target, market;
  if (liveScope) {
    target = liveScope.expected_model;
    market = liveScope.expected_market;
    for (const [table, records] of [['canonical_models', [target]], ['model_aliases', [liveScope.expected_alias]],
      ['market_models', [market]], ['market_model_monthly_stats', liveScope.expected_monthly],
      ['manufacturer_sources', liveScope.expected_sources]]) {
      for (const row of records) await db.query(`INSERT INTO public.${table} SELECT * FROM json_populate_record(NULL::public.${table}, $1::json)`, [JSON.stringify(row)]);
    }
  } else {
    ({rows: [target]} = await db.query(`INSERT INTO canonical_models(brand,model,normalized_brand,normalized_model)
      VALUES ('Xpeng','G6','xpeng','g6') RETURNING id`));
    await db.query(`INSERT INTO model_aliases(canonical_model_id,brand_raw,model_raw,normalized_brand,normalized_model,alias_rule)
      VALUES($1,'XPENG','G6','xpeng','g6','mobility_sweden_exact_raw_name')`, [target.id]);
    ({rows: [market]} = await db.query(`INSERT INTO market_models(brand_raw,model_raw,fuel_type_raw,normalized_brand,normalized_model,first_seen_month,last_seen_month)
      VALUES('XPENG','G6','EL','xpeng','g6','2026-03-01','2026-03-01') RETURNING id`));
    await db.query(`INSERT INTO market_model_monthly_stats(market_model_id,month,brand_raw,model_raw,fuel_type_raw,registrations)
      VALUES($1,'2026-03-01','XPENG','G6','EL',98)`, [market.id]);
  }

  const {rows: [toyota]} = await db.query(`INSERT INTO canonical_models(brand,model,normalized_brand,normalized_model)
    VALUES('Toyota','C-Hr+','toyota','c hr') RETURNING id`);
  for (const variant of JSON.parse(await read('tests/fixtures/toyota_chr_plus_intake.json')).drafts) {
    const { source_url, source_hash, quote, value } = variant.price_evidence;
    await db.query(`INSERT INTO canonical_model_variants(canonical_model_id,variant_name,price_sek,validation_status,
      source_url,source_hash,source_quote,extraction_confidence)
      VALUES ($1,$2,$3,'published',$4,$5,$6,1)`, [toyota.id, variant.variant_name, value, source_url, source_hash, quote]);
  }
  const before = await publicationSnapshot(db);
  const visibleBefore = await publicRows();
  assert.equal(visibleBefore.length, 3);
  const baseline = catalogHash((await db.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')).rows.map(r => r.row));
  const fixtureUi = approvedRoute && { ...approvedRoute.ui, main_review: { ...approvedRoute.ui.main_review,
    baseline_sha256: baseline, baseline_count: 3, preserved_other_variants: 3, candidate_count: 6 } };
  const reconstructed = buildNewModelPlan(before, intake, image, now);
  if (liveScope) assert.deepEqual(reconstructed, liveScope, 'Use exactly the read-only snapshot scope');
  // Preserve the prepared field order: Postgres and PGlite can serialize equal JSON objects differently.
  const plan = liveScope ?? reconstructed;
  const planHash = publicationHash(plan);
  const prepare = async () => {
    await db.exec('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
    try { return await prepareXpG6Readback(db, intake, image, now); }
    finally { await db.exec('ROLLBACK'); }
  };
  await assert.rejects(prepareXpG6Readback(db, intake, image, now), /Read-only transaction required/);
  const prepared = await prepare();
  assert.deepEqual(prepared.plan, plan);
  assert.equal(prepared.plan_hash, publicationHash(prepared.plan));
  assert.deepEqual(await publicationSnapshot(db), before, 'Preparation must be read-only');

  for (const mutate of [
    x => { x.drafts[0].manufacturer_identity = 'F30bV$FFAB'; },
    x => { x.drafts[0].identity_evidence.source_hash = '0'.repeat(64); },
    x => { x.drafts[1].field_evidence.wltp_range_km.wheels_inches = 18; },
    x => { x.drafts[0].field_evidence.battery_kwh.capacity_basis = 'net'; },
    x => { x.drafts[0].price_evidence.corroboration.value = 507900; },
    x => { x.drafts[0].price_evidence.authorization.source_url = x.sources[0].final_url; },
    x => { x.market.row.model_raw = 'G6 2024'; },
  ]) {
    const invalid = structuredClone(intake);
    mutate(invalid);
    assert.throws(() => buildNewModelPlan(before, invalid, image, now));
  }
  assert.throws(() => buildNewModelPlan(before, intake, {...image, full_frame: false}, now));
  assert.throws(() => buildNewModelPlan(before, intake, {...image, source_content_sha256: '0'.repeat(64)}, now));
  assert.throws(() => buildNewModelPlan(before, intake, image, new Date(now.getTime() + 900001)), /Fresh source/);
  await assert.rejects(applyNewModelPlan({query() { assert.fail('Remote access was attempted'); }}, plan, planHash, now),
    /restricted to a local PGlite/);
  await assert.rejects(applyNewModelPlan(db, plan, '0'.repeat(64), now), /Prepared publication packet changed/);
  if (approvedRoute) {
    const {reviewed, ui} = approvedRoute;
    const remote = {query() { assert.fail('Remote access was attempted'); }};
    const approved = reviewed.plan_hash;
    await assert.rejects(applyXpG6Release(remote, freshRecord, reviewed, ui, '0'.repeat(64), now), /Wrong approved G6 scope/);
    await assert.rejects(applyXpG6Release(remote, freshRecord, reviewed, {...ui, runs: ui.runs.slice(1)}, approved, now), /browser matrix/);
    await assert.rejects(applyXpG6Release(remote, freshRecord, reviewed, ui, approved,
      new Date(freshRecord.evidence_expires_at)), /window expired/);
    await assert.rejects(applyXpG6Release(remote, freshRecord, reviewed, ui, approved, now), /Require the reviewed production catalog hash/);
    await assert.rejects(applyXpG6Release(remote, freshRecord, reviewed, ui, approved, now, '0'.repeat(64)), /Unreviewed G6 catalog hash/);
    await db.query('UPDATE public.canonical_model_variants SET price_sek=price_sek+10000 WHERE canonical_model_id=$1', [toyota.id]);
    const drifted = await publicationSnapshot(db);
    await assert.rejects(applyXpG6Release(db, freshRecord, reviewed, fixtureUi, approved, now, baseline), /Anonymous catalog changed before G6 writes/);
    assert.deepEqual(await publicationSnapshot(db), drifted, 'Catalog drift must leave all tables untouched');
    await db.query('UPDATE public.canonical_model_variants SET price_sek=price_sek-10000 WHERE canonical_model_id=$1', [toyota.id]);
    assert.deepEqual(await publicationSnapshot(db), before);
  }
  const apply = () => approvedRoute
    ? applyXpG6Release(db, freshRecord, approvedRoute.reviewed, fixtureUi, approvedRoute.reviewed.plan_hash, now, baseline)
    : applyNewModelPlan(db, plan, planHash, now);

  const config = intake.sources[0].final_url;
  const {rows: [collision]} = await db.query(`INSERT INTO extracted_variant_drafts(canonical_model_id,brand,model,variant_name,source_url)
    VALUES($1,'Xpeng','G6',$2,$3) RETURNING id`, [target.id, intake.drafts[1].variant_name, config]);
  const beforeCollision = await publicationSnapshot(db);
  await assert.rejects(prepare(), /existing draft needs separate review/);
  await assert.rejects(apply(), /Staging collision/);
  assert.deepEqual(await publicationSnapshot(db), beforeCollision, 'A second-variant collision must preserve the whole database');
  await db.query('DELETE FROM extracted_variant_drafts WHERE id=$1', [collision.id]);
  await db.query('UPDATE market_models SET registrations_ytd=10 WHERE id=$1', [market.id]);
  const beforeConcurrent = await publicationSnapshot(db);
  await assert.rejects(apply(), /Concurrent market change/);
  assert.deepEqual(await publicationSnapshot(db), beforeConcurrent);
  await db.query('UPDATE market_models SET registrations_ytd=$2 WHERE id=$1', [market.id, plan.expected_market.registrations_ytd]);
  assert.deepEqual(await publicationSnapshot(db), before);

  await db.exec(`CREATE FUNCTION fixture_g6_late_fail() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'G6 late failure'; END $$;
    CREATE TRIGGER fixture_g6_late_fail BEFORE UPDATE ON market_models FOR EACH ROW EXECUTE FUNCTION fixture_g6_late_fail();`);
  await assert.rejects(apply(), /G6 late failure/);
  assert.deepEqual(await publicationSnapshot(db), before, 'Source, variant, image and monthly writes must all roll back');
  assert.deepEqual(await publicRows(), visibleBefore);
  await db.exec('DROP TRIGGER fixture_g6_late_fail ON market_models');

  assert.match(target.id, /^[0-9a-f-]{36}$/);
  const variantView = 'public.public_ev_variants', modelView = 'public.public_ev_models';
  const viewDefinition = async name => (await db.query('SELECT pg_get_viewdef($1::regclass,true) AS sql', [name]))
    .rows[0].sql.trim().replace(/;$/, '');
  const setView = (name, sql) => db.exec(`CREATE OR REPLACE VIEW ${name} WITH (security_barrier=true) AS ${sql}`);
  const variantsSql = await viewDefinition(variantView), modelsSql = await viewDefinition(modelView);
  const {rows: [variantColumns]} = await db.query(`SELECT array_agg(quote_ident(attname) ORDER BY attnum) AS names
    FROM pg_attribute WHERE attrelid=$1::regclass AND attnum>0 AND NOT attisdropped`, [variantView]);
  const changedPrice = variantColumns.names.map(name => name === 'price_sek'
    ? `CASE WHEN canonical_model_id='${target.id}'::uuid THEN price_sek+1 ELSE price_sek END AS price_sek` : name).join(', ');
  const changedPhoto = variantColumns.names.map(name => name === 'image_url'
    ? `CASE WHEN canonical_model_id='${target.id}'::uuid THEN NULL::text ELSE image_url END AS image_url` : name).join(', ');
  for (const [name, original, broken, error] of [
    [variantView, variantsSql, `SELECT * FROM (${variantsSql}) v WHERE v.canonical_model_id<>'${target.id}'::uuid`, /G6 public variant IDs or visibility/],
    [variantView, variantsSql, `SELECT ${changedPrice} FROM (${variantsSql}) v`, /Unexpected public G6 field: price_sek/],
    [variantView, variantsSql, `SELECT ${changedPhoto} FROM (${variantsSql}) v`, /Unexpected public G6 field: image_url/],
    [modelView, modelsSql, `SELECT * FROM (${modelsSql}) m WHERE m.id<>'${target.id}'::uuid`, /G6 model must be visible anonymously/],
  ]) {
    await setView(name, broken);
    try {
      await assert.rejects(apply(), error);
      assert.deepEqual(await publicationSnapshot(db), before, 'Incorrect anonymous readback must roll back all writes');
      assert.deepEqual(await publicRows(), visibleBefore);
    } finally {
      await setView(name, original);
    }
  }

  await db.exec(`DROP VIEW ${modelView};
    CREATE VIEW ${modelView} WITH (security_barrier=true) AS
    SELECT id,brand,model,body_type,market_seen,available_confirmed,discontinued_candidate,coming_or_low_volume,published_at
    FROM (${modelsSql}) m;
    GRANT SELECT ON ${modelView} TO anon,authenticated,service_role;`);
  const result = await apply();
  assert(result.committed);
  assert.equal(result.variants_inserted, 3);
  assert.equal(result.anonymous_before_commit, true);
  const after = await publicationSnapshot(db);
  for (const historic of before.market_model_monthly_stats) {
    assert.deepEqual(after.market_model_monthly_stats.find(row => row.id === historic.id), historic);
  }
  const month = intake.market.row.last_seen_month;
  assert.equal(after.market_models[0].registrations_12m, rollingRegistrations(after.market_model_monthly_stats, month));
  assert.equal(after.market_models[0].registrations_last_month, 115);
  assert.equal(after.market_models[0].first_seen_month, plan.expected_market.first_seen_month ?? month);
  assert.equal(after.extracted_variant_drafts.length, 3);
  for (const saved of after.extracted_variant_drafts) {
    const draft = intake.drafts.find(row => row.variant_name === saved.variant_name);
    assert(draft);
    assert.deepEqual(saved.extraction_payload.identity_evidence, draft.identity_evidence);
    assert.deepEqual(saved.extraction_payload.price_evidence, draft.price_evidence);
    assert.deepEqual(saved.extraction_payload.field_evidence, draft.field_evidence);
  }

  let previewRows;
  await db.exec('SET ROLE anon');
  try {
    const visible = await publicRows();
    assert.deepEqual(visible.filter(row => row.canonical_model_id === toyota.id), visibleBefore);
    const variants = visible.filter(row => row.canonical_model_id === target.id);
    assert.equal(variants.length, 3);
    for (const row of variants) {
      const draft = intake.drafts.find(r => r.variant_name === row.variant_name);
      assert(draft);
      for (const field of CORE_FIELDS) assert.equal(field === 'drivetrain' ? row[field] : Number(row[field]), draft.facts[field]);
      assert.equal(row.price_sek, draft.price_evidence.value);
      assert.equal(row.price_source_url, config);
      assert.equal(row.price_type, 'list_price');
      assert.equal(row.image_url, image.asset_url);
      assert.equal(row.available_confirmed, plan.expected_model.available_confirmed);
    }
    // PGlite returns Date objects, whereas the public REST endpoint serializes them.
    previewRows = normalizeCatalog(JSON.parse(JSON.stringify(variants)).map(row => ({
      ...row, ...Object.fromEntries(CORE_FIELDS.filter(field => field !== 'drivetrain')
        .map(field => [field, Number(row[field])])),
      extraction_confidence: Number(row.extraction_confidence),
    })));
    await assert.rejects(db.query('SELECT id FROM public.extracted_variant_drafts'), {code: '42501'});
  } finally {
    await db.exec('RESET ROLE');
  }
  if (approvedRoute) await assert.rejects(apply(), /original production catalog/);
  const repeated = await applyNewModelPlan(db, plan, planHash, now);
  assert(repeated.already_applied);
  assert.deepEqual(await publicationSnapshot(db), after);
  const receipt = {status: 'passed_local_only', source_review_hash: reviewHash, captured_at: capturedAt,
    plan_hash: planHash, model: 'xpeng|g6', variants: 3, technical_fields: 27,
    rollback: true, staging_collision: true, concurrent_change: true, exact_replay: true, anonymous_readback: true,
    anonymous_before_commit: true, anonymous_projection_failure_cases_rolled_back: 4,
    production_model_view_without_photos: true,
    preserved_toyota_variants: visibleBefore.length, database_fixture: liveScope ? 'isolated PGlite, scoped production readback' : 'isolated PGlite, synthetic scope',
    preview_rows_sha256: publicationHash(previewRows), approval_route_rehearsed: Boolean(approvedRoute),
    locked_catalog_guard_rehearsed: Boolean(approvedRoute),
    publication_approved: false, production_writes: 0, paid_calls: 0};
  const folder = await mkdtemp(join(evidence, 'xpeng-g6-local-test-'));
  await writeFile(join(folder, 'preview-rows.json'), JSON.stringify(previewRows, null, 2) + '\n', {flag: 'wx'});
  const output = join(folder, 'transaction.json');
  await writeFile(output, JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({...receipt, output}));
} finally {
  await db.close();
}
