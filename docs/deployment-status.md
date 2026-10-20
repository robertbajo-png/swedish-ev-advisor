# Publiceringsstatus

Kontrollerad 2026-10-20. DNS är oförändrad. Första verifieringsbatchen är genomförd;
priser, tekniska värden och tillgänglighetsflaggor är oförändrade.

## Toyota: Privat Variantinläsning

Den aktuella specifikationssidans strukturerade data läses nu med exakt
tillverkar-ID, batteri, effekt och drivning. En variant är sparad i privat
Supabase-staging, nu `validated` inför separat publicering. Upprepade körningar skapade ingen dubblett.
Äldre Active FWD/AWD kräver generationsmappning och har inte skrivits över.
PDF-servern ger dokumentrubriker men nedladdningen av innehållet misslyckas;
det försöket ligger kvar i karantän. Långsamma strömmar har nu en tidsgräns.

Den publika katalogen är oförändrad och matchar fortsatt Supabase i alla 29 fält.
Ingen ny migration, UI-publicering, DNS-ändring eller betald AI gjordes i detta
steg. Tolv nya tester, tidigare käll-/publiceringstester, bygge och SEO passerar.
Se `docs/toyota-current-prices.md` för ändrade filer, tester och nästa steg.

Fortsättning: migration 011 med privata tillverkar-ID:n och en begränsad atomisk
publiceringsfunktion är testad och förberedd, men inte körd. Ägarens godkännande
är efterfrågat. Sex nya servertester samt PostgreSQL-tester för återställning,
identitet, källbevis och behörigheter passerar. Publika 66 poster är oförändrade.
Se `docs/toyota-variant-publication.md`.

## Första Aktualitetsbatchen: Publicerad

Tre befintliga Polestar 2-varianter har extraherats på nytt från exakta kolumner
i den svenska specifikationstabellen, validerats i privat staging och publicerats
atomiskt efter ägarens godkännande av migration 010. Pris och teknik stämde redan;
källkoppling, källbevis, confidence och verifieringsdatum har uppdaterats. Antalet
är fortsatt 66 varianter / 30 modeller, med oförändrade tillgänglighetsflaggor.
Återspelning av samma batch ändrade inga värden eller datum. Anonyma och inloggade
roller saknar exekveringsrätt; samtliga sju interna tabeller är fortsatt skyddade.

Snapshoten är exporterad från den anonyma vyn, med hash
`8d436119b4a289a3ed25117597cc9d31cdfc94c28f02720002ebf894c1b7c09d`.
Runtime `3ffb28262c2493736b512bdbb865aa9540bf0d13` är publicerad efter grön CI
(`39467788570`). Både den fasta AI-previewen och versionsadressen
https://a5c4f6b7.seekev-ai-preview.pages.dev/ klarar åtta externa GET-kontroller.
Alla 29 publika fält och innehållshashen matchar den anonyma Supabase-vyn.
Polestar-sidan visar verifieringsdatum 2026-10-20 och oförändrat saknade värden.

Två Polestar 4-uppdateringar kräver säker variantmappning; befintliga publika
poster har inte ändrats eller tagits bort. Toyotas aktuella dokumentlänk
är upptäckt men ännu inte godkänd/extraherad i den automatiska pipelinen.
Se `docs/verified-variant-refresh.md` för exakta kommandon och återstående steg.
Den nya läsande källkontrollen har 17 av 33 URL:er åtkomliga; övriga kräver
åtkomst-/källåtgärder. Bara tre av 66 varianter är aktualitetsverifierade i denna
batch. Inga betalda AI-anrop har gjorts.

## Katalogsynkning: Publicerad

Migration 009 är applicerad efter ägarens uttryckliga godkännande. Den kompletterar
sex saknade fält i den publika katalogvyn utan att ändra bilvärden eller
åtkomstregler. Efterkontrollen visar 30 modeller/66 varianter, nekad anonym
läsning av samtliga sju interna tabeller och fungerande serverläsning.

Den nya lokala release-snapshoten kommer direkt från den anonyma Supabase-vyn
och matchar alla 29 publika fält. Tre äldre, enbart lokala modellprofiler ligger
kvar för granskning och visas inte publikt. Webb och API använder samma snapshot
som standard. Runtime `2a909c950232a1bdb667b4610a0a8ad3ee72cdcd` är nu publicerad
efter grön CI. Både den fasta adressen och versionsadressen klarar åtta externa
GET-kontroller. Den publicerade katalogens alla 29 fält och innehållshash matchar
den anonyma Supabase-vyn.

Den första aktualitetskontrollen var inte en ny faktaverifiering: då gick 18 av
33 officiella källor att läsa; övriga krävde åtkomst-/källåtgärder. Uppgifter från en
prislista från 2024 måste extraheras och valideras på nytt före release. Se
`docs/release-data-refresh.md`. Inga betalda AI-anrop gjordes i denna kontroll.

Uppdatering efter releasegranskningen: migration 008 är nu applicerad i Supabase
på användarens begäran. Endast databasbehörigheter/radskydd har ändrats, inga
bildata eller DNS-poster. Sju interna tabeller nekar publik läsning; publika
vyer har kvar samma 30 modeller/66 varianter och identiska innehållshashar.
`anon` och `authenticated` är verifierade utan intern tabellåtkomst, medan
serverrollen behåller insamlingens CRUD-behörigheter. Se
`docs/vehicle-access-hardening.md`. AI-kostnadstaket är nu också verifierat i
förhandsversionen. Övriga releasehinder kvarstår.

## Aktuell AI-version Med Kostnadstak

- Runtime: `3ffb28262c2493736b512bdbb865aa9540bf0d13` med grön CI:
  https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/39467788570
- Fast adress: https://codex-ai-preview.seekev-ai-preview.pages.dev/
- Versionsbunden adress: https://a5c4f6b7.seekev-ai-preview.pages.dev/
- Gemensam privat D1-policy: högst 1 USD/dygn och 10 USD/kalendermånad UTC.
  Både rådgivning och jämförelse reserverar kostnad innan ett betalt anrop.
- Okänd förbrukning behåller säkerhetsreservationen. Budgetfel, nått tak och
  nödstopp ger databaserade resultat utan betalda AI-anrop.
- Katalogversionens nödstopp är också testat på distans för båda funktionerna
  och återställt. D1-bokföringen är oförändrad: två reglerade anrop, 2 636
  mikro-USD. Migration, källkontroll och publicering gjorde inga betalda AI-anrop.
- Externt nödstopp är provat för båda funktionerna och återställt. Två riktiga
  AI-anrop den 20 oktober fungerade och gav två reglerade D1-poster, sammanlagt
  0,002636 USD efter avrundning. Det är bokförd tokenkostnad, inte kontoavläsning.
- De två gamla AI-versionerna utan tak är borttagna; deras API-adresser ger 404.
  Den aktuella versionen klarar samtliga åtta externa GET-kontroller.
- Endast AI-preview har fått D1-bindning och en ny slumpmässig serverhemlighet
  för dagliga klienthashar. Ingen DNS-behörighet eller Supabase-hemlighet behövdes.
- Separat UI-preview, numeriska bilvärden, DNS och pausad nyhetsautomation är oförändrade.
  Produktionens AI är avstängd som standard. Prisreglerna kräver ny kontroll
  före 19 november, annars stoppas betalda anrop automatiskt.

Driftrutin och avgränsningar: `docs/ai-budget.md`.

## Föregående AI-version: Historik

Nedanstående version är ersatt och dess versionsadress borttagen. Aktuell
publicering och kostnadskontroll beskrivs ovan.

- Separat projekt `seekev-ai-preview`, endast preview-grenen `codex-ai-preview`.
- Kodversion `125d0e7e70b054c13ef66c3e237e5640332223da` har grön CI:
  https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/39265741684
- Fast adress: https://codex-ai-preview.seekev-ai-preview.pages.dev/
- Versionsbunden adress: https://9b3fb8af.seekev-ai-preview.pages.dev/
- Endast OpenAI-nyckeln är överförd till detta projekts preview-hemligheter,
  via CLI-stdin. Inga Supabase-hemligheter är överförda.
- Alla åtta GET-kontroller passerar på båda aktuella adresserna med 69
  publicerade källbundna varianter och `noindex`. Skydd för origin, innehållstyp
  och ogiltig body ingår i gröna kontraktstester; externa 403/415/400-kontroller
  gjordes även på den föregående versionen.
- OpenAI accepterar den lokala nyckeln och modellen `gpt-5.4-mini` (HTTP 200).
  Min kontroll missade först UTF-8 BOM i miljöfilen; ingen ny nyckel behövdes.
- Det tidigare HTTP 429-felet (`insufficient_quota`) är åtgärdat efter
  användarens påfyllning av API-krediter.
- Rådgivaren använder nu AI endast för kravtolkning med högst 512 output-tokens.
  Filtrering, rangordning och bilförklaringar skapas deterministiskt från
  canonical-poster. Sökning med enbart reglagen gör inget AI-anrop.
- Fem jämförbara frågor kostar 0,0035865 USD mot tidigare 0,051945 USD:
  93,1 procent lägre beräknad API-kostnad. Med antagna 10 SEK/USD blir det
  cirka 0,72 öre per fråga, exklusive moms och hosting. Se
  `docs/advisor-cost-reduction-results.md`.
- `SMOKE_REQUIRE_AI=1` passerar på den nya fasta preview-adressen. Rådgivning
  och jämförelse returnerar `mode: openai`; rådgivningens mode avser lyckad
  kravtolkning, inte AI-genererade bilfakta.
- Smoketestets hårda krav ger nu en säker rekommendation, Polestar 2 Long
  range Single motor, och jämförelsen omfattar den valda varianten. Identitet,
  källor, pris och WLTP matchar publicerad snapshot. Testet gör två riktiga
  Responses-anrop; jämförelsens separata AI-rapport är inte kostnadsoptimerad.
- Responsiv UI-testning omfattar tre träffar respektive tomt resultat på
  desktop/mobil. CI omfattar även sidornas tillgänglighet och regressionstester.
- Ingen ny nyckel behövdes för denna publicering.
- UI-preview, datainsamling, databas, nyhetsautomation och DNS är oförändrade.

Plan, tester och säkert återtest: `docs/live-ai-rollout.md`.

## Separat UI-förhandsversion

- Cloudflare-inloggningen är godkänd via Wranglers vanliga OAuth-flöde.
  Behörigheten gäller kontoläsning och Pages; ingen DNS-behörighet begärdes.
  Inloggningen lagras krypterat med Windows Credential Manager, inte i repot.
- Separat Pages-projekt: `seekev-preview`, produktionsgren `main`.
  Endast preview-grenen `codex-ui-preview` har publicerats.
- Publicerad kodversion: `1cd2463c958feaa30b871efb24bc1262e263d4d1`.
  Exakt commit har grön CI:
  https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/39235918853
- Fast preview-länk: https://codex-ui-preview.seekev-preview.pages.dev/
- Versionsbunden länk: https://5e237fc9.seekev-preview.pages.dev/
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
- Preview innehåller nu proportionsgranskningen: kompaktare rubriker/bilder,
  större kontrolltexter och tryckytor samt skydd för fokus bakom jämförelsefältet.
  Alla 24 måttester passerar mot den publicerade versionen. Se
  `docs/ui-proportion-refinement.md`.

Nästa driftsteg: verifiera aktuella priser/specifikationer via den nya källkön.
66/69-skillnaden är löst i den aktuella AI-previewen, inte genom att publicera
de tre lokala modellprofilerna.
Förbered därefter identitet/integritetsinformation, separat produktion och
slutligen domänkopplingen. Det enkla skyddet per isolat kompletteras nu av D1
för gemensam anropskvot och kostnadskontroll.

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
