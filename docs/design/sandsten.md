# Sandsten: Elbilsagentens startsida

## Designbeslut
- B Sandsten: varm pappersyta `#f8f4ed`, mörk brun text `#332820`, terrakotta `#863c29` och mjukt sandfält `#eee2d4`. Newsreader för de större redaktionella rubrikerna, Manrope för kontroller och löptext. Typsnitten serveras lokalt.
- Lugn öppning med tydlig huvudrubrik, AI-frågerutan först och en sammanhängande landskapsbild efter rådgivaren. Efter landskapsbilden följer nyheter och bilurvalet direkt, utan tom mellansektion. Bildkrediter i sidfoten; materialvillkor stannar vid berörd uppgift.
- Ägarens beslut 27 november 2026 efter publiceringen: Din körvecka tas bort helt, inklusive navigering, ankare, formulär, sorterings- och kalkylkoppling. Mest räckvidd för pengarna är liksom de andra behovsexemplen endast en genväg som fyller i AI-frågan och fokuserar frågefältet. Inget skickas före ett uttryckligt klick på Hitta min elbil. Körsträcka och laddmix anges oberoende i ägandekostnaden.
- Startsidan och endast Körveckans tidigare koppling till katalog/kalkyl omfattas. Katalog, artiklar, rättigheter för befintliga bilbilder, rådgivarens API och kalkylens affärsregler ändras inte.
- Designgrunden är den fastnålade OpenAI Frontend Design Skill på `82d2c5b44ac234ec0f204f647562a4349d90ef43`. Ägaren valde B och bad 27 november 2026 att publicera den nya designen. En senare större designändring ska granskas här och godkännas separat.

## Kontroller innan publicering
- Faktisk förstasida på 320, 390, 768, 1024 och 1440 px: inga avklippta rubriker/överflöden; rådgivare, bild, navigering och kontroller är läsbara.
- Kontrollera att modulen, dess gamla ankare och text saknas även efter navigation och direktlänk. Testa tangentbordsfokus, att räckviddsförslaget fyller i frågan utan anrop och att ett uttryckligt klick använder rådgivartransporten (mock i test). Testa oberoende modellval och redigerbara kalkylantaganden.
- Katalog-, SEO- och produktionskontroller gäller oförändrat. Vid blockerad prisverifiering: behåll föregående produktionsversion. Publicera enbart via den befintliga kontrollerade vägen och verifiera den verkliga aktivt levererade sidan efteråt.

## Avgränsad formgranskning – borttagning

Frontend Design Skill `82d2c5b44ac234ec0f204f647562a4349d90ef43`, läst fil-SHA-256 `d367b2d22825d74c169475507e7ff109b81c1e9c20b2de3421fb19fcfbe3329b`. Visuell tes: behåll Sandstens varma redaktionella lugn, en dominerande landskapsbild och AI-frågan som första handling. Innehåll: öppning → bild → nyheter → katalogurval → befintliga behov och förklaring. Den onyttiga mellansektionen utgår helt; ingen ersättningsdekor eller ny design. Fokus och befintlig rörelse respekterar reducerad rörelse, ingen ny animation.
