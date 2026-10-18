# Publiceringsstatus

Kontrollerad 2026-10-18. Ingen produktionsdatabas eller DNS har ändrats.

## Aktuell extern förhandsversion

- Cloudflare-inloggningen är godkänd via Wranglers vanliga OAuth-flöde.
  Behörigheten gäller kontoläsning och Pages; ingen DNS-behörighet begärdes.
  Inloggningen lagras krypterat med Windows Credential Manager, inte i repot.
- Separat Pages-projekt: `seekev-preview`, produktionsgren `main`.
  Endast preview-grenen `codex-ui-preview` har publicerats.
- Publicerad kodversion: `0d65c1bdf42a60c0673410b8d13bec743426b0d0`.
  Exakt commit har grön CI:
  https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/39063781903
- Fast preview-länk: https://codex-ui-preview.seekev-preview.pages.dev/
- Versionsbunden länk: https://99fcf2c3.seekev-preview.pages.dev/
- Båda adresserna passerar alla åtta GET-kontroller: app, katalog, jämförelse,
  nyheter, bil-deeplink, JSON-health, 69 publicerade källbundna varianter och
  webbplatskarta. Preview-sidorna har `noindex` och omdirigerar inte till localhost.
- Det externa smoketestets två POST-anrop passerar i `deterministic_fallback`
  för rådgivning och jämförelse. Detta bekräftar inte en aktiv LLM-integration.
- `verify:site-qa` passerar mot den externa adressen: 18 sidlägen utan
  automatiskt upptäckta tillgänglighetsfel, tangentbord och 320/640px-reflow.
  Testet använder märkta lokala transportfixturer för nyheter och fellägen;
  inga testartiklar eller bildfixturer har publicerats.
- Preview använder samma validerade snapshot i frontend och API. Inga AI- eller
  databasnycklar har lagts in. Nyhetsautomatiken förblir pausad.
- GitHub-flödet är implementerat men ännu inte kontokopplat för automatiska
  uppladdningar. Den första uppladdningen gjordes med autentiserad Wrangler CLI.

Nästa driftsteg: konfigurera serverhemligheter säkert och verifiera live-AI med
ett begränsat `SMOKE_REQUIRE_AI=1`-test. Hantera därefter separat databasens
66/69-skillnad, GitHub-miljöns Pages-token och slutligen domänkopplingen.

## Historik före publiceringen

Följande avsnitt beskriver tidigare kontroller; uppgifter om väntande inloggning
eller saknad preview ersätts av den aktuella statusen ovan.

## Bekräftat

- GitHub-snapshot `5d11e64` har en helt grön `Verify SeekEV`-körning:
  https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/38911960798
  Den omfattar kontrakt, nyhetstester, Functions-kompilering, SEO och samtliga
  UI-sviter. Den första QA-körningens timing-/transportproblem är rättat.
- UI-fas 5 är testad enligt `docs/ui-phase5-qa.md`.
- Cloudflare Pages Functions kompilerar med Wrangler.
- Publika byggen försöker aldrig kontakta besökarens localhost vid API-fel.
  Lokal API-reservadress används endast i utvecklingsläge på loopback-värd.
- Lokalt Pages-runtime-test på port 5184 passerar app-, deep-link-, hälso-,
  bilunderlags- och sitemapkontroller. Health är JSON, inte HTML-fallback.
- Rådgivning och jämförelse returnerar giltiga svar i `deterministic_fallback`.
  Den lokala kontrollen använder ingen AI-nyckel och gör inga betalda AI-anrop.
- Supabases publika vy svarar med 66 publicerade rader med källhash. Den lokala
  canonical-exporten har 69. De gemensamma radernas pris/WLTP skiljer sig inte.

## Kvarstående skillnader

Dessa lokala varianter saknas i Supabases publika vy:

- Cupra / Tavascan / Tavascan
- Subaru / Solterra / Solterra
- Volvo / Ex90 / EX90

Ingen automatisk databassynk har körts i detta leveranssteg. Kontrollera källornas
aktualitet och publiceringskontrakt innan eventuell separat synk.

## Extern hosting

- `https://seekev.se/` och `/health` svarar med samma HTML: `Parked at Loopia`.
  Domänen visar alltså inte Elbilsguiden ännu, trots HTTP 200.
- Cloudflare-fliken visar fortfarande inloggningssidan. Kontoanslutningen väntar
  på användarens inloggning; ingen extern deployment är ännu bekräftad.
- Wranglers Windows-modul för säker nyckellagring är installerad och laddar.
  Detta är inte en slutförd inloggning; inga kontouppgifter har sparats i steget.
- Den lokala miljön saknar `OPENAI_API_KEY`. Äldre nycklar från chatten används
  inte som ersättning för en konfigurerad serverhemlighet.
- Ingen AI-/Supabase-nyckel har lagts in i en extern hostingmiljö i detta steg.
- Nyhetsautomatiken förblir pausad. Inga nyhetsartiklar publiceras av testerna.

## Nästa åtgärder

1. GitHub-push och Actions är bekräftade för `5d11e64`.
2. Slutför Cloudflare-anslutningen och identifiera rätt konto/projekt.
3. Publicera en separat preview och kör `verify:deployment -- URL --expect-preview`.
4. Konfigurera endast publika läsnycklar respektive serverhemligheter i rätt miljö.
5. Kör ett begränsat AI-smoketest med `SMOKE_REQUIRE_AI=1` innan tjänsten kallas
   skarpt AI-driven. Databaserat reservläge räcker inte för den kontrollen.
6. Koppla `seekev.se` först när preview, API, datakontrakt och nyckelhantering är godkända.

Alla kontroller, utom det uttryckliga smoketestet, är skrivskyddade och gör inga
AI-POST-anrop. `verify:deployment-contract` testar kontrollverktyget med fixturer.

## Uppdatering 2026-10-17

- GitHub-kontrollen för `13b9287` är också grön:
  https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/38931769683
- `Publish Pages preview` är implementerat som ett separat GitHub-flöde.
  Exakt grön main-commit, rätt konto/projekt och en separat preview-gren krävs.
  Automatisk körning är avstängd tills `PREVIEW_DEPLOY_ENABLED=true` sätts.
- Lokal validering av preview-skydd, YAML, publiceringskontrakt, Functions,
  canonical-underlag och produktionsbygge passerar. Inga verkliga provider-anrop
  eller uppladdningar görs av fixturtesterna.
- Ett första UI-preview använder samma validerade snapshot i frontend och API,
  utan AI-/databasnycklar. Det är inte ett skarpt LLM-test.
- Wrangler är fortfarande inte inloggat och ingen webbläsare är ansluten till
  datorverktyget. Ingen ny tidsbegränsad inloggningskod har skapats i detta steg.
- För extern publicering återstår kontobehörigheten: Pages-token som skyddad
  GitHub-hemlighet samt account ID/projektnamn som variabler. Dessa läggs direkt
  i GitHub, inte i chatten. Följ avsnitt 7 i hostingchecklistan.

Implementationsplan: `docs/cloudflare-preview-plan.md`. Ingen DNS, canonical-data,
nyhetspublicering eller produktdesign har ändrats i detta steg.
