import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.cwd();

async function loadLocalEnv() {
  for (const filename of ['.env.local', '.env']) {
    try {
      const text = await readFile(join(ROOT, filename), 'utf8');
      for (const line of text.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
        const [rawKey, ...rawValueParts] = trimmed.split('=');
        const key = rawKey.trim();
        const rawValue = rawValueParts.join('=').trim();
        if (!key || process.env[key]) continue;
        process.env[key] = rawValue.replace(/^['"]|['"]$/g, '');
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
}

await loadLocalEnv();

const PORT = Number(process.env.ADVISOR_API_PORT || 8787);
const OPENAI_MODEL = process.env.OPENAI_MODEL || 'gpt-5.4-mini';
const PUBLIC_STATUSES = new Set(['published', 'published_reviewed']);
const ADVISOR_RESPONSE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['mode', 'interpreted_requirements', 'summary', 'shortlist'],
  properties: {
    mode: { type: 'string', enum: ['openai'] },
    interpreted_requirements: {
      type: 'object',
      additionalProperties: false,
      required: ['budget_sek', 'min_wltp_range_km', 'need', 'notes'],
      properties: {
        budget_sek: { type: ['number', 'null'] },
        min_wltp_range_km: { type: ['number', 'null'] },
        need: { type: 'string', maxLength: 120 },
        notes: { type: 'string', maxLength: 220 },
      },
    },
    summary: { type: 'string', maxLength: 360 },
    shortlist: {
      type: 'array',
      minItems: 1,
      maxItems: 3,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'brand', 'model', 'variant_name', 'match_score', 'reasons', 'tradeoffs', 'source_url'],
        properties: {
          id: { type: 'string' },
          brand: { type: 'string' },
          model: { type: 'string' },
          variant_name: { type: 'string' },
          match_score: { type: 'number' },
          reasons: { type: 'array', items: { type: 'string', maxLength: 140 }, minItems: 1, maxItems: 3 },
          tradeoffs: { type: 'array', items: { type: 'string', maxLength: 140 }, minItems: 1, maxItems: 3 },
          source_url: { type: 'string' },
        },
      },
    },
  },
};
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

function jsonResponse(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type',
    'cache-control': 'no-store',
  });
  res.end(body);
}

async function readRequestJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

function toNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

async function loadPublicVariants() {
  const raw = await readFile(join(ROOT, 'public/data/public_ev_variants.json'), 'utf8');
  const payload = JSON.parse(raw);
  return (payload.records || [])
    .filter((row) => PUBLIC_STATUSES.has(row.validation_status))
    .map((row) => {
      const variantKey = `${row.brand}|${row.model}|${row.variant_name}`;
      return {
        id: createHash('sha1').update(variantKey).digest('hex').slice(0, 12),
        variant_key: variantKey,
        brand: row.brand,
        model: row.model,
        variant_name: row.variant_name,
        price_sek: toNumber(row.price_sek, null),
        wltp_range_km: toNumber(row.wltp_range_km, null),
        dc_charge_kw: toNumber(row.dc_charge_kw, null),
        boot_liters: toNumber(row.boot_liters, null),
        tow_kg: toNumber(row.tow_kg, null),
        seats: toNumber(row.seats, null),
        drivetrain: row.drivetrain || '',
        source_url: row.source_url,
        source_hash: row.source_hash,
        source_quote: row.source_quote,
        validation_status: row.validation_status,
        market_seen: Boolean(row.market_seen),
        available_confirmed: Boolean(row.available_confirmed),
      };
    });
}

function scoreVariant(row, request) {
  const prompt = String(request.prompt || '').toLowerCase();
  const budget = toNumber(request.budget, 700000);
  const minRange = toNumber(request.range, 450);
  const price = row.price_sek || 9999999;
  const range = row.wltp_range_km || 0;
  const tow = row.tow_kg || 0;
  const boot = row.boot_liters || 0;
  const drivetrain = String(row.drivetrain || '').toLowerCase();

  const budgetScore = price <= budget ? 32 : Math.max(0, 32 - (price - budget) / 14000);
  const rangeScore = Math.min(28, (range / Math.max(minRange, 1)) * 24);
  const practicalScore = Math.min(16, (boot || 300) / 35) + Math.min(10, tow / 180);
  const promptScore =
    (prompt.includes('familj') || prompt.includes('barn') ? (boot >= 400 ? 8 : 2) : 0) +
    (prompt.includes('drag') ? (tow >= 1000 ? 10 : 0) : 0) +
    (prompt.includes('vinter') || prompt.includes('fjäll') ? (drivetrain.includes('fyr') || drivetrain.includes('awd') ? 8 : 3) : 0) +
    (prompt.includes('billig') || prompt.includes('pris') ? (price <= budget ? 6 : 0) : 0);

  return Math.round(Math.min(100, budgetScore + rangeScore + practicalScore + promptScore));
}

export function deterministicAdvice(variants, request) {
  const shortlist = variants
    .map((row) => ({ ...row, match_score: scoreVariant(row, request) }))
    .sort((a, b) => b.match_score - a.match_score)
    .slice(0, 3)
    .map((row) => ({
      id: row.id,
      brand: row.brand,
      model: row.model,
      variant_name: row.variant_name,
      match_score: row.match_score,
      reasons: [
        row.price_sek ? `Pris från ${new Intl.NumberFormat('sv-SE').format(row.price_sek)} kr.` : 'Pris saknas i publicerad data.',
        row.wltp_range_km ? `${row.wltp_range_km} km WLTP i verifierad publicerad data.` : 'WLTP saknas i publicerad data.',
        row.tow_kg ? `Dragvikt ${row.tow_kg} kg.` : row.boot_liters ? `Bagage ${row.boot_liters} liter.` : 'Se källan för fler detaljer.',
      ],
      tradeoffs: [
        row.available_confirmed ? 'Tillgänglighet är bekräftad i canonical data.' : 'Tillgänglighet är inte bekräftad separat ännu.',
      ],
      source_url: row.source_url,
    }));

  return {
    mode: 'deterministic_fallback',
    interpreted_requirements: {
      budget_sek: toNumber(request.budget, 700000),
      min_wltp_range_km: toNumber(request.range, 450),
      need: request.need || 'allround',
      notes: 'Fallback utan OpenAI: rankning görs bara mot publicerade canonical-varianter.',
    },
    summary: 'Här är en preliminär shortlist från verifierade publicerade varianter. Starta API-servern med OPENAI_API_KEY för mer nyanserad rådgivning.',
    shortlist,
  };
}

function compareScore(row) {
  const priceScore = row.price_sek ? Math.max(0, 30 - (row.price_sek - 450000) / 30000) : 8;
  const rangeScore = row.wltp_range_km ? Math.min(28, row.wltp_range_km / 24) : 8;
  const chargeScore = row.dc_charge_kw ? Math.min(16, row.dc_charge_kw / 14) : 5;
  const utilityScore = Math.min(14, (row.boot_liters || 320) / 40) + Math.min(12, (row.tow_kg || 0) / 160);
  return Math.round(Math.max(0, Math.min(100, priceScore + rangeScore + chargeScore + utilityScore)));
}

function formatSek(value) {
  if (!value) return 'pris saknas';
  return `${new Intl.NumberFormat('sv-SE').format(value)} kr`;
}

function displayName(row) {
  const variant = row.variant_name && row.variant_name.toLowerCase() !== row.model.toLowerCase() ? ` ${row.variant_name}` : '';
  return `${row.brand} ${row.model}${variant}`.trim();
}

function cleanText(value, fallback = '', maxLength = 220) {
  const text = String(value || fallback || '').replace(/\s+/g, ' ').trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 1)).trim()}…`;
}

function cleanList(value, fallback, maxItems, maxLength) {
  const source = Array.isArray(value) && value.length ? value : fallback;
  return source.slice(0, maxItems).map((item) => cleanText(item, '', maxLength)).filter(Boolean);
}

function advisorSummaryText(result, shortlist) {
  const summary = cleanText(result?.summary, '', 260);
  if (/Bäst för dig:|Tänk på:|Alternativ:/i.test(summary)) return cleanText(summary, '', 360);
  const best = shortlist[0] ? `${shortlist[0].brand} ${shortlist[0].model}` : 'shortlisten';
  const tradeoff = shortlist[0]?.tradeoffs?.[0] || 'kontrollera kompromisserna mot dina krav';
  const alternative = shortlist[1] ? `${shortlist[1].brand} ${shortlist[1].model}` : 'nästa bil i listan';
  return cleanText(`Bäst för dig: ${best}. Tänk på: ${tradeoff}. Alternativ: ${alternative} om prioriteringen skiftar.`, '', 360);
}

function compareSummaryText(result, winnerRow, compared) {
  const summary = cleanText(result?.summary, '', 260);
  if (/Bäst val:|Tänk på:|Välj alternativet om:/i.test(summary)) return cleanText(summary, '', 360);
  const best = displayName(winnerRow);
  const alternative = compared.find((item) => item.variant_key !== winnerRow.variant_key)?.name || 'nästa alternativ';
  return cleanText(`Bäst val: ${best}. Tänk på: jämför pris, räckvidd och praktiska krav innan beslut. Välj alternativet om: ${alternative} passar din budget eller körning bättre.`, '', 360);
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
  };
}

function canonicalShortlistItem(row, item = {}) {
  const safeReasons = cleanList(item.reasons, [], 3, 140);
  const safeTradeoffs = cleanList(item.tradeoffs, [], 3, 140);
  return {
    id: row.id,
    brand: row.brand,
    model: row.model,
    variant_name: row.variant_name,
    match_score: toNumber(item.match_score, row.match_score || scoreVariant(row, {})),
    reasons: Array.isArray(item.reasons) && item.reasons.length
      ? safeReasons
      : [
          row.price_sek ? `Pris från ${new Intl.NumberFormat('sv-SE').format(row.price_sek)} kr.` : 'Pris saknas i publicerad data.',
          row.wltp_range_km ? `${row.wltp_range_km} km WLTP i verifierad publicerad data.` : 'WLTP saknas i publicerad data.',
        ],
    tradeoffs: Array.isArray(item.tradeoffs) && item.tradeoffs.length
      ? safeTradeoffs
      : [
          row.available_confirmed ? 'Tillgänglighet är bekräftad i canonical data.' : 'Tillgänglighet är inte bekräftad separat ännu.',
        ],
    source_url: row.source_url,
  };
}

export function normalizeAdvisorResult(result, variants, request) {
  if (!result) return deterministicAdvice(variants, request);
  const byId = new Map(variants.map((row) => [row.id, row]));
  const byKey = new Map(variants.map((row) => [row.variant_key, row]));
  const shortlist = [];

  for (const item of Array.isArray(result.shortlist) ? result.shortlist : []) {
    const row = byId.get(item.id) || byKey.get(item.variant_key);
    if (!row || shortlist.some((current) => current.id === row.id)) continue;
    shortlist.push(canonicalShortlistItem(row, item));
    if (shortlist.length === 3) break;
  }

  if (!shortlist.length) return deterministicAdvice(variants, request);

  return {
    mode: 'openai',
    interpreted_requirements: {
      budget_sek: toNumber(result.interpreted_requirements?.budget_sek, toNumber(request.budget, 700000)),
      min_wltp_range_km: toNumber(result.interpreted_requirements?.min_wltp_range_km, toNumber(request.range, 450)),
      need: cleanText(result.interpreted_requirements?.need, request.need || 'allround', 120),
      notes: cleanText(result.interpreted_requirements?.notes, 'AI-rådet är eftervaliderat mot publicerade canonical-varianter.', 220),
    },
    summary: advisorSummaryText(result, shortlist),
    shortlist,
  };
}

function canonicalComparedItem(row, item = {}) {
  return {
    variant_key: row.variant_key,
    name: displayName(row),
    decision_score: toNumber(item.decision_score, compareScore(row)),
    price_sek: row.price_sek,
    wltp_range_km: row.wltp_range_km,
    source_url: row.source_url,
  };
}

export function normalizeCompareReport(result, selected) {
  if (!result) return deterministicCompareReport(selected);
  const byKey = new Map(selected.map((row) => [row.variant_key, row]));
  const compared = [];

  for (const item of Array.isArray(result.compared) ? result.compared : []) {
    const row = byKey.get(item.variant_key);
    if (!row || compared.some((current) => current.variant_key === row.variant_key)) continue;
    compared.push(canonicalComparedItem(row, item));
  }

  if (!compared.length) return deterministicCompareReport(selected);

  const winnerRow = byKey.get(result.winner?.variant_key) || byKey.get(compared[0].variant_key);
  if (!winnerRow) return deterministicCompareReport(selected);

  const fallback = deterministicCompareReport(selected);
  return {
    mode: 'openai',
    winner: {
      variant_key: winnerRow.variant_key,
      name: displayName(winnerRow),
      decision_score: toNumber(result.winner?.decision_score, compareScore(winnerRow)),
      source_url: winnerRow.source_url,
    },
    summary: compareSummaryText(result, winnerRow, compared),
    reasons: cleanList(result.reasons, fallback.reasons, 4, 150),
    tradeoffs: cleanList(result.tradeoffs, fallback.tradeoffs, 4, 150),
    compared,
  };
}

export function deterministicCompareReport(selected) {
  const ranked = selected
    .map((row) => ({ ...row, decision_score: compareScore(row) }))
    .sort((a, b) => b.decision_score - a.decision_score);
  const winner = ranked[0];
  const alternatives = ranked.slice(1);

  return {
    mode: 'deterministic_fallback',
    winner: winner
      ? {
          variant_key: winner.variant_key,
          name: displayName(winner),
          decision_score: winner.decision_score,
          source_url: winner.source_url,
        }
      : null,
    summary: winner
      ? `${displayName(winner)} är starkast i jämförelsen med bäst balans mellan pris, räckvidd, laddning och vardagsnytta i publicerad canonical-data.`
      : 'Välj minst en publicerad bil för att skapa en beslutsrapport.',
    reasons: winner
      ? [
          `Prisnivå: ${formatSek(winner.price_sek)}.`,
          winner.wltp_range_km ? `Räckvidd: ${winner.wltp_range_km} km WLTP.` : 'Räckvidd saknas i publicerad data.',
          winner.tow_kg ? `Dragvikt: ${winner.tow_kg} kg.` : winner.boot_liters ? `Bagage: ${winner.boot_liters} liter.` : 'Kompletterande nyttodata saknas.',
        ]
      : [],
    tradeoffs: alternatives.slice(0, 2).map((row) => {
      if ((row.price_sek || 9999999) < (winner.price_sek || 9999999)) {
        return `${displayName(row)} är billigare men väger svagare i helhetsbalansen.`;
      }
      if ((row.wltp_range_km || 0) > (winner.wltp_range_km || 0)) {
        return `${displayName(row)} har längre räckvidd men sämre totalpoäng här.`;
      }
      return `${displayName(row)} är ett rimligt alternativ om känsla, varumärke eller utrustning väger tyngre.`;
    }),
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

function buildAdvisorPrompt(variants, request) {
  const compactVariants = variants.map(compactVariant);

  return [
    {
      role: 'system',
      content:
        'Du är Elbilsguidens svenska AI-rådgivare. Rekommendera endast bilar från medskickad publicerad canonical-data. Använd aldrig externa fakta. Svara kort och beslutsorienterat. Summary ska ha formatet: "Bäst för dig: ... Tänk på: ... Alternativ: ...". Reasons och tradeoffs ska vara konkreta, max en mening var.',
    },
    {
      role: 'user',
      content: JSON.stringify({
        user_requirements: {
          prompt: request.prompt || '',
          budget_sek: request.budget,
          min_wltp_range_km: request.range,
          need: request.need,
        },
        public_variants: compactVariants,
        response_language: 'sv-SE',
        writing_rules: {
          summary_format: 'Bäst för dig: <kort slutsats>. Tänk på: <viktig kompromiss>. Alternativ: <när annat val passar>.',
          max_summary_characters: 360,
          max_reason_characters: 140,
          max_tradeoff_characters: 140,
        },
      }),
    },
  ];
}

function buildComparePrompt(selected) {
  return [
    {
      role: 'system',
      content:
        'Du är Elbilsguidens svenska jämförelseanalytiker. Skapa en kort beslutsrapport enbart från medskickade publicerade canonical-varianter. Använd aldrig externa fakta. Summary ska ha formatet: "Bäst val: ... Tänk på: ... Välj alternativet om: ...". Reasons och tradeoffs ska vara konkreta, max en mening var.',
    },
    {
      role: 'user',
      content: JSON.stringify({
        selected_public_variants: selected.map(compactVariant),
        response_language: 'sv-SE',
        scoring_guidance:
          'Väg pris, WLTP-räckvidd, laddning, bagage, dragvikt, säten och drivlina. Beskriv konkreta kompromisser för svenska konsumenter.',
        writing_rules: {
          summary_format: 'Bäst val: <kort slutsats>. Tänk på: <viktig kompromiss>. Välj alternativet om: <när annan bil passar>.',
          max_summary_characters: 360,
          max_reason_characters: 150,
          max_tradeoff_characters: 150,
        },
      }),
    },
  ];
}

function parseOpenAiJson(payload) {
  const outputText = payload.output_text || payload.output?.flatMap((item) => item.content || []).find((item) => item.type === 'output_text')?.text;
  if (!outputText) throw new Error('OpenAI response did not include output_text.');
  return JSON.parse(outputText);
}

async function openAiJson(input, schemaName, schema) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return null;

  const response = await fetch('https://api.openai.com/v1/responses', {
    method: 'POST',
    headers: {
      authorization: `Bearer ${apiKey}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: OPENAI_MODEL,
      input,
      text: {
        format: {
          type: 'json_schema',
          name: schemaName,
          strict: true,
          schema,
        },
      },
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenAI request failed: ${response.status} ${errorText.slice(0, 300)}`);
  }

  return parseOpenAiJson(await response.json());
}

async function openAiAdvice(variants, request) {
  return openAiJson(buildAdvisorPrompt(variants, request), 'ev_advisor_response', ADVISOR_RESPONSE_SCHEMA);
}

async function openAiCompareReport(selected) {
  return openAiJson(buildComparePrompt(selected), 'ev_compare_report', COMPARE_RESPONSE_SCHEMA);
}

async function handleAdvisor(req, res) {
  try {
    const request = await readRequestJson(req);
    const variants = await loadPublicVariants();
    if (!variants.length) {
      return jsonResponse(res, 503, { error: 'No published canonical variants available.' });
    }

    const openAiResult = await openAiAdvice(variants, request);
    return jsonResponse(res, 200, normalizeAdvisorResult(openAiResult, variants, request));
  } catch (error) {
    console.error(error);
    return jsonResponse(res, 500, { error: error.message });
  }
}

async function handleCompare(req, res) {
  try {
    const request = await readRequestJson(req);
    const requestedKeys = new Set(Array.isArray(request.variant_keys) ? request.variant_keys : []);
    const variants = await loadPublicVariants();
    const selected = variants.filter((row) => requestedKeys.has(row.variant_key)).slice(0, 3);

    if (!selected.length) {
      return jsonResponse(res, 400, { error: 'No selected published canonical variants matched.' });
    }

    const openAiResult = await openAiCompareReport(selected);
    return jsonResponse(res, 200, normalizeCompareReport(openAiResult, selected));
  } catch (error) {
    console.error(error);
    return jsonResponse(res, 500, { error: error.message });
  }
}

export const server = createServer((req, res) => {
  if (req.method === 'OPTIONS') return jsonResponse(res, 200, { ok: true });
  if (req.method === 'GET' && req.url === '/health') return jsonResponse(res, 200, { ok: true });
  if (req.method === 'POST' && req.url === '/api/advisor') return handleAdvisor(req, res);
  if (req.method === 'POST' && req.url === '/api/compare') return handleCompare(req, res);
  return jsonResponse(res, 404, { error: 'Not found' });
});

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  server.listen(PORT, '127.0.0.1', () => {
    console.log(`Advisor API listening on http://127.0.0.1:${PORT}`);
  });
}
