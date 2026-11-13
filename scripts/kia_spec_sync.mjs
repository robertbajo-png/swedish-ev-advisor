import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

export const ADAPTER = 'kia_sweden_technical_pdf_v1';
export const TECHNICAL_FIELDS = ['wltp_range_km', 'wltp_consumption_kwh_100km', 'battery_kwh',
  'dc_charge_kw', 'boot_liters', 'tow_kg', 'drivetrain', 'seats'];
const bounds = { wltp_range_km: [50, 1200], wltp_consumption_kwh_100km: [5, 50],
  battery_kwh: [10, 250], dc_charge_kw: [20, 600], boot_liters: [50, 3500], tow_kg: [0, 4000], seats: [1, 9] };
const plain = value => JSON.parse(JSON.stringify(value));
export const specPlanHash = plan => createHash('sha256').update(JSON.stringify(plan)).digest('hex');
const editable = new Set([...TECHNICAL_FIELDS, 'source_id', 'source_url', 'source_hash', 'source_quote',
  'extraction_confidence', 'updated_at']);
const retained = (row, policy) => Object.fromEntries(Object.entries(row).filter(([name]) => !editable.has(name) &&
  !(policy?.extraFields || []).includes(name) && !(policy?.reviewResetFields || []).includes(name) &&
  !(policy?.canonicalFields || []).includes(name)));
const identity = row => `${row.brand}|${row.model}|${row.variant_name}`;
const KIA_POLICY = { adapter: ADAPTER, validate: validateSpecDraft, sourceType: 'technical_pdf',
  sourceName: 'Kia Sverige', sourceTitle: draft => 'Kia ' + draft.model.toUpperCase() + ' produktfakta', lockKey: 7240016 };

export function validateSpecDraft(row, now = new Date()) {
  assert.equal(row.adapter, ADAPTER);
  assert.equal(row.brand, 'Kia');
  assert.match(row.model, /^Ev[34569]$/);
  assert(row.extraction_confidence >= 0.92 && row.extraction_confidence <= 1);
  const source = row.source;
  assert.equal(source.status, 'reachable');
  assert.equal(source.http_status, 200);
  const url = new URL(source.final_url);
  assert.equal(url.origin, 'https://www.kia.com');
  assert(!url.search && !url.hash);
  assert(url.pathname.startsWith('/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/' + row.model.toLowerCase() + '/'));
  assert(url.pathname.endsWith('.pdf'));
  assert.match(source.content_hash, /^[a-f0-9]{64}$/);
  const age = now.getTime() - Date.parse(source.fetched_at);
  assert(Number.isFinite(age) && age >= -60000 && age <= 900000, 'Fresh technical document required');
  assert(row.variant_name.startsWith(row.model.toUpperCase() + ' '));
  assert(!/\bGT\s*\(/.test(row.variant_name), 'GT is not GT Line');
  assert(row.model !== 'Ev3' || !/AWD/.test(row.variant_name), 'Preliminary AWD is held');
  assert(Number.isInteger(row.facts.wltp_range_km), 'A technical profile needs exact WLTP evidence');
  assert.deepEqual(Object.keys(row.field_evidence).sort(), Object.keys(row.facts).sort());
  for (const [field, value] of Object.entries(row.facts)) {
    assert(TECHNICAL_FIELDS.includes(field), 'No prices, identities, availability or rounded AC updates');
    const evidence = row.field_evidence[field];
    assert.equal(evidence.source_url, source.final_url);
    assert.equal(evidence.source_hash, source.content_hash);
    assert.equal(evidence.variant_name, row.variant_name);
    assert.equal(evidence.value, value);
    assert.equal(evidence.page, 3);
    assert(typeof evidence.quote === 'string' && evidence.quote.length > 5);
    assert(typeof evidence.column_header === 'string' && evidence.column_header.includes('Teknisk specifikation'));
    assert(/^(?:sr|lr)_(?:fwd|rwd|awd)$/.test(evidence.technical_scope));
    if (field === 'drivetrain') {
      assert(['FWD', 'RWD', 'AWD'].includes(value));
      assert(evidence.technical_scope.endsWith('_' + value.toLowerCase()));
    } else {
      assert(typeof value === 'number' && Number.isFinite(value));
      assert(value >= bounds[field][0] && value <= bounds[field][1], 'Technical value outside hard bounds');
      if (!['battery_kwh', 'wltp_consumption_kwh_100km'].includes(field)) assert(Number.isInteger(value));
    }
  }
  return row;
}

// Reuse the guarded transaction for an explicitly validated manufacturer adapter.
export function buildSpecPlan(variants, intake, now = new Date(), policy = KIA_POLICY) {
  assert.equal(intake.adapter, policy.adapter);
  assert(intake.drafts.length > 0 && intake.drafts.length <= 30);
  const seen = new Set();
  const targets = intake.drafts.map(draft => {
    policy.validate(draft, now);
    assert(!seen.has(identity(draft)), 'Duplicate technical target');
    seen.add(identity(draft));
    const matches = variants.filter(row => identity(row) === identity(draft));
    assert.equal(matches.length, 1, 'One exact existing canonical version required');
    const previous = plain(matches[0]);
    assert(['published', 'published_reviewed'].includes(previous.validation_status));
    assert(!previous.review_approved_by && !previous.review_promoted_at || policy.reviewRefresh?.(previous, draft),
      'Reviewed exceptions require separate reconciliation');
    assert(previous.price_sek == null || previous.price_source_url && previous.price_source_hash && previous.price_source_quote && previous.price_verified_at ||
      policy.priceRefresh?.(previous, draft),
      'Existing independent price evidence must be retained');
    for (const [field, value] of Object.entries(draft.facts)) {
      const prior = previous[field];
      assert(prior == null || (typeof value === 'number' ? Number(prior) === value : prior === value) || policy.resolveConflict?.(field, prior, value, previous, draft),
        'A conflicting existing technical fact must be quarantined: ' + field);
    }
    for (const field of [...new Set([...TECHNICAL_FIELDS, 'ac_charge_kw', ...(policy.extraFields || [])])]) {
      assert(previous[field] == null || field in draft.facts,
        'A retained technical field needs evidence from the new source: ' + field);
    }
    return { id: previous.id, expected: previous, draft };
  });
  return { adapter: policy.adapter, targets: targets.sort((a, b) => a.id.localeCompare(b.id)) };
}

export async function applySpecPlan(client, plan, expectedHash, now = new Date(), policy = KIA_POLICY) {
  assert.equal(specPlanHash(plan), expectedHash, 'Prepared technical packet changed');
  assert.deepEqual(buildSpecPlan(plan.targets.map(row => row.expected),
    { adapter: policy.adapter, drafts: plan.targets.map(row => row.draft) }, now, policy), plan);
  assert(['technical_pdf', 'manufacturer_model_page'].includes(policy.sourceType));
  assert(Number.isSafeInteger(policy.lockKey));
  let committed = false;
  await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE READ WRITE');
  try {
    await client.query('SET LOCAL search_path=pg_catalog');
    await client.query("SET LOCAL lock_timeout='10s'");
    await client.query('SELECT pg_advisory_xact_lock($1)', [policy.lockKey]);
    const before = plain((await client.query('SELECT * FROM public.canonical_model_variants ORDER BY id FOR UPDATE')).rows);
    const models = plain((await client.query('SELECT * FROM public.canonical_models ORDER BY id FOR UPDATE')).rows);
    const expectedModels = plain(models);
    const beforeById = new Map(before.map(row => [row.id, row]));
    const modelById = new Map(models.map(row => [row.id, row]));
    const sources = new Map();
    for (const target of plan.targets) {
      const { brand, model, ...expected } = target.expected;
      assert.deepEqual(beforeById.get(target.id), expected, 'Concurrent canonical change');
      const parent = modelById.get(expected.canonical_model_id);
      assert.equal(parent?.brand, brand);
      assert.equal(parent?.model, model);
      const { draft } = target;
      const modelFacts = policy.modelFacts?.(draft) || {};
      assert(Object.keys(modelFacts).every(field => field === 'body_type'), 'Only explicit model body classification allowed');
      if (Object.hasOwn(modelFacts, 'body_type')) {
        assert((policy.allowedBodyTypes || ['SUV']).includes(modelFacts.body_type), 'Explicit model body type required');
        assert(parent.body_type == null || parent.body_type === modelFacts.body_type, 'Existing model classification conflicts');
        const expectedParent = expectedModels.find(row => row.id === parent.id);
        if (expectedParent.body_type !== modelFacts.body_type) {
          const changed = await client.query('UPDATE public.canonical_models SET body_type=$1,updated_at=now() WHERE id=$2 RETURNING updated_at', [modelFacts.body_type, parent.id]);
          expectedParent.body_type = modelFacts.body_type;
          expectedParent.updated_at = plain(changed.rows[0].updated_at);
        }
      }
      const source = draft.source;
      const sourceName = typeof policy.sourceName === 'function' ? policy.sourceName(draft) : policy.sourceName;
      for (const extra of draft.supporting_sources || []) {
        const descriptor = policy.supportingSource?.(extra, draft);
        assert(descriptor && ['manufacturer_page', 'price_list_pdf'].includes(descriptor.sourceType), 'Supporting manufacturer source must be explicitly registered');
        const country = descriptor.country || 'SE', language = descriptor.language || 'sv';
        assert(country === 'SE' && language === 'sv' || country === 'DE' && language === 'de', 'Registered source locale required');
        if (sources.has(extra.final_url)) continue;
        const old = (await client.query('SELECT * FROM public.manufacturer_sources WHERE url=$1 FOR UPDATE', [extra.final_url])).rows;
        const sourceParent = descriptor.shared ? null : parent.id;
        assert(old.length <= 1 && (!old[0] || old[0].brand === brand && old[0].model === descriptor.model &&
          (!old[0].canonical_model_id || old[0].canonical_model_id === sourceParent)), 'Supporting source identity changed');
        const saved = await client.query(`INSERT INTO public.manufacturer_sources
          (canonical_model_id,brand,model,source_type,url,title,country,language,fetched_at,content_hash,http_status,final_url,
           source_validation,source_authority,source_name,extraction_status,verified_at)
          VALUES ($6,$1,$7,$8,$2,$9,$10,$11,$3,$4,200,$2,
           $12,'manufacturer',$5,'published',$3)
          ON CONFLICT(url) DO UPDATE SET fetched_at=excluded.fetched_at,content_hash=excluded.content_hash,
           http_status=200,final_url=excluded.final_url,source_validation=excluded.source_validation,
           country=excluded.country,language=excluded.language,source_name=excluded.source_name,
           extraction_status='published',verified_at=excluded.verified_at,updated_at=now() RETURNING id`,
          [brand,extra.final_url,extra.fetched_at,extra.content_hash,descriptor.sourceName || sourceName,sourceParent,descriptor.model,descriptor.sourceType,descriptor.title,
            country,language,country === 'SE' ? 'reachable_official_model_source' : 'reachable_eu_official_source']);
        sources.set(extra.final_url, saved.rows[0].id);
      }
      if (!sources.has(source.final_url)) {
        const old = (await client.query('SELECT * FROM public.manufacturer_sources WHERE url=$1 FOR UPDATE', [source.final_url])).rows;
        assert(old.length <= 1);
        if (old[0]) {
          assert.equal(old[0].brand, brand);
          assert.equal(old[0].model, model);
          assert(!old[0].canonical_model_id || old[0].canonical_model_id === parent.id);
        }
        const saved = await client.query(`INSERT INTO public.manufacturer_sources
          (canonical_model_id,brand,model,source_type,url,title,country,language,fetched_at,content_hash,
           http_status,final_url,source_validation,source_authority,source_name,extraction_status,verified_at)
          VALUES ($1,$2,$3,$8,$4,$5,'SE','sv',$6,$7,200,$4,'reachable_official_model_source',
           'manufacturer',$9,'published',$6)
          ON CONFLICT(url) DO UPDATE SET canonical_model_id=excluded.canonical_model_id,
           fetched_at=excluded.fetched_at,content_hash=excluded.content_hash,http_status=200,
           final_url=excluded.final_url,source_validation=excluded.source_validation,
           extraction_status='published',verified_at=excluded.verified_at,updated_at=now() RETURNING id`,
          [parent.id, brand, model, source.final_url, policy.sourceTitle(draft), source.fetched_at, source.content_hash, policy.sourceType, sourceName]);
        sources.set(source.final_url, saved.rows[0].id);
      }
      const quote = [...new Set(Object.values(draft.field_evidence).map(item => item.source_url === source.final_url
        ? item.quote : item.source_url + ' | ' + item.quote))].join(' | ');
      const payload = { adapter: policy.adapter, field_evidence: draft.field_evidence, held_fields: draft.held_fields,
        supporting_sources: draft.supporting_sources || [], source_resolution: draft.source_resolution || null,
        model_facts: draft.model_facts || {}, model_field_evidence: draft.model_field_evidence || {},
        ...(draft.price_evidence ? { price_evidence: draft.price_evidence } : {}),
        ...(draft.source_decisions ? { source_decisions: draft.source_decisions } : {}),
        previous_canonical: target.expected,
        refresh_batch_id: expectedHash, previous_source_url: expected.source_url, previous_source_hash: expected.source_hash };
      const fields = Object.keys(draft.facts);
      const values = fields.map(field => draft.facts[field]);
      const sourceId = sources.get(source.final_url);
      const draftColumns = ['canonical_model_id','source_id','brand','model','variant_name',...fields,
        'source_url','source_hash','source_quote','extraction_confidence','extraction_payload','validation_status'];
      const draftValues = [parent.id,sourceId,brand,model,draft.variant_name,...values,
        source.final_url,source.content_hash,quote,draft.extraction_confidence,JSON.stringify(payload),'extracted'];
      const placeholders = draftValues.map((_, index) => '$' + (index + 1));
      await client.query(`INSERT INTO public.extracted_variant_drafts (${draftColumns.join(',')}) VALUES (${placeholders.join(',')})
        ON CONFLICT(source_url,variant_name) DO UPDATE SET ${draftColumns.filter(field => !['source_url','variant_name'].includes(field)).map(field => field + '=excluded.' + field).join(',')},updated_at=now()`, draftValues);
      const extra = policy.canonicalExtras?.(draft, target.expected) || {};
      const allowedPriceFields = ['price_type','price_valid_until','price_source_url','price_source_hash',
        'price_source_quote','price_verified_at','price_source_name','price_refresh_batch_id'];
      assert(Object.keys(extra).every(field => allowedPriceFields.includes(field) && policy.canonicalFields?.includes(field)),
        'Only explicitly validated price provenance may supplement technical facts');
      const updateFields = [...fields, ...Object.keys(extra)];
      const updates = updateFields.map((field, index) => field + '=$' + (index + 1));
      const updateValues = [...values, ...Object.values(extra),sourceId,source.final_url,source.content_hash,quote,draft.extraction_confidence,target.id];
      const offset = updateFields.length;
      updates.push(`source_id=$${offset + 1}`,`source_url=$${offset + 2}`,`source_hash=$${offset + 3}`,
        `source_quote=$${offset + 4}`,`extraction_confidence=$${offset + 5}`,'updated_at=now()');
      if (policy.reviewRefresh?.(target.expected, draft)) {
        assert.deepEqual(policy.reviewResetFields, ['validation_status', 'review_approved_by', 'review_reason', 'review_promoted_at']);
        updates.push("validation_status='published'", 'review_approved_by=null', 'review_reason=null', 'review_promoted_at=null');
      }
      await client.query(`UPDATE public.canonical_model_variants SET ${updates.join(',')} WHERE id=$${offset + 6}`, updateValues);
      await client.query("UPDATE public.extracted_variant_drafts SET validation_status='published',validation_errors='[]'::jsonb WHERE source_url=$1 AND variant_name=$2", [source.final_url,draft.variant_name]);
    }
    const after = plain((await client.query('SELECT * FROM public.canonical_model_variants ORDER BY id')).rows);
    const targets = new Map(plan.targets.map(row => [row.id, row]));
    assert.equal(after.length, before.length);
    for (const row of after) {
      const target = targets.get(row.id);
      if (!target) assert.deepEqual(row, beforeById.get(row.id), 'Out-of-scope variant changed');
      else {
        assert.deepEqual(retained(row, policy), retained(beforeById.get(row.id), policy), 'Price, status or identity changed');
        if (policy.reviewRefresh?.(target.expected, target.draft)) {
          assert.equal(row.validation_status, 'published');
          assert(policy.reviewResetFields.filter(field => field !== 'validation_status').every(field => row[field] === null));
        } else for (const field of policy.reviewResetFields || []) assert.deepEqual(row[field], beforeById.get(row.id)[field]);
        for (const [field, value] of Object.entries(target.draft.facts)) {
          assert.equal(typeof value === 'number' ? Number(row[field]) : row[field], value);
        }
        for (const [field, value] of Object.entries(policy.canonicalExtras?.(target.draft, target.expected) || {}))
          assert.equal(field === 'price_verified_at' ? new Date(row[field]).toISOString() : row[field], value,
            'Saved price evidence differs: ' + field);
        for (const field of TECHNICAL_FIELDS.filter(field => !(field in target.draft.facts)))
          assert.deepEqual(row[field], beforeById.get(row.id)[field], 'An unprovided fact was cleared');
      }
    }
    assert.deepEqual(plain((await client.query('SELECT * FROM public.canonical_models ORDER BY id')).rows), expectedModels);
    await client.query('COMMIT');
    committed = true;
    return { committed: true, variants_updated: plan.targets.length, sources_updated: sources.size,
      new_technical_values: plan.targets.reduce((sum, row) => sum + Object.keys(row.draft.facts).filter(field => row.expected[field] == null).length, 0),
      plan_sha256: expectedHash, prices_changed: 0,
      models_changed: expectedModels.filter((row, index) => row.body_type !== models[index].body_type).length, paid_calls: 0 };
  } finally { if (!committed) await client.query('ROLLBACK'); }
}
