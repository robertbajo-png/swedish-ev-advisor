import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { parseArgs } from 'node:util';
import { PGlite } from '@electric-sql/pglite';
import { CORE_FIELDS, applyIdBuzzRelease, applyNewModelPlan, assertIdBuzzReleaseScope, buildNewModelPlan, publicationHash, publicationSnapshot } from './new_model_publication.mjs';
import { selectImageRegistryForPublic } from './model_image_sync.mjs';
import { marketUrl, prepareIdBuzzIntake } from './volkswagen_id_buzz_publication.mjs';
import { readIdBuzzReview, prepareIdBuzzReadback } from './prepare_id_buzz_readback.mjs';
import { normalizeCatalog } from './sync_public_catalog.mjs';

const json = async path => JSON.parse(await readFile(path, 'utf8'));
const hash = value => createHash('sha256').update(value).digest('hex');
const nowFixture = '2026-11-19T10:30:00Z';
const base = 'https://www.volkswagen-transportbilar.se';
const page = base + '/sv/modeller/id-buzz.html';
const tech = base + '/sv/modeller/id-buzz/tekniska-data.html';
const dealer = 'https://mollerbil.se/erbjudanden/id-buzz-pro-sweden-olympic-edition';
const auth = base + '/sv/om-oss/transportmagasinet/foretag-och-forare/anpassa-transportbilen-efter-dina-behov.html';
const fr = 'https://www.volkswagen-utilitaires.fr/idhub/content/dam/onehub_nfz/importers/fr/documentation/fiches-tarifs/Tarif_ID_Buzz.pdf';
const fi = 'https://api.k-auto.fi/priceCatalog/api/PriceCatalog/d1c60397-8685-48d3-b954-e08eb0b50361';
const photo = await json('src/id-buzz-photo-policy.json');

function fixture() {
  const review = { publication_approved: false, status: 'needs_review', photo, variants: [], configurations: [],
    sources: Object.fromEntries([page, tech, dealer, auth, fr, fi].map(url => [url, { content_hash: hash(url), fetched_at: nowFixture }])) };
  const proof = (value, source_url, quote = 'Synthetic source fixture') => ({ value, source_url, quote });
  for (const [trim, code, slug, cash, range, consumption, boot, tow, drive] of [
    ['Pro', 'EBBR7R', 'pro', 589900, 452, 19.6, 1121, 1200, 'RWD'],
    ['Pro 4MOTION', 'EBBR5R', 'pro-4motion', 625900, 416, 21.5, 1131, 1800, 'AWD'],
  ]) {
    const url = base + `/sv/bygg-din-bil.html/__app/72006/edition/${slug}.app`;
    const configuration_id = code + '$FIXTURE';
    const summary = `${url}?modelId-app=${encodeURIComponent(configuration_id)}`;
    review.configurations.push({ trim, source_url: url, captured_at: nowFixture, motor_id: code, configuration_id,
      model_year: 2027, wheelbase_mm: 2989, seats: 5, summary: { final_url: summary, evidence_sha256: hash(summary) } });
    review.variants.push({ trim, model_code: code, configuration_id, observed_configurator_tow: proof(1800, summary),
      price: { ...proof(cash, dealer, `ID. Buzz ${trim} Sweden Olympic Edition 5-sits pris fr\u00e5n ${cash.toLocaleString('en-US').replace(',', ' ')} kr inkl. moms`),
        price_type: 'dealer_offer', price_valid_until: '2026-12-31', expiry_quote: 'Erbjudandet g\u00e4ller tom 31/12 2026',
        authorization: proof(undefined, auth), manufacturer_base_cash: proof(cash, summary) },
      facts: { wltp_range_km: proof(range, summary), wltp_consumption_kwh_100km: proof(consumption, summary),
        dc_charge_kw: { ...proof(185, page), corroboration: proof(185, fi), alternative: proof(183, fr) },
        ac_charge_kw: { ...proof(11, fr), corroboration: proof(11, fi) },
        battery_kwh: proof(79, page), boot_liters: proof(boot, trim === 'Pro' ? tech : page),
        tow_kg: proof(tow, tech), seats: proof(5, page), drivetrain: proof(drive, page) } });
  }
  return review;
}

const { values } = parseArgs({ options: { review: { type: 'string' }, readback: { type: 'string' }, preview: { type: 'boolean' } } });
assert(!values.preview || values.readback, 'Preview requires the actual read-only production scope');
const captured = values.review ? await readIdBuzzReview(values.review) : null;
const review = captured?.review ?? fixture();
let readbackPlan, readbackDirectory;
if (values.readback) {
  assert(captured?.review.market, 'A live-source review and market workbook are required');
  const path = await realpath(values.readback);
  assert.equal(basename(path), 'readback.json');
  assert.equal(dirname(dirname(path)), captured.root, 'Use a private readback in the project evidence directory');
  assert.match(basename(dirname(path)), /^volkswagen-id-buzz-readback-[a-z0-9]+$/i);
  const receipt = await json(path);
  assert.equal(receipt.status, 'ready_for_review');
  assert.equal(receipt.apply_allowed, false);
  assert.equal(receipt.production_writes, 0);
  assert.equal(receipt.review_hash, captured.reviewHash, 'Wrong source review for this readback');
  assert.equal(receipt.plan_hash, publicationHash(receipt.plan), 'Readback plan changed');
  readbackPlan = receipt.plan;
  readbackDirectory = dirname(path);
}
const now = new Date(Math.max(...review.configurations.map(c => Date.parse(c.captured_at)),
  ...Object.values(review.sources).map(s => Date.parse(s.fetched_at)), review.market ? Date.parse(review.market.source.fetched_at) : 0));
const market = review.market ?? { sheet: 'Elbil ranking', source: { status: 'reachable', http_status: 200, final_url: marketUrl,
  content_hash: hash('Isolated market fixture, not fresh evidence'), fetched_at: now.toISOString() },
  row: { brand_raw: 'VW', model_raw: 'ID. BUZZ', fuel_type_raw: 'EL', normalized_brand: 'volkswagen', normalized_model: 'id buzz',
    needs_mapping: false, last_seen_month: '2026-10-01', registrations_last_month: 147, registrations_ytd: 910,
    source_name: 'Mobility Sweden', source_url: marketUrl } };
const intake = prepareIdBuzzIntake(review, market);
const registry = await json('src/image-rights.json');
const image = registry.assets.find(row => row.model_key === photo.model_key);
assert(image);
assert.equal((await json('src/model-images.json'))[photo.model_key], image.asset_url);
assert.equal(selectImageRegistryForPublic([], { schema_version: 1, assets: [image] }).assets.length, 0);
assert.equal(selectImageRegistryForPublic([{ brand: 'Volkswagen', model: 'Id. Buzz' }], { schema_version: 1, assets: [image] }).assets.length, 1);
assert.throws(() => selectImageRegistryForPublic([], { schema_version: 1, assets: [{ ...image, full_frame: false }] }));
const db = new PGlite();
try {
  const schema = await readFile('database/schema.sql', 'utf8');
  await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role');
  await db.exec(schema.split('-- Keep the fresh-install access boundary identical to migration 008.')[0].replace('create extension if not exists pgcrypto;', ''));
  for (const name of ['008_vehicle_access_boundary', '009_public_catalog_contract', '020_price_only_refresh']) {
    await db.exec(await readFile(`database/migrations/${name}.sql`, 'utf8'));
  }
  // Production exposes photos on public_ev_variants, not public_ev_models.
  const originalViews = await readFile('database/migrations/002_public_canonical_views.sql', 'utf8');
  const modelView = originalViews.match(/create or replace view public_ev_models as[^;]+;/i)?.[0];
  assert(modelView);
  await db.exec('DROP VIEW public.public_ev_models; ' + modelView + ' GRANT SELECT ON public.public_ev_models TO anon;');
  let m;
  if (readbackPlan) {
    // Copy only the already scoped, read-only snapshot into an in-memory database.
    for (const [table, rows] of [['canonical_models', [readbackPlan.expected_model]], ['model_aliases', [readbackPlan.expected_alias]],
      ['market_models', [readbackPlan.expected_market]], ['market_model_monthly_stats', readbackPlan.expected_monthly],
      ['manufacturer_sources', readbackPlan.expected_sources]]) {
      for (const row of rows) await db.query(`INSERT INTO public.${table} SELECT * FROM json_populate_record(NULL::public.${table}, $1::json)`, [JSON.stringify(row)]);
    }
    m = readbackPlan.expected_model;
  } else {
    const { rows } = await db.query(`INSERT INTO canonical_models(brand,model,normalized_brand,normalized_model) VALUES('Volkswagen','Id. Buzz','volkswagen','id buzz') RETURNING id`);
    m = rows[0];
    await db.query(`INSERT INTO model_aliases(canonical_model_id,brand_raw,model_raw,normalized_brand,normalized_model,alias_rule)
      VALUES($1,'VW','ID. BUZZ','volkswagen','id buzz','mobility_sweden_exact_raw_name')`, [m.id]);
    const { rows: [index] } = await db.query(`INSERT INTO market_models(brand_raw,model_raw,fuel_type_raw,normalized_brand,normalized_model,first_seen_month,last_seen_month)
      VALUES('VW','ID. BUZZ','EL','volkswagen','id buzz','2026-03-01','2026-03-01') RETURNING id`);
    await db.query(`INSERT INTO market_model_monthly_stats(market_model_id,month,brand_raw,model_raw,fuel_type_raw,registrations)
      VALUES($1,'2026-03-01','VW','ID. BUZZ','EL',98)`, [index.id]);
  }
  const { rows: [toyota] } = await db.query(`INSERT INTO canonical_models(brand,model,normalized_brand,normalized_model)
    VALUES('Toyota','C-Hr+','toyota','c hr') RETURNING id`);
  for (const draft of (await json('tests/fixtures/toyota_chr_plus_intake.json')).drafts) {
    await db.query(`INSERT INTO canonical_model_variants(canonical_model_id,variant_name,price_sek,validation_status)
      VALUES($1,$2,$3,'published')`, [toyota.id, draft.variant_name, draft.price_evidence.value]);
  }

  const before = await publicationSnapshot(db);
  const plan = buildNewModelPlan(before, intake, image, now), planHash = publicationHash(plan);
  if (readbackPlan) assert.deepEqual(plan, readbackPlan, 'The isolated database must reproduce the exact reviewed scope');
  const publicRows = () => db.query('SELECT * FROM public.public_ev_variants ORDER BY id').then(r => r.rows);
  const publicBefore = await publicRows();
  assert.equal(publicBefore.length, 3);
  const readback = async () => {
    await db.exec('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
    try { return await prepareIdBuzzReadback(db, intake, image, now); }
    finally { await db.exec('ROLLBACK'); }
  };
  await assert.rejects(prepareIdBuzzReadback(db, intake, image, now), /read-only transaction/);
  const prepared = await readback();
  assert.equal(prepared.apply_allowed, false);
  assert.equal(prepared.plan_hash, planHash);
  assertIdBuzzReleaseScope(prepared, prepared, planHash, now);
  assert.throws(() => assertIdBuzzReleaseScope(prepared, prepared, hash('unapproved'), now), /Wrong approved/);
  assert.throws(() => assertIdBuzzReleaseScope({ ...prepared, evidence_expires_at: now.toISOString() }, prepared, planHash, now), /expired/);
  for (const change of [
    data => { data.expected_model.updated_at = 'unexpected'; },
    data => { data.intake.market.source.content_hash = hash('Changed workbook'); },
    data => { data.targets[1].draft.price_evidence.price_valid_until = '2027-01-01'; },
    data => { data.targets[0].draft.field_evidence.dc_charge_kw.quote = 'Changed evidence'; },
  ]) {
    const alternative = structuredClone(plan);
    change(alternative);
    assert.throws(() => assertIdBuzzReleaseScope({ ...prepared, plan: alternative,
      plan_hash: publicationHash(alternative) }, prepared, planHash, now), /changed/i);
  }
  assert.deepEqual(await publicationSnapshot(db), before);
  assert.deepEqual(await publicRows(), publicBefore);
  const collision = await db.query(`INSERT INTO extracted_variant_drafts(canonical_model_id,brand,model,variant_name,source_url)
    VALUES($1,'Volkswagen','Id. Buzz',$2,$3) RETURNING id`, [m.id, intake.drafts[0].variant_name, page]);
  await assert.rejects(readback(), /existing draft needs separate review/);
  await db.query('DELETE FROM extracted_variant_drafts WHERE id=$1', [collision.rows[0].id]);
  for (const mutate of [
    v => { v.sources.find(s => s.final_url === dealer).authorization_evidence_url = page; },
    v => { v.sources.find(s => s.final_url === fr).country = 'SE'; },
    v => { v.drafts[0].facts.dc_charge_kw = 183; },
    v => { v.drafts[0].price_evidence.price_type = 'list_price'; },
    v => { v.drafts[0].price_evidence.price_valid_until = null; },
    v => { v.drafts[0].price_evidence.source_url = page; },
    v => { v.market.row.model_raw = 'ID. BUZZ CARGO'; },
  ]) {
    const invalid = structuredClone(intake); mutate(invalid);
    assert.throws(() => buildNewModelPlan(before, invalid, image, now));
  }
  assert.throws(() => buildNewModelPlan(before, intake, { ...image, full_frame: false }, now));
  assert.throws(() => buildNewModelPlan(before, intake, image, new Date(now.getTime() + 900001)));
  await assert.rejects(applyNewModelPlan({ query() { assert.fail('Local guard ran after query'); } }, plan, planHash, now), /restricted to a local PGlite/);
  await db.exec(`CREATE FUNCTION test_rollback() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Late fixture failure'; END $$;
    CREATE TRIGGER test_rollback BEFORE UPDATE ON market_models FOR EACH ROW EXECUTE FUNCTION test_rollback();`);
  await assert.rejects(applyIdBuzzRelease(db, prepared, prepared, planHash, now), /Late fixture failure/);
  assert.deepEqual(await publicationSnapshot(db), before);
  await db.exec('DROP TRIGGER test_rollback ON market_models');
  await db.exec('REVOKE SELECT ON public.public_ev_variants FROM anon');
  await assert.rejects(applyIdBuzzRelease(db, prepared, prepared, planHash, now), { code: '42501' });
  assert.deepEqual(await publicationSnapshot(db), before);
  await db.exec('GRANT SELECT ON public.public_ev_variants TO anon');
  const result = await applyIdBuzzRelease(db, prepared, prepared, planHash, now);
  assert(result.committed); assert.equal(result.variants_inserted, 2);
  const after = await publicationSnapshot(db);
  await assert.rejects(readback(), /Existing variants need a separate refresh/);
  assert.deepEqual(after.canonical_model_variants.filter(row => row.canonical_model_id === toyota.id), before.canonical_model_variants);
  assert.equal(after.canonical_models.find(row => row.id === m.id).available_confirmed, plan.expected_model.available_confirmed);
  for (const [url, country, authority] of [[fi, 'FI', 'importer'], [fr, 'FR', 'importer'], [dealer, 'SE', 'authorized_dealer']]) {
    const source = after.manufacturer_sources.find(row => row.url === url);
    assert.equal(source.country, country);
    assert.equal(source.source_authority, authority);
    assert.equal(source.authorization_evidence_url, url === dealer ? auth : null);
  }
  for (const variant of after.canonical_model_variants.filter(row => row.canonical_model_id === m.id)) {
    assert.equal(variant.price_source_url, dealer);
    assert.equal(variant.price_type, 'dealer_offer');
    assert.equal(variant.price_valid_until, '2026-12-31');
    assert.equal(variant.dc_charge_kw, 185);
    assert.equal(variant.validation_status, 'published');
  }
  for (const draft of after.extracted_variant_drafts.filter(row => row.canonical_model_id === m.id)) {
    assert.equal(draft.extraction_payload.field_evidence.tow_kg.alternative.value, 1800);
    assert.equal(draft.extraction_payload.field_evidence.dc_charge_kw.alternative.value, 183);
  }
  for (const history of before.market_model_monthly_stats) {
    assert.deepEqual(after.market_model_monthly_stats.find(row => row.id === history.id), history);
  }
  let previewRows;
  await db.exec('SET ROLE anon');
  try {
    const visible = await publicRows();
    assert.deepEqual(visible.filter(row => row.canonical_model_id === toyota.id), publicBefore);
    const candidates = visible.filter(row => row.canonical_model_id === m.id);
    assert.equal(candidates.length, 2);
    for (const row of candidates) {
      const draft = intake.drafts.find(entry => entry.variant_name === row.variant_name);
      assert(draft);
      assert.equal(row.price_type, 'dealer_offer');
      assert.equal(row.price_source_url, dealer);
      assert.equal(row.price_source_name, 'M\u00f6ller Bil');
      assert.equal(row.price_sek, draft.price_evidence.value);
      assert.equal(row.wltp_range_km, draft.facts.wltp_range_km);
      assert.equal(row.tow_kg, draft.facts.tow_kg);
      assert.equal(row.image_url, image.asset_url);
      assert.equal(row.available_confirmed, plan.expected_model.available_confirmed);
    }
    await assert.rejects(db.query('SELECT * FROM public.extracted_variant_drafts'), { code: '42501' });
    previewRows = candidates;
  } finally { await db.exec('RESET ROLE'); }
  const repeat = await applyNewModelPlan(db, plan, planHash, now);
  assert(repeat.already_applied);
  assert.deepEqual(await publicationSnapshot(db), after);
  await db.query("UPDATE manufacturer_sources SET country='SE' WHERE url=$1", [fr]);
  await assert.rejects(applyNewModelPlan(db, plan, planHash, now), /Saved field disagrees: country/);
  let previewPath;
  if (values.preview) {
    const baseline = await json('public/data/public_ev_variants.json');
    const rows = JSON.parse(JSON.stringify(previewRows));
    for (const row of rows) {
      for (const key of [...CORE_FIELDS.filter(field => field !== 'drivetrain'), 'price_sek', 'extraction_confidence']) row[key] = Number(row[key]);
      row.price_valid_until = row.price_valid_until.slice(0, 10);
    }
    const records = normalizeCatalog([...baseline.records, ...rows]);
    previewPath = join(readbackDirectory, 'id-buzz-preview-catalog.json');
    const body = JSON.stringify({ source: 'isolated_id_buzz_release_preview', production_writes: 0, publication_approved: false,
      baseline_sha256: publicationHash(baseline), plan_sha256: publicationHash(readbackPlan), records }, null, 2) + '\n';
    await writeFile(previewPath, body, { flag: 'wx' });
  }
  console.log(JSON.stringify({ id_buzz_local_publication: 'passed', variants: result.variants_inserted,
    price_and_source_attribution: true, local_only: true, rollback_and_replay: true, toyota_preserved: 3,
    public_view_and_acl: true, actual_draft_snapshot: Boolean(readbackPlan), preview_path: previewPath,
    source_review: values.review ? 'captured specifications and prices' : 'synthetic fixture', market_fixture: !review.market, remote_writes: 0 }));
} finally {
  await db.close();
}
