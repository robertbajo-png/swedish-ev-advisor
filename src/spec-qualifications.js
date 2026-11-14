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
  const ev3 = row.brand === 'Kia' && row.model === 'Ev3' && /9VW5(?:ZHZ7Z|YGZ7Z)-(?:TX1|LX[123]|SX[12]|DX1)/.test(quote);
  const ev3Gt = ev3 && row.variant_name === 'EV3 GT (292hk) AWD Long Range';
  const ev4 = row.brand === 'Kia' && row.model === 'Ev4' && /7ZS6(?:ZHZ7Z-LX1|YGZ7Z-LX1_V00|YGZ7Z-LX2)/.test(quote);
  const ev4Gt = ev4 && row.variant_name === 'EV4 GT (292hk) AWD Long Range' && row.wltp_range_km === 505;
  const ev5 = row.brand === 'Kia' && row.model === 'Ev5' && /X9W5(?:ZHZ7Z-LX1|YLZ7Z-(?:SX1|GX1)_V00|YRZ7Z-GX2)/.test(quote);
  const ev5Gt = ev5 && row.variant_name === 'EV5 GT (306hk) AWD Long Range';
  const ev5Panorama = ev5 && row.variant_name === 'EV5 GT Line Panorama AWD Long Range';
  const ev3Preliminary = ev3 && /^EV3 (?:Plus|GT Line) AWD Long Range$/.test(row.variant_name) &&
    quote.includes('(AWD, Preliminär information i väntan på homologering)');
  const rangeIsTarget = ev3Preliminary || polestar && row.model === '4' && row.variant_name === 'Dual motor' &&
    quote.includes('Räckviddsmål (WLTP)');
  const groupInterval = row.brand === 'Renault' && row.model === '5' &&
    quote.match(/Förbrukning \(WLTP, versionsgrupp\): ([0-9]+,[0-9]+)–([0-9]+,[0-9]+) kWh\/100 km/);
  const interval = groupInterval || polestar && quote.match(/Energikonsumtion \(WLTP\)² ([0-9]+,[0-9]+)[–-]([0-9]+,[0-9]+) kWh\/100 km/);
  return {
    imageNotice: ev3 && row.image_url === '/media/vehicles/kia-ev3-press-b0de32637809.jpg'
      ? 'Modellbild: Kia EV3 GT Line. Färg och utrustning kan skilja från den valda versionen.'
      : ev4 && row.image_url === '/media/vehicles/kia-ev4-press-0446f33614bd.jpg'
        ? 'Modellbild: Kia EV4 GT Line halvkombi. Färg och utrustning kan skilja från den valda versionen.'
        : ev5 && row.image_url === '/media/vehicles/kia-ev5-press-de4eab70d59a.jpg'
          ? 'Modellbild: Kia EV5 Baseline. Färg och utrustning kan skilja från den valda versionen.' : null,
    rangeIsTarget,
    rangeInterval: born ? '552–631 km' : null,
    rangeNote: ev3Preliminary ? '572 km är en preliminär tillverkaruppgift i väntan på homologering enligt Kias svenska faktablad, inte slutlig certifierad räckvidd. Den används inte för att bekräfta ett hårt räckviddskrav.'
      : rangeIsTarget ? 'Tillverkarens räckviddsmål enligt WLTP, inte ett slutligt certifierat värde.'
      : ev5Panorama ? '491 km är maxvärdet för GT Line AWD-gruppen enligt Kias svenska MY2027-faktablad, inte ett individuellt mätvärde för varje bil med panoramatak. Hjul och tillvalsutrustning påverkar räckvidden.'
      : ev5Gt ? 'Upp till 476 km enligt Kias svenska GT-sida för 306 hk. Den tyska GT-tabellen anger samma blandade WLTP-värde; 615 km där avser stadskörning, inte blandad körning.'
      : ev4Gt ? 'Upp till 505 km enligt Kias svenska GT-sida. I den tyska GT-tabellen gäller 505 km med 20-tums Pirelli och 473 km med 20-tums Michelin. Däck och utrustning påverkar räckvidden.'
      : born ? 'CUPRA:s internationella VZ-tabell anger 552–631 km WLTP för modellår 2027. Hjul och utrustning påverkar värdet; 631 km är intervallets övre gräns, inte räckvidden för varje svensk konfiguration.' : null,
    consumptionInterval: i4 ? '14,9–17,1 kWh/100 km' : interval ? `${interval[1]}–${interval[2]} kWh/100 km` : null,
    consumptionNote: i4 ? 'BMW:s WLTP-intervall för eDrive40, typ 61HD, inte ett individuellt förbrukningsvärde för lagerbilen. Kostnadskalkylen använder 14,9 kWh/100 km; hjul och utrustning påverkar förbrukningen. Räckvidden 588 km kommer från just lagerbil FW37556. Batteri och laddning gäller samma tekniska typ; lagerbilens produktionsår är 2026.'
      : ev5Gt ? 'GT 306 hk: 18,6 kWh/100 km enligt Kias svenska bränsledeklaration. AC 10,5 kW gäller standardladdaren i Kias polska GT-tabell, inte tillvalet 22 kW. Den tyska GT-tabellen styrker maximal DC-effekt 150 kW; AC-tider vid 11 kW är inte ett annat maximivärde för ombordladdaren.'
      : ev5 ? 'Svenska produktfakta från 14 oktober 2026, modellår 2027: FWD 16,0, Plus AWD 17,2 och GT Line AWD 18,1 kWh/100 km med standardhjulen 18 respektive 19 tum. Dessa versionsbundna värden väljs framför webbplatsens generella fotnot. AC är 10,5 kW ombord; 350 kW i laddtidsvillkoret avser stationen, inte bilens maxeffekt.'
      : ev4Gt ? 'Blandad WLTP-förbrukning 17,9 kWh/100 km för svenska GT 292 hk, enligt bränsledeklarationen oktober 2026. AC 10,5 kW gäller standardladdaren i den polska GT-tabellen, inte tillvalet 22 kW. DC 128 kW är nominell maximal effekt enligt den tyska GT-tabellen.'
      : ev4 ? 'GT Line modellår 2027 med 19-tumshjul: 15,8 kWh/100 km för FWD och 16,5 för AWD. Ombordladdaren är 10,5 kW. Faktabladets 350 kW avser laddstationen, inte bilens maximala mottagning.'
      : ev3Gt ? '532 km och 17,1 kWh/100 km kommer från Kias svenska GT-sida och bränsledeklaration, oktober 2026. Andra marknader anger 501 km och 18,1 kWh/100 km. AC 10,5 kW gäller standardladdaren i Kias polska GT-tabell, inte tillvalet 22 kW. DC 128 kW är tillverkarens nominella GT-uppgift i det tyska faktabladet.'
      : ev3 ? 'FWD-värdena gäller standardhjulen: 17 tum, eller 19 tum för GT Line. AC-laddaren är 10,5 kW, inte avrundat till 11 kW. Vanliga AWD-versioners tekniska uppgifter är preliminära enligt det svenska faktabladet; de är inte GT 292 hk.'
      : groupInterval ? 'Tillverkarens gemensamma WLTP-intervall för 52 kWh-versionerna. Kostnadskalkylen använder det lägre värdet; exakt förbrukning beror på version och utrustning.'
      : interval ? 'Tillverkarens WLTP-intervall. Kostnadskalkylen använder det lägre värdet; hjul och utrustning påverkar förbrukningen.'
      : quote.includes('*Värde gäller för motor i grundutförande.')
        ? 'Motor i grundutförande. Utrustning och hjul kan påverka förbrukningen.'
        : cla ? 'Tillverkarens svenska modelltabell. Hjul och tillval kan påverka WLTP-värden och laddprestanda.'
        : explorer ? 'Svensk Premium Edition MY27.25. Hjul och utrustning påverkar WLTP-värden. Laddning och dragvikt gäller det aktuella modellåret, inte äldre Explorer.'
        : born ? 'Förbrukningen 14,2 kWh/100 km gäller grundversionen i den svenska bränsledeklarationen, oktober 2026. Batteriet är 79 kWh netto (84 kWh brutto). DC 183 kW gäller den aktuella internationella 79 kWh-tabellen; AC är 11 kW ombord, inte kabelns märkning.' : null,
    practicalNote: i4 ? 'BMW anger 1 600 kg bromsad släpvagn vid 12 % lutning för typ 61HD. Lagerbilen har utrustningskod 3AC för utfällbar dragkrok; kontrollera registreringsbeviset. 75 kg kultryck är inte dragvikt. Bagagevolymen 470 liter gäller med baksätet uppfällt. Pressbilden visar samma i4 eDrive40-modell, inte nödvändigtvis lagerbilens färg och hjul.'
      : ev5Gt ? 'GT: 566 liter enligt den tyska GT-tabellen med baksätet uppfällt, inklusive utrymmet under lastgolvet. 1 650 liter kräver fällt baksäte och frunken ingår inte. Bromsad dragvikt är 1 800 kg med rätt utrustning; kontrollera registreringsbeviset.'
      : ev5 ? '566 liter gäller med baksätet uppfällt, utan frunkens 44 liter. 1 650 liter gäller fällt baksäte. Bromsad dragvikt är 1 200 kg för FWD och 1 800 kg för AWD med rätt utrustning. Panorama är ett GT Line-tillval, inte en annan motor. Kontrollera registreringsbeviset.'
      : ev4Gt ? 'Bagagevolymen 359 liter kommer från den polska GT-kolumnen. Den tyska uppgiften 377 liter räknar även in dubbelbotten och har en annan mätgrund. Dragvikten 1 500 kg avser bromsat släp med rätt utrustning, inte kultryck eller taklast. Kontrollera registreringsbeviset.'
      : ev4 ? 'Svenska GT Line halvkombi: 435 liter för FWD och 359 för AWD med baksätet uppfällt, inte Fastback eller fällt baksäte. Bromsad dragvikt är 1 000 respektive 1 500 kg med rätt utrustning. Kontrollera registreringsbeviset.'
      : ev3 ? 'Bagagevolymen gäller med baksätet uppfällt: 460 liter för FWD och 413 liter för AWD/GT, utan frunken. Dragvikten avser bromsat släp med rätt utrustning; kontrollera registreringsbeviset. Bilden är en EV3-modellbild i GT Line-utförande, inte en utfästelse om varje versions utrustning.'
      : cla ? 'Maximal bromsad dragvikt med erforderlig dragutrustning. Monterad dragkrok ingår inte automatiskt; kontrollera utrustning och registreringsbevis för bilen du beställer.'
      : explorer ? 'Bagagevolymen kommer från Fords danska presentation av samma europeiska Explorer, med baksätet uppfällt. Lastgolv och utrustning påverkar utrymmet. Dragvikten gäller svensk MY27.25; kontrollera registreringsbeviset för bilen du beställer.'
      : born ? 'Bilen är inte godkänd för släp enligt den svenska instruktionsboken. 0 kg är därför ett styrkt förbud, inte saknad data. Fästet för cykelhållare får inte användas för släp; dess vertikala belastning är ingen dragvikt.' : null,
    practicalSource: explorer && quote.includes('https://www.ford.dk/koeb/kampagner/explorer-og-capri') ? 'https://www.ford.dk/koeb/kampagner/explorer-og-capri' : null,
    specSources: ev5 ? [
      ...(!ev5Gt ? [{ label: 'Kia Sverige: EV5 MY2027 och standardhjul', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev5/kia-sweden-ev5-specification.pdf#page=3' }] : []),
      { label: 'Kia Sverige: motorer och fem sittplatser', url: ev5Gt ? 'https://www.kia.com/se/nya-bilar/ev5-gt/specifikationer/' : 'https://www.kia.com/se/nya-bilar/ev5/specifikationer/' },
      ...(ev5Gt ? [
        { label: 'Kia Sverige: EV5 GT 306 hk', url: 'https://www.kia.com/se/nya-bilar/ev5-gt/upptack/' },
        { label: 'Kia Sverige: bränsledeklaration oktober 2026', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf' },
        { label: 'Kia Polen: GT-kolumn och standardladdare', url: 'https://www.kia.com/content/dam/kwcms/kme/pl/pl/assets/contents/utility/Price_list/ev5/Cennik_EV5_MY26-1_RP26_2026-06-18.pdf#page=15' },
        { label: 'Kia Tyskland: GT-laddning och bagage', url: 'https://www.kia.com/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV5-GT-Preisliste.pdf#page=10' },
      ] : []),
    ] : ev4 ? [
      ...(!ev4Gt ? [{ label: 'Kia Sverige: EV4 GT Line MY2027, 19-tumshjul', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev4/kia-sweden-ev4-specification.pdf#page=3' }] : []),
      { label: 'Kia Sverige: motorer och sittplatser', url: ev4Gt ? 'https://www.kia.com/se/nya-bilar/ev4-gt/specifications/' : 'https://www.kia.com/se/nya-bilar/ev4/specs/' },
      { label: 'Kia Sverige: bränsledeklaration oktober 2026', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf' },
      ...(ev4Gt ? [
        { label: 'Kia Sverige: EV4 GT 292 hk', url: 'https://www.kia.com/se/nya-bilar/ev4-gt/upptack/' },
        { label: 'Kia Polen: GT-kolumnens AC och bagage', url: 'https://www.kia.com/pl/modele/ev4/dane-techniczne/' },
        { label: 'Kia Tyskland: GT-laddning, däck och mätvillkor', url: 'https://www.kia.com/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV4-GT-Preisliste.pdf#page=11' },
      ] : []),
    ] : ev3 ? [
      { label: 'Svenska EV3-produktfakta och hjulbundna värden', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev3/Faktablad-Kia-EV3.pdf' },
      { label: 'Kia Sverige: bränsledeklaration oktober 2026', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf' },
      ...(ev3Gt ? [
        { label: 'Svenska EV3 GT: räckvidd, batteri och dragvikt', url: 'https://www.kia.com/se/nya-bilar/ev3-gt/upptack/' },
        { label: 'Kia Polen: GT-kolumnens AC och bagage', url: 'https://www.kia.com/pl/modele/ev3/dane-techniczne/' },
        { label: 'Kia Tyskland: nominell DC-effekt för GT', url: 'https://www.kia.com/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV3-GT-Preisliste.pdf#page=12' },
      ] : []),
    ] : i4 ? [
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
