// Preserve manufacturer qualifications when a scalar field represents a range.
export function specQualifications(row) {
  const quote = row.source_quote || '';
  const polestar = row.brand === 'Polestar';
  const cla = row.brand === 'Mercedes-Benz' && row.model === 'Cla' && quote.includes('Tillåten släpvagnsvikt (bromsad släpvagn vid 12 %)');
  const explorer = row.brand === 'Ford' && row.model === 'Explorer' && /^Explorer Premium Edition (RWD 79|AWD 77) kWh MY27\.25$/.test(row.variant_name);
  const born = row.brand === 'Cupra' && row.model === 'Born' && row.variant_name === 'Born VZ' &&
    quote.includes('VZ (240kW/79kWh) | Range (km) 631 - 552');
  const i4 = row.brand === 'BMW' && row.model === 'i4' && quote.includes('BMW i4 eDrive40 Gran Coupé | 61HD') &&
    quote.includes('WBY61HD030FW37556 | WLTP räckvidd 588 km');
  const rangeIsTarget = polestar && row.model === '4' && row.variant_name === 'Dual motor' &&
    quote.includes('Räckviddsmål (WLTP)');
  const groupInterval = row.brand === 'Renault' && row.model === '5' &&
    quote.match(/Förbrukning \(WLTP, versionsgrupp\): ([0-9]+,[0-9]+)–([0-9]+,[0-9]+) kWh\/100 km/);
  const interval = groupInterval || polestar && quote.match(/Energikonsumtion \(WLTP\)² ([0-9]+,[0-9]+)[–-]([0-9]+,[0-9]+) kWh\/100 km/);
  return {
    rangeIsTarget,
    rangeInterval: born ? '552–631 km' : null,
    rangeNote: rangeIsTarget ? 'Tillverkarens räckviddsmål enligt WLTP, inte ett slutligt certifierat värde.'
      : born ? 'CUPRA:s internationella VZ-tabell anger 552–631 km WLTP för modellår 2027. Hjul och utrustning påverkar värdet; 631 km är intervallets övre gräns, inte räckvidden för varje svensk konfiguration.' : null,
    consumptionInterval: i4 ? '14,9–17,1 kWh/100 km' : interval ? `${interval[1]}–${interval[2]} kWh/100 km` : null,
    consumptionNote: i4 ? 'BMW:s WLTP-intervall för eDrive40, typ 61HD, inte ett individuellt förbrukningsvärde för lagerbilen. Kostnadskalkylen använder 14,9 kWh/100 km; hjul och utrustning påverkar förbrukningen. Räckvidden 588 km kommer från just lagerbil FW37556. Batteri och laddning gäller samma tekniska typ; lagerbilens produktionsår är 2026.'
      : groupInterval ? 'Tillverkarens gemensamma WLTP-intervall för 52 kWh-versionerna. Kostnadskalkylen använder det lägre värdet; exakt förbrukning beror på version och utrustning.'
      : interval ? 'Tillverkarens WLTP-intervall. Kostnadskalkylen använder det lägre värdet; hjul och utrustning påverkar förbrukningen.'
      : quote.includes('*Värde gäller för motor i grundutförande.')
        ? 'Motor i grundutförande. Utrustning och hjul kan påverka förbrukningen.'
        : cla ? 'Tillverkarens svenska modelltabell. Hjul och tillval kan påverka WLTP-värden och laddprestanda.'
        : explorer ? 'Svensk Premium Edition MY27.25. Hjul och utrustning påverkar WLTP-värden. Laddning och dragvikt gäller det aktuella modellåret, inte äldre Explorer.'
        : born ? 'Förbrukningen 14,2 kWh/100 km gäller grundversionen i den svenska bränsledeklarationen, oktober 2026. Batteriet är 79 kWh netto (84 kWh brutto). DC 183 kW gäller den aktuella internationella 79 kWh-tabellen; AC är 11 kW ombord, inte kabelns märkning.' : null,
    practicalNote: i4 ? 'BMW anger 1 600 kg bromsad släpvagn vid 12 % lutning för typ 61HD. Lagerbilen har utrustningskod 3AC för utfällbar dragkrok; kontrollera registreringsbeviset. 75 kg kultryck är inte dragvikt. Bagagevolymen 470 liter gäller med baksätet uppfällt. Pressbilden visar samma i4 eDrive40-modell, inte nödvändigtvis lagerbilens färg och hjul.'
      : cla ? 'Maximal bromsad dragvikt med erforderlig dragutrustning. Monterad dragkrok ingår inte automatiskt; kontrollera utrustning och registreringsbevis för bilen du beställer.'
      : explorer ? 'Bagagevolymen kommer från Fords danska presentation av samma europeiska Explorer, med baksätet uppfällt. Lastgolv och utrustning påverkar utrymmet. Dragvikten gäller svensk MY27.25; kontrollera registreringsbeviset för bilen du beställer.'
      : born ? 'Bilen är inte godkänd för släp enligt den svenska instruktionsboken. 0 kg är därför ett styrkt förbud, inte saknad data. Fästet för cykelhållare får inte användas för släp; dess vertikala belastning är ingen dragvikt.' : null,
    practicalSource: explorer && quote.includes('https://www.ford.dk/koeb/kampagner/explorer-og-capri') ? 'https://www.ford.dk/koeb/kampagner/explorer-og-capri' : null,
    specSources: i4 ? [
      { label: 'Lagerbil FW37556: pris, räckvidd och utrustning', url: 'https://hitta.bmw.se/r/G26E-i4/i4-eDrive40-WBY61HD030FW37556' },
      { label: 'BMW Sverige: teknisk typ 61HD (eDrive40)', url: 'https://www.bmw.se/sv/alla-modeller/i-series/i4/bmw-i4-gran-coupe-technical-data.html' },
    ] : born ? [
      { label: 'Räckvidd och DC: CUPRA:s internationella VZ-tabell', url: 'https://www.seat-cupra-mediacenter.com/content/dam/seat-media-center/models-all-brands/cupra-models/cupra-born/technical-data/New_CUPRA_Born_Technical_Data_26.pdf' },
      { label: 'Förbrukning: svensk bränsledeklaration', url: 'https://www.cupraofficial.se/content/dam/countries/se/cupra-website/broschyr/cupra-bransledeklaration-okt2026.pdf' },
      { label: 'Släp: svensk instruktionsbok, sidan 288', url: 'https://www.cupraofficial.se/datamanual-manual/manuals/cupra/se-se/CUPRA_Born_03_26_SE.pdf#page=290' },
      { label: 'Bagage och säten: CUPRA Sverige', url: 'https://www.cupraofficial.se/bilar/born' },
    ] : [],
  };
}
