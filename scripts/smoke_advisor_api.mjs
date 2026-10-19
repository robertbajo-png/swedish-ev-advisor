const baseUrl = process.env.ADVISOR_API_BASE_URL || 'http://127.0.0.1:8787';

async function requestJson(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, { ...options, signal: AbortSignal.timeout(35000), redirect: 'error' });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}: ${JSON.stringify(payload)}`);
  }
  return payload;
}

function assertCanonicalShortlist(payload) {
  if (!['openai', 'deterministic_fallback'].includes(payload.mode)) {
    throw new Error(`Unexpected advisor mode: ${payload.mode}`);
  }
  if (!Array.isArray(payload.shortlist) || payload.shortlist.length < 1 || payload.shortlist.length > 3) {
    throw new Error('Advisor shortlist must contain 1-3 cars.');
  }
  for (const item of payload.shortlist) {
    for (const field of ['id', 'brand', 'model', 'variant_name', 'source_url']) {
      if (!item[field]) throw new Error(`Advisor item missing ${field}.`);
    }
    if (!Array.isArray(item.reasons) || !item.reasons.length) {
      throw new Error(`Advisor item ${item.id} is missing reasons.`);
    }
    if (!/^https:\/\/(www\.)?/.test(item.source_url)) {
      throw new Error(`Advisor item ${item.id} has invalid source_url: ${item.source_url}`);
    }
  }
}

function assertCanonicalCompare(payload) {
  if (!['openai', 'deterministic_fallback'].includes(payload.mode)) {
    throw new Error(`Unexpected compare mode: ${payload.mode}`);
  }
  if (!payload.winner?.variant_key || !payload.winner?.source_url) {
    throw new Error('Compare report winner must include canonical variant_key and source_url.');
  }
  if (!Array.isArray(payload.compared) || !payload.compared.length || payload.compared.length > 3) {
    throw new Error('Compare report must contain 1-3 compared cars.');
  }
  for (const item of payload.compared) {
    for (const field of ['variant_key', 'name', 'source_url']) {
      if (!item[field]) throw new Error(`Compare item missing ${field}.`);
    }
  }
}

const health = await requestJson('/health');
if (health.ok !== true) throw new Error('Advisor health check did not return ok=true.');
const exportPayload = await requestJson('/data/public_ev_variants.json');
const canonical = new Map((Array.isArray(exportPayload) ? exportPayload : exportPayload.records)
  .filter((row) => ['published', 'published_reviewed'].includes(row.validation_status) && row.source_hash)
  .map((row) => [`${row.brand}|${row.model}|${row.variant_name}`, row]));

const advisor = await requestJson('/api/advisor', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    prompt: 'Vi är en familj med två barn, kör till fjällen ibland, vill ha dragkrok och minst 520 km räckvidd.',
    budget: 620000,
    range: 520,
    need: 'familj',
  }),
});
assertCanonicalShortlist(advisor);
for (const item of advisor.shortlist) {
  const row = canonical.get(`${item.brand}|${item.model}|${item.variant_name}`);
  if (!row || row.source_url !== item.source_url) throw new Error('Advisor recommendation does not match the public snapshot.');
}
if (process.env.SMOKE_REQUIRE_AI === '1' && advisor.mode !== 'openai') {
  throw new Error('Advisor returned database fallback; a real AI response was required.');
}

const compare = await requestJson('/api/compare', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({
    variant_keys: advisor.shortlist.map((item) => `${item.brand}|${item.model}|${item.variant_name}`).slice(0, 3),
  }),
});
assertCanonicalCompare(compare);
if (compare.compared.length !== advisor.shortlist.length) throw new Error('Compare report omitted a selected variant.');
for (const item of compare.compared) {
  const row = canonical.get(item.variant_key);
  if (!row || row.source_url !== item.source_url || row.price_sek !== item.price_sek || row.wltp_range_km !== item.wltp_range_km) {
    throw new Error('Compare facts do not match the public snapshot.');
  }
}
if (process.env.SMOKE_REQUIRE_AI === '1' && compare.mode !== 'openai') {
  throw new Error('Compare returned database fallback; a real AI response was required.');
}

console.log(JSON.stringify({
  health_ok: true,
  advisor_mode: advisor.mode,
  advisor_shortlist: advisor.shortlist.map((item) => `${item.brand} ${item.model} ${item.variant_name}`),
  compare_mode: compare.mode,
  compare_winner: compare.winner.name,
}, null, 2));
