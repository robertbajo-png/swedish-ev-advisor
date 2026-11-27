/** Temporary, source-unverified exact stock offers from the scoped 2026-11-27
 * adjudication. Never accept an arbitrary empty variant as a published row. */
export const WITHHELD_FIELDS = ['price_withheld_reason','price_withheld_at'];
const scope = [
  ['A6 E-Tron','A6 Sportback e-tron performance S-line 270 kW MY2027 (lagerbil RRR07B)',
    'https://lagerbilar.vwgroup.se/audi/RRR07B','source_unavailable'],
  ['Q6 E-Tron','Q6 e-tron quattro SUV 315 kW MY2027 (lagerbil JCE98Y)',
    'https://www.bilia.se/bilar/sok-bil/audi/q6-e-tron/jce98y/','source_gone'],
];
export const hasWithheldPrice = row => WITHHELD_FIELDS.some(field=>row[field] != null);
export function priceWithholding(row) {
  const match=scope.find(([model,name,url,reason])=>row.brand==='Audi' && row.model===model
    && row.variant_name===name && row.source_url===url && row.price_withheld_reason===reason);
  if (!match || row.price_sek != null || row.price_type != null || row.price_valid_until != null
    || ['price_source_url','price_source_hash','price_source_quote','price_source_name','price_verified_at'].some(k=>row[k]!=null)
    || !['published','published_reviewed'].includes(row.validation_status)
    || row.available_confirmed!==false || row.discontinued_candidate!==false
    || !/^[a-f0-9]{64}$/i.test(row.source_hash||'')
    || !Number.isFinite(Date.parse(row.price_withheld_at))
    || !Number.isFinite(Date.parse(row.verified_at))
    || Date.parse(row.price_withheld_at)<=Date.parse(row.verified_at)) return null;
  return {reason:match[3],at:row.price_withheld_at};
}
