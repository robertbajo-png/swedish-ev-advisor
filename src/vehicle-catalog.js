export function groupCatalogVariants(cars) {
  const models = new Map();
  for (const car of cars) {
    const key = [car.brand, car.canonicalModel || car.model]
      .map(value => String(value).normalize('NFC').trim().toLowerCase()).join('|');
    if (!models.has(key)) models.set(key, { key, variants: [] });
    models.get(key).variants.push(car);
  }
  return [...models.values()];
}
