import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { PGlite } from '@electric-sql/pglite';
import { pumaIdentitySnapshot, readPumaIdentity } from './ford_puma_identity.mjs';
import { policy, readPumaCapture, readPumaImage } from './ford_puma_gen_e_publication.mjs';
import { anonymousCatalogRows, catalogWithComparableTimes, readCommittedPublicBaseline,
  readPublishedFixture, seedCatalogFixture } from './isolated_catalog_review.mjs';
import { applyPumaAtomicLocally, applyPumaRelease, buildNewModelPlan, publicationHash, publicationSnapshot } from './new_model_publication.mjs';
import { assertPumaPriceMigration, pumaApprovalHash } from './ford_puma_release_scope.mjs';
import { runPumaRelease } from './publish_approved_ford_puma.mjs';
import { catalogHash, compareCatalogs, normalizeCatalog, variantKey } from './sync_public_catalog.mjs';

async function readOnly(root, intake) {
  const connector = join(root, 'data', 'local', 'db-tools', 'source-client.mjs');
  assert.equal(await realpath(connector), connector);
  const {openSourceSnapshot, closeSourceSnapshot} = await import(pathToFileURL(connector).href);
  const client = await openSourceSnapshot();
  try {
    const identity = await readPumaIdentity(client);
    const {rows} = await client.query('SELECT to_jsonb(s) AS row FROM public.manufacturer_sources s WHERE url=ANY($1::text[]) ORDER BY id',
      [intake.sources.map(s => s.final_url)]);
    const existingSources = rows.map(r => r.row);
    for (const source of existingSources) {
      assert.deepEqual([source.brand, source.model, source.canonical_model_id], ['Ford', 'Puma Gen-E', null],
        'A Puma source already belongs to another identity');
    }
    const drafts = await client.query('SELECT id FROM public.extracted_variant_drafts WHERE source_url=$1 AND variant_name=ANY($2::text[])',
      [policy.primaryUrl, intake.drafts.map(d => d.variant_name)]);
    assert.equal(drafts.rows.length, 0, 'Existing Puma extraction needs separate review');
    const published = await client.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id');
    return {identity, existingSources, fixture: await readPublishedFixture(client),
      databaseCatalog: catalogWithComparableTimes(published.rows.map(r => r.row))};
  } finally { await closeSourceSnapshot(client); }
}

async function rehearseApprovedRunner(db, reviewed, packet, baseline, now) {
  // Code/CDN prerequisites are simulated here; the SQL writer is not.
  const commit = reviewed.baseline_commit;
  const approval = pumaApprovalHash(reviewed, commit);
  const args = {reviewed, commit, approval};
  const journal = {};
  let writes = 0;
  const io = {
    now: () => now,
    verifyCode: async (candidate, code) => {assert.equal(candidate, commit); assert.deepEqual(code, reviewed.code);},
    verifyMedia: async (media, image) => { assert.deepEqual(media, reviewed.media); assert.deepEqual(image, packet.image); },
    baseline: () => ({records: baseline}), liveBaseline: () => baseline,
    publicRows: async () => (await db.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id')).rows.map(r => r.row),
    freshSource: () => packet.intake,
    async openSnapshot() { await db.exec('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY'); return db; },
    readState: async (client) => ({identity: await readPumaIdentity(client), expected_sources: packet.expected_sources}),
    async closeSnapshot(client) {if (client.isInTransaction()) await client.exec('ROLLBACK');},
    saveAttempt: async attempt => { assert(!journal.attempt, 'An existing journal must not be overwritten'); journal.attempt = attempt; },
    async commit(client, fresh, token) {
      writes++;
      await client.exec('ROLLBACK');
      return applyPumaRelease(client, reviewed, fresh, commit, token, now);
    },
    saveCommit: async receipt => { journal.receipt = receipt; },
    readJournal: async () => journal,
    saveExport: async payload => { journal.export = payload; },
  };
  await assert.rejects(runPumaRelease({...args, mode: 'commit', approval: '0'.repeat(64)}, io), /explicit approved hash/);
  const check = await runPumaRelease({...args, mode: 'check'}, io);
  assert.equal(check.status, 'ready_for_explicit_owner_approval');
  assert.equal(writes, 0);
  const changed = structuredClone(packet.intake);
  changed.drafts[0].price_evidence.value += 1000;
  await assert.rejects(runPumaRelease({...args, mode: 'commit'}, {...io, freshSource: () => changed}));
  assert.equal(writes, 0);
  const written = await runPumaRelease({...args, mode: 'commit'}, io);
  assert.deepEqual([written.status, written.added, written.deployed], ['committed_private_export_pending', 2, false]);
  await assert.rejects(runPumaRelease({...args, mode: 'commit'}, io), /Anonymous Supabase baseline changed/);
  assert.equal(writes, 1);
  const staged = await runPumaRelease({...args, mode: 'export'}, io);
  assert.equal(staged.status, 'private_export_verified');
  assert.equal(journal.export.records.length, baseline.length + 2);
  const driftRows = (await io.publicRows()).map(row => row.brand === 'Ford' && row.model === 'Puma Gen-E' ? row : {...row, seats: null});
  await assert.rejects(runPumaRelease({...args, mode: 'export'}, {...io, publicRows: () => driftRows}), /Existing public rows changed/);
  return journal.receipt.result;
}

export async function rehearse(scope, intake, image, base, now, reviewed) {
  const db = new PGlite();
  try {
    // Compare copied timestamptz values in the same zone as the source snapshot.
    await db.exec("SET TIME ZONE 'UTC'");
    const {identity, existingSources, fixture} = scope;
    await seedCatalogFixture(db, fixture, identity.expected.market.map(market => ({
      expected_model: identity.expected.models[0], expected_alias: identity.expected.aliases[0],
      expected_market: market, expected_monthly: identity.expected.months.filter(s => s.market_model_id === market.id),
      expected_sources: existingSources,
    })));
    const initial = await anonymousCatalogRows(db);
    const unmigrated = await publicationSnapshot(db);
    await assert.rejects(assertPumaPriceMigration(db), /Migration 026 is not installed/);
    const migration = await readFile(new URL('../database/migrations/026_manufacturer_from_price.sql', import.meta.url), 'utf8');
    await db.exec(migration);
    await db.exec(migration);
    assert.deepEqual(await publicationSnapshot(db), unmigrated, 'The starting-price migration changed catalog rows');
    assert.deepEqual(await anonymousCatalogRows(db), initial, 'The migration changed public projection or privileges');
    assert(compareCatalogs(catalogWithComparableTimes(base), catalogWithComparableTimes(initial)).ok,
      'Isolated baseline differs from the released catalog');
    const unstaged = await publicationSnapshot(db);
    assert.throws(() => buildNewModelPlan(unstaged, intake, image, now), /existing canonical discovery draft/);
    const packet = {status: 'puma_atomic_rehearsal_only', identity, intake, image,
      expected_sources: unstaged.manufacturer_sources.filter(row => intake.sources.some(s => s.final_url === row.url)),
      baseline_sha256: catalogHash(catalogWithComparableTimes(base)), publication_approved: false};
    const hash = publicationHash(packet);
    const apply = (candidate = packet, at = now) => applyPumaAtomicLocally(db, candidate, publicationHash(candidate), at);
    await assert.rejects(applyPumaAtomicLocally({query: () => assert.fail('Remote query attempted')}, packet, hash, now), /local PGlite/);
    await assert.rejects(apply({...packet, baseline_sha256: '0'.repeat(64)}), /catalog changed/);
    const wrongFuel = structuredClone(packet);
    wrongFuel.identity.expected.market.find(r => r.id === identity.market_id).fuel_type_raw = 'BENSIN';
    await assert.rejects(apply(wrongFuel), /BEV market row/);
    const wrongPrice = structuredClone(intake);
    wrongPrice.drafts[0].price_evidence.value = 397000;
    await assert.rejects(apply({...packet, intake: wrongPrice}));
    const wrongType = structuredClone(intake);
    wrongType.drafts[0].price_evidence.price_type = 'list_price';
    await assert.rejects(apply({...packet, intake: wrongType}), /starting price, not list price/);
    await assert.rejects(apply({...packet, image: {...image, model_key: 'ford|puma'}}));
    await assert.rejects(apply(packet, new Date(+now + 900001)), /Fresh source capture/);
    await assert.rejects(applyPumaAtomicLocally(db, packet, '0'.repeat(64), now), /packet changed/);
    assert.deepEqual(await publicationSnapshot(db), unstaged, 'Rejected candidates changed the local database');
    await db.exec("CREATE FUNCTION public.puma_late_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN " +
      "IF OLD.canonical_model_id IS NULL THEN RETURN NEW; END IF; " +
      "IF (SELECT COUNT(*) FROM public.canonical_model_variants WHERE canonical_model_id=NEW.canonical_model_id)<>2 " +
      "OR (SELECT COUNT(*) FROM public.model_aliases WHERE canonical_model_id=NEW.canonical_model_id)<>1 THEN " +
      "RAISE EXCEPTION 'Puma rollback was triggered before the model, alias and both variants existed'; END IF; " +
      "RAISE EXCEPTION 'Puma late atomic rollback probe'; END $$; " +
      "CREATE TRIGGER puma_late_failure BEFORE UPDATE ON public.market_models FOR EACH ROW EXECUTE FUNCTION public.puma_late_failure()");
    await assert.rejects(apply(), /Puma late atomic rollback probe/);
    assert.deepEqual(await pumaIdentitySnapshot(db), identity.expected, 'Rollback left an identity or market link behind');
    assert.deepEqual(await publicationSnapshot(db), unstaged, 'Rollback left variant, source, alias or staging rows behind');
    assert.deepEqual(await anonymousCatalogRows(db), initial, 'Rollback changed anonymous results');
    await db.exec('DROP TRIGGER puma_late_failure ON public.market_models');
    const inserted = reviewed ? await rehearseApprovedRunner(db, reviewed, packet, base, now) : await apply();
    const plan = inserted.variant_plan;
    assert.deepEqual([inserted.variants_inserted, inserted.anonymous_before_commit, inserted.atomic_identity], [2, true, true]);
    assert.deepEqual([plan.expected_model.id, plan.expected_alias.id, plan.expected_market.id],
      [inserted.model_id, inserted.alias_id, identity.market_id]);
    const after = await publicationSnapshot(db);
    assert.equal((await apply()).already_applied, true);
    assert.deepEqual(await publicationSnapshot(db), after, 'Exact replay changed rows');
    const [id] = inserted.canonical_variant_ids;
    await assert.rejects(db.query('UPDATE public.canonical_model_variants SET price_sek=399000 WHERE id=$1', [id]), {code: '23514'});
    await assert.rejects(db.query("UPDATE public.canonical_model_variants SET price_source_hash=NULL WHERE id=$1", [id]), {code: '23514'});
    await assert.rejects(db.query("UPDATE public.extracted_variant_drafts SET extraction_payload='{}' WHERE canonical_model_id=$1", [inserted.model_id]), {code: '23514'});
    await assert.rejects(db.query("UPDATE public.extracted_variant_drafts SET price_valid_until='2026-12-31' WHERE canonical_model_id=$1", [inserted.model_id]), {code: '23514'});
    assert.deepEqual(await publicationSnapshot(db), after, 'Invalid price evidence changed rows');
    const previousMonths = new Set(unstaged.market_model_monthly_stats.map(r => r.id));
    assert.deepEqual(after.market_model_monthly_stats.filter(r => previousMonths.has(r.id)), unstaged.market_model_monthly_stats);
    const actual = await anonymousCatalogRows(db);
    const targetIds = new Set(plan.targets.map(t => t.id));
    const added = catalogWithComparableTimes(actual.filter(r => targetIds.has(r.id)));
    assert.deepEqual(actual.filter(r => !targetIds.has(r.id)), initial, 'The Gen-E trial changed earlier variants');
    assert.equal(added.length, 2);
    return {packet, plan, hash, added};
  } finally { await db.close(); }
}

async function main() {
  const {values, positionals} = parseArgs({options: {review: {type: 'string'}, 'release-scope': {type: 'string'}}, allowPositionals: true});
  assert(values.review && !positionals.length, 'Supply the fresh private Puma review with --review');
  const root = await realpath('.');
  const evidence = await realpath('data/local/release-data');
  assert.equal(evidence, join(root, 'data', 'local', 'release-data'));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(root));
  let reviewed;
  if (values['release-scope']) {
    const path = resolve(values['release-scope']);
    assert.equal(await realpath(path), path);
    assert.equal(dirname(dirname(path)), evidence);
    assert.match(basename(dirname(path)), /^ford-puma-release-review-[a-z0-9]+$/i);
    assert.equal(basename(path), 'scope.json');
    reviewed = JSON.parse(await readFile(path, 'utf8'));
  }
  const {intake, reviewHash} = readPumaCapture(values.review);
  const image = readPumaImage();
  const scope = await readOnly(root, intake);
  const output = await mkdtemp(join(evidence, 'ford-puma-local-'));
  const {base, proof} = await readCommittedPublicBaseline(evidence, output, {imageTools: true});
  assert.equal(execFileSync('git', ['ls-remote', 'origin', 'refs/heads/main'], {encoding: 'utf8', timeout: 20000}).trim(),
    proof.commit + '\trefs/heads/main', 'Local origin/main is not the current release revision');
  const parity = compareCatalogs(catalogWithComparableTimes(base), scope.databaseCatalog);
  if (!parity.ok) {
    const {quarantine: _quarantine, ...summary} = parity;
    await writeFile(join(output, 'baseline-drift.json'), JSON.stringify(summary, null, 2) + '\n', {flag: 'wx'});
    throw new Error('Released export differs from the canonical view: ' + JSON.stringify(summary));
  }
  const {packet, plan, hash, added} = await rehearse(scope, intake, image, base, new Date(), reviewed);
  const candidate = normalizeCatalog([...base, ...added]);
  assert.equal(candidate.length, base.length + 2);
  const oldKeys = new Set(base.map(variantKey));
  assert.deepEqual(candidate.filter(row => oldKeys.has(variantKey(row))), base);
  const report = {status: 'puma_local_insertion_verified', ...proof, variants: 2, fields: 18,
    preserved_market_months: scope.identity.bev_historical_rows, candidate_count: candidate.length,
    candidate_sha256: catalogHash(candidate), plan_sha256: hash, review_sha256: reviewHash,
    exact_replay_noop: true, late_rollback: true, atomic_identity: true, anonymous_before_commit: true,
    starting_price_migration_local: true, invalid_price_evidence_rejected: true,
    ...(reviewed ? {approved_runner_with_local_database: true, private_export_verified: true, production_prerequisites_simulated: true} : {}),
    publication_approved: false, production_writes: 0, paid_calls: 0};
  const save = (name, data) => writeFile(join(output, name), JSON.stringify(data, null, 2) + '\n', {flag: 'wx'});
  await save('candidate-catalog.json', {status: 'local_only', publication_approved: false, records: candidate});
  await save('puma-plan.json', plan);
  await save('atomic-packet.json', packet);
  await save('report.json', report);
  console.log(JSON.stringify({...report, output}));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main().catch(error => {
  console.error(JSON.stringify({status: 'held', reason: error.message.split('\n')[0],
    location: error.stack?.split('\n').find(line => /^\s+at .*\.mjs:\d+:\d+/.test(line))?.trim(),
    production_writes: 0}));
  process.exitCode = 1;
});
