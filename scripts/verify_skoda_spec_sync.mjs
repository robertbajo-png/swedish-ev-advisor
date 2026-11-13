import assert from 'node:assert/strict';
import { PGlite } from '@electric-sql/pglite';
import { ADAPTER, buildSpecPlan, applySpecPlan, specPlanHash, validateSpecDraft } from './skoda_spec_sync.mjs';
import { TECHNICAL_FIELDS, buildSpecPlan as buildKia } from './kia_spec_sync.mjs';
const db = new PGlite();
const now = new Date('2026-11-13T12:00:00Z');
try {
  const columns = TECHNICAL_FIELDS.map(field => field + (field === 'drivetrain' ? ' text' : ' numeric')).join(',');
  await db.exec(`CREATE TABLE canonical_models(id text primary key,brand text,model text,market_seen boolean,body_type text,updated_at timestamptz);
    CREATE TABLE canonical_model_variants(id text primary key,canonical_model_id text,variant_name text,
      validation_status text,review_approved_by text,review_reason text,review_promoted_at text,price_sek int,price_type text,
      price_source_url text,price_source_hash text,price_source_quote text,price_verified_at text,
      ${columns},ac_charge_kw int,source_id text,source_url text,source_hash text,source_quote text,
      extraction_confidence numeric,updated_at timestamptz);
    CREATE TABLE manufacturer_sources(id text primary key default gen_random_uuid()::text,
      canonical_model_id text,brand text,model text,source_type text,url text unique,title text,country text,
      language text,fetched_at timestamptz,content_hash text,http_status int,final_url text,source_validation text,
      source_authority text,source_name text,extraction_status text,verified_at timestamptz,updated_at timestamptz);
    CREATE TABLE extracted_variant_drafts(canonical_model_id text,source_id text,brand text,model text,variant_name text,
      ${columns},ac_charge_kw int,source_url text,source_hash text,source_quote text,extraction_confidence numeric,extraction_payload jsonb,
      validation_status text,validation_errors jsonb,updated_at timestamptz,unique(source_url,variant_name));
    INSERT INTO canonical_models VALUES ('m','Skoda','Elroq',true),('other','Other','Untouched',false);`);
  const intake = { adapter: ADAPTER, drafts: [] };
  for (const [index, trim] of ['Selection', 'Sportline'].entries()) {
    const variant_name = '85 ' + trim + ' Explore Edition';
    await db.query(`INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,validation_status,
      price_sek,price_type,price_source_url,price_source_hash,price_source_quote,price_verified_at,
      source_url,source_hash,source_quote,extraction_confidence,updated_at)
      VALUES ($1,'m',$2,'published',494900,'campaign_price','https://www.skoda.se/_doc/price',$3,
      'Exact retained campaign price','2026-11-01','https://www.skoda.se/_doc/price',$3,'Original price evidence',0.99,now())`,
      [String(index), variant_name, 'b'.repeat(64)]);
    const source = { final_url: 'https://www.skoda.se/modeller/elroq/elroq', status: 'reachable', http_status: 200,
      content_hash: 'a'.repeat(64), fetched_at: now.toISOString() };
    const facts = { boot_liters: 470, dc_charge_kw: 165, wltp_range_km: 569, battery_kwh: 77,
      ac_charge_kw: 11, tow_kg: 1800, drivetrain: 'RWD' };
    const field_evidence = {
      boot_liters: { quote: 'Trots sin kompakta storlek har Elroq ett stort bagageutrymme på 470 liter (1580 liter med nedfällda säten).', scope: 'model_rear_boot_seats_up' },
      dc_charge_kw: { quote: 'Elroq 85, 85x och RS: cirka 29 minuter från 10 till 80 procent, med en maximal laddeffekt på 165 kW.', scope: 'faq_variant_dc', question: 'Hur snabbt kan Elroq laddas?' },
      wltp_range_km: { quote: 'Elroq 85 och 85x: upp till 569 km.', scope: 'faq_variant_wltp', question: 'Hur lång räckvidd har Elroq?',
        engine_label: 'Elroq 85 och 85x', qualification: 'WLTP, upp till; versionens angivna standardutförande' },
      battery_kwh: { quote: 'Elroq 85 Škoda Elroq Batterikapacitet (Brutto/netto) [kWh] 82/77', scope: 'my2027_engine_net_battery', engine_label: 'Elroq 85' },
      ac_charge_kw: { quote: 'Elroq kan laddas med upp till 11 kW AC, exempelvis hemma.', scope: 'faq_model_ac', question: 'Hur snabbt kan Elroq laddas?' },
      tow_kg: { quote: 'Elroq 85, 85x och RS: upp till 1 800 kg.', scope: 'faq_braked_towing', question: 'Hur mycket får Elroq dra?',
        engine_label: 'Elroq 85, 85x och RS', qualification: 'Bromsad släpvagn; kontrollera registreringsbevis.' },
      drivetrain: { quote: 'Elroq 60 och 85 har bakhjulsdrift.', scope: 'explicit_engine_drivetrain' },
    };
    if (index) {
      facts.wltp_range_km = 560;
      Object.assign(field_evidence.wltp_range_km, { quote: 'Elroq Sportline 85: upp till 560 km.', engine_label: 'Elroq Sportline 85' });
    }
    for (const field of Object.keys(facts)) Object.assign(field_evidence[field], { value: facts[field], variant_name,
      model_heading: 'Elroq Explore Edition', source_url: source.final_url, source_hash: source.content_hash });
    const extra = { ...source, final_url: 'https://www.skoda.se/nyheter-och-pressklipp/nyhet/skoda-uppdaterar-elroq-och-enyaq-infor-modellar-2027', content_hash: 'c'.repeat(64) };
    Object.assign(field_evidence.battery_kwh, { source_url: extra.final_url, source_hash: extra.content_hash });
    intake.drafts.push({ adapter: ADAPTER, brand: 'Skoda', model: 'Elroq', variant_name, source, facts,
      model_facts: { body_type: 'SUV' }, model_field_evidence: { body_type: { value: 'SUV', scope: 'exact_model_description',
        quote: 'Upptäck Škoda Elroq, en kompakt el-SUV.', source_url: source.final_url, source_hash: source.content_hash } },
      supporting_sources: [extra], source_resolution: 'owner_2026_11_13_exact_current_edition_faq_over_estimated_price_list',
      field_evidence, extraction_confidence: 0.99, held_fields: { wltp_range_km: { reason: 'estimated' } } });
  }
  const joined = () => db.query('SELECT v.*,m.brand,m.model FROM canonical_model_variants v JOIN canonical_models m ON m.id=v.canonical_model_id ORDER BY v.id').then(result => result.rows);
  const rows = await joined();
  const plan = buildSpecPlan(rows, intake, now);
  const full = structuredClone(intake.drafts[0]);
  const price = { ...full.source, final_url: 'https://www.skoda.se/_doc/ec8b0854-d72e-4c53-8678-3b189a5388eb', content_hash: 'd'.repeat(64) };
  full.supporting_sources.push(price);
  full.facts.seats = 5; full.facts.wltp_consumption_kwh_100km = 15.6;
  full.field_evidence.seats = { ...full.field_evidence.boot_liters, value: 5, scope: 'model_gallery_seating',
    quote: 'När baksätets ryggstöd förblir upprättstående finns det 470 liters bagageutrymme för upp till fem passagerare.' };
  full.field_evidence.wltp_consumption_kwh_100km = { ...full.field_evidence.boot_liters, value: 15.6,
    source_url: price.final_url, source_hash: price.content_hash, scope: 'price_table_engine_standard_consumption',
    engine_label: '85', raw_wh_km: 156, unit_source_url: full.source.final_url, unit_source_hash: full.source.content_hash,
    unit_quote: 'Elförbrukning, blandad körning 155 171 Wh/km',
    quote: 'Škoda Elroq Explore Edition | 85 | 286 | 567 | 156 | 0 | 494 900 kr | 510 300 kr | – | *Värde gäller för motor i grundutförande.',
    qualification: 'Motor i grundutförande; utrustning och hjul kan påverka förbrukningen.' };
  validateSpecDraft(full, now);
  for (const mutate of [value => value.facts.wltp_consumption_kwh_100km = 156,
    value => value.field_evidence.wltp_consumption_kwh_100km.engine_label = '60',
    value => value.field_evidence.wltp_consumption_kwh_100km.unit_quote = 'Förbrukning l/100 km',
    value => value.field_evidence.seats.quote = 'Peaq har sju sittplatser.',
    value => value.model_field_evidence.body_type.quote = 'Upptäck Škoda Peaq, en el-SUV.']) {
    const invalid = structuredClone(full); mutate(invalid);
    assert.throws(() => validateSpecDraft(invalid, now));
  }
  assert.throws(() => buildKia(rows, intake, now), 'Skoda cannot enter the default Kia publisher');
  for (const mutate of [value => value.drafts[0].facts.wltp_range_km = 567,
    value => value.drafts[0].facts.dc_charge_kw = 166,
    value => value.drafts[0].field_evidence.boot_liters.source_hash = 'c'.repeat(64),
    value => value.drafts[0].source.fetched_at = '2020-01-01',
    value => value.drafts[0].variant_name = 'Solid Edition RS',
    value => value.drafts.push(value.drafts[0])]) {
    const changed = structuredClone(intake); mutate(changed);
    assert.throws(() => buildSpecPlan(rows, changed, now));
  }
  const unsupported = structuredClone(rows); unsupported[0].dc_charge_kw = 185;
  assert.throws(() => buildSpecPlan(unsupported, intake, now), /conflicting/);
  const retained = structuredClone(rows); retained[0].seats = 5;
  assert.throws(() => buildSpecPlan(retained, intake, now), /retained technical field needs evidence/);
  const before = (await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
  const beforeModels = (await db.query('SELECT * FROM canonical_models ORDER BY id')).rows;
  await db.exec(`CREATE FUNCTION fail_second() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
    IF NEW.variant_name LIKE '%Sportline%' THEN RAISE EXCEPTION 'Fixture failure'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER late_failure BEFORE INSERT ON extracted_variant_drafts FOR EACH ROW EXECUTE FUNCTION fail_second();`);
  await assert.rejects(applySpecPlan(db, plan, specPlanHash(plan), now));
  assert.deepEqual((await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows, before);
  assert.deepEqual((await db.query('SELECT * FROM canonical_models ORDER BY id')).rows, beforeModels);
  assert.equal((await db.query('SELECT * FROM manufacturer_sources')).rows.length, 0);
  assert.equal((await db.query('SELECT * FROM extracted_variant_drafts')).rows.length, 0);
  await db.exec('DROP TRIGGER late_failure ON extracted_variant_drafts');
  const result = await applySpecPlan(db, plan, specPlanHash(plan), now);
  assert.equal(result.new_technical_values, 14);
  assert.equal(result.models_changed, 1);
  assert.equal((await db.query("SELECT body_type FROM canonical_models WHERE id='m'")).rows[0].body_type, 'SUV');
  const after = (await db.query('SELECT * FROM canonical_model_variants ORDER BY id')).rows;
  assert(after.every(row => row.price_sek === 494900 && row.price_type === 'campaign_price' && row.price_source_hash === 'b'.repeat(64)));
  assert.equal(Number(after[0].wltp_range_km), 569); assert.equal(Number(after[1].wltp_range_km), 560);
  assert(after.every(row => Number(row.tow_kg) === 1800 && row.ac_charge_kw === 11));
  const savedSources = (await db.query('SELECT * FROM manufacturer_sources')).rows;
  assert.equal(savedSources.filter(row => row.source_type === 'manufacturer_model_page').length, 1);
  assert.equal(savedSources.filter(row => row.source_type === 'manufacturer_page' && row.canonical_model_id === null).length, 1);
  assert(savedSources.every(row => row.source_name === 'Škoda Sverige'));
  await assert.rejects(applySpecPlan(db, plan, specPlanHash(plan), now), 'A committed before-image is not replayable');
  await db.exec(`INSERT INTO canonical_models VALUES ('enq','Skoda','Enyaq',true);
    INSERT INTO canonical_model_variants(id,canonical_model_id,variant_name,validation_status,review_approved_by,review_reason,
      review_promoted_at,price_sek,price_type,price_source_url,price_source_hash,price_source_quote,price_verified_at,
      source_url,source_hash,source_quote,dc_charge_kw,extraction_confidence,updated_at)
    VALUES ('rs','enq','Solid Edition RS','published_reviewed','pipeline_auto_review','Historical fixture approval','2026-05-10',
      689900,'campaign_price','https://www.skoda.se/_doc/price',repeat('b',64),'Retained price','2026-11-01',
      'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660',repeat('d',64),'185 kW DC-laddning',185,0.9,now());`);
  const rs = structuredClone(intake.drafts[0]);
  rs.model = 'Enyaq'; rs.variant_name = 'Solid Edition RS'; rs.source.final_url = 'https://www.skoda.se/modeller/enyaq/enyaq';
  Object.assign(rs.model_field_evidence.body_type, { quote: 'Upptäck Škoda Enyaq, en rymlig el-SUV.', source_url: rs.source.final_url });
  Object.assign(rs.facts, { boot_liters: 585, wltp_range_km: 558, tow_kg: 2200, drivetrain: 'AWD', seats: 5 });
  rs.field_evidence.seats = { scope: 'model_seating', quote: 'Enyaq har fem sittplatser och ett bagageutrymme på 585 liter.' };
  for (const [field, proof] of Object.entries(rs.field_evidence)) Object.assign(proof, { value: rs.facts[field], variant_name: rs.variant_name,
    model_heading: 'Enyaq Solid Edition', source_url: field === 'battery_kwh' ? rs.supporting_sources[0].final_url : rs.source.final_url,
    source_hash: field === 'battery_kwh' ? rs.supporting_sources[0].content_hash : rs.source.content_hash,
    ...(proof.question ? { question: proof.question.replace('Elroq', 'Enyaq') } : {}) });
  Object.assign(rs.field_evidence.boot_liters, { quote: 'Stort bagageutrymme på 585 liter (1710 liter med nedfällda säten).' });
  Object.assign(rs.field_evidence.dc_charge_kw, { quote: 'Snabbladdning (DC): Enyaq 85, 85x, 85x Sportline och RS kan snabbladdas med en maximal DC-laddeffekt på 165 kW.' });
  Object.assign(rs.field_evidence.wltp_range_km, { quote: 'Enyaq RS: upp till 558 km.', engine_label: 'Enyaq RS' });
  Object.assign(rs.field_evidence.battery_kwh, { quote: 'Enyaq RS (Coupé)Škoda Enyaq Batterikapacitet (brutto/netto) [kWh] 82/77', engine_label: 'Enyaq RS' });
  Object.assign(rs.field_evidence.ac_charge_kw, { quote: 'Enyaq kan laddas med upp till 11 kW AC, exempelvis hemma.' });
  Object.assign(rs.field_evidence.tow_kg, { quote: 'Enyaq RS: upp till 2 200 kg.', engine_label: 'Enyaq RS' });
  Object.assign(rs.field_evidence.drivetrain, { quote: 'Ja, Enyaq 85x, 85x Sportline och RS har fyrhjulsdrift (4×4).' });
  const rsRows = await joined();
  const rsPlan = buildSpecPlan(rsRows, { adapter: ADAPTER, drafts: [rs] }, now);
  const unknownOldSource = structuredClone(rsRows); unknownOldSource.find(row => row.id === 'rs').source_url = 'https://wrong.invalid/';
  assert.throws(() => buildSpecPlan(unknownOldSource, { adapter: ADAPTER, drafts: [rs] }, now), /reconciliation|conflicting/);
  await applySpecPlan(db, rsPlan, specPlanHash(rsPlan), now);
  const resolved = (await db.query("SELECT * FROM canonical_model_variants WHERE id='rs'")).rows[0];
  assert.equal(Number(resolved.dc_charge_kw), 165); assert.equal(resolved.validation_status, 'published');
  assert.equal(resolved.review_approved_by, null); assert.equal(resolved.review_reason, null); assert.equal(resolved.review_promoted_at, null);
  assert.equal(resolved.price_sek, 689900);
  const packet = (await db.query("SELECT extraction_payload FROM extracted_variant_drafts WHERE variant_name='Solid Edition RS'")).rows[0].extraction_payload;
  assert.equal(packet.previous_canonical.dc_charge_kw, '185');
  assert.equal(packet.source_resolution, rs.source_resolution);
  console.log(JSON.stringify({ skoda_spec_sync: 'passed', uncertain_facts_held: true, price_preservation: true,
    rollback_and_replay_guard: true, exact_owner_source_adjudication: true, old_review_not_reused: true, production_writes: 0, paid_calls: 0 }));
} finally { await db.close(); }
