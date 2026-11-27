import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { readFile, writeFile, rename, mkdir, unlink } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseEnv } from 'node:util';
import { MANUFACTURER_FROM_PRICE, PRICE_EVIDENCE_FIELDS, PRICE_TYPES, hasPriceEvidence, priceEvidence, verifiedManufacturerFrom } from '../src/price-evidence.js';

import { WITHHELD_FIELDS, hasWithheldPrice, priceWithholding } from '../src/price-withholding.js';

export const SOURCE = 'supabase_public_ev_variants';
export const FIELDS = ['brand', 'model', 'variant_name', 'body_type', 'price_sek', 'price_type', 'price_valid_until',
  'wltp_range_km', 'wltp_consumption_kwh_100km', 'battery_kwh', 'dc_charge_kw', 'ac_charge_kw', 'boot_liters',
  'tow_kg', 'seats', 'drivetrain', 'source_url', 'source_name', 'source_hash', 'source_quote', 'extraction_confidence',
  'validation_status', 'market_seen', 'available_confirmed', 'discontinued_candidate', 'coming_or_low_volume',
  'image_url', 'image_source_url', 'verified_at', ...PRICE_EVIDENCE_FIELDS, ...WITHHELD_FIELDS];
const NUMERIC = { price_sek: [100000, 3000000], wltp_range_km: [50, 1200], wltp_consumption_kwh_100km: [5, 50],
  battery_kwh: [5, 300], dc_charge_kw: [20, 600], ac_charge_kw: [1, 50], boot_liters: [50, 3500], tow_kg: [0, 4000], seats: [1, 9] };
const FLAGS = ['market_seen', 'available_confirmed', 'discontinued_candidate', 'coming_or_low_volume'];
export const variantKey = (row) => [row.brand, row.model, row.variant_name].map((s) => String(s || '').normalize('NFC').trim().toLowerCase()).join('|');

function secureUrl(value) {
  const url = new URL(value);
  assert(url.protocol === 'https:' && !url.username && !url.password, 'Expected a safe HTTPS URL');
  return url;
}

export function publicHeaders(key) {
  if (key?.startsWith('sb_publishable_')) return { apikey: key };
  let role;
  try { role = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString()).role; } catch {}
  assert.equal(role, 'anon', 'Catalog export requires a public key, never a server/service key');
  return { apikey: key, authorization: `Bearer ${key}` };
}

export function normalizeCatalog(rows) {
  assert(Array.isArray(rows) && rows.length > 0 && rows.length <= 10000, 'Empty or excessive public catalog');
  const keys = new Set();
  return rows.map((input) => {
    const row = Object.fromEntries(FIELDS.map((field) => [field, input[field] ?? null]));
    if (hasPriceEvidence(row)) assert(priceEvidence(row), 'Incomplete or invalid price-specific evidence');
    else for (const field of PRICE_EVIDENCE_FIELDS) delete row[field];
    if (hasWithheldPrice(row)) assert(priceWithholding(row), 'Invalid exact withheld-stock proof');
    else for (const field of WITHHELD_FIELDS) delete row[field];
    for (const field of ['brand', 'model', 'variant_name', 'source_url', 'source_hash', 'source_quote']) {
      assert(typeof row[field] === 'string' && row[field].trim(), `Missing published evidence/identity: ${field}`);
    }
    assert(['published', 'published_reviewed'].includes(row.validation_status), 'Non-published record in catalog');
    const source = secureUrl(row.source_url);
    assert(!/mobilitysweden|ev-database|car\.info/.test(source.hostname), 'Market/comparison source is not specification evidence');
    assert(/^[a-f0-9]{64}$/i.test(row.source_hash), 'Missing SHA-256 source hash');
    for (const flag of FLAGS) assert.equal(typeof row[flag], 'boolean', `Missing boolean market flag: ${flag}`);
    for (const [field, [min, max]] of Object.entries(NUMERIC)) {
      const value = row[field];
      assert(value === null || (typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max), `Invalid numeric field: ${field}`);
    }
    assert(row.price_sek !== null || row.wltp_range_km !== null || priceWithholding(row), 'Missing both price and WLTP');
    assert(row.price_type === null || PRICE_TYPES.includes(row.price_type), 'Invalid price classification');
    if (row.price_type === MANUFACTURER_FROM_PRICE) {
      assert(verifiedManufacturerFrom(row),
        'Manufacturer starting price requires its own current price evidence');
    }
    for (const field of ['verified_at', 'price_valid_until']) if (row[field] !== null) assert(Number.isFinite(Date.parse(row[field])), `Invalid ${field}`);
    assert(typeof row.extraction_confidence === 'number' && row.extraction_confidence >= 0 && row.extraction_confidence <= 1, 'Invalid confidence');
    assert(row.validation_status === 'published_reviewed' || row.extraction_confidence >= 0.92, 'Unreviewed low-confidence record');
    const key = variantKey(row);
    assert(!keys.has(key), 'Duplicate public variant'); keys.add(key);
    return row;
  }).sort((a, b) => variantKey(a) < variantKey(b) ? -1 : variantKey(a) > variantKey(b) ? 1 : 0);
}

export function catalogHash(rows) {
  return createHash('sha256').update(JSON.stringify(normalizeCatalog(rows))).digest('hex');
}

export async function fetchCatalog({ url, key, fetchImpl = fetch, pageSize = 250, onSchema = () => {}, includeIds = false }) {
  const base = secureUrl(url);
  assert(base.pathname === '/' && !base.search && !base.hash, 'Use the plain Supabase project URL');
  const headers = { ...publicHeaders(key), prefer: 'count=exact' };
  const rows = [];
  let total;
  for (let offset = 0; total === undefined || offset < total; offset += pageSize) {
    const endpoint = new URL('/rest/v1/public_ev_variants', base);
    endpoint.search = new URLSearchParams({ select: '*', order: 'brand.asc,model.asc,variant_name.asc,id.asc', offset: String(offset), limit: String(pageSize) });
    const response = await fetchImpl(endpoint, { headers, redirect: 'error', signal: AbortSignal.timeout(15000) });
    assert(response.ok, `Canonical public read returned HTTP ${response.status}`);
    const range = /^(\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('content-range') || '');
    assert(range && Number(range[1]) === offset, 'Missing/incomplete canonical pagination');
    const count = Number(range[3]);
    assert(count > 0 && count <= 10000 && (total === undefined || total === count), 'Catalog changed or is empty/excessive during pagination');
    total = count;
    const page = await response.json();
    assert(Array.isArray(page) && page.length === Number(range[2]) - offset + 1
      && page.length === Math.min(pageSize, total - offset), 'Truncated canonical public page');
    if (offset === 0) onSchema(FIELDS.filter((field) => !Object.hasOwn(page[0], field)));
    rows.push(...page);
  }
  assert.equal(rows.length, total);
  const normalized = normalizeCatalog(rows);
  if (!includeIds) return normalized;
  const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  const identities = new Map(rows.map(row => {
    assert.match(row.id, uuid, 'Missing public variant ID');
    if (Object.hasOwn(row, 'canonical_model_id')) {
      assert.match(row.canonical_model_id, uuid, 'Invalid public canonical model ID');
      return [variantKey(row), {id: row.id, canonical_model_id: row.canonical_model_id}];
    }
    return [variantKey(row), {id: row.id}];
  }));
  assert.equal(new Set([...identities.values()].map(row => row.id)).size, identities.size, 'Duplicate public variant ID');
  return normalized.map(row => ({...row, ...identities.get(variantKey(row))}));
}

export function compareCatalogs(local, remote) {
  const byKey = (rows) => new Map(rows.map((row) => [variantKey(row), row]));
  const a = byKey(normalizeCatalog(local)), b = byKey(normalizeCatalog(remote));
  const localOnly = [...a.keys()].filter((key) => !b.has(key));
  const remoteOnly = [...b.keys()].filter((key) => !a.has(key));
  const changed = [...a.keys()].filter((key) => b.has(key)).flatMap((key) => {
    const fields = FIELDS.filter((field) => JSON.stringify(a.get(key)[field]) !== JSON.stringify(b.get(key)[field]));
    return fields.length ? [{ key, fields }] : [];
  });
  return { ok: !localOnly.length && !remoteOnly.length && !changed.length, local_count: a.size, remote_count: b.size,
    local_only: localOnly, remote_only: remoteOnly, changed,
    quarantine: localOnly.map((key) => ({ ...a.get(key), previous_validation_status: a.get(key).validation_status,
      validation_status: 'needs_review', reason: 'not_in_canonical_public_view', next_action: 'exact_variant_source_verification' })) };
}


// The only scoped timestamp representation exception supported by this mode:
// a previously published UTC ISO millisecond string generated from *the exact
// unchanged raw database value*. Strict raw before/after comparison happens
// first, so even a sub-millisecond update cannot be hidden by the projection.
const ENYAQ_PROOF_KEYS = ['85','85x','85x Sportline','RS'].map(motor=>variantKey({brand:'Skoda',model:'Enyaq',variant_name:'Solid Edition '+motor})).sort();
const ENYAQ_PRICE_URL = 'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660';
const PROOF_CHANGE_FIELDS = ['price_source_hash','price_source_quote','price_verified_at'];
const TIMESTAMP_FIELDS = ['verified_at','price_verified_at'];
const timestampPattern = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/;
function micros(value) {
  const match=typeof value==='string'&&timestampPattern.exec(value);
  assert(match,'Expected an explicit ISO timestamp with at most microsecond precision');
  const fraction=(match[2]||'').padEnd(6,'0');
  const ms=Date.parse(match[1]+'.'+fraction.slice(0,3)+match[3]);
  assert(Number.isFinite(ms),'Invalid timestamp');
  return BigInt(ms)*1000n+BigInt(fraction.slice(3));
}
function assertExactFour(diff) {
  assert(!diff.local_only.length&&!diff.remote_only.length,'Catalog identities changed');
  assert.deepEqual(diff.changed.map(x=>x.key).sort(),ENYAQ_PROOF_KEYS,'Only the four approved Enyaq proof rows may change');
  for(const change of diff.changed){
    assert(change.fields.includes('price_verified_at')&&change.fields.every(f=>PROOF_CHANGE_FIELDS.includes(f)),'Unexpected price-only field change');
  }
}
// Derive the scoped export receipt from the actual saved atomic publication
// record, not a hand-entered replacement catalog. A dry-run/stage receipt is
// insufficient. Only non-secret public rows are copied into the export receipt.
export function prepareEnyaqProofExportReceipt(liveBytes,canonicalBefore,record) {
  const live=JSON.parse(liveBytes.toString('utf8')),before=normalizeCatalog(canonicalBefore.records);
  assert.equal(catalogHash(live.records),live.catalog_sha256);
  assert.equal(catalogHash(before),canonicalBefore.canonicalHash,'Canonical pre-write receipt hash mismatch');
  const packet=record.packet,result=record.operation_result,source=record.source;
  assert(record.publication_requested===true&&result?.staged===4&&result.published===4&&result.price_verified===true&&result.specifications_reverified===false,'A real successful publication receipt is required');
  assert(packet?.adapter==='skoda_enyaq_price_separate_proof_v2'&&packet.final_url===ENYAQ_PRICE_URL&&source?.url===ENYAQ_PRICE_URL&&source.final_url===ENYAQ_PRICE_URL&&source.status==='reachable'
    &&source.brand==='Skoda'&&source.model==='Enyaq'&&source.http_status===200&&typeof source.content_type==='string'&&source.content_type.includes('pdf')
    &&source.content_hash===packet.source_hash&&micros(source.fetched_at)===micros(packet.fetched_at),'Unbound official publication source');
  assert(/^[a-f0-9]{64}$/.test(packet.batch_id||'')&&/^[a-f0-9]{64}$/.test(packet.source_hash||''));
  const expected_proofs={},m=new Map(before.map(row=>[variantKey(row),row]));
  assert.equal(record.drafts?.length,4);assert.equal(packet.targets?.length,4);
  for(const d of record.drafts){
    const key=variantKey(d),prior=m.get(key),target=packet.targets.find(t=>t.variant_name===d.variant_name);
    assert(ENYAQ_PROOF_KEYS.includes(key)&&prior&&target?.expected_price&&!expected_proofs[key],'Unbound exact published target');
    assert(d.source_url===ENYAQ_PRICE_URL&&d.source_hash===packet.source_hash&&d.extraction_payload?.adapter===packet.adapter);
    for(const field of ['price_sek','price_type','price_valid_until','price_source_url','price_source_hash','price_source_quote','price_source_name'])
      assert.equal(target.expected_price[field],prior[field],'Pre-write proof/fact mismatch: '+key+'/'+field);
    assert(micros(target.expected_price.price_verified_at)===micros(prior.price_verified_at),'Pre-write proof timestamp mismatch');
    for(const field of ['price_sek','price_type','price_valid_until'])assert.equal(d[field],prior[field]);
    expected_proofs[key]={price_sek:d.price_sek,price_type:d.price_type,price_valid_until:d.price_valid_until,
      price_source_url:d.source_url,price_source_hash:d.source_hash,price_source_quote:d.source_quote,
      price_source_name:'Skoda Sverige',price_verified_at:packet.fetched_at};
  }
  assert.deepEqual(Object.keys(expected_proofs).sort(),ENYAQ_PROOF_KEYS);
  return {kind:'approved_enyaq_proof_refresh_v2',live_snapshot_sha256:createHash('sha256').update(liveBytes).digest('hex'),
    canonical_before_hash:canonicalBefore.canonicalHash,canonical_before_records:before,
    publication:{adapter:packet.adapter,published:result.published,price_verified:result.price_verified,specifications_reverified:result.specifications_reverified,
      batch_id:packet.batch_id,source_hash:packet.source_hash,fetched_at:packet.fetched_at},expected_proofs};
}

export function planEnyaqProofOnlyExport(liveSnapshot,canonicalBefore,canonicalAfter,receipt) {
  assert.equal(receipt.kind,'approved_enyaq_proof_refresh_v2');
  assert.equal(catalogHash(liveSnapshot.records),liveSnapshot.catalog_sha256,'Invalid public baseline hash');
  const live=normalizeCatalog(liveSnapshot.records),before=normalizeCatalog(canonicalBefore),after=normalizeCatalog(canonicalAfter);
  assert.equal(catalogHash(before),receipt.canonical_before_hash,'Wrong pre-write canonical hash');
  const publication=receipt.publication;
  assert(publication?.adapter==='skoda_enyaq_price_separate_proof_v2'&&publication.published===4&&publication.price_verified===true&&publication.specifications_reverified===false
    &&/^[a-f0-9]{64}$/.test(publication.batch_id||'')&&/^[a-f0-9]{64}$/.test(publication.source_hash||''),'Expected the exact recorded v2 publication receipt');
  const freshMicros=micros(publication.fetched_at);
  const byKey=rows=>new Map(rows.map(row=>[variantKey(row),row]));
  const l=byKey(live),b=byKey(before),a=byKey(after);
  const beforeDiff=compareCatalogs(live,before);
  assert(!beforeDiff.local_only.length&&!beforeDiff.remote_only.length,'Live/canonical baseline identities differ');
  const rawDiff=compareCatalogs(before,after);
  assertExactFour(rawDiff); // Strict, unmodified canonical values, no date conversion.
  const expected=receipt.expected_proofs;
  assert.deepEqual(Object.keys(expected||{}).sort(),ENYAQ_PROOF_KEYS,'Exact approved proof matrix required');
  for(const key of ENYAQ_PROOF_KEYS){
    const old=b.get(key),row=a.get(key),proof=expected[key];
    for(const field of ['price_sek','price_type','price_valid_until','price_source_url','price_source_name']){
      assert.equal(old[field],proof[field],'Old approved fact mismatch: '+key+'/'+field);
      assert.equal(row[field],proof[field],'New approved fact mismatch: '+key+'/'+field);
    }
    assert(old.price_type==='campaign_price'&&old.price_source_url===ENYAQ_PRICE_URL&&old.price_source_name==='Skoda Sverige');
    assert.equal(row.price_source_hash,publication.source_hash,'Fresh proof hash mismatch');
    assert.equal(row.price_source_hash,proof.price_source_hash);
    assert.equal(row.price_source_quote,proof.price_source_quote);
    assert(micros(row.price_verified_at)===freshMicros&&micros(proof.price_verified_at)===freshMicros,'Fresh verification time mismatch');
    assert(micros(old.price_verified_at)<freshMicros,'Price proof did not advance');
  }
  const representation_aliases=[];
  for(const delta of beforeDiff.changed){
    assert(!ENYAQ_PROOF_KEYS.includes(delta.key),'Target price baseline must match exactly');
    for(const field of delta.fields){
      assert(TIMESTAMP_FIELDS.includes(field),'Unrelated baseline fact differs');
      const old=l.get(delta.key)[field],raw=b.get(delta.key)[field];
      micros(raw);micros(old);
      assert.equal(old,new Date(raw).toISOString(),'Not the established UTC millisecond rendering of the raw timestamp');
      assert.equal(a.get(delta.key)[field],raw,'Raw canonical timestamp changed after the baseline');
      representation_aliases.push({key:delta.key,field,retained:old,raw_canonical:raw});
    }
  }
  // Whole-catalog canonical export. Only restore the explicitly proven prior
  // serialization for unchanged raw field values; never copy prior facts.
  const rows=normalizeCatalog(after.map(row=>{
    const copy={...row};
    for(const alias of representation_aliases.filter(x=>x.key===variantKey(row)))copy[alias.field]=alias.retained;
    return copy;
  }));
  const difference=compareCatalogs(live,rows);
  assertExactFour(difference);
  for(const row of rows)if(!ENYAQ_PROOF_KEYS.includes(variantKey(row)))assert.deepEqual(row,l.get(variantKey(row)),'Unrelated published row changed');
  return {rows,difference,representation_aliases,raw_canonical_before_hash:catalogHash(before),raw_canonical_after_hash:catalogHash(after),scope:receipt.kind};
}


const PRICE_20261127_NAMES = [
  ...['60 Selection','60 Sportline','85 Selection','85 Sportline','85x Selection','85x Sportline','RS'].map(x=>['Skoda','Elroq',x+' Explore Edition']),
  ['Volkswagen','Id.3','ID.3 Neo Trend'],
  ['Volkswagen','Id.4','ID.4 Pro 4MOTION 77 kWh MY2027 (lagerbil BSJ09L)'],
  ['Volvo','Es90','ES90 Single Motor Extended Range Ultra MY2026 (lagerbil JWR04C)'],
  ['Volvo','Ex30','EX30 P5 Long Range Core MY2027 (lagerbil)'],
  ['Audi','A6 E-Tron','A6 Sportback e-tron performance S-line 270 kW MY2027 (lagerbil RRR07B)'],
  ['Audi','Q6 E-Tron','Q6 e-tron quattro SUV 315 kW MY2027 (lagerbil JCE98Y)']
];
const PRICE_20261127_KEYS=PRICE_20261127_NAMES.map(([brand,model,variant_name])=>variantKey({brand,model,variant_name})).sort();
const WITHHELD_20261127_KEYS=PRICE_20261127_KEYS.filter(k=>k.startsWith('audi|'));
const CURRENT_PRICE_FIELDS=['price_sek','price_type','price_valid_until',...PRICE_EVIDENCE_FIELDS];

function assertExactThirteen(diff) {
  assert(!diff.local_only.length&&!diff.remote_only.length,'Scoped price export cannot change identities');
  assert.deepEqual(diff.changed.map(x=>x.key).sort(),PRICE_20261127_KEYS,'Expected exactly thirteen adjudicated rows');
  for(const delta of diff.changed){
    const held=WITHHELD_20261127_KEYS.includes(delta.key);
    assert(delta.fields.every(f=>(held?[...CURRENT_PRICE_FIELDS,...WITHHELD_FIELDS]:PROOF_CHANGE_FIELDS).includes(f)), 'Out-of-scope field change');
    assert(delta.fields.includes(held?'price_withheld_reason':'price_verified_at'),'Missing adjudication evidence');
  }
}

/** The operator supplies the actual successful RPC response plus its private
 * archive readback; only public-price expectations enter the export receipt. */
export function prepareScopedPriceExportReceipt(liveBytes, canonicalBefore, record) {
  const live=JSON.parse(liveBytes.toString('utf8')),before=normalizeCatalog(canonicalBefore.records);
  assert.equal(catalogHash(live.records),live.catalog_sha256);assert.equal(catalogHash(before),canonicalBefore.canonicalHash);
  const {packet,operation_result:r,history}=record;
  assert(record.publication_requested===true&&r?.refreshed===11&&r.withheld===2&&r.already_applied===false&&r.technical_facts_changed===0,
    'Successful exact-price publication required');
  assert(packet?.adapter==='scoped_price_reverification_20261127_v1'&&packet.batch_id===r.batch_id&&/^[a-f0-9]{64}$/.test(r.batch_id||''));
  assert.equal(packet.targets?.length,13);assert.equal(history?.length,13);
  const b=new Map(before.map(row=>[variantKey(row),row])),expected_proofs={};
  const ids=new Set();
  for(const t of packet.targets) {
    const key=variantKey(t),old=b.get(key),h=history.find(x=>x.variant_id===t.id);
    assert(PRICE_20261127_KEYS.includes(key)&&old&&!expected_proofs[key]&&!ids.has(t.id)&&h&&h.batch_id===r.batch_id,'Exact target/archive binding required');
    ids.add(t.id);
    assert.equal(h.operation,t.operation);assert.deepEqual(h.before_row,t.expected);assert.deepEqual(h.evidence,t.proof);
    if(packet.source_alignment) {
      assert.equal(r.source_registry_aligned,true);
      assert.deepEqual(h.source_alignment?.before,packet.source_alignment.expected);
      assert.deepEqual(h.source_alignment?.after,{...packet.source_alignment.expected,source_authority:'manufacturer',source_name:'Skoda Sverige'});
    } else {
      assert.equal(r.source_registry_aligned,false);assert.equal(h.source_alignment,null);
    }
    assert.equal(h.before_row.id,t.id);assert.equal(h.after_row.id,t.id);
    assert(micros(h.observed_at)===micros(t.proof.observed_at));
    for(const f of CURRENT_PRICE_FIELDS) {
      if(f==='price_verified_at')assert(micros(h.before_row[f])===micros(old[f]));
      else assert.equal(h.before_row[f]??null,old[f]??null,'Prior canonical price proof mismatch');
    }
    const p=t.proof,held=WITHHELD_20261127_KEYS.includes(key);
    assert.equal(t.operation,held?'withhold':'refresh');assert.equal(p.source_url,old.price_source_url);
    if(held) {
      for(const f of CURRENT_PRICE_FIELDS)assert.equal(h.after_row[f],null);
      expected_proofs[key]={operation:'withhold',reason:p.reason,observed_at:p.observed_at};
    } else {
      for(const f of ['price_sek','price_type','price_valid_until']) {
        assert.equal(p[f]??null,old[f]??null);assert.equal(h.after_row[f],old[f]);
      }
      assert.equal(h.after_row.price_source_hash,p.source_hash);assert.equal(h.after_row.price_source_quote,p.source_quote);
      assert(micros(h.after_row.price_verified_at)===micros(p.observed_at));
      assert.equal(h.after_row.price_refresh_batch_id,r.batch_id);
      expected_proofs[key]={operation:'refresh',source_hash:p.source_hash,source_quote:p.source_quote,observed_at:p.observed_at};
    }
  }
  assert.deepEqual(Object.keys(expected_proofs).sort(),PRICE_20261127_KEYS);
  return {kind:'approved_scoped_price_reverification_20261127',live_snapshot_sha256:createHash('sha256').update(liveBytes).digest('hex'),
    canonical_before_hash:canonicalBefore.canonicalHash,canonical_before_records:before,publication:{...r,adapter:packet.adapter},expected_proofs};
}

export function planScopedPriceExport(liveSnapshot,canonicalBefore,canonicalAfter,receipt) {
  assert.equal(receipt.kind,'approved_scoped_price_reverification_20261127');
  assert.equal(catalogHash(liveSnapshot.records),liveSnapshot.catalog_sha256);
  const live=normalizeCatalog(liveSnapshot.records),before=normalizeCatalog(canonicalBefore),after=normalizeCatalog(canonicalAfter);
  assert.equal(catalogHash(before),receipt.canonical_before_hash);
  const p=receipt.publication;
  assert(p?.adapter==='scoped_price_reverification_20261127_v1'&&p.refreshed===11&&p.withheld===2&&p.already_applied===false&&p.technical_facts_changed===0&&/^[a-f0-9]{64}$/.test(p.batch_id||''));
  assert.deepEqual(Object.keys(receipt.expected_proofs||{}).sort(),PRICE_20261127_KEYS);
  const byKey=rows=>new Map(rows.map(row=>[variantKey(row),row]));
  const l=byKey(live), b=byKey(before), a=byKey(after);
  const beforeDiff=compareCatalogs(live,before);
  assert(!beforeDiff.local_only.length&&!beforeDiff.remote_only.length,'Live and canonical identities differ');
  assertExactThirteen(compareCatalogs(before,after));
  for(const key of PRICE_20261127_KEYS) {
    const old=b.get(key),row=a.get(key),proof=receipt.expected_proofs[key];
    if(WITHHELD_20261127_KEYS.includes(key)) {
      assert.equal(proof.operation,'withhold');
      const hold=priceWithholding(row);
      assert(hold&&hold.reason===proof.reason&&micros(hold.at)===micros(proof.observed_at));
      assert(micros(old.price_verified_at)<micros(hold.at));
    } else {
      assert.equal(proof.operation,'refresh');
      assert.equal(row.price_source_hash,proof.source_hash);assert.equal(row.price_source_quote,proof.source_quote);
      assert(micros(row.price_verified_at)===micros(proof.observed_at)&&micros(old.price_verified_at)<micros(row.price_verified_at));
      for(const f of ['price_sek','price_type','price_valid_until','price_source_url','price_source_name'])assert.equal(row[f],old[f]);
    }
  }
  const representation_aliases=[];
  for(const delta of beforeDiff.changed) {
    // Preserve precisely the existing proven ISO-millisecond representation of
    // a genuinely unchanged raw field. Never round a newly changed proof.
    for(const field of delta.fields) {
      assert(TIMESTAMP_FIELDS.includes(field),'Unrelated baseline fact differs');
      const old=l.get(delta.key)[field],raw=b.get(delta.key)[field];
      micros(raw);micros(old);
      assert.equal(old,new Date(raw).toISOString(),'Not the established UTC millisecond rendering');
      assert.equal(a.get(delta.key)[field],raw,'Raw timestamp changed; cannot restore representation');
      representation_aliases.push({key:delta.key,field,retained:old,raw_canonical:raw});
    }
  }
  const rows=normalizeCatalog(after.map(row=>{
    const copy={...row};
    for(const alias of representation_aliases.filter(x=>x.key===variantKey(row)))copy[alias.field]=alias.retained;
    return copy;
  }));
  const difference=compareCatalogs(live,rows);assertExactThirteen(difference);
  for(const row of rows)if(!PRICE_20261127_KEYS.includes(variantKey(row)))assert.deepEqual(row,l.get(variantKey(row)),'Unrelated published row changed');
  return {rows,difference,representation_aliases,raw_canonical_before_hash:catalogHash(before),raw_canonical_after_hash:catalogHash(after),scope:receipt.kind};
}

export function mergeQuarantine(previous, current, remote) {
  const published = new Set(remote.map(variantKey));
  return [...new Map([...previous, ...current].map((row) => [variantKey(row), row])).values()]
    .filter((row) => !published.has(variantKey(row)));
}

export async function atomicJson(path, value) {
  const destination = resolve(path), temporary = `${destination}.${randomUUID()}.tmp`;
  await mkdir(dirname(destination), { recursive: true });
  try { await writeFile(temporary, JSON.stringify(value, null, 2) + '\n'); await rename(temporary, destination); }
  finally { await unlink(temporary).catch((error) => { if (error.code !== 'ENOENT') throw error; }); }
}

export async function syncPublicCatalog({argv=process.argv.slice(2),fetchImpl=fetch}={}) {
  const env = {};
  for (const name of ['.env', '.env.local']) {
    try { Object.assign(env, parseEnv((await readFile(name, 'utf8')).replace(/^\uFEFF/, ''))); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  Object.assign(env, process.env);
  const config = { url: env.SUPABASE_URL || env.VITE_SUPABASE_URL, key: env.SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY };
  const path = 'public/data/public_ev_variants.json';
  const previousBytes=await readFile(path);
  const previous=JSON.parse(previousBytes.toString('utf8'));
  const receiptFlags=['--enyaq-proof-receipt','--scoped-price-reverification-receipt'];
  const requestedFlags=argv.filter(a=>receiptFlags.includes(a));
  assert(requestedFlags.length<=1,'Supply exactly one scoped export receipt');
  const receiptFlag=requestedFlags[0],receiptIndex=receiptFlag?argv.indexOf(receiptFlag):-1;
  let receipt;
  if(receiptIndex>=0){
    assert(argv[receiptIndex+1]&&argv.filter(a=>a===receiptFlag).length===1,'Expected one reviewed price receipt');
    assert(argv.every((a,i)=>a==='--write'||i===receiptIndex||i===receiptIndex+1),'Unexpected scoped export argument');
    receipt=JSON.parse(await readFile(argv[receiptIndex+1],'utf8'));
    assert.equal(createHash('sha256').update(previousBytes).digest('hex'),receipt.live_snapshot_sha256,'Public baseline bytes changed');
  }
  let missingFields, confirmationMissing;
  let rows = await fetchCatalog({ ...config, fetchImpl, onSchema: (fields) => { missingFields = fields; } });
  const confirmation = await fetchCatalog({ ...config, fetchImpl, onSchema: (fields) => { confirmationMissing = fields; } });
  assert.equal(catalogHash(rows), catalogHash(confirmation), 'Canonical catalog changed during export; retry later');
  assert.deepEqual(missingFields, confirmationMissing, 'Canonical view schema changed during export; retry later');
  if(receiptFlag==='--scoped-price-reverification-receipt')assert.equal(receipt.kind,'approved_scoped_price_reverification_20261127');
  const scoped=receipt?(receiptFlag==='--scoped-price-reverification-receipt'?planScopedPriceExport:planEnyaqProofOnlyExport)(previous,receipt.canonical_before_records,rows,receipt):null;
  if(scoped)rows=scoped.rows;
  const difference = compareCatalogs(previous.records, rows);
  const scopeReport=scoped?{scope:scoped.scope,representation_aliases:scoped.representation_aliases,
    raw_canonical_before_hash:scoped.raw_canonical_before_hash,raw_canonical_after_hash:scoped.raw_canonical_after_hash,
    scoped_export_verified:true}: {};
  if (!argv.includes('--write')) {
    console.log(JSON.stringify({ ...difference, quarantine: difference.quarantine.map(variantKey), missing_view_columns: missingFields, remote_writes: false, ...scopeReport }, null, 2));
    if (!scoped && !difference.ok) process.exitCode = 1;
    return;
  }
  const reportPath = 'data/review/catalog_reconciliation.json';
  let previousQuarantine = [];
  try { previousQuarantine = JSON.parse(await readFile(reportPath, 'utf8')).quarantine || []; }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const quarantine = mergeQuarantine(previousQuarantine, difference.quarantine, rows);
  await atomicJson(reportPath, { checked_at: new Date().toISOString(), ...difference,
    quarantine, missing_view_columns: missingFields, remote_writes: false, ...scopeReport });
  await atomicJson(path, { generated_at: new Date().toISOString(), source: SOURCE, schema_version: 1,
    missing_view_columns: missingFields, catalog_sha256: catalogHash(rows), records: rows });
  console.log(JSON.stringify({ canonical_snapshot_written: true, records: rows.length, new_local_only: difference.local_only, pending_review: quarantine.length,
    changed_rows: difference.changed.length, missing_view_columns: missingFields, remote_writes: false, ...scopeReport }));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  syncPublicCatalog().catch((error) => { console.error(error.name === 'AssertionError' ? error.message : 'Catalog synchronization failed; existing snapshot retained. Credentials/provider bodies are not logged.'); process.exitCode = 1; });
}
