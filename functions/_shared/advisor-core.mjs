import { isPublicVariant, normalizeRequirements, ruleAdvice, matchAdvisorVariants } from '../../src/advisor-matching.js';
import { REQUIREMENTS_SCHEMA, requirementsPrompt } from './advisor-requirements.mjs';

const COMPARE_RESPONSE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['mode', 'winner', 'summary', 'reasons', 'tradeoffs', 'compared'],
  properties: {
    mode: { type: 'string', enum: ['openai'] },
    winner: {
      type: 'object',
      additionalProperties: false,
      required: ['variant_key', 'name', 'decision_score', 'source_url'],
      properties: {
        variant_key: { type: 'string' },
        name: { type: 'string' },
        decision_score: { type: 'number' },
        source_url: { type: 'string' },
      },
    },
    summary: { type: 'string', maxLength: 360 },
    reasons: { type: 'array', minItems: 1, maxItems: 4, items: { type: 'string', maxLength: 150 } },
    tradeoffs: { type: 'array', minItems: 1, maxItems: 4, items: { type: 'string', maxLength: 150 } },
    compared: {
      type: 'array',
      minItems: 1,
      maxItems: 3,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['variant_key', 'name', 'decision_score', 'price_sek', 'wltp_range_km', 'source_url'],
        properties: {
          variant_key: { type: 'string' },
          name: { type: 'string' },
          decision_score: { type: 'number' },
          price_sek: { type: ['number', 'null'] },
          wltp_range_km: { type: ['number', 'null'] },
          source_url: { type: 'string' },
        },
      },
    },
  },
};

function toNumber(value, fallback = null) {
  if (value === null || value === undefined || value === '') return fallback;
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function stableId(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `ev-${(hash >>> 0).toString(36)}`;
}

function cleanText(value, fallback = '', maxLength = 220) {
  const text = String(value || fallback || '').replace(/\s+/g, ' ').trim();
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1).trim()}…`;
}

function cleanList(value, fallback, maxItems, maxLength) {
  const source = Array.isArray(value) && value.length ? value : fallback;
  return source.slice(0, maxItems).map((item) => cleanText(item, '', maxLength)).filter(Boolean);
}

function formatSek(value) {
  return value ? `${new Intl.NumberFormat('sv-SE').format(value)} kr` : 'pris saknas';
}

function displayName(row) {
  const variant = row.variant_name && row.variant_name.toLowerCase() !== row.model.toLowerCase()
    ? ` ${row.variant_name}`
    : '';
  return `${row.brand} ${row.model}${variant}`.trim();
}

export function normalizePublicVariants(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter(isPublicVariant)
    .map((row) => {
      const variantKey = `${row.brand}|${row.model}|${row.variant_name}`;
      return {
        id: row.id || stableId(variantKey),
        variant_key: variantKey,
        brand: row.brand,
        model: row.model,
        variant_name: row.variant_name,
        price_sek: toNumber(row.price_sek),
        wltp_range_km: toNumber(row.wltp_range_km),
        dc_charge_kw: toNumber(row.dc_charge_kw),
        boot_liters: toNumber(row.boot_liters),
        tow_kg: toNumber(row.tow_kg),
        seats: toNumber(row.seats),
        drivetrain: row.drivetrain || '',
        source_url: row.source_url,
        source_hash: row.source_hash,
        price_type: ['list_price', 'campaign_price', 'dealer_offer'].includes(row.price_type) ? row.price_type : null,
        price_valid_until: row.price_valid_until || null,
        validation_status: row.validation_status,
        market_seen: row.market_seen === true,
        available_confirmed: row.available_confirmed === true,
      };
    });
}

export function deterministicAdvice(variants, request = {}) {
  return ruleAdvice(variants, request);
}

function compareScore(row) {
  const priceScore = row.price_sek ? Math.max(0, 30 - (row.price_sek - 450000) / 30000) : 8;
  const rangeScore = row.wltp_range_km ? Math.min(28, row.wltp_range_km / 24) : 8;
  const chargeScore = row.dc_charge_kw ? Math.min(16, row.dc_charge_kw / 14) : 5;
  const utilityScore = Math.min(14, (row.boot_liters || 320) / 40) + Math.min(12, (row.tow_kg || 0) / 160);
  return Math.round(Math.max(0, Math.min(100, priceScore + rangeScore + chargeScore + utilityScore)));
}

export function deterministicCompareReport(selected) {
  const ranked = selected
    .map((row) => ({ ...row, decision_score: compareScore(row) }))
    .sort((a, b) => b.decision_score - a.decision_score);
  const winner = ranked[0];
  return {
    mode: 'deterministic_fallback',
    winner: winner ? {
      variant_key: winner.variant_key,
      name: displayName(winner),
      decision_score: winner.decision_score,
      source_url: winner.source_url,
    } : null,
    summary: winner
      ? `${displayName(winner)} ger den starkaste balansen i den här jämförelsen utifrån tillgängliga verifierade värden.`
      : 'Välj minst en publicerad bil för att skapa rapporten.',
    reasons: winner ? [
      `Prisnivå: ${formatSek(winner.price_sek)}.`,
      winner.wltp_range_km ? `Räckvidd: ${winner.wltp_range_km} km WLTP.` : 'Räckvidd saknas i databasen.',
      winner.tow_kg ? `Dragvikt: ${winner.tow_kg} kg.` : winner.boot_liters ? `Bagage: ${winner.boot_liters} liter.` : 'Praktiska uppgifter saknas.',
    ] : [],
    tradeoffs: ranked.slice(1, 3).map((row) => `${displayName(row)} kan passa bättre om dess enskilda styrkor väger tyngre för dig.`),
    compared: ranked.map((row) => ({
      variant_key: row.variant_key,
      name: displayName(row),
      decision_score: row.decision_score,
      price_sek: row.price_sek,
      wltp_range_km: row.wltp_range_km,
      source_url: row.source_url,
    })),
  };
}

function compactVariant(row) {
  return {
    id: row.id,
    variant_key: row.variant_key,
    name: displayName(row),
    brand: row.brand,
    model: row.model,
    variant: row.variant_name,
    price_sek: row.price_sek,
    wltp_range_km: row.wltp_range_km,
    dc_charge_kw: row.dc_charge_kw,
    boot_liters: row.boot_liters,
    tow_kg: row.tow_kg,
    seats: row.seats,
    drivetrain: row.drivetrain,
    source_url: row.source_url,
    validation_status: row.validation_status,
    price_type: row.price_type,
    price_valid_until: row.price_valid_until,
    market_seen: row.market_seen,
    available_confirmed: row.available_confirmed,
  };
}

function normalizeCompareReport(result, selected) {
  if (!result) return deterministicCompareReport(selected);
  const byKey = new Map(selected.map((row) => [row.variant_key, row]));
  const compared = [];
  for (const item of Array.isArray(result.compared) ? result.compared : []) {
    if (!item || typeof item !== 'object') continue;
    const row = byKey.get(item.variant_key);
    if (!row || compared.some((current) => current.variant_key === row.variant_key)) continue;
    compared.push({
      variant_key: row.variant_key,
      name: displayName(row),
      decision_score: Math.max(0, Math.min(100, toNumber(item.decision_score, compareScore(row)))),
      price_sek: row.price_sek,
      wltp_range_km: row.wltp_range_km,
      source_url: row.source_url,
    });
  }
  const winnerItem = compared.find((row) => row.variant_key === result.winner?.variant_key);
  const winnerRow = byKey.get(winnerItem?.variant_key);
  if (!winnerRow || compared.length !== selected.length) return deterministicCompareReport(selected);
  const fallback = deterministicCompareReport(selected);
  return {
    mode: 'openai',
    winner: {
      variant_key: winnerRow.variant_key,
      name: displayName(winnerRow),
      decision_score: winnerItem.decision_score,
      source_url: winnerRow.source_url,
    },
    summary: cleanText(result.summary, fallback.summary, 360),
    reasons: cleanList(result.reasons, fallback.reasons, 4, 150),
    tradeoffs: cleanList(result.tradeoffs, fallback.tradeoffs, 4, 150),
    compared,
  };
}

function parseOpenAiJson(payload) {
  if (payload.status && payload.status !== 'completed') throw new Error('OpenAI response was not completed.');
  const outputText = payload.output_text || payload.output
    ?.flatMap((item) => item.content || [])
    .find((item) => item.type === 'output_text')?.text;
  if (!outputText) throw new Error('OpenAI response did not include output_text.');
  return JSON.parse(outputText);
}

async function openAiJson({ input, schemaName, schema, apiKey, model, fetchImpl, maxOutputTokens = 2400 }) {
  if (!apiKey) return null;
  const response = await fetchImpl('https://api.openai.com/v1/responses', {
    method: 'POST',
    signal: AbortSignal.timeout(25000),
    redirect: 'manual',
    headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json' },
    body: JSON.stringify({
      model: model || 'gpt-5.4-mini',
      store: false,
      max_output_tokens: maxOutputTokens,
      input,
      text: { format: { type: 'json_schema', name: schemaName, strict: true, schema } },
    }),
  });
  if (!response.ok) {
    const error = new Error('OpenAI request failed.');
    error.providerStatus = response.status;
    const payload = await response.json().catch(() => ({}));
    const knownCodes = ['insufficient_quota', 'rate_limit_exceeded', 'invalid_api_key', 'model_not_found'];
    error.providerCode = knownCodes.find((code) => code === payload.error?.code || code === payload.error?.type);
    throw error;
  }
  return parseOpenAiJson(await response.json());
}

function failureCode(error) {
  if (Number.isInteger(error?.providerStatus)) return `http_${error.providerStatus}${error.providerCode ? `_${error.providerCode}` : ''}`;
  return ['TimeoutError', 'AbortError', 'SyntaxError', 'TypeError'].includes(error?.name) ? error.name : 'invalid_response';
}

function comparePrompt(selected) {
  return [
    {
      role: 'system',
      content: 'Du är SeekEV:s svenska jämförelseanalytiker. Använd endast medskickade publicerade canonical-varianter och aldrig externa fakta. Saknade värden är okända, inte noll. Skilj listpris från kampanj och återförsäljarerbjudande. Tillgänglighet måste vara uttryckligen bekräftad i underlaget. Vinnaren gäller rapportens allmänna viktning, inte alla köpares behov.',
    },
    {
      role: 'user',
      content: JSON.stringify({ selected_public_variants: selected.map(compactVariant), response_language: 'sv-SE' }),
    },
  ];
}

export async function createAdvisorResult({ request, variants, apiKey, model, fetchImpl = fetch }) {
  variants = variants.filter(isPublicVariant);
  if (apiKey && variants.length && String(request.prompt || '').trim()) {
    try {
      const result = await openAiJson({
        input: requirementsPrompt(request),
        schemaName: 'ev_search_requirements',
        schema: REQUIREMENTS_SCHEMA,
        apiKey,
        model,
        fetchImpl,
        maxOutputTokens: 512,
      });
      const requirements = normalizeRequirements(result, request);
      return matchAdvisorVariants(variants, requirements, { mode: 'openai', interpretation: 'openai' });
    } catch (error) {
      console.error('OpenAI advisor unavailable; returning canonical fallback.', failureCode(error));
    }
  }
  return deterministicAdvice(variants, request);
}

export async function createCompareResult({ variantKeys, variants, apiKey, model, fetchImpl = fetch }) {
  variants = variants.filter(isPublicVariant);
  const requested = new Set(Array.isArray(variantKeys) ? variantKeys : []);
  const selected = variants.filter((row) => requested.has(row.variant_key)).slice(0, 3);
  if (!selected.length) return null;
  let result = null;
  if (apiKey) {
    try {
      result = await openAiJson({
        input: comparePrompt(selected),
        schemaName: 'ev_compare_report',
        schema: COMPARE_RESPONSE_SCHEMA,
        apiKey,
        model,
        fetchImpl,
      });
    } catch (error) {
      console.error('OpenAI comparison unavailable; returning canonical fallback.', failureCode(error));
    }
  }
  return normalizeCompareReport(result, selected);
}
