import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

export const POLICY = 'current_exact_variants_2026_10_v1';
export const RETIRED = {
  'Kia|Ev3': ['EV3'], 'Kia|Ev4': ['EV4'], 'Kia|Ev5': ['EV5 AWD'],
  'Kia|Ev9': ['EV9 RWD Standard Range'],
  'Polestar|4': ['Long range Dual motor', 'Long range Single motor'],
  'Renault|5': ['evolution', 'evolution EV 40', 'iconic five EV 52', 'roland garros EV52', 'techno EV52'],
};
const KIA = 'https://www.kia.com/se/kopa/prislista/';
const POLESTAR = 'https://www.polestar.com/se/polestar-4-models/polestar-4-coupe/specifications/';
const RENAULT = 'https://edge.sitecorecloud.io/hedinitaban27a1-hedin8837-prod5c4b-4604/media/project/hedin/distribution-cars/renaultsesite/cardocuments/prislista-renault-5-e-tech-electric.pdf';
const SOURCES = { Kia: KIA, Polestar: POLESTAR, Renault: RENAULT };
const ADAPTERS = { Kia: 'kia_sweden_exact_price_row_v1', Polestar: 'polestar4_coupe_exact_price_v1', Renault: 'renault5_linked_price_pdf_v1' };
const UNKNOWN = ['wltp_range_km', 'wltp_consumption_kwh_100km', 'battery_kwh', 'dc_charge_kw', 'ac_charge_kw',
  'boot_liters', 'tow_kg', 'seats', 'drivetrain', 'price_valid_until'];
const plain = x => JSON.parse(JSON.stringify(x));
const key = row => `${row.brand}|${row.model}`;
export const replacementPlanHash = plan => createHash('sha256').update(JSON.stringify(plan)).digest('hex');
export function recollectedFacts(intake) {
  return intake.groups.map(group => ({ ...group, profiles: group.profiles.map(({ fetched_at, ...profile }) => {
    const copy = structuredClone(profile);
    // The parent page is discovery evidence, not the price document. Its changing
    // navigation/marketing bytes are harmless only after the fresh collector has
    // proved the exact same official link and the identical PDF/facts again.
    if (copy.brand === 'Renault') delete copy.extraction_payload.discovery_source_hash;
    return copy;
  }) }));
}
const slug = text => text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
export function retiredSlug(brand, model, variant) {
  const norm = text => String(text).toLowerCase().replace(/[^a-z0-9]/g, '');
  const variantWithoutBrand = variant.replace(new RegExp(`^${brand}\\s+`, 'i'), '');
  const display = norm(variantWithoutBrand).startsWith(norm(model)) ? variantWithoutBrand : `${model} ${variantWithoutBrand}`;
  return slug(`${brand} ${display}`);
}

export function validateProfile(row, now = new Date()) {
  assert(Object.hasOwn(RETIRED, key(row)), 'Unapproved model');
  assert.equal(row.source_url, SOURCES[row.brand], 'Exact accepted source required');
  assert.equal(row.source_authority, row.brand === 'Renault' ? 'importer' : 'manufacturer');
  assert.equal(row.source_name, row.brand + ' Sverige');
  assert.match(row.source_hash, /^[a-f0-9]{64}$/);
  const age = now.getTime() - Date.parse(row.fetched_at);
  assert(Number.isFinite(age) && age >= -60000 && age <= 900000, 'Fresh evidence required');
  assert(row.extraction_confidence >= 0.92 && row.extraction_confidence <= 1);
  assert.equal(row.price_type, 'list_price');
  assert(Number.isInteger(row.price_sek) && row.price_sek >= 100000 && row.price_sek <= 3000000);
  for (const field of UNKNOWN) assert.equal(row[field], null, 'No inherited/estimated facts in a price-only replacement');
  const payload = row.extraction_payload;
  assert.equal(payload.policy, POLICY);
  assert.equal(payload.adapter, ADAPTERS[row.brand]);
  assert.deepEqual(payload.field_evidence.price_sek, { quote: row.source_quote, variant: row.variant_name,
    source_url: row.source_url, source_hash: row.source_hash });
  const sections = row.source_quote.split(' | ');
  if (row.brand === 'Kia') {
    assert.match(row.variant_name, new RegExp(`^${row.model.toUpperCase()} (?:FWD|Plus|GT|RWD)`));
    if (row.model === 'Ev5') assert(row.variant_name.includes(' AWD '));
    if (row.model === 'Ev9') assert.equal(row.variant_name, 'EV9 RWD 7-SITS');
    assert.equal(sections.length, 4);
    const caption = `Prislista för Kia ${row.model.toUpperCase()}`;
    assert([caption, caption + ' med fullständiga versionsnamn'].includes(sections[0]), 'Exact model table caption required');
    assert.equal(sections[1], row.variant_name);
    assert.equal(sections[2].toLowerCase().replace(/[^a-z]/g, ''), 'rekcirkaprisinklmoms');
  } else if (row.brand === 'Polestar') {
    assert(['Rear motor', 'Dual motor'].includes(row.variant_name));
    assert.equal(sections.length, 2);
    assert.equal(sections[0], row.variant_name);
    assert.match(sections[1], /^Pris från [0-9 ]+ kr$/);
  } else {
    assert(['evolution 40 kWh', 'techno 52 kWh', 'iconic five 52 kWh'].includes(row.variant_name));
    assert.equal(payload.discovered_from, 'https://www.renault.se/personbilar/elbilar/r5-e-tech-electric/versioner-och-priser');
    assert.match(payload.discovery_source_hash, /^[a-f0-9]{64}$/);
    assert.equal(sections.length, 3);
    assert.equal(sections[0], 'EVOLUTION TECHNO ICONIC FIVE');
    assert.equal(sections[1], row.variant_name);
    assert.match(sections[2], /^Rek\. cirkapris [0-9 ]+ kr$/);
  }
  const amount = sections.at(-1).match(/([0-9][0-9 ]*[0-9])(?: kr| SEK)?$/);
  assert(amount && Number(amount[1].replace(/ /g, '')) === row.price_sek, 'Price must equal exact quoted cash value');
  return row;
}

export function buildReplacementPlan(variants, intake, now = new Date()) {
  assert.equal(intake.policy, POLICY);
  assert.equal(intake.groups.length, Object.keys(RETIRED).length);
  const seen = new Set();
  const groups = intake.groups.map(group => {
    const identity = key(group);
    assert(Object.hasOwn(RETIRED, identity) && !seen.has(identity), 'Unexpected/duplicate model group');
    seen.add(identity);
    assert.deepEqual(group.retire, RETIRED[identity]);
    const expected = group.retire.map(name => {
      const matches = variants.filter(v => key(v) === identity && v.variant_name === name
        && ['published', 'published_reviewed'].includes(v.validation_status));
      assert.equal(matches.length, 1, 'Retired variant must be an exact current public record');
      return plain(matches[0]);
    });
    const modelId = expected[0].canonical_model_id;
    assert(expected.every(row => row.canonical_model_id === modelId));
    assert(group.profiles.length >= 1 && group.profiles.length <= 20);
    const names = new Set();
    for (const profile of group.profiles) {
      validateProfile(profile, now);
      assert.equal(key(profile), identity);
      assert(!names.has(profile.variant_name)); names.add(profile.variant_name);
      assert(!variants.some(v => v.canonical_model_id === modelId && v.variant_name === profile.variant_name), 'New identity already exists; reconcile before replay');
    }
    return { brand: group.brand, model: group.model, canonical_model_id: modelId,
      expected, profiles: plain(group.profiles), redirects: expected.map(row => ({
        slug: retiredSlug(row.brand, row.model, row.variant_name), brand: row.brand, model: row.model })) };
  });
  return { policy: POLICY, groups };
}

export async function applyReplacementPlan(client, plan, expectedHash, now = new Date()) {
  assert.equal(replacementPlanHash(plan), expectedHash, 'Plan changed');
  assert.deepEqual(plan, buildReplacementPlan(plan.groups.flatMap(g => g.expected), {
    policy: plan.policy, groups: plan.groups.map(g => ({ brand: g.brand, model: g.model,
      retire: g.expected.map(v => v.variant_name), profiles: g.profiles })) }, now));
  let committed = false;
  await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE READ WRITE');
  try {
    await client.query('SET LOCAL search_path=pg_catalog');
    await client.query("SET LOCAL lock_timeout='10s'");
    await client.query('SELECT pg_advisory_xact_lock(7240008)');
    const before = plain((await client.query('SELECT * FROM public.canonical_model_variants ORDER BY id FOR UPDATE')).rows);
    const models = plain((await client.query('SELECT * FROM public.canonical_models ORDER BY id')).rows);
    const publicModels = plain((await client.query('SELECT id FROM public.public_ev_models ORDER BY id')).rows);
    const byId = new Map(before.map(row => [row.id, row]));
    const affected = new Set();
    for (const group of plan.groups) {
      assert(models.some(m => m.id === group.canonical_model_id && m.brand === group.brand && m.model === group.model));
      for (const expected of group.expected) {
        const { brand, model, ...value } = expected;
        assert.deepEqual(byId.get(expected.id), value, 'Concurrent variant change');
        affected.add(expected.id);
      }
      for (const profile of group.profiles) {
        validateProfile(profile, now);
        const sources = (await client.query('SELECT id FROM public.manufacturer_sources WHERE url=$1', [profile.source_url])).rows;
        let sourceId = sources[0]?.id;
        if (!sourceId) {
          sourceId = (await client.query(`INSERT INTO public.manufacturer_sources
            (canonical_model_id,brand,model,source_type,url,title,country,language,fetched_at,content_hash,
              extraction_status,extraction_confidence,http_status,final_url,source_validation,source_authority,source_name,verified_by,verified_at)
            VALUES($1,$2,$3,$4,$5,$6,'SE','sv',$7,$8,'validated',0.99,200,$5,'reachable',$9,$6,$10,$7) RETURNING id`,
          [group.canonical_model_id, group.brand, group.model, profile.source_url.endsWith('.pdf') ? 'price_list_pdf' : 'manufacturer_page',
            profile.source_url, profile.source_name, profile.fetched_at, profile.source_hash, profile.source_authority, POLICY])).rows[0].id;
        }
        // Shared documents may already support older technical records: never refresh their date/hash globally.
        const draft = (await client.query(`INSERT INTO public.extracted_variant_drafts
          (canonical_model_id,source_id,brand,model,variant_name,price_sek,price_type,source_url,source_quote,
            source_hash,extraction_confidence,extraction_payload,validation_status)
          VALUES($1,$2,$3,$4,$5,$6,'list_price',$7,$8,$9,0.99,$10,'validated')
          ON CONFLICT(source_url,variant_name) DO NOTHING RETURNING id`,
          [group.canonical_model_id, sourceId, group.brand, group.model, profile.variant_name, profile.price_sek,
            profile.source_url, profile.source_quote, profile.source_hash, JSON.stringify(profile.extraction_payload)])).rows;
        assert.equal(draft.length, 1, 'Staging identity exists; reconcile instead of overwriting history');
        const result = await client.query(`INSERT INTO public.canonical_model_variants
          (canonical_model_id,variant_name,price_sek,price_type,source_url,source_hash,source_quote,
            extraction_confidence,source_id,validation_status,published_at,price_source_url,price_source_hash,
            price_source_quote,price_source_name,price_verified_at,price_refresh_batch_id)
          VALUES($1,$2,$3,'list_price',$4,$5,$6,0.99,$7,'published',now(),$4,$5,$6,$8,$9,$10) RETURNING id`,
          [group.canonical_model_id, profile.variant_name, profile.price_sek, profile.source_url, profile.source_hash,
            profile.source_quote, sourceId, profile.source_name, profile.fetched_at, expectedHash]);
        affected.add(result.rows[0].id);
      }
      for (const old of group.expected) await client.query(`UPDATE public.canonical_model_variants
        SET validation_status='needs_review',updated_at=now() WHERE id=$1`, [old.id]);
    }
    const after = plain((await client.query('SELECT * FROM public.canonical_model_variants ORDER BY id')).rows);
    const oldIds = new Set(plan.groups.flatMap(g => g.expected.map(v => v.id)));
    for (const row of after) {
      if (!affected.has(row.id)) assert.deepEqual(row, byId.get(row.id), 'Unrelated variant changed');
      else if (oldIds.has(row.id)) {
        const retained = value => Object.fromEntries(Object.entries(value).filter(([name]) => !['validation_status', 'updated_at'].includes(name)));
        assert.equal(row.validation_status, 'needs_review');
        assert.deepEqual(retained(row), retained(byId.get(row.id)), 'Historical facts must remain intact');
      } else for (const field of UNKNOWN) assert.equal(row[field], null, 'New profile inherited unsupported facts');
    }
    const added = plan.groups.reduce((sum, group) => sum + group.profiles.length, 0);
    assert.equal(after.length, before.length + added);
    assert.deepEqual(plain((await client.query('SELECT * FROM public.canonical_models ORDER BY id')).rows), models, 'Models/availability/images changed');
    assert.deepEqual(plain((await client.query('SELECT id FROM public.public_ev_models ORDER BY id')).rows), publicModels, 'Public model coverage changed');
    await client.query('COMMIT'); committed = true;
    return { committed: true, retired: oldIds.size, published: added, models_preserved: publicModels.length,
      plan_sha256: expectedHash, paid_calls: 0, redirects: plan.groups.flatMap(group => group.redirects) };
  } finally { if (!committed) await client.query('ROLLBACK'); }
}
