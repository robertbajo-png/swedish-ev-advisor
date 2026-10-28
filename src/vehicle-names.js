export function normalizeNameToken(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
}

export function normalizeVehicleNameKey(value, brand = '') {
  const brandKey = normalizeNameToken(brand);
  return String(value || '')
    .toLowerCase()
    .replace(/\b(suv|sportback|edition|advanced|business)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .split(' ')
    .filter((part) => part && normalizeNameToken(part) !== brandKey)
    .join('');
}

export function stripLeadingBrand(brand, value) {
  const brandText = String(brand || '').trim();
  const text = String(value || '').trim();
  if (!brandText) return text;
  const pattern = new RegExp(`^${brandText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+`, 'i');
  return text.replace(pattern, '').trim();
}

export function displayModelName(brand, model, variantName) {
  const modelText = String(model || '').trim();
  const variantText = stripLeadingBrand(brand, variantName);
  if (!variantText) return modelText;
  const normalizedModel = normalizeNameToken(modelText);
  const normalizedVariant = normalizeNameToken(variantText);
  const vehicleModel = normalizeVehicleNameKey(modelText, brand);
  const vehicleVariant = normalizeVehicleNameKey(variantText, brand);
  if (!normalizedModel || normalizedVariant === normalizedModel || normalizedVariant.startsWith(normalizedModel)
    || (vehicleModel && (vehicleVariant === vehicleModel || vehicleVariant.startsWith(vehicleModel)))) {
    return variantText;
  }
  return `${modelText} ${variantText}`.trim();
}

export function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

export function vehicleSlug(brand, model, variant) {
  return slug(`${brand} ${displayModelName(brand, model, variant)}`);
}
