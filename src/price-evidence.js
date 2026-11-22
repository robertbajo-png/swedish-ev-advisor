export const PRICE_EVIDENCE_FIELDS = ['price_source_url', 'price_source_hash', 'price_source_quote', 'price_source_name', 'price_verified_at'];
export const MANUFACTURER_FROM_PRICE = 'manufacturer_from';
export const PRICE_TYPES = ['list_price', 'campaign_price', 'dealer_offer', MANUFACTURER_FROM_PRICE];

export function priceTypeLabel(type) {
  switch (type) {
    case 'list_price': return 'Listpris';
    case 'campaign_price': return 'Kampanjpris';
    case 'dealer_offer': return '\u00c5terf\u00f6rs\u00e4ljarerbjudande';
    case MANUFACTURER_FROM_PRICE: return 'Tillverkarens fr\u00e5npris';
    default: return null;
  }
}

export function priceOfferEnd(type, value) {
  if (!['campaign_price', 'dealer_offer'].includes(type) || !/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : null;
}

export function hasPriceEvidence(row) {
  return PRICE_EVIDENCE_FIELDS.some(field => row[field] != null);
}

export function priceEvidence(row) {
  if (!hasPriceEvidence(row)) return null;
  if (PRICE_EVIDENCE_FIELDS.some(field => typeof row[field] !== 'string' || !row[field].trim())
    || !/^[a-f0-9]{64}$/i.test(row.price_source_hash)
    || !Number.isFinite(Date.parse(row.price_verified_at))) return null;
  try {
    const url = new URL(row.price_source_url);
    if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443')
      || /mobilitysweden|ev-database|car\.info/.test(url.hostname)) return null;
  } catch { return null; }
  return Object.fromEntries(PRICE_EVIDENCE_FIELDS.map(field => [field, row[field]]));
}

export function verifiedManufacturerFrom(row) {
  return row.price_type === MANUFACTURER_FROM_PRICE && Number.isSafeInteger(row.price_sek)
    && row.price_sek >= 100000 && row.price_sek <= 3000000 && row.price_valid_until == null
    && !!priceEvidence(row);
}

export function priceVerificationDate(row) {
  // A partial price proof must not fall back to a newer technical-source date.
  return hasPriceEvidence(row) ? priceEvidence(row)?.price_verified_at || null : row.verified_at;
}
