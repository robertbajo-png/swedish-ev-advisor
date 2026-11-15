// A deliberately narrow pilot: exact Swedish five-seat canonical variants only.
const ev2Versions = [
  { variant: 'EV2 FWD 5-sits', name: 'Standard Range', wheel: 16, use: 'För dig som prioriterar lägst inköpspris och oftast kan ladda mellan vardagsresorna.' },
  { variant: 'EV2 FWD Long Range 5-sits', name: 'Long Range', wheel: 16, use: 'För dig som prioriterar längre angiven räckvidd framför extra utrustning.' },
  { variant: 'EV2 GT Line FWD Long Range 5-sits', name: 'GT Line Long Range', wheel: 19, use: 'För dig som vill ha GT Line-utförandet och 19-tumshjul. Jämför utrustningen hos Kia innan du betalar mellanskillnaden.' },
];

export function ev2VersionGuide(car, cars) {
  if (car.brand !== 'Kia' || car.canonicalModel !== 'Ev2' || !ev2Versions.some(item => item.variant === car.variantName)) return [];
  const versions = ev2Versions.map(config => {
    const matches = cars.filter(item => item.brand === 'Kia' && item.canonicalModel === 'Ev2'
      && item.variantName === config.variant && item.seatsVerified === 5 && item.validationStatus === 'published');
    const item = matches.length === 1 ? matches[0] : null;
    if (!item || !item.priceSource || !item.priceVerifiedAt || item.priceType !== 'list_price'
      || !Number.isFinite(item.price) || item.price <= 0 || !item.source || item.source === '#quality'
      || !Number.isFinite(item.rangeVerified) || item.rangeVerified <= 0 || item.rangeIsTarget
      || item.rangeInterval || !Number.isFinite(item.batteryVerified) || item.batteryVerified <= 0) return null;
    return { ...config, car: item };
  });
  if (versions.some(version => !version)) return [];
  return versions.map((version, index) => {
    const baseline = index > 0 ? versions[index - 1] : null;
    return {
      ...version,
      baseline: baseline?.name ?? null,
      priceDifference: baseline ? version.car.price - baseline.car.price : null,
      rangeDifference: baseline ? version.car.rangeVerified - baseline.car.rangeVerified : null,
      batteryDifference: baseline ? Math.round((version.car.batteryVerified - baseline.car.batteryVerified) * 10) / 10 : null,
    };
  });
}
