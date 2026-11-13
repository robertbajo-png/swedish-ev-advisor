const priceNames = { list_price: 'Listpris', campaign_price: 'Kampanjpris', dealer_offer: 'Återförsäljarerbjudande' };

export function decisionMetricsFor(car, cars = [], now = new Date()) {
  const comparable = cars.filter(item => item.rangeVerified != null && !item.rangeIsTarget);
  const averageRange = comparable.length > 1 ? Math.round(comparable.reduce((sum, item) => sum + item.rangeVerified, 0) / comparable.length) : null;
  const type = priceNames[car.priceType];
  const expired = car.priceValidUntil && car.priceValidUntil.slice(0, 10) < now.toISOString().slice(0, 10);
  const price = Number.isFinite(car.price) && car.price > 0 && type && !expired ? car.price : null;
  const basis = price ? type + (car.priceValidUntil ? ', giltigt till ' + car.priceValidUntil.slice(0, 10) : '') +
    (car.rangeIsTarget ? '; baserat på tillverkarens räckviddsmål, inte slutlig certifiering' : '') : 'Verifierad prisuppgift krävs';
  const missing = expired ? 'Erbjudandet har gått ut.' : 'Beräknas med verifierat pris och WLTP.';
  return [
    { label: 'Räckvidd per 100 000 kr', value: price && car.rangeVerified ? (car.rangeVerified / (price / 100000)).toLocaleString('sv-SE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' km' : 'Uppgift saknas', note: price ? basis + ' och angiven WLTP-räckvidd.' : missing },
    { label: 'Pris per WLTP-km', value: price && car.rangeVerified ? Math.round(price / car.rangeVerified).toLocaleString('sv-SE') + ' kr/km' : 'Uppgift saknas', note: price ? basis + ' fördelat på angiven räckvidd. Inte körkostnad.' : missing },
    { label: 'Räckvidd mot utbudets snitt', value: car.rangeIsTarget ? 'Ej jämförbart' : averageRange != null && car.rangeVerified != null ? (car.rangeVerified >= averageRange ? '+' : '') + (car.rangeVerified - averageRange) + ' km' : 'Uppgift saknas', note: car.rangeIsTarget ? 'Räckviddsmålet jämförs inte med certifierade räckviddsvärden.' : averageRange ? 'Snittet för publicerade varianter med räckviddsuppgift är ' + averageRange + ' km WLTP.' : 'Jämförelseunderlag saknas.' }
  ];
}
