# UI QA: fas 5

Datum: 2026-10-16. Gäller QA-rättningar efter GitHub-snapshot `25f3aff`.

## Genomfört

- Landmärken: sidhuvud och sidfot ligger utanför det enda huvudinnehållet.
- Tangentbord: hopplänk, fokus efter sidbyte/bakåt, fungerande AI-genväg och
  fokuserbar tabell med sidledes scroll. Jämförelseraden skymmer inte sidfoten.
- Rubriker: bilkatalogens kort och informationssidans avsnitt följer hierarkin.
- Kontrast: kalkylens etiketter, saknat pris och avancerade enheter har rättats.
- Responsivitet: filter stängs vid desktop-brytpunkt och släpper scroll-låset.
- Rörelse: även JavaScript-scroll respekterar önskemål om reducerad rörelse.
- Felhantering: datafel skiljs från okänd modell och återförsök laddar om sidan.
- Visuell samstämmighet: informationssidan använder kontrollerade rubriker,
  neutralt underlag, 8px-radie och samma sidbredd som övriga produkten.
- Metadata: egna sidtitlar, ingen påhittad lagertillgänglighet eller sittplatser,
  verifierad nolla skiljs från saknat värde. Statisk SEO följer samma offertregel.

## Verifiering

`verify:site-qa` kördes både mot utvecklingsservern och produktionsförhandsvisningen.
Den nya kontrollen omfattar startsida, katalog, familjeurval, två bilsidor
(inklusive saknad bild), jämförelse, informationssida, nyhetslista och artikel.
Alla 18 desktop-/mobilvyer samt filterdialogen passerar den automatiska kontrollen.

Övriga kontroller: `verify:home-ui`, `verify:vehicle-ui`, `verify:journal-ui`,
`verify:news-ui`, `verify:news-presentation`, `verify:advisor`,
`verify:advisor-data`, `verify:cloudflare`, `verify:tco`, `verify:images`,
23 nyhetsenhetstester, fem SEO-enhetstester och produktionsbygget.

Bredder: 320, 390, 640, 820 och 1440 px över testsviterna. 640px-kontrollen
testar omflöde motsvarande minskat layoututrymme; det är inte ett separat test
av textförstoring i alla webbläsare. Körningen använder Chromium/Microsoft Edge.

Bundle-budget: högst 130 KiB gzip JavaScript och 30 KiB CSS. Bygget ligger runt
93 kB JS och 20 kB CSS (decimal gzipstorlek). Detta är inte ett Lighthouse- eller
Core Web Vitals-resultat. Bildnätverkets fördröjning påverkas av externa värdar.

Skärmbilder och maskinrapport: `data/local/design-qa/site-qa-report.json` och
`qa-*.png`, lokalt och Git-ignorerat. Nyhetsbilderna är tydligt märkta testfixturer,
inte publicerat innehåll. Publika JSON-exporter kontrolleras som oförändrade.

Automatisk granskning använder
[@axe-core/playwright](https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright).
Automatiska kontroller ersätter inte manuell granskning med skärmläsare och riktiga
enheter. Fall där verktyget inte kan avgöra exempelvis bildbaserad kontrast finns
i maskinrapportens `manualChecks` och ska inte tolkas som godkända automatiskt.

## Ändrade filer

- UI: `src/main.jsx`, `src/home.jsx`, `src/vehicle-ui.jsx`, `src/ui-navigation.js`.
- Stil: `src/design-system.css`, `src/vehicles.css`, `src/styles.css`.
- SEO-presentation: `scripts/prerender_static_routes.py`, `tests/test_pipeline.py`.
- QA: `scripts/verify_site_qa.mjs`, `package.json`, `bun.lock`, `.github/workflows/ci.yml`.
- Dokumentation: denna rapport, `docs/ui-redesign-plan.md`, `docs/PROJECT_STATUS.md`.

## Kvar före lansering

- Bekräfta GitHub Actions-resultatet för snapshoten med fas 5.
- Testa verklig driftadress, publika Supabase-vyer, AI-anrop, rapporter och djupa
  länkar på hostingmiljön. Testerna här gör inga betalda AI-anrop.
- Kontrollera Safari/iOS, Android och skärmläsare på riktiga enheter.
- Fyra modellbilder saknas fortfarande: Audi A6 e-tron, Cupra Tavascan, Kia EV6,
  Volvo EX90. Ingen annan modell används som reservbild.
- Nyhetsmotorn förblir pausad och den verkliga publika nyhetsexporten är tom.
  Skarp generering och driftsättning av nyhetsmotorn är separata uppgifter.

Rekommenderad nästa uppgift: publicera en förhandsversion med fas 5 och gör en
begränsad skarp integrationskontroll. Databasens insamling/publiceringsregler
och bilarnas verifierade värden har inte ändrats av denna QA-runda.
