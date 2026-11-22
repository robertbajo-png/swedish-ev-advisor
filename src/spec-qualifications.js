// Preserve manufacturer qualifications when a scalar field represents a range.
export function specQualifications(row) {
  const quote = row.source_quote || '';
  const r4Source = 'https://rnautomotive.se/bilar/261900/pc-nc-renault-4-e-tech-2027';
  const r4TechnoSource = 'https://hedinautomotive.se/bilar/kop-bil/258900/pc-nc-renault-4-e-tech-2026';
  const r4Evolution = row.brand === 'Renault' && row.model === '4' && row.variant_name === 'Evolution EV52'
    && row.wltp_range_km === 407 && row.wltp_consumption_kwh_100km === 15.2 && quote.includes(r4Source + ' | ');
  const r4Techno = row.brand === 'Renault' && row.model === '4' && row.variant_name === 'Techno EV52'
    && row.wltp_range_km === 398 && row.wltp_consumption_kwh_100km === 15.5 && quote.includes(r4TechnoSource + ' | ');
  const polestar = row.brand === 'Polestar';
  const polestar3 = polestar && row.model === '3' && row.variant_name === 'Performance'
    && row.source_url === 'https://www.polestar.com/se/polestar-3/specifications/'
    && quote.match(/https:\/\/www\.polestar\.com\/se\/manual\/polestar-3\/2027\/article\/[^ |]+\/ \| Performance \| \d{3} \| (\d{3}) \| (\d{2},\d) \| \d{3} \| (\d{3}) \| (\d{2},\d)(?= \||$)/);
  const certified = polestar3 && Number(polestar3[1]) === row.wltp_range_km
    && Number(polestar3[3]) < Number(polestar3[1])
    && Number(polestar3[4].replace(',', '.')) > Number(polestar3[2].replace(',', '.')) ? polestar3 : null;
  const cla = row.brand === 'Mercedes-Benz' && row.model === 'Cla' && quote.includes('Tillåten släpvagnsvikt (bromsad släpvagn vid 12 %)');
  const glb = row.brand === 'Mercedes-Benz' && row.model === 'Glb' && row.seats === 5
    && /^GLB (?:250\+|350 4MATIC) Advanced Edition$/.test(row.variant_name)
    && row.source_url === 'https://www.mercedes-benz.se/passengercars/models/suv/glb-electric/overview.html';
  const ioniq9 = row.brand === 'Hyundai' && row.model === 'Ioniq 9' && row.seats === 7
    && row.variant_name === 'Advanced AWD 7-sits MY27' && row.wltp_range_km === 606
    && row.source_url === 'https://www.hyundai.com/se/sv/bilar/ioniq9.html';
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
  const ev6 = row.brand === 'Kia' && row.model === 'Ev6' && /ASW5(?:ZHZ7Z-TX1|YCZ7Z-TX1|YDZ7Z-GX2)/.test(quote);
  const ev6Gt = ev6 && row.variant_name === 'EV6 GT';
  const ev9 = row.brand === 'Kia' && row.model === 'Ev9' && /DOW[67](?:ZHZ7Z-LX2|YBZ7Z-(?:TX2|GX1|SX2))/.test(quote);
  const ev2 = row.brand === 'Kia' && row.model === 'Ev2' && /6NW5ZFZ7Z-(?:TX2(?:_V00)?|LX1)/.test(quote);
  const chrPlus = row.brand === 'Toyota' && row.model === 'C-Hr+' &&
    quote.includes('Active 2WD 18": 607 km') && quote.includes('Executive AWD: 507 km');
  const idBuzz = row.brand === 'Volkswagen' && row.model === 'Id. Buzz' && row.seats === 5 &&
    /^(?:Pro|Pro 4MOTION) Sweden Olympic Edition 5-sits MY2027$/.test(row.variant_name) &&
    row.source_url === 'https://www.volkswagen-transportbilar.se/sv/modeller/id-buzz.html';
  const ev3Preliminary = ev3 && /^EV3 (?:Plus|GT Line) AWD Long Range$/.test(row.variant_name) &&
    quote.includes('(AWD, Preliminär information i väntan på homologering)');
  const rangeIsTarget = ev3Preliminary || polestar && row.model === '4' && row.variant_name === 'Dual motor' &&
    quote.includes('Räckviddsmål (WLTP)');
  const groupInterval = row.brand === 'Renault' && row.model === '5' &&
    quote.match(/Förbrukning \(WLTP, versionsgrupp\): ([0-9]+,[0-9]+)–([0-9]+,[0-9]+) kWh\/100 km/);
  const interval = groupInterval || polestar && quote.match(/Energikonsumtion \(WLTP\)² ([0-9]+,[0-9]+)[–-]([0-9]+,[0-9]+) kWh\/100 km/);
  return {
    imageNotice: ioniq9 && row.image_url === '/media/vehicles/hyundai-ioniq-9-press-4556561b89d9.jpg'
      ? 'Pressbild av IONIQ 9. Utrustningen kan skilja mellan versioner.'
      : glb && row.image_url === '/media/vehicles/mercedes-benz-glb-press-01ba09303394.jpg'
      ? 'Pressbild av eldrivna GLB. Utrustningen kan skilja mellan versioner.'
      : (r4Evolution || r4Techno) && row.image_url === '/media/vehicles/renault-4-press-08f8b8956c0a.jpg'
      ? `Modellbild: Renault 4 E-Tech electric. Utrustningen kan skilja sig från ${row.variant_name}.`
      : certified && row.image_url === '/media/vehicles/polestar-3-press-450c917205da.jpg'
      ? 'Pressbild av Polestar 3 med 800 V. Utrustningen kan skilja fr\u00e5n den svenska versionen.'
      : chrPlus && row.image_url === '/media/vehicles/toyota-c-hr-press-39c5e82ee449.jpg'
      ? 'Modellbild: Toyota C-HR+ i brittiskt Design-utförande. Färg, hjul och utrustning kan skilja från den svenska versionen.'
      : idBuzz && row.image_url === '/media/vehicles/volkswagen-id-buzz-00832a4a6a37.jpg'
      ? 'Modellbild: Volkswagen ID. Buzz Pro med kort hjulbas, inte Sweden Olympic Edition. Utrustningen kan skilja sig.'
      : ev2 && row.image_url === '/media/vehicles/kia-ev2-press-42a663c6e0ce.jpg'
      ? 'Modellbild: Kia EV2 GT Line. Färg, hjul och utrustning kan skilja från den valda versionen.'
      : ev3 && row.image_url === '/media/vehicles/kia-ev3-press-b0de32637809.jpg'
      ? 'Modellbild: Kia EV3 GT Line. Färg och utrustning kan skilja från den valda versionen.'
      : ev4 && row.image_url === '/media/vehicles/kia-ev4-press-0446f33614bd.jpg'
        ? 'Modellbild: Kia EV4 GT Line halvkombi. Färg och utrustning kan skilja från den valda versionen.'
        : ev5 && row.image_url === '/media/vehicles/kia-ev5-press-de4eab70d59a.jpg'
          ? 'Modellbild: Kia EV5 Baseline. Färg och utrustning kan skilja från den valda versionen.'
          : ev6 && row.image_url === '/media/vehicles/kia-ev6-press-5e19a7dc0d49.jpg'
            ? 'Modellbild: Kia EV6 Baseline. Färg och utrustning kan skilja från den valda versionen.'
            : ev9 && row.image_url === '/media/vehicles/kia-ev9-press-731db0e8f686.jpg'
              ? 'Modellbild: Kia EV9. Färg och utrustning kan skilja från den valda versionen.' : null,
    rangeIsTarget,
    rangeMinimum: certified ? Number(certified[3]) : null,
    rangeInterval: certified ? certified[3] + '\u2013' + certified[1] + ' km' : born ? '552–631 km' : null,
    rangeNote: ioniq9 ? 'Blandad WLTP f\u00f6r den sjusitsiga svenska versionen med 20-tumshjul. Andra hjul kan ge annan r\u00e4ckvidd.'
      : glb ? 'Blandad WLTP f\u00f6r den svenska grundversionen med fem s\u00e4ten. Hjul och tillval kan p\u00e5verka r\u00e4ckvidden.'
      : certified ? 'Certifierat intervall f\u00f6r blandad WLTP, modell\u00e5r 2027. Hjul och utrustning p\u00e5verkar var i intervallet bilen hamnar.'
      : ev3Preliminary ? '572 km är en preliminär tillverkaruppgift i väntan på homologering enligt Kias svenska faktablad, inte slutlig certifierad räckvidd. Den används inte för att bekräfta ett hårt räckviddskrav.'
      : rangeIsTarget ? 'Tillverkarens räckviddsmål enligt WLTP, inte ett slutligt certifierat värde.'
      : r4Evolution ? '407 km och 15,2 kWh/100 km avser det svenska Evolution EV52-exemplar som RN Automotive specificerar. Renault anger också 407 km för versionen. Utrustningen kan påverka värdena.'
      : r4Techno ? '398 km och 15,5 kWh/100 km gäller den svenska Techno EV52 av modellår 2026 med 18-tumshjul som Hedin specificerar. Renault anger också 398 km för versionen. Hjul och utrustning kan påverka värdena.'
      : chrPlus ? 'Slutlig blandad WLTP med standardhjul: Active FWD 18 tum upp till 607 km, Active AWD 18 tum 548 km och Executive AWD 20 tum 507 km. Tillvalshjul och utrustning påverkar räckvidden.'
      : idBuzz ? 'Blandad WLTP för den svenska grundkonfigurationen med kort hjulbas och fem sittplatser. Hjul och tillval kan påverka räckvidden.'
      : ev2 ? 'WLTP upp till: Standard Range 317 km och Long Range 453 km med standardhjulen 16 tum. GT Line Long Range har 19-tumshjul och anges till 413 km, inte modellens högsta 453 km. Uppgifterna gäller de femsitsiga versionerna.'
      : ev9 ? 'WLTP upp till: 443 km för RWD 76,1 kWh och 512 km för AWD 99,8 kWh med 19-tumshjul. GT Line med 21-tumshjul anges till 505 km för både sex och sju sittplatser. Hjul och utrustning påverkar räckvidden.'
      : ev6Gt ? 'Upp till 450 km blandad WLTP för EV6 GT med 84 kWh och 21-tumshjul. 550 km i den tyska tabellen gäller stadskörning. Däck, utrustning och körförhållanden påverkar räckvidden.'
      : ev6 ? 'Upp till 582 km för RWD och 546 km för AWD med standardhjulen 19 tum. 522 km gäller GT Line AWD med tillvalshjul på 20 tum, inte dessa basversioner.'
      : ev5Panorama ? '491 km är maxvärdet för GT Line AWD-gruppen enligt Kias svenska MY2027-faktablad, inte ett individuellt mätvärde för varje bil med panoramatak. Hjul och tillvalsutrustning påverkar räckvidden.'
      : ev5Gt ? 'Upp till 476 km enligt Kias svenska GT-sida för 306 hk. Den tyska GT-tabellen anger samma blandade WLTP-värde; 615 km där avser stadskörning, inte blandad körning.'
      : ev4Gt ? 'Upp till 505 km enligt Kias svenska GT-sida. I den tyska GT-tabellen gäller 505 km med 20-tums Pirelli och 473 km med 20-tums Michelin. Däck och utrustning påverkar räckvidden.'
      : born ? 'CUPRA:s internationella VZ-tabell anger 552–631 km WLTP för modellår 2027. Hjul och utrustning påverkar värdet; 631 km är intervallets övre gräns, inte räckvidden för varje svensk konfiguration.' : null,
    consumptionInterval: certified ? certified[2] + '\u2013' + certified[4] + ' kWh/100 km' : i4 ? '14,9–17,1 kWh/100 km' : interval ? `${interval[1]}–${interval[2]} kWh/100 km` : null,
    consumptionNote: ioniq9 ? '10,5 kW AC avser ombordladdaren vid trefas. 233 kW DC \u00e4r tillverkarens angivna maxeffekt, inte snittet under laddningen.'
      : glb ? '85 kWh anv\u00e4ndbar batterikapacitet. 11 kW AC avser standardladdaren och 320 kW DC \u00e4r bilens maximala laddeffekt.'
      : certified ? 'Certifierat WLTP-intervall. Kalkylen anv\u00e4nder det l\u00e4gre f\u00f6rbrukningsv\u00e4rdet. 350 kW DC g\u00e4ller vid 800 V, och Polestar anger upp till 120 kW vid 400 V. 106 kWh \u00e4r angiven batterikapacitet, inte ett nettov\u00e4rde.'
      : chrPlus ? '77 kWh är bruttobatterikapacitet. Svenskt grundutförande: Active FWD 13,4, Active AWD 14,4 och Executive AWD 15,5 kWh/100 km. Active har 11 kW AC ombord, Executive 22 kW; samtliga anges till 150 kW DC.'
      : idBuzz ? 'Batteriet anges till 79 kWh netto. Volkswagen Transportbilar anger upp till 185 kW DC för det batteriet. AC-effekten 11 kW avser bilens ombordladdare.'
      : i4 ? 'BMW:s WLTP-intervall för eDrive40, typ 61HD, gäller den tekniska typen, inte det enskilda exemplaret. Kostnadskalkylen använder 14,9 kWh/100 km; hjul och utrustning påverkar förbrukningen. Räckvidden 588 km gäller det BMW-exemplar som källan beskriver. Batteri och laddning gäller samma tekniska typ. Exemplaret är tillverkat 2026.'
      : ev2 ? 'Svenska produktfakta från 29 september 2026: Standard Range 15,1 och Long Range 14,9 kWh/100 km med 16-tumshjul; GT Line Long Range 16,3 med 19 tum. Ombordladdaren är 10,5 kW och maximal DC-effekt 150 kW. Den äldre broschyrens preliminära värden används inte.'
      : ev9 ? 'Svenska produktfakta från 20 augusti 2026: RWD 18,7 och AWD 22,2 kWh/100 km med 19-tumshjul; GT Line 22,8 med 21 tum. Ombordladdaren är 10,5 kW och maximal DC-effekt 210 kW. 250 kW i laddtidsvillkoret avser stationen, inte bilen.'
      : ev6Gt ? 'Blandad WLTP-förbrukning 20,9 kWh/100 km enligt Kia Sverige. Ombordladdaren är 10,5 kW och maximal DC-effekt 258 kW, styrkt av Kias tyska tabell för samma 84 kWh-GT. 650 hk gäller med Launch Control; normal maxeffekt är 609 hk.'
      : ev6 ? '84 kWh-versioner med standardhjulen 19 tum: RWD 15,9 och AWD 17,0 kWh/100 km. Ombordladdaren är 10,5 kW och maximal DC-effekt 258 kW. 17,7 kWh/100 km gäller AWD med 20-tumshjul.'
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
    practicalNote: ioniq9 ? '338 liter bakom tredje s\u00e4tesraden med alla sju s\u00e4ten i bruk, utan frunk. 2 500 kg g\u00e4ller bromsat sl\u00e4p med r\u00e4tt dragutrustning. Kontrollera bilens registreringsbevis.'
      : glb ? '540 liter bak med fem s\u00e4ten i bruk, utan det fr\u00e4mre bagaget. Dragvikten avser bromsat sl\u00e4p med r\u00e4tt dragutrustning. Kontrollera bilens registreringsbevis.'
      : certified ? '484 liter bak upp till ryggst\u00f6den med s\u00e4tena uppf\u00e4llda, inklusive utrymmet under golvet. Det fr\u00e4mre bagaget ing\u00e5r inte. Dragvikten avser bromsat sl\u00e4p.'
      : chrPlus ? '416 liter bak med baksätet uppfällt och fem sittplatser. Bromsad dragvikt är 750 kg för FWD och 1 500 kg för AWD, med rätt dragutrustning. Dragkrok ingår inte automatiskt; kontrollera bilens utrustning och registreringsbevis.'
      : idBuzz ? 'Bagagevolymen gäller med fem säten i bruk. Dragvikten är tillverkarens svenska uppgift för bromsat släp vid 12 % lutning med rätt dragutrustning. Kontrollera registreringsbeviset för bilen du överväger.'
      : i4 ? 'BMW anger 1 600 kg bromsad släpvagn vid 12 % lutning för typ 61HD. Exemplaret har utrustningskod 3AC för utfällbar dragkrok; kontrollera registreringsbeviset. 75 kg kultryck är inte dragvikt. Bagagevolymen 470 liter gäller med baksätet uppfällt. Pressbilden visar samma i4 eDrive40-modell, inte nödvändigtvis samma färg och hjul.'
      : ev2 ? 'Fem sittplatser i bruk: 362 liter bak. 403 liter avser den separata fyrasitsversionens skjutbara baksäte, inte dessa bilar; 1 201 liter kräver fällt baksäte. Frunkens 15 liter ingår inte och basversionen har ingen frunk. Bromsad dragvikt är 750 kg med rätt utrustning; kontrollera registreringsbeviset.'
      : ev9 ? '333 liter bak med samtliga sittplatser i bruk. Sexsitsversionen styrks separat av Kias tyska VDA-tabell inklusive utrymmet under lastgolvet; 828 liter kräver fälld tredje rad. Frunken ingår inte. Bromsad dragvikt är 900 kg för RWD och 2 500 kg för AWD med rätt utrustning; kontrollera registreringsbeviset.'
      : ev6Gt ? 'GT: 480 liter bak med baksätet uppfällt, inklusive utrymmet under lastgolvet enligt den tyska VDA-tabellen. Frunkens 20 liter ingår inte. Bromsad dragvikt är 1 800 kg med rätt utrustning; kontrollera registreringsbeviset.'
      : ev6 ? '480 liter bak med baksätet uppfällt, utan frunkens 50 liter för RWD eller 20 liter för AWD. Bromsad dragvikt är 1 800 kg med rätt utrustning; körkortsbehörighet och registreringsbevis kan begränsa vad du får dra.'
      : ev5Gt ? 'GT: 566 liter enligt den tyska GT-tabellen med baksätet uppfällt, inklusive utrymmet under lastgolvet. 1 650 liter kräver fällt baksäte och frunken ingår inte. Bromsad dragvikt är 1 800 kg med rätt utrustning; kontrollera registreringsbeviset.'
      : ev5 ? '566 liter gäller med baksätet uppfällt, utan frunkens 44 liter. 1 650 liter gäller fällt baksäte. Bromsad dragvikt är 1 200 kg för FWD och 1 800 kg för AWD med rätt utrustning. Panorama är ett GT Line-tillval, inte en annan motor. Kontrollera registreringsbeviset.'
      : ev4Gt ? 'Bagagevolymen 359 liter kommer från den polska GT-kolumnen. Den tyska uppgiften 377 liter räknar även in dubbelbotten och har en annan mätgrund. Dragvikten 1 500 kg avser bromsat släp med rätt utrustning, inte kultryck eller taklast. Kontrollera registreringsbeviset.'
      : ev4 ? 'Svenska GT Line halvkombi: 435 liter för FWD och 359 för AWD med baksätet uppfällt, inte Fastback eller fällt baksäte. Bromsad dragvikt är 1 000 respektive 1 500 kg med rätt utrustning. Kontrollera registreringsbeviset.'
      : ev3 ? 'Bagagevolymen gäller med baksätet uppfällt: 460 liter för FWD och 413 liter för AWD/GT, utan frunken. Dragvikten avser bromsat släp med rätt utrustning; kontrollera registreringsbeviset. Bilden är en EV3-modellbild i GT Line-utförande, inte en utfästelse om varje versions utrustning.'
      : cla ? 'Maximal bromsad dragvikt med erforderlig dragutrustning. Monterad dragkrok ingår inte automatiskt; kontrollera utrustning och registreringsbevis för bilen du beställer.'
      : explorer ? 'Bagagevolymen kommer från Fords danska presentation av samma europeiska Explorer, med baksätet uppfällt. Lastgolv och utrustning påverkar utrymmet. Dragvikten gäller svensk MY27.25; kontrollera registreringsbeviset för bilen du beställer.'
      : born ? 'Bilen är inte godkänd för släp enligt den svenska instruktionsboken. 0 kg är därför ett styrkt förbud, inte saknad data. Fästet för cykelhållare får inte användas för släp; dess vertikala belastning är ingen dragvikt.' : null,
    practicalSource: explorer && quote.includes('https://www.ford.dk/koeb/kampagner/explorer-og-capri') ? 'https://www.ford.dk/koeb/kampagner/explorer-og-capri' : null,
    specSources: r4Evolution ? [
      { label: 'Räckvidd och förbrukning: RN Automotive Tagene', url: r4Source },
      { label: 'Renault Sverige: Evolution EV52', url: 'https://www.renault.se/personbilar/elbilar/r4-e-tech-electric/versioner-och-priser' },
    ] : r4Techno ? [
      { label: 'Räckvidd och förbrukning: Hedin Automotive Helsingborg', url: r4TechnoSource },
      { label: 'Renault Sverige: Techno EV52', url: 'https://www.renault.se/personbilar/elbilar/r4-e-tech-electric/versioner-och-priser' },
    ] : chrPlus ? [
      { label: 'Toyota Sverige: slutlig räckvidd per version och standardhjul', url: 'https://www.toyota.se/bilar/toyota-c-hr-plus' },
      { label: 'Toyota Sverige: utrustning, pris och tekniska motorkolumner', url: 'https://pdf.toyotasverigebroschyr.com/price-list/nya-toyota-c-hr' },
    ] : idBuzz ? [
      { label: 'Volkswagen Transportbilar: tekniska data för kort ID. Buzz', url: 'https://www.volkswagen-transportbilar.se/sv/modeller/id-buzz/tekniska-data.html' },
    ] : ev2 ? [
      { label: 'Kia Sverige: slutliga EV2-produktfakta, september 2026', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev2/kia-sweden-ev2-specification.pdf#page=3' },
      { label: 'Kia Sverige: exakt motor och femsitsutförande', url: 'https://www.kia.com/se/nya-bilar/ev2/specifikationer/' },
    ] : ev9 ? [
      { label: 'Kia Sverige: EV9, motorer och standardhjul', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev9/kia-sweden-ev9-gtline-specification.pdf#page=3' },
      { label: 'Kia Sverige: exakt motor och sex/sju sittplatser', url: 'https://www.kia.com/se/nya-bilar/ev9/specifications/' },
      ...(row.seats === 6 ? [{ label: 'Kia Tyskland: sexsitsversionens bagage, alla säten i bruk', url: 'https://www.kia.com/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV9-Preisliste.pdf#page=15' }] : []),
    ] : ev6 ? [
      ...(!ev6Gt ? [{ label: 'Kia Sverige: EV6 84 kWh och standardhjul', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/specifications/ev6/kia-sweden-ev6-specification.pdf#page=3' }] : []),
      { label: 'Kia Sverige: exakt motor och fem sittplatser', url: ev6Gt ? 'https://www.kia.com/se/nya-bilar/ev6-gt/specifikationer/' : 'https://www.kia.com/se/nya-bilar/ev6/technische-daten/' },
      ...(ev6Gt ? [
        { label: 'Kia Sverige: EV6 GT 84 kWh', url: 'https://www.kia.com/se/nya-bilar/ev6-gt/upptack/' },
        { label: 'Kia Sverige: bränsledeklaration oktober 2026', url: 'https://www.kia.com/content/dam/kwcms/kme/se/sv/assets/contents/utility/bransledeklaration/kia-sweden-bransledeklaration.pdf' },
        { label: 'Kia Tyskland: samma GT, laddning och bagage', url: 'https://www.kia.com/content/dam/kwcms/kme/de/de/assets/contents/utility/Preisliste/Kia-Germany-EV6-GT-Pricelist.pdf#page=10' },
      ] : []),
    ] : ev5 ? [
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
      { label: 'BMW Sverige: pris, räckvidd och utrustning för exemplaret', url: 'https://hitta.bmw.se/r/G26E-i4/i4-eDrive40-WBY61HD030FW37556' },
      { label: 'BMW Sverige: teknisk typ 61HD (eDrive40)', url: 'https://www.bmw.se/sv/alla-modeller/i-series/i4/bmw-i4-gran-coupe-technical-data.html' },
    ] : born ? [
      { label: 'Räckvidd och DC: CUPRA:s internationella VZ-tabell', url: 'https://www.seat-cupra-mediacenter.com/content/dam/seat-media-center/models-all-brands/cupra-models/cupra-born/technical-data/New_CUPRA_Born_Technical_Data_26.pdf' },
      { label: 'Förbrukning: svensk bränsledeklaration', url: 'https://www.cupraofficial.se/content/dam/countries/se/cupra-website/broschyr/cupra-bransledeklaration-okt2026.pdf' },
      { label: 'Släp: svensk instruktionsbok, sidan 288', url: 'https://www.cupraofficial.se/datamanual-manual/manuals/cupra/se-se/CUPRA_Born_03_26_SE.pdf#page=290' },
      { label: 'Bagage och säten: CUPRA Sverige', url: 'https://www.cupraofficial.se/bilar/born' },
    ] : [],
  };
}
