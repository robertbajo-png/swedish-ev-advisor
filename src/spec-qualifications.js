// Preserve manufacturer qualifications when a scalar field represents a range.
export function specQualifications(row) {
  const quote = row.source_quote || '';
  const polestar = row.brand === 'Polestar';
  const cla = row.brand === 'Mercedes-Benz' && row.model === 'Cla' && quote.includes('Tillåten släpvagnsvikt (bromsad släpvagn vid 12 %)');
  const explorer = row.brand === 'Ford' && row.model === 'Explorer' && /^Explorer Premium Edition (RWD 79|AWD 77) kWh MY27\.25$/.test(row.variant_name);
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
        ? 'Motor i grundutförande. Utrustning och hjul kan påverka förbrukningen.'
        : cla ? 'Tillverkarens svenska modelltabell. Hjul och tillval kan påverka WLTP-värden och laddprestanda.'
        : explorer ? 'Svensk Premium Edition MY27.25. Hjul och utrustning påverkar WLTP-värden. Laddning och dragvikt gäller det aktuella modellåret, inte äldre Explorer.' : null,
    practicalNote: cla ? 'Maximal bromsad dragvikt med erforderlig dragutrustning. Monterad dragkrok ingår inte automatiskt; kontrollera utrustning och registreringsbevis för bilen du beställer.'
      : explorer ? 'Bagagevolymen kommer från Fords danska presentation av samma europeiska Explorer, med baksätet uppfällt. Lastgolv och utrustning påverkar utrymmet. Dragvikten gäller svensk MY27.25; kontrollera registreringsbeviset för bilen du beställer.' : null,
    practicalSource: explorer && quote.includes('https://www.ford.dk/koeb/kampagner/explorer-og-capri') ? 'https://www.ford.dk/koeb/kampagner/explorer-og-capri' : null,
  };
}
