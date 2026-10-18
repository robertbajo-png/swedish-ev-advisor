# UI-proportioner 2026-10-18

## Granskning

Den externa förhandsversionens komponenter och lokala skärmbilder granskades för
startsida, katalog, bilsida, jämförelse och nyhetspresentation. Befintliga routes,
bilunderlag och rådgivnings-/publiceringslogik behålls.

Identifierade problem: stora sidrubriker i förhållande till små kontrolltexter,
höga bildytor, ojämn placering av kortpriser, onödigt tomrum i mobilens bilhero
och en mobil verktygsrad som kunde brytas till tre rader.

## Ändringar

- Gemensamma storlekar för etiketter (13px), kontroller (14px) och sidrubriker.
- Startsidesrubrik 56px på desktop, 34-36px på mobil. Kolumner linjerar upptill;
  kortare bildyta och sektioner gör bilutbudet synligt tidigare.
- Katalog/jämförelse använder 40px sidrubrik på desktop, 32px på mobil.
- Bilkort har 20px modellnamn, 22px pris, större specifikationsetiketter och
  konsekvent identitetsyta. Bilderna har samma 1.8-format över hela kortgridet.
- Filter, sortering och visningsläge har minst 44px höga tryckytor på mobil.
  Verktygsraden har två explicita rader och hoppar inte när texten får mer plats.
- Bilhero växer med innehållet i stället för att tvingas till 820px på mobil.
  Okända värden förblir text, inte noll; faktapanelen ryms också vid 320px.
- Jämförelsens bilder och mobilkort är kompaktare; desktoppriser linjerar.
- Fokuserade kontroller flyttas fram om det fasta jämförelsefältet täcker dem.
  Ett separat regressionstest återskapar också redan synlig men täckt fokus.
- Nyhetsrubriker och artikelradavstånd följer en lugnare, sammanhängande skala.
  Nyhetsinsamling och publicering är fortfarande pausade.

## Verifiering

- `verify:ui-proportions`: 24 kombinationer av fyra sidor och sex bredder
  (320, 390, 768, 1024, 1280, 1440px). Kontrollerar rubrikskala, bilkortens
  prislinjering, synlig sökknapp, tryckytor, bilherons fakta och sidledes overflow.
- `verify:site-qa`: 18 sidlägen utan automatiskt upptäckta axe-fel samt
  tangentbordsflöden, reducerad rörelse, felhantering och smala skärmar.
- `verify:home-ui`, `verify:vehicle-ui`, `verify:journal-ui` passerar med
  testfixturer för API-svar och nyheter. Fixturer publiceras aldrig.
- `verify:advisor-data`: samma 69 publicerade källbundna varianter, inga ändringar.
- Produktionsbygge passerar. Projektet har inga separata lint-/typecheck-skript.
- `verify:ui-proportions` ingår nu i GitHubs befintliga UI-regressionsjobb.

Skärmbilder och mätresultat finns lokalt i `data/local/ui-proportions/`,
`data/local/design-qa/` och `data/local/news-qa/` och versionshanteras inte.

## Nästa steg

Publicera samma kodversion som separat preview efter grön CI. Kontrollera de
externa sidorna och API-kontrakten igen. Ingen DNS- eller databasändring ingår.
Live-AI och produktionsdomän kräver fortfarande egna driftkontroller.
