import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {realpath} from 'node:fs/promises';
import {basename,dirname,join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {anonymousCatalogRows,catalogWithComparableTimes,readPublishedFixture,seedCatalogFixture} from './isolated_catalog_review.mjs';
import {catalogConnectorPath,openCatalogSnapshot} from './local_catalog_connector.mjs';
import {compareCatalogs} from './sync_public_catalog.mjs';

export const MACAN_MODEL = Object.freeze({
  brand: 'Porsche', model: 'Macan', normalized_brand: 'porsche', normalized_model: 'macan', body_type: 'SUV',
});
const raw = {brand_raw: 'PORSCHE', model_raw: 'MACAN', fuel_type_raw: 'EL'};
const october = '2026-10-01';
const fields = (row, expected) => {
  for (const [key, value] of Object.entries(expected)) assert.equal(row?.[key], value, 'Macan scope changed: ' + key);
};
const one=(rows, label)=>{
  assert.equal(rows.length, 1, 'Require one exact Macan ' + label);
  return rows[0];
};

export function verifyMacanScope({models, aliases, market, months, variants, drafts}, incoming) {
  fields(incoming, {...raw, normalized_brand: 'porsche', normalized_model: 'macan',
    last_seen_month: october, registrations_last_month: 43, registrations_ytd: 367, needs_mapping: false});
  const m = one(models, 'canonical draft');
  fields(m, {brand: 'Porsche', model: 'Macan', normalized_brand: 'porsche',
    normalized_model: 'macan', validation_status: 'draft'});
  assert([null, 'SUV'].includes(m.body_type) && !m.image_url, 'Existing Macan equipment or photo requires review');
  assert(variants.length===0 && drafts.length===0, 'Existing Macan variant or extraction needs separate review');
  const a = one(aliases, 'alias');
  fields(a, {brand_raw: raw.brand_raw, model_raw: raw.model_raw, normalized_brand: 'porsche', normalized_model: 'macan',
    canonical_model_id: m.id, alias_rule: 'mobility_sweden_exact_raw_name', model_group: null, needs_mapping: false});
  assert(Number(a.confidence)>=0.92, 'Macan alias is not resolved');
  const row = one(market.filter(r => r.fuel_type_raw==='EL'), 'BEV market row');
  fields(row, {...raw, normalized_brand: 'porsche', normalized_model: 'macan',
    model_group: null, needs_mapping: false, source_name: 'Mobility Sweden'});
  assert([null,m.id].includes(row.canonical_model_id), 'Macan market row belongs to another model');
  assert(!market.some(r => r!==row && r.canonical_model_id===m.id), 'Conflicting linked Macan fuel or market identity');
  assert(/^\d{4}-\d{2}-01$/.test(row.first_seen_month) && /^\d{4}-\d{2}-01$/.test(row.last_seen_month) &&
    row.first_seen_month<=row.last_seen_month && row.last_seen_month<=october, 'A newer or invalid Macan market row needs review');
  const national = new Map();
  for (const month of months) {
    fields(month, {...raw, market_model_id: row.id});
    assert(Number.isSafeInteger(month.registrations) && month.registrations>=0, 'Invalid Macan registrations');
    assert(/^\d{4}-\d{2}-01$/.test(month.month) && month.month<=october, 'Unexpected Macan historical month');
    if (month.county!==null || month.municipality!==null) continue;
    assert(!national.has(month.month), 'Conflicting national Macan month');
    national.set(month.month, month.registrations);
  }
  assert(national.has(row.first_seen_month), 'The first Macan national month is missing');
  if (national.has(october)) assert.equal(national.get(october), incoming.registrations_last_month, 'Conflicting saved October Macan count');
  return {expected_model: m, expected_alias: a, expected_market: row, expected_monthly: months};
}

export async function readMacanScope(db, incoming) {
  assert.equal((await db.query('SHOW transaction_read_only')).rows[0].transaction_read_only, 'on');
  assert.equal((await db.query('SHOW transaction_isolation')).rows[0].transaction_isolation, 'repeatable read');
  const rows = async(sql, args) => (await db.query(sql, args)).rows.map(({row}) => row);
  const terms = ['porsche',['macan','macan electric']];
  const where = 'normalized_brand=$1 AND normalized_model=ANY($2::text[])';
  const models = await rows('SELECT to_jsonb(m) AS row FROM public.canonical_models m WHERE '+where+' ORDER BY id', terms);
  const m = one(models, 'canonical draft');
  const args = [...terms,m.id];
  const aliases = await rows('SELECT to_jsonb(a) AS row FROM public.model_aliases a WHERE ('+where+') OR canonical_model_id=$3 ORDER BY id', args);
  const market = await rows('SELECT to_jsonb(m) AS row FROM public.market_models m WHERE ('+where+') OR canonical_model_id=$3 ORDER BY id', args);
  const ids = market.filter(r => r.normalized_model==='macan' && r.fuel_type_raw==='EL').map(r=>r.id);
  const months = await rows('SELECT to_jsonb(s) AS row FROM public.market_model_monthly_stats s WHERE market_model_id=ANY($1::uuid[]) ORDER BY id', [ids]);
  const variants = await rows('SELECT to_jsonb(v) AS row FROM public.canonical_model_variants v WHERE canonical_model_id=$1 ORDER BY id', [m.id]);
  const drafts = await rows('SELECT to_jsonb(d) AS row FROM public.extracted_variant_drafts d WHERE canonical_model_id=$1 ORDER BY id', [m.id]);
  return verifyMacanScope({models,aliases,market,months,variants,drafts}, incoming);
}

async function rehearseMacanScope(fixture, publicRows, expected, incoming) {
  const {PGlite}=await import('@electric-sql/pglite');
  const db = new PGlite();
  try {
    await db.exec("SET TIME ZONE 'UTC'");
    await seedCatalogFixture(db,fixture,[{...expected,expected_sources:[]}]);
    const before=await anonymousCatalogRows(db);
    assert(compareCatalogs(catalogWithComparableTimes(publicRows),catalogWithComparableTimes(before)).ok,
      'Isolated Macan baseline differs from the canonical public view');
    await db.exec('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
    try {
      const replay=await readMacanScope(db,incoming);
      assert.deepEqual(replay,expected,'Isolated Macan scope differs from the real saved history');
    } finally {
      await db.exec('ROLLBACK');
    }
    assert.deepEqual(await anonymousCatalogRows(db),before,'Read-only Macan rehearsal changed public rows');
    return {isolated_identity_verified:true,public_variants_unchanged:before.length};
  } finally {
    await db.close();
  }
}

async function main() {
  const {values} = parseArgs({options:{market:{type:'string'},'client-module':{type:'string'},rehearse:{type:'boolean'}}});
  assert(values.market, 'Supply the exact Macan market packet');
  const root = await realpath('.');
  const release = join(root,'data','local','release-data');
  const packet = await realpath(values.market);
  assert.equal(packet,resolve(values.market),'Require the original unlinked packet');
  assert.equal(dirname(packet),release);
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(packet));
  assert.match(basename(packet),/^porsche-macan-market-[a-z0-9_]+$/);
  const evidence = JSON.parse(execFileSync(process.execPath,['scripts/run_python.mjs','scripts/porsche_macan_market.py',
    '--replay',packet],{cwd:root,encoding:'utf8',timeout:120000,windowsHide:true}));
  assert.deepEqual([evidence.status,evidence.publication_approved,evidence.database_writes],
    ['macan_market_evidence_verified_private',false,0]);
  const snapshot = await openCatalogSnapshot(await catalogConnectorPath(root,values['client-module']));
  let scope,fixture,publicRows;
  try {
    scope=await readMacanScope(snapshot.client,evidence.row);
    if(values.rehearse){
      fixture=await readPublishedFixture(snapshot.client);
      publicRows=(await snapshot.client.query('SELECT to_jsonb(v) AS row FROM public.public_ev_variants v ORDER BY id'))
        .rows.map(({row})=>row);
    }
  } finally {
    await snapshot.close();
  }
  const local=values.rehearse?await rehearseMacanScope(fixture,publicRows,scope,evidence.row):{};
  console.log(JSON.stringify({status:'macan_scope_verified_read_only',model:scope.expected_model.model,
    existing_month:scope.expected_market.last_seen_month,history_rows:scope.expected_monthly.length,
    candidate_month:evidence.row.last_seen_month,candidate_registrations:evidence.row.registrations_last_month,
    publication_approved:false,production_writes:0,...local}));
}

if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href)await main().catch(error=>{
  // Expose gate failures without returning connection or query details.
  console.error(JSON.stringify({status:'held',reason:error.code==='ERR_ASSERTION'
    ?error.message.split('\n')[0]:'Macan scope could not be verified',production_writes:0}));
  process.exitCode=1;
});
