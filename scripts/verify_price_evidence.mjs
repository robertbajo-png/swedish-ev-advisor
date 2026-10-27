import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {hasPriceEvidence,priceEvidence,priceVerificationDate,PRICE_EVIDENCE_FIELDS} from '../src/price-evidence.js';
import {normalizeCatalog,catalogHash} from './sync_public_catalog.mjs';
import {auditReleaseConfig} from './verify_release_config.mjs';
import {normalizePublicVariants} from '../functions/_shared/advisor-core.mjs';
import {SITE_ORIGIN} from '../src/site-info.js';

const fixture={brand:'Skoda',model:'Enyaq',variant_name:'Solid Edition 85',price_sek:501000,price_type:'campaign_price',price_valid_until:'2026-12-15',
  source_url:'https://www.skoda.se/technical',source_hash:'a'.repeat(64),source_quote:'Synthetic technical evidence',extraction_confidence:0.95,
  validation_status:'published',market_seen:true,available_confirmed:false,coming_or_low_volume:false,discontinued_candidate:false,verified_at:'2026-07-01T00:00:00Z'};
const proof={price_source_url:'https://www.skoda.se/_doc/1d23f075-2685-40f9-ad6f-a31b09f3d660',price_source_hash:'b'.repeat(64),
  price_source_quote:'Synthetic campaign evidence only',price_source_name:'Skoda Sverige',price_verified_at:'2026-10-26T12:00:00Z'};
const row={...fixture,...proof};
assert.deepEqual(priceEvidence(row),proof);
assert.equal(hasPriceEvidence(fixture),false);
assert.equal(priceVerificationDate(row),proof.price_verified_at);
assert.equal(priceVerificationDate(fixture),fixture.verified_at);
assert.equal(normalizeCatalog([row])[0].verified_at,fixture.verified_at,'Price evidence cannot refresh technical-source dates');
assert.equal(normalizePublicVariants([row])[0].price_source_hash,proof.price_source_hash,'Advisor keeps the distinct price proof');
assert.equal(normalizePublicVariants([row])[0].source_hash,fixture.source_hash);
for(const patch of [...PRICE_EVIDENCE_FIELDS.map(field=>({[field]:null})),{price_source_url:'http://www.skoda.se/'},
    {price_source_url:'https://user:secret@www.skoda.se/'},{price_source_url:'https://ev-database.org/'},
    {price_source_hash:'bad'},{price_verified_at:'bad'}]) {
  const invalid={...row,...patch};
  assert.equal(priceEvidence(invalid),null);
  assert.equal(priceVerificationDate(invalid),null);
  assert.throws(()=>normalizeCatalog([invalid]));
  assert.equal(normalizePublicVariants([invalid]).length,0);
}
const env={SITE_URL:SITE_ORIGIN,VITE_SITE_URL:SITE_ORIGIN,VITE_OPERATOR_NAME:'Fixture operator',VITE_CONTACT_EMAIL:'contact@fixture.invalid',PUBLIC_PRIVACY_REVIEWED:'true',PUBLIC_IMAGE_RIGHTS_REVIEWED:'true'};
const audit=value=>auditReleaseConfig(env,{source:'supabase_public_ev_variants',records:[value]},new Date('2026-10-27T12:00:00Z'));
assert.equal(audit(row).checks.current_published_prices,true);
assert.equal(audit({...row,price_verified_at:'2026-08-01T00:00:00Z',verified_at:'2026-10-26T12:00:00Z'}).checks.current_published_prices,false);
assert.equal(audit({...row,price_source_hash:null,verified_at:'2026-10-26T12:00:00Z'}).checks.current_published_prices,false);
assert.equal(audit({...row,price_verified_at:'2026-10-28T12:00:00Z'}).checks.current_published_prices,false);
const snapshot=JSON.parse(await readFile(new URL('../public/data/public_ev_variants.json',import.meta.url),'utf8'));
assert.equal(catalogHash(snapshot.records),snapshot.catalog_sha256,'Legacy snapshot hashes must not change just because nullable evidence columns were added');
assert.equal(catalogHash([{...fixture,...Object.fromEntries(PRICE_EVIDENCE_FIELDS.map(field=>[field,null]))}]),catalogHash([fixture]));
console.log(JSON.stringify({price_evidence_contract_ok:true,separate_price_freshness:true,partial_evidence_fails_closed:true,advisor_evidence_preserved:true,legacy_snapshot_hash_preserved:true,remote_calls:0,paid_calls:0}));
