import assert from 'node:assert/strict';
import { mkdtemp, realpath, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { PGlite } from '@electric-sql/pglite';
import { anonymousCatalogRows, catalogWithComparableTimes, readCommittedPublicBaseline,
  readPublishedFixture, seedCatalogFixture } from './isolated_catalog_review.mjs';
import { applyNewModelPlan, buildNewModelPlan, publicationHash, publicationSnapshot,
  validateNewModelIntake } from './new_model_publication.mjs';
import { ADAPTER, readEvolutionCapture, readEvolutionImage } from './renault_4_evolution_publication.mjs';
import { ADAPTER as PAIR_ADAPTER, readPairCapture, renault4LocatorRow } from './renault_4_pair_publication.mjs';
import { useCalendarDateText } from './refresh_kia_specs.mjs';
import { catalogHash, compareCatalogs } from './sync_public_catalog.mjs';

function appointmentSource(intake, now) {
  assert([ADAPTER, PAIR_ADAPTER].includes(intake.adapter),'Require an exact local Renault 4 scope');
  assert(validateNewModelIntake(intake,now).localOnly);
  const sources = intake.sources.filter(row=>row.shared);
  assert.equal(sources.length,1);
  return sources[0];
}

function checkShared(row, source) {
  for (const [key,value] of Object.entries(renault4LocatorRow(source)))
    assert.equal(row[key],value,'Shared Renault locator conflict: '+key);
}

export async function readRenault4Scope(client, intake, image, now) {
  assert.equal((await client.query('SHOW transaction_read_only')).rows[0].transaction_read_only,'on');
  assert.equal((await client.query('SHOW transaction_isolation')).rows[0].transaction_isolation,'repeatable read');
  const locator = appointmentSource(intake,now);
  const query = async (sql,args) => JSON.parse(JSON.stringify((await client.query(sql,args)).rows));
  const key = ['renault','4'];
  const canonical_models = await query('SELECT * FROM public.canonical_models WHERE normalized_brand=$1 AND normalized_model=$2',key);
  assert.equal(canonical_models.length,1,'One existing R4 draft required');
  const [model] = canonical_models;
  assert.equal(model.validation_status,'draft');
  const model_aliases = await query('SELECT * FROM public.model_aliases WHERE normalized_brand=$1 AND normalized_model=$2',key);
  const market_models = await query("SELECT * FROM public.market_models WHERE normalized_brand=$1 AND normalized_model=$2 AND fuel_type_raw='EL'",key);
  assert.equal(market_models.length,1,'One exact R4 market row required');
  const market_model_monthly_stats = await query('SELECT * FROM public.market_model_monthly_stats WHERE market_model_id=$1 ORDER BY id',[market_models[0].id]);
  const current = market_model_monthly_stats.filter(r=>r.month===intake.market.row.last_seen_month && r.county===null && r.municipality===null);
  assert(current.length<=1);
  if (current.length) assert.equal(current[0].registrations,intake.market.row.registrations_last_month);
  const urls = intake.sources.map(row=>row.final_url);
  const manufacturer_sources = await query('SELECT * FROM public.manufacturer_sources WHERE url=ANY($1::text[]) ORDER BY id',[urls]);
  const found = manufacturer_sources.find(r=>r.url===locator.final_url);
  for (const row of manufacturer_sources) {
    if (row.url===locator.final_url) checkShared(row,locator);
    else {
      assert.equal(row.brand,model.brand);
      assert.equal(row.model,model.model);
      assert([null,model.id].includes(row.canonical_model_id),'Exact source linked elsewhere');
    }
  }
  const canonical_model_variants = await query('SELECT * FROM public.canonical_model_variants WHERE canonical_model_id=$1',[model.id]);
  const plan = buildNewModelPlan({canonical_models, model_aliases, market_models, market_model_monthly_stats,
    manufacturer_sources, canonical_model_variants},intake,image,now);
  const exclusive = manufacturer_sources.filter(row=>row.url!==locator.final_url).map(row=>row.id);
  assert.equal((await client.query('SELECT id FROM public.canonical_model_variants WHERE id=ANY($1::uuid[]) OR source_id=ANY($2::uuid[])',
    [plan.targets.map(t=>t.id),exclusive])).rows.length,0,'Target ID or model source already used');
  assert.equal((await client.query('SELECT id FROM public.extracted_variant_drafts WHERE source_url=ANY($1::text[]) AND variant_name=ANY($2::text[])',
    [urls,intake.drafts.map(d=>d.variant_name)])).rows.length,0,'An existing draft needs separate review');
  return {plan,found:!!found};
}

async function registerLocalLocator(db, intake, now) {
  assert(db instanceof PGlite,'Local PGlite only');
  const source = appointmentSource(intake,now);
  const expected = renault4LocatorRow(source);
  await db.query('BEGIN ISOLATION LEVEL SERIALIZABLE READ WRITE');
  try {
    await db.query('SELECT pg_advisory_xact_lock(7240040)');
    const {rows:[old]} = await db.query('SELECT * FROM public.manufacturer_sources WHERE url=$1 FOR UPDATE',[source.final_url]);
    if (old) checkShared(old,source);
    else {
      const record = {...expected,title:'Renault Sverige: officiellt aterforsaljarregister',source_name:'Renault Sverige',
        fetched_at:source.fetched_at,verified_at:source.fetched_at,extraction_status:'validated'};
      const values = Object.values(record);
      const {rows:[inserted]} = await db.query(`INSERT INTO public.manufacturer_sources(${Object.keys(record).join(',')})
        VALUES(${values.map((_,i)=>'$'+(i+1)).join(',')}) RETURNING *`,values);
      checkShared(inserted,source);
    }
    await db.query('COMMIT');
    return !old;
  } catch (error) {await db.query('ROLLBACK');throw error;}
}

async function rehearse(fixture, plan, found, base, now) {
  const db = new PGlite();
  const {intake,image} = plan;
  const locator = appointmentSource(intake,now);
  try {
    await seedCatalogFixture(db,fixture,[plan]);
    const initial = await anonymousCatalogRows(db);
    assert(compareCatalogs(catalogWithComparableTimes(base),catalogWithComparableTimes(initial)).ok,
      'Committed, live and locally projected catalog must agree');
    const before = await publicationSnapshot(db);
    assert.deepEqual(buildNewModelPlan(before,intake,image,now),plan);
    if (!found) {
      await assert.rejects(applyNewModelPlan(db,plan,publicationHash(plan),now));
      assert.deepEqual(await publicationSnapshot(db),before);
    }
    assert.equal(await registerLocalLocator(db,intake,now),!found);
    const registered = await publicationSnapshot(db);
    const entry = registered.manufacturer_sources.find(row=>row.url===locator.final_url);
    const prior = before.manufacturer_sources.find(row=>row.url===locator.final_url);
    if (found) assert.deepEqual(entry,prior);
    assert.deepEqual({...registered,manufacturer_sources:registered.manufacturer_sources.filter(row=>found||row.id!==entry.id)},before);
    assert.deepEqual(await anonymousCatalogRows(db),initial,'Source setup changed the public catalog');
    assert.equal(await registerLocalLocator(db,intake,now),false);
    assert.deepEqual(await publicationSnapshot(db),registered,'Exact source replay wrote data');
    await db.query('UPDATE public.manufacturer_sources SET content_hash=$1 WHERE id=$2',['0'.repeat(64),entry.id]);
    const conflicting = await publicationSnapshot(db);
    await assert.rejects(registerLocalLocator(db,intake,now),/locator conflict: content_hash/);
    assert.deepEqual(await publicationSnapshot(db),conflicting);
    await db.query('UPDATE public.manufacturer_sources SET content_hash=$1 WHERE id=$2',[locator.content_hash,entry.id]);
    assert.deepEqual(await publicationSnapshot(db),registered);
    const localPlan = buildNewModelPlan(registered,intake,image,now);
    const digest = publicationHash(localPlan);
    if (intake.adapter===PAIR_ADAPTER) {
      await db.exec(`CREATE FUNCTION fail_r4_after_both_variants() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (SELECT COUNT(*) FROM public.canonical_model_variants
              WHERE canonical_model_id=NEW.canonical_model_id) <> 2 THEN
            RAISE EXCEPTION 'Expected both scoped R4 rows before the rollback probe';
          END IF;
          RAISE EXCEPTION 'Local paired R4 late failure';
        END $$;
        CREATE TRIGGER r4_pair_failure BEFORE UPDATE ON public.market_models
        FOR EACH ROW EXECUTE FUNCTION fail_r4_after_both_variants();`);
      await assert.rejects(applyNewModelPlan(db,localPlan,digest,now),/Local paired R4 late failure/);
      assert.deepEqual(await publicationSnapshot(db),registered,'Paired transaction left a partial write');
      assert.deepEqual(await anonymousCatalogRows(db),initial,'Paired rollback changed public rows');
      await db.exec('DROP TRIGGER r4_pair_failure ON public.market_models');
    }
    const receipt = await applyNewModelPlan(db,localPlan,digest,now);
    assert(receipt.anonymous_before_commit && receipt.variants_inserted===localPlan.targets.length);
    const after = await anonymousCatalogRows(db);
    const ids = new Set(localPlan.targets.map(t=>t.id));
    const additions = after.filter(r=>ids.has(r.id));
    assert.equal(additions.length,ids.size);
    assert.deepEqual(after.filter(r=>!ids.has(r.id)),initial);
    const persisted = await publicationSnapshot(db);
    assert.deepEqual(persisted.manufacturer_sources.find(r=>r.id===entry.id),entry);
    assert.equal((await applyNewModelPlan(db,localPlan,digest,now)).already_applied,true);
    assert.deepEqual(await publicationSnapshot(db),persisted);
    return {candidate_count:after.length,candidate_sha256:catalogHash(catalogWithComparableTimes(after)),
      ...(ids.size===1?{added_variant:additions[0]}:{added_variants:additions,paired_late_rollback:true}),
      registered_source:renault4LocatorRow(locator),locator_hash:locator.content_hash};
  } finally {await db.close();}
}

async function main() {
  const {values} = parseArgs({options:{review:{type:'string'},pair:{type:'boolean'}}});
  assert(values.review,'Supply a fresh, private Renault 4 capture');
  const {intake} = (values.pair?readPairCapture:readEvolutionCapture)(values.review);
  const image = readEvolutionImage();
  const root = await realpath('.');
  const releaseRoot = join(root,'data','local','release-data');
  assert.equal(await realpath(releaseRoot),releaseRoot);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(releaseRoot));
  const connector = join(root,'data','local','db-tools','source-client.mjs');
  assert.equal(await realpath(connector),connector);
  const {openSourceSnapshot,closeSourceSnapshot} = await import(pathToFileURL(connector).href);
  const now = new Date();
  appointmentSource(intake,now);
  const client = await openSourceSnapshot();
  let scope,fixture;
  try {
    useCalendarDateText(client);
    scope = await readRenault4Scope(client,intake,image,now);
    fixture = await readPublishedFixture(client);
  } finally {await closeSourceSnapshot(client);}
  const output = await mkdtemp(join(releaseRoot,'renault-4-readback-'));
  const {base,proof} = await readCommittedPublicBaseline(releaseRoot,output);
  const {registered_source,added_variant,added_variants,...result} = await rehearse(fixture,scope.plan,scope.found,base,now);
  const report = {status:values.pair?'source_setup_and_pair_passed_local_only':'source_setup_and_evolution_passed_local_only',...proof,...result,
    production_locator_present:scope.found,local_source_conflict_and_replay:true,
    prior_catalog_preserved:true,production_writes:0,paid_calls:0,publication_approved:false};
  await writeFile(join(output,'report.json'),JSON.stringify({...report,registered_source,added_variant,added_variants},null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({...report,output}));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href===import.meta.url) await main().catch(error=>{
  console.error(JSON.stringify({status:'held',error:error.name,code:error.code??null,
    ...(error.code==='ERR_ASSERTION'?{reason:error.message.split('\n')[0]}:{}),production_writes:0}));
  process.exitCode=1;
});
