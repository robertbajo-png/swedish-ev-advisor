// Preserve manufacturer qualifications when a scalar field represents a range.
export function specQualifications(row) {
  const quote = row.source_quote || '';
  const polestar = row.brand === 'Polestar';
  const rangeIsTarget = polestar && row.model === '4' && row.variant_name === 'Dual motor' &&
    quote.includes('Räckviddsmål (WLTP)');
  const groupInterval = row.brand === 'Renault' && row.model === '5' &&
    quote.match(/Förbrukning \(WLTP, versionsgrupp\): ([0-9]+,[0-9]+)–([0-9]+,[0-9]+) kWh\/100 km/);
  const interval = groupInterval || polestar && quote.match(/Energikonsumtion \(WLTP\)² ([0-9]+,[0-9]+)[–-]([0-9]+,[0-9]+) kWh\/100 km/);
  return {
    rangeIsTarget,
    rangeNote: rangeIsTarget ? 'Tillverkarens räckviddsmål enligt WLTP, inte ett slutligt certifierat värde.' : null,
    consumptionInterval: interval ? `${interval[1]}–${interval[2]} kWh/100 km` : null,
    consumptionNote: groupInterval ? 'Tillverkarens gemensamma WLTP-intervall för 52 kWh-versionerna. Kostnadskalkylen använder det lägre värdet; exakt förbrukning beror på version och utrustning.'
      : interval ? 'Tillverkarens WLTP-intervall. Kostnadskalkylen använder det lägre värdet; hjul och utrustning påverkar förbrukningen.'
      : quote.includes('*Värde gäller för motor i grundutförande.')
        ? 'Motor i grundutförande. Utrustning och hjul kan påverka förbrukningen.' : null,
  };
}
