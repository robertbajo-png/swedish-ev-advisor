import registry from './vehicle-redirects.json' with { type: 'json' };

export function validateVehicleRedirects(value = registry) {
  if (value.schema_version !== 1 || !Array.isArray(value.redirects)) throw new Error('Invalid vehicle redirects');
  const seen = new Set();
  for (const row of value.redirects) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(row.slug) || seen.has(row.slug)
        || typeof row.brand !== 'string' || typeof row.model !== 'string'
        || !row.brand.trim() || !row.model.trim() || row.brand.length > 60 || row.model.length > 80
        || /[\u0000-\u001f<>|]/.test(row.brand + row.model)) throw new Error('Unsafe/duplicate vehicle redirect');
    seen.add(row.slug);
  }
  return value.redirects;
}

// Retired trims go to their model's catalog, never to an assumed successor drivetrain.
export function vehicleRedirect(slug, value = registry) {
  const row = validateVehicleRedirects(value).find(row => row.slug === slug);
  return row ? `/bilar?${new URLSearchParams({ brand: row.brand, query: row.model })}` : null;
}

export function catalogQuery(search) {
  const params = new URLSearchParams(search);
  const brand = params.get('brand') || '';
  const query = params.get('query') || '';
  if (!brand || !query || brand.length > 60 || query.length > 80 || /[\u0000-\u001f<>|]/.test(brand + query)) return null;
  return { brand, query, maxPrice: 1200000 };
}
