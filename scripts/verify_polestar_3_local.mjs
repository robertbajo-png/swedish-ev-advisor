import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { PGlite } from '@electric-sql/pglite';
import { anonymousCatalogRows, catalogWithComparableTimes, readCommittedPublicBaseline,
  readPublishedFixture, seedCatalogFixture } from './isolated_catalog_review.mjs';
import { applyNewModelPlan, buildNewModelPlan, publicationHash, publicationSnapshot } from './new_model_publication.mjs';
import { MODEL, policy, readPolestar3Capture, readPolestar3Image } from './polestar_3_publication.mjs';
import { readPolestar3Identity } from './prepare_polestar_3_readback.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { catalogHash, compareCatalogs, normalizeCatalog, variantKey } from './sync_public_catalog.mjs';

export async function readPolestar3Plan(client, intake, image, now) {
  useCalendarDateText(client);
  const identity = await readPolestar3Identity(client);
  const rows = async (table, where, args) => JSON.parse(JSON.stringify((await client.query(
    'SELECT t.* FROM public.' + table + ' t WHERE ' + where + ' ORDER BY t.id', args)).rows)).map(row => {
    for (const key of ['first_seen_month', 'last_seen_month', 'month']) if (row[key] != null) {
      assert.match(row[key], /^\d{4}-\d{2}-\d{2}(?:T00:00:00\.000Z)?$/);
      row[key] = row[key].slice(0,10);
    }
    return row;
  });
  const models = await rows('canonical_models', 't.id=$1', [identity.model.id]);
  const aliases = await rows('model_aliases', 't.id=$1', [identity.alias.id]);
  const markets = await rows('market_models', 't.id=$1', [identity.market.id]);
  const months = await rows('market_model_monthly_stats', 't.market_model_id=$1', [identity.market.id]);
  const sources = await rows('manufacturer_sources', 't.url=ANY($1::text[])', [intake.sources.map(s => s.final_url)]);
  for (const source of sources) {
    assert.deepEqual([source.brand, source.model], [MODEL.brand, MODEL.model]);
    assert([null, identity.model.id].includes(source.canonical_model_id), 'Source belongs to another model');
  }
  const plan = buildNewModelPlan({canonical_models: models, model_aliases: aliases, market_models: markets,
    market_model_monthly_stats: months, manufacturer_sources: sources, canonical_model_variants: []}, intake, image, now);
  const collision = await rows('canonical_model_variants', 't.id=$1 OR t.source_id=ANY($2::uuid[])',
    [plan.targets[0].id, sources.map(s => s.id)]);
  assert.equal(collision.length, 0, 'Target ID or existing Polestar source is used by another variant');
  assert.equal((await rows('extracted_variant_drafts', 't.source_url=$1 AND t.variant_name=$2',
    [policy.primaryUrl, intake.drafts[0].variant_name])).length, 0, 'Existing draft requires separate review');
  return plan;
}

async function readOnly(root, intake, image, now, connectorPath) {
  const connector = resolve(connectorPath ?? join(root, 'data', 'local', 'db-tools', 'source-client.mjs'));
  assert.equal(await realpath(connector), connector);
  const sourceRoot = resolve(dirname(connector), '../../..');
  assert.equal(connector, join(sourceRoot, 'data', 'local', 'db-tools', 'source-client.mjs'));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(sourceRoot));
  const {PROJECT_REF, openSourceSnapshot, closeSourceSnapshot} = await import(pathToFileURL(connector).href);
  assert.equal(PROJECT_REF, 'eutcryxbitudllcnpnex');
  let client;
  try {
    process.chdir(sourceRoot);
    client = await openSourceSnapshot();
  } finally { process.chdir(root); }
  try {
    return {plan: await readPolestar3Plan(client, intake, image, now), fixture: await readPublishedFixture(client)};
  } finally { await closeSourceSnapshot(client); }
}

export async function rehearsePolestar3({plan, fixture}, baseline, now) {
  const db = new PGlite();
  try {
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db, fixture, [plan]);
    const initial = await anonymousCatalogRows(db);
    assert(compareCatalogs(catalogWithComparableTimes(baseline), catalogWithComparableTimes(initial)).ok,
      'Live and isolated baseline rows differ');
    const before = await publicationSnapshot(db);
    const rebuilt = buildNewModelPlan(before, plan.intake, plan.image, now);
    const apply = (target = rebuilt, time = now) => applyNewModelPlan(db, target, publicationHash(target), time);
    await assert.rejects(applyNewModelPlan({query: () => assert.fail('Remote query attempted')},
      rebuilt, publicationHash(rebuilt), now), /local PGlite/);
    for (const mutate of [
      x => {x.intake.drafts[0].manufacturer_identity = 'SE|MY27|359|DE|XPFWHE';},
      x => {x.intake.drafts[0].price_evidence.value = 924000;},
      x => {x.intake.drafts[0].field_evidence.tow_kg.source_hash = '0'.repeat(64);},
      x => {x.image.source_url = 'https://example.com/other-photo';},
      x => {x.intake.market.row.fuel_type_raw = 'HYBRID';},
      x => {x.intake.market.row.registrations_last_month = 16;},
      x => {x.expected_alias.brand_raw = 'VOLVO';},
    ]) {
      const changed = structuredClone(rebuilt);
      mutate(changed);
      await assert.rejects(apply(changed));
    }
    await assert.rejects(apply(rebuilt, new Date(+now + 910000)), /Fresh/);
    assert.deepEqual(await publicationSnapshot(db), before);

    await db.exec(`CREATE FUNCTION public.polestar_3_late_failure() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (SELECT count(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id)<>1
          OR (SELECT count(*) FROM public.extracted_variant_drafts WHERE canonical_model_id=NEW.canonical_model_id)<>1
        THEN RAISE EXCEPTION 'Polestar rollback did not reach the insertion'; END IF;
        RAISE EXCEPTION 'Polestar late rollback probe';
      END $$;
      CREATE TRIGGER polestar_3_late_failure BEFORE UPDATE ON public.market_models
        FOR EACH ROW EXECUTE FUNCTION public.polestar_3_late_failure()`);
    await assert.rejects(apply(), /Polestar late rollback probe/);
    assert.deepEqual(await publicationSnapshot(db), before, 'Rollback left model, variant, source or market changes');
    assert.deepEqual(await anonymousCatalogRows(db), initial);
    await db.exec('DROP TRIGGER polestar_3_late_failure ON public.market_models');

    const receipt = await apply();
    assert.deepEqual([receipt.committed, receipt.variants_inserted, receipt.anonymous_before_commit], [true, 1, true]);
    const after = await publicationSnapshot(db);
    assert.equal((await apply()).already_applied, true);
    assert.deepEqual(await publicationSnapshot(db), after, 'Exact replay changed the database');
    const previousMonths = new Set(before.market_model_monthly_stats.map(row => row.id));
    assert.deepEqual(after.market_model_monthly_stats.filter(row => previousMonths.has(row.id)), before.market_model_monthly_stats);
    const newMonths = after.market_model_monthly_stats.filter(row => !previousMonths.has(row.id));
    const existingOctober = rebuilt.expected_monthly.some(row => row.month === '2026-10-01' && row.county === null && row.municipality === null);
    assert.deepEqual(newMonths.map(r => [r.market_model_id, r.month, r.registrations]),
      existingOctober ? [] : [[rebuilt.expected_market.id, '2026-10-01', 15]]);
    const market = after.market_models.find(row => row.id === rebuilt.expected_market.id);
    assert.deepEqual([market.first_seen_month, market.registrations_12m], [rebuilt.expected_market.first_seen_month, null],
      'Do not infer 12-month registrations from incomplete history');
    const publicRows = await anonymousCatalogRows(db);
    const targetId = receipt.canonical_variant_ids[0];
    assert.deepEqual(publicRows.filter(row => row.id !== targetId), initial, 'Existing public variants changed');
    const added = catalogWithComparableTimes(publicRows.filter(row => row.id === targetId));
    assert.equal(added.length, 1);
    return {plan: rebuilt, added, receipt};
  } finally { await db.close(); }
}

async function main() {
  const {values} = parseArgs({options: {review: {type: 'string'}, connector: {type: 'string'}}});
  assert(values.review, 'Supply --review with the fresh private Polestar 3 capture');
  const root = await realpath('.');
  const releaseRoot = await realpath('data/local/release-data');
  assert.equal(releaseRoot, join(root, 'data', 'local', 'release-data'));
  const {intake, reviewHash} = readPolestar3Capture(values.review);
  const image = readPolestar3Image();
  const now = new Date();
  const scope = await readOnly(root, intake, image, now, values.connector);
  const output = await mkdtemp(join(releaseRoot, 'polestar-3-local-'));
  const {base, proof} = await readCommittedPublicBaseline(releaseRoot, output, {imageTools: true});
  assert.equal(execFileSync('git', ['ls-remote', 'origin', 'refs/heads/main'], {encoding:'utf8', timeout:20000}).trim(),
    proof.commit + '\trefs/heads/main', 'Local origin/main is stale');
  const {plan, added, receipt} = await rehearsePolestar3(scope, base, now);
  const candidate = normalizeCatalog([...base, ...added]);
  const previousKeys = new Set(base.map(variantKey));
  assert.equal(candidate.length, base.length + 1);
  assert.deepEqual(candidate.filter(row => previousKeys.has(variantKey(row))), base);
  const report = {status: 'polestar_3_local_insertion_verified', ...proof, variants: 1, technical_fields: 9,
    candidate_count: candidate.length, candidate_sha256: catalogHash(candidate), plan_sha256: publicationHash(plan),
    review_sha256: reviewHash, anonymous_before_commit: receipt.anonymous_before_commit, exact_replay_noop: true,
    late_rollback: true, historical_months_preserved: plan.expected_monthly.length,
    publication_approved: false, photo_status: 'local_only_pending_final_attribution', production_writes: 0, paid_calls: 0};
  const save = (file, body) => writeFile(join(output, file), JSON.stringify(body, null, 2) + '\n', {flag: 'wx'});
  await save('candidate-catalog.json', {status: 'local_only', publication_approved: false, source: 'isolated_catalog_rehearsal',
    missing_view_columns: [], catalog_sha256: report.candidate_sha256, records: candidate});
  await save('plan.json', plan);
  await save('report.json', {...report, added_variant: added[0]});
  console.log(JSON.stringify({...report, output}));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(error => {
  console.error(JSON.stringify({status: 'held', reason: error.message.split('\n')[0],
    location: error.stack?.split('\n').find(line => /^\s+at .*\.mjs:\d+:\d+/.test(line))?.trim(), production_writes: 0}));
  process.exitCode = 1;
});
