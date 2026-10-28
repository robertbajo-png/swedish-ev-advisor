import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';
import { validateProfile, buildReplacementPlan, replacementPlanHash, retiredSlug, RETIRED, POLICY, applyReplacementPlan, recollectedFacts } from './current_variant_sync.mjs';
import { validateVehicleRedirects, vehicleRedirect, catalogQuery } from '../src/vehicle-redirects.js';

const now = new Date('2026-10-27T20:00:00Z');
const kia = (model, variant) => ({ brand: 'Kia', model, variant_name: variant, price_sek: 599000, price_type: 'list_price',
  price_valid_until: null, wltp_range_km: null, wltp_consumption_kwh_100km: null, battery_kwh: null,
  dc_charge_kw: null, ac_charge_kw: null, boot_liters: null, tow_kg: null, seats: null, drivetrain: null,
  source_url: 'https://www.kia.com/se/kopa/prislista/', source_hash: 'a'.repeat(64), source_authority: 'manufacturer',
  source_name: 'Kia Sverige', fetched_at: now.toISOString(), extraction_confidence: 0.99,
  source_quote: `Prislista för Kia ${model.toUpperCase()} | ${variant} | Rek. cirkapris inkl. moms | 599 000 kr` });
const finish = (row, adapter) => ({...row, extraction_payload: { policy: POLICY, adapter,
  field_evidence: { price_sek: { quote: row.source_quote, variant: row.variant_name, source_url: row.source_url, source_hash: row.source_hash } } } });
const row = finish(kia('Ev3', 'EV3 FWD'), 'kia_sweden_exact_price_row_v1');
validateProfile(row, now);
for (const patch of [{price_sek: 3990}, {price_sek: 600000}, {wltp_range_km: 605}, {dc_charge_kw: 0},
  {price_type: 'campaign_price'}, {source_url: 'https://ev-database.org/'}, {source_hash: 'bad'},
  {extraction_confidence: 0.91}, {fetched_at: '2026-10-27T19:00:00Z'}, {variant_name: 'EV3'}]) {
  assert.throws(() => validateProfile({...structuredClone(row), ...patch}, now));
}
assert.equal(retiredSlug('Kia', 'Ev3', 'EV3'), 'kia-ev3');
assert.equal(retiredSlug('Polestar', '4', 'Long range Single motor'), 'polestar-4-long-range-single-motor');
assert.equal(retiredSlug('Audi','A6 E-Tron','A6 Sportback e-tron'),'audi-a6-sportback-e-tron');
assert.equal(retiredSlug('Volvo','Ex30','EX30 Core'),'volvo-ex30-core');
const registry = { schema_version: 1, redirects: [{ slug: 'kia-ev3', brand: 'Kia', model: 'Ev3' }] };
assert.equal(vehicleRedirect('kia-ev3', registry), '/bilar?brand=Kia&query=Ev3');
assert.equal(vehicleRedirect('unknown', registry), null);
assert.deepEqual(catalogQuery('?brand=Kia&query=Ev3'), {brand:'Kia',query:'Ev3',maxPrice:1200000});
assert.equal(catalogQuery('?query=EV3'), null);
for (const patch of [{slug:'//evil.invalid'}, {slug:'kia-ev3\n/evil'}, {brand:'<script>'}]) {
  assert.throws(() => validateVehicleRedirects({schema_version:1,redirects:[{...registry.redirects[0],...patch}]}));
}

const db = new PGlite();
try {
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls; grant usage on schema public to anon,authenticated,service_role');
  await db.exec((await readFile(new URL('../database/schema.sql', import.meta.url), 'utf8')).replace('create extension if not exists pgcrypto;', ''));
  const groups = [];
  for (const [identity, retire] of Object.entries(RETIRED)) {
    const [brand, model] = identity.split('|');
    const canonical = (await db.query(`insert into canonical_models(brand,model,normalized_brand,normalized_model,market_seen)
      values($1,$2,$3,$4,true) returning id`, [brand,model,brand.toLowerCase(),model.toLowerCase()])).rows[0];
    for (const name of retire) await db.query(`insert into canonical_model_variants(canonical_model_id,variant_name,
      price_sek,wltp_range_km,source_url,source_hash,source_quote,extraction_confidence,validation_status)
      values($1,$2,450000,600,'https://fixture.invalid/old','old','historical maximum',0.95,'published')`,[canonical.id,name]);
    let next;
    if (brand === 'Kia') next = finish(kia(model, model === 'Ev5' ? 'EV5 Plus AWD Long Range' : model === 'Ev9' ? 'EV9 RWD 7-SITS' : model.toUpperCase() + ' FWD'), 'kia_sweden_exact_price_row_v1');
    else if (brand === 'Polestar') next = finish({...row,brand,model,variant_name:'Rear motor',
      source_name:'Polestar Sverige',source_url:'https://www.polestar.com/se/polestar-4-models/polestar-4-coupe/specifications/',
      source_quote:'Rear motor | Pris från 599 000 kr'},'polestar4_coupe_exact_price_v1');
    else {
      next = finish({...row,brand,model,variant_name:'evolution 40 kWh',source_authority:'importer',source_name:'Renault Sverige',
        source_url:'https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/renaultsesite/cardocuments/prislista-renault-5-e-tech-electric.pdf',
        source_quote:'EVOLUTION TECHNO ICONIC FIVE | evolution 40 kWh | Rek. cirkapris 599 000 kr'},'renault5_linked_price_pdf_v1');
      Object.assign(next.extraction_payload,{discovered_from:'https://www.renault.se/personbilar/elbilar/r5-e-tech-electric/versioner-och-priser',discovery_source_hash:'b'.repeat(64)});
    }
    groups.push({brand,model,retire,profiles:[next]});
  }
  const variants = (await db.query('select v.*,m.brand,m.model from canonical_model_variants v join canonical_models m on m.id=v.canonical_model_id order by v.id')).rows;
  const plan = buildReplacementPlan(variants,{policy:POLICY,groups},now);
  const freshMarketing = structuredClone({groups});
  freshMarketing.groups.at(-1).profiles[0].extraction_payload.discovery_source_hash = 'd'.repeat(64);
  assert.deepEqual(recollectedFacts(freshMarketing),recollectedFacts({groups}));
  for (const mutate of [r=>r.source_hash='d'.repeat(64), r=>r.price_sek=1, r=>r.source_url='https://unapproved.invalid/',
    r=>r.extraction_payload.discovered_from='https://unapproved.invalid/']) {
    const changed = structuredClone(freshMarketing); mutate(changed.groups.at(-1).profiles[0]);
    assert.notDeepEqual(recollectedFacts(changed),recollectedFacts({groups}));
  }
  const hash = replacementPlanHash(plan);
  const snapshot = async () => (await db.query(`select jsonb_build_object(
    'variants',(select jsonb_agg(to_jsonb(v) order by id) from public.canonical_model_variants v),
    'drafts',(select jsonb_agg(to_jsonb(d) order by id) from public.extracted_variant_drafts d),
    'sources',(select jsonb_agg(to_jsonb(s) order by id) from public.manufacturer_sources s),
    'models',(select jsonb_agg(to_jsonb(m) order by id) from public.canonical_models m)) as state`)).rows[0].state;
  // A late staging collision must roll back all earlier inserts and retirements.
  const last = groups.at(-1).profiles[0];
  const conflict = (await db.query(`insert into extracted_variant_drafts(brand,model,variant_name,source_url)
    values($1,$2,$3,$4) returning id`,[last.brand,last.model,last.variant_name,last.source_url])).rows[0].id;
  const before = await snapshot();
  await assert.rejects(applyReplacementPlan(db,plan,hash,now), /Staging identity exists/);
  assert.deepEqual(await snapshot(), before, 'Late failure must roll back the whole transaction');
  await db.query('delete from extracted_variant_drafts where id=$1',[conflict]);
  // Shared source timestamps must not make old technical evidence appear fresh.
  await db.query(`insert into manufacturer_sources(brand,model,source_type,url,content_hash,verified_at)
    values('Kia','Ev5','manufacturer_page',$1,$2,'2020-01-01')`,[row.source_url,'c'.repeat(64)]);
  const shared = (await db.query('select * from manufacturer_sources where url=$1',[row.source_url])).rows;
  const result = await applyReplacementPlan(db,plan,hash,now);
  assert.equal(result.retired,11);
  assert.equal(result.published,6);
  assert.equal(result.models_preserved,6);
  assert.deepEqual((await db.query('select * from manufacturer_sources where url=$1',[row.source_url])).rows,shared);
  assert.equal((await db.query('select count(*)::int as n from public_ev_variants')).rows[0].n,6);
  const after = await snapshot();
  await assert.rejects(applyReplacementPlan(db,plan,hash,now));
  assert.deepEqual(await snapshot(),after,'Replay cannot create more variants or change historical records');
  for (const role of ['anon','authenticated']) {
    await db.exec(`set role ${role}`);
    await assert.rejects(db.query('select * from canonical_model_variants'),e=>e.code==='42501');
    await assert.rejects(db.query('select * from extracted_variant_drafts'),e=>e.code==='42501');
    assert.equal((await db.query('select count(*)::int as n from public_ev_variants')).rows[0].n,6);
    await db.exec('reset role');
  }
} finally { await db.close(); }
console.log(JSON.stringify({ current_profiles_contract_ok:true, unknown_specs_stay_null:true,
  unsafe_sources_rejected:true, price_quote_bound:true, safe_retired_urls:true,
  real_postgres_rollback:true, replay_safe:true, public_roles_denied_private_tables:true, paid_calls:0 }));
