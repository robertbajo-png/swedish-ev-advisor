const PUBLIC_STATUSES = new Set(['published', 'published_reviewed']);
export const NEEDS = ['allround', 'familj', 'pendling', 'langresa', 'vinter', 'dragkrok', 'budget'];
export const PRIORITIES = ['balanced', 'value', 'range', 'charging', 'practicality'];
export const UNSUPPORTED = ['body_type', 'equipment', 'real_world_range', 'charging_curve', 'leasing', 'availability', 'other'];
const UNSUPPORTED_LABELS = {
  body_type: 'karosstyp', equipment: 'utrustning och praktisk passform',
  real_world_range: 'verklig r\u00e4ckvidd i dina k\u00f6rf\u00f6rh\u00e5llanden',
  charging_curve: 'laddkurva och laddtid', leasing: 'leasingvillkor', availability: 'aktuell leveranstid', other: '\u00f6vriga s\u00e4rskilda \u00f6nskem\u00e5l',
};
export const REQUIREMENT_FIELDS = ['budget_sek', 'min_wltp_range_km', 'min_tow_kg', 'awd_required', 'min_seats', 'min_boot_liters', 'min_dc_charge_kw', 'brand', 'model', 'need', 'priority', 'unsupported'];
const LIMITS = { budget_sek: 3000000, min_wltp_range_km: 1200, min_tow_kg: 4000, min_seats: 9, min_boot_liters: 2000, min_dc_charge_kw: 600 };
const folded = (value) => String(value || '').normalize('NFKD').replace(/\p{Diacritic}/gu, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const number = (value) => value === null || value === undefined || value === '' || typeof value === 'boolean' ? null : Number.isFinite(Number(value)) ? Number(value) : null;
const text = (value, max) => String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
const money = (value) => new Intl.NumberFormat('sv-SE').format(value) + ' kr';

export function isPublicVariant(row) {
  if (!row || !PUBLIC_STATUSES.has(row.validation_status) || typeof row.source_hash !== 'string' || !row.source_hash.trim()) return false;
  if (![row.brand, row.model, row.variant_name].every((value) => typeof value === 'string' && value.trim())) return false;
  try {
    const source = new URL(row.source_url);
    return source.protocol === 'https:' && !source.username && !source.password;
  } catch { return false; }
}

export function normalizeRequirements(raw, request = {}) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw) || Object.keys(raw).length !== REQUIREMENT_FIELDS.length || REQUIREMENT_FIELDS.some((key) => !Object.hasOwn(raw, key))) throw new Error('Invalid requirements fields.');
  for (const [key, max] of Object.entries(LIMITS)) {
    const value = raw[key];
    if (value !== null && (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > max || (key === 'min_seats' && (!Number.isInteger(value) || value < 1)))) throw new Error('Invalid numeric requirement.');
  }
  if (typeof raw.awd_required !== 'boolean' || !NEEDS.includes(raw.need) || !PRIORITIES.includes(raw.priority)) throw new Error('Invalid requirement type.');
  if (!Array.isArray(raw.unsupported) || raw.unsupported.length > 3 || raw.unsupported.some((value) => !UNSUPPORTED.includes(value))) throw new Error('Invalid unsupported requirements.');
  for (const key of ['brand', 'model']) if (raw[key] !== null && (typeof raw[key] !== 'string' || !raw[key].trim() || raw[key].length > 80)) throw new Error('Invalid vehicle name requirement.');
  const formNumber = (value, fallback, max) => { const n = number(value); return n !== null && n >= 0 && n <= max ? n : fallback; };
  return {
    ...raw,
    budget_sek: request.explicit_controls?.budget === true ? formNumber(request.budget, 700000, LIMITS.budget_sek) : raw.budget_sek ?? formNumber(request.budget, 700000, LIMITS.budget_sek),
    min_wltp_range_km: request.explicit_controls?.range === true ? formNumber(request.range, 450, LIMITS.min_wltp_range_km) : raw.min_wltp_range_km ?? formNumber(request.range, 450, LIMITS.min_wltp_range_km),
    brand: raw.brand === null ? null : text(raw.brand, 80),
    model: raw.model === null ? null : text(raw.model, 80),
    unsupported: [...new Set(raw.unsupported)],
  };
}

export function ruleRequirements(request = {}) {
  const prompt = String(request.prompt || '').normalize('NFKD').replace(/\p{Diacritic}/gu, '').toLowerCase().replace(/[\u00a0\u202f]/g, ' ');
  const numeric = (match, multiplier = 1) => match ? Number(match[1].replace(/\s/g, '').replace(',', '.')) * multiplier : null;
  const budget = prompt.match(/(?<![-\d])(\d[\d ]*(?:[.,]\d+)?)\s*(?:(mkr|tkr)\b|(miljoner?|tusen|k)?\s*(?:kr\b|kronor\b|sek\b))/);
  const budgetUnit = budget?.[2] || budget?.[3] || '';
  const range = prompt.match(/(?:minst|minimum|minsta|rackvidd(?: pa)?)[ :]*(\d[\d ]*)\s*km\b/);
  const noTow = /(?:inte|ingen|inget|utan|ej)[^.!?]{0,25}(?:dragkrok|dragvikt|slap)/.test(prompt);
  const tow = !noTow && /drag|husvagn|slap/.test(prompt) ? prompt.match(/(\d[\d ]*(?:[.,]\d+)?)\s*(kg|ton)\b/) : null;
  const noAwd = /(?:inte|ingen|inget|utan|ej)[^.!?]{0,25}(?:fyrhjulsdrift|awd|4wd)|(?:fyrhjulsdrift|awd|4wd)[^.!?]{0,20}(?:inte|ej)[^.!?]{0,15}(?:krav|nodvandig)/.test(prompt);
  const need = /familj|barn/.test(prompt) ? 'familj' : /husvagn|dragkrok|slap/.test(prompt) && !noTow ? 'dragkrok' : /fjall|vinter/.test(prompt) ? 'vinter' : /langres/.test(prompt) ? 'langresa' : /budget|billig|prisvard/.test(prompt) ? 'budget' : NEEDS.includes(request.need) ? request.need : request.need === 'langresor' ? 'langresa' : 'allround';
  return normalizeRequirements({
    budget_sek: numeric(budget, /mkr|miljon/.test(budgetUnit) ? 1e6 : /tkr|tusen|k/.test(budgetUnit) ? 1000 : 1),
    min_wltp_range_km: numeric(range), min_tow_kg: tow ? numeric(tow, tow[2] === 'ton' ? 1000 : 1) : !noTow && /dragkrok|dragvikt/.test(prompt) ? 1 : null,
    awd_required: !noAwd && /fyrhjulsdrift|\bawd\b|\b4wd\b/.test(prompt),
    min_seats: numeric(prompt.match(/(?:minst\s*)?(\d)\s*(?:sittplatser|saten|platser)\b/)),
    min_boot_liters: numeric(prompt.match(/(?:minst\s*)?(\d[\d ]*)\s*liter\b/)),
    min_dc_charge_kw: numeric(prompt.match(/(?:minst\s*)?(\d[\d ]*)\s*kw\b/)),
    brand: null, model: null, need,
    priority: /snabb.*ladd|dc.ladd/.test(prompt) ? 'charging' : /pengarna|prisvard|billig/.test(prompt) ? 'value' : /lang.*rackvidd/.test(prompt) ? 'range' : need === 'familj' ? 'practicality' : 'balanced',
    unsupported: [],
  }, request);
}

function awd(row) {
  const value = folded(row.drivetrain);
  if (/\b(awd|4wd|4x4|quattro|4matic|xdrive)\b|fyrhjul/.test(value)) return true;
  if (/\b(rwd|fwd)\b|bakhjul|framhjul/.test(value)) return false;
  return null;
}

function currentPrice(row, asOf) {
  if (['campaign_price', 'dealer_offer'].includes(row.price_type) && /^\d{4}-\d{2}-\d{2}$/.test(row.price_valid_until || '') && row.price_valid_until < asOf) return null;
  return number(row.price_sek);
}

function nameMatches(value, expected) {
  if (!expected) return true;
  const haystack = folded(value).replace(/ /g, '');
  return haystack.includes(folded(expected).replace(/ /g, ''));
}

function evaluate(row, r, asOf) {
  if (!nameMatches(row.brand, r.brand) || !nameMatches(row.model, r.model)) return 'no';
  const tests = [
    [r.budget_sek, currentPrice(row, asOf), (v, target) => v <= target],
    [r.min_wltp_range_km, number(row.wltp_range_km), (v, target) => v >= target],
    [r.min_tow_kg, number(row.tow_kg), (v, target) => v >= target],
    [r.min_seats, number(row.seats), (v, target) => v >= target],
    [r.min_boot_liters, number(row.boot_liters), (v, target) => v >= target],
    [r.min_dc_charge_kw, number(row.dc_charge_kw), (v, target) => v >= target],
  ].filter(([target], index) => target !== null && (index === 0 || target > 0));
  if (tests.some(([target, value, passes]) => value !== null && !passes(value, target)) || (r.awd_required && awd(row) === false)) return 'no';
  if (tests.some(([, value]) => value === null) || (r.awd_required && awd(row) === null)) return 'unknown';
  return 'yes';
}

function score(row, r, asOf) {
  const range = number(row.wltp_range_km) ?? 0;
  const price = currentPrice(row, asOf);
  const dc = number(row.dc_charge_kw) ?? 0;
  const boot = number(row.boot_liters) ?? 0;
  let value = 50 + Math.min(20, range / Math.max(r.min_wltp_range_km || 450, 1) * 12);
  if (price > 0) value += Math.min(15, (r.budget_sek || 700000) / price * 8);
  if (r.priority === 'value') value += price > 0 ? Math.min(15, range / (price / 100000) / 10) : 0;
  else if (r.priority === 'range') value += Math.min(15, range / 50);
  else if (r.priority === 'charging') value += Math.min(15, dc / 20);
  else if (r.priority === 'practicality' || r.need === 'familj') value += Math.min(15, boot / 40);
  else value += Math.min(8, dc / 40) + Math.min(7, boot / 80);
  if (r.need === 'vinter' && awd(row) === true) value += 5;
  return Math.min(100, Math.max(0, Math.round(value)));
}

function recommendation(row, r, asOf) {
  const reasons = [];
  const tradeoffs = [];
  const price = currentPrice(row, asOf);
  if (price !== null) {
    const label = row.price_type === 'campaign_price' ? 'Kampanjpris' : row.price_type === 'dealer_offer' ? '\u00c5terf\u00f6rs\u00e4ljarerbjudande' : row.price_type === 'list_price' ? 'Listpris' : 'Prisuppgift';
    reasons.push(`${label}: ${money(price)}${r.budget_sek !== null ? ', inom din budget' : ''}.`);
  } else tradeoffs.push('Ett aktuellt svenskt pris kan inte verifieras.');
  if (number(row.wltp_range_km) !== null) reasons.push(`${row.wltp_range_km} km WLTP${r.min_wltp_range_km > 0 ? ` mot ditt krav p\u00e5 ${r.min_wltp_range_km} km` : ''}.`);
  if (r.min_tow_kg > 0) reasons.push(`Verifierad dragvikt: ${row.tow_kg} kg.`);
  else if (r.awd_required) reasons.push('Fyrhjulsdrift anges i bilens verifierade uppgifter.');
  else if (r.priority === 'charging' && number(row.dc_charge_kw) !== null) reasons.push(`DC-laddning: upp till ${row.dc_charge_kw} kW.`);
  else if (r.need === 'familj' && number(row.boot_liters) !== null) reasons.push(`Bagage: ${row.boot_liters} liter. Kontrollera att barnvagnen f\u00e5r plats.`);
  if (r.need === 'familj' && number(row.boot_liters) === null) tradeoffs.push('Bagagevolym saknas i de verifierade uppgifterna.');
  if (r.priority === 'charging' && number(row.dc_charge_kw) === null) tradeoffs.push('DC-laddning saknas i de verifierade uppgifterna.');
  if (row.available_confirmed !== true) tradeoffs.push('Aktuell tillg\u00e4nglighet \u00e4r inte separat bekr\u00e4ftad.');
  if (['campaign_price', 'dealer_offer'].includes(row.price_type)) tradeoffs.push(row.price_valid_until ? `Erbjudandet anges g\u00e4lla till ${row.price_valid_until}. Kontrollera villkoren.` : 'Kontrollera erbjudandets giltighet och villkor.');
  if (!tradeoffs.length) tradeoffs.push('Kontrollera utrustning och aktuella villkor i originalk\u00e4llan.');
  return { id: row.id, brand: row.brand, model: row.model, variant_name: row.variant_name,
    match_score: score(row, r, asOf), reasons: reasons.slice(0, 3), tradeoffs: tradeoffs.slice(0, 3), source_url: row.source_url };
}

export function matchAdvisorVariants(variants, requirements, { mode = 'deterministic_fallback', interpretation = 'rules', asOf = new Date().toISOString().slice(0, 10) } = {}) {
  const r = normalizeRequirements(requirements);
  const eligible = [];
  let unknown = 0;
  for (const row of variants.filter(isPublicVariant)) {
    const match = evaluate(row, r, asOf);
    if (match === 'yes') eligible.push(row);
    else if (match === 'unknown') unknown++;
  }
  eligible.sort((a, b) => score(b, r, asOf) - score(a, r, asOf) || String(a.variant_key || a.id).localeCompare(String(b.variant_key || b.id), 'sv-SE'));
  const shortlist = eligible.slice(0, 3).map((row) => recommendation(row, r, asOf));
  const notes = [unknown ? 'Vissa bilar saknar verifierade uppgifter f\u00f6r dina krav och har inte tagits med.' : '', r.unsupported.length ? `Kan inte kontrolleras: ${r.unsupported.map((key) => UNSUPPORTED_LABELS[key]).join('; ')}.` : ''].filter(Boolean).join(' ').slice(0, 360);
  return {
    mode, interpretation_method: interpretation, recommendation_method: 'database_rules',
    interpreted_requirements: { ...r, notes },
    summary: shortlist.length ? `${eligible.length} varianter uppfyller de krav som kan kontrolleras. H\u00e4r \u00e4r ${shortlist.length === 1 ? 'f\u00f6rslaget' : 'f\u00f6rslagen'} utifr\u00e5n din prioritering.` : 'Ingen bil kan bekr\u00e4ftas uppfylla dina krav med uppgifterna som finns. Prova att justera budget eller andra krav.',
    matching_count: eligible.length, excluded_unknown_count: unknown, shortlist,
  };
}

export function ruleAdvice(variants, request = {}, { mode = 'deterministic_fallback' } = {}) {
  try {
    return matchAdvisorVariants(variants, ruleRequirements(request), { mode, interpretation: String(request.prompt || '').trim() ? 'rules' : 'form' });
  } catch {
    const result = matchAdvisorVariants([], ruleRequirements({ budget: request.budget, range: request.range, need: request.need }), { mode, interpretation: 'unresolved' });
    return { ...result, summary: 'Dina krav kunde inte tolkas s\u00e4kert. F\u00f6rtydliga belopp och enheter eller anv\u00e4nd reglagen. Inga bilf\u00f6rslag visas innan kraven kan kontrolleras.' };
  }
}
