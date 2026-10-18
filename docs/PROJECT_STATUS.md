# Projektstatus: Elbilsguiden

Datum: 2026-10-18. Denna rapport beskriver kodens status i denna snapshot.
En GitHub-push betyder inte att webbplatsen eller databasen har driftsatts.

## Publicerad förhandsversion

- Extern UI-preview: https://codex-ui-preview.seekev-preview.pages.dev/
- Versionsbunden deployment: https://99fcf2c3.seekev-preview.pages.dev/
- Publicerad kod: `0d65c1bdf42a60c0673410b8d13bec743426b0d0`, med grön CI.
- Åtta externa GET-kontroller passerar på båda adresserna. 69 validerade
  snapshot-varianter visas; preview är `noindex`.
- Externt rådgivnings-/jämförelsesmoketest passerar i databasbaserat reservläge.
  Live-LLM är ännu inte konfigurerad eller verifierad på Cloudflare.
- Samlad webbläsar-QA mot preview passerar: 18 sidlägen, tangentbord, smala
  skärmar och inga automatiskt upptäckta tillgänglighetsfel. Nyheter och
  fellägen använder testfixturer endast i testwebbläsarens transport.
- Domän, DNS, canonical-databas och nyhetsautomation har inte ändrats.
- Automatisk GitHub-publicering kräver fortfarande en separat begränsad
  Pages-token i GitHubs skyddade preview-miljö. Lokal OAuth ersätter inte den.

Full driftstatus och nästa kontokopplingar: `docs/deployment-status.md`.

## Proportionsgranskning 2026-10-18

En extra UI-granskning jämnar ut rubrik-/kontrollskala, bildformat, kortpriser,
mobilfilter och bilherons innehållshöjd. Nya måttester omfattar 24 sidlägen och
ingår i CI. Se `docs/ui-proportion-refinement.md`. Ändringen påverkar inte
canonical-data, AI-tjänster eller nyhetspublicering. Preview-adressen ovan avser
senast bekräftade deployment; nya lokala ändringar blir inte publika via HMR.

## GitHub och delning

- Repo: https://github.com/robertbajo-png/swedish-ev-advisor
- Lokal gren: `main`.
- Föregående GitHub-snapshot: `25f3aff`, med UI-faserna 1-4 och tidigare plattformsarbete.
- Denna snapshot omfattar även fas 5 och återanvändbara publiceringskontroller.
- Exakt version kan identifieras med `git rev-parse HEAD` efter checkout.
- Lokala miljöfiler, databaser, beroenden och QA-skärmbilder följer inte med.
- Nyhetsjobbet kräver `NEWS_AUTOMATION_ENABLED=true` som GitHub Actions-variabel.
  Det förblir avstängt utan detta uttryckliga driftval, även efter en push.

För extern granskning: ange commit-hash tillsammans med denna rapport och
`docs/ui-redesign-plan.md`. För visuell feedback behövs även en nåbar
förhandsvisning eller skärmbilder. En lokal adress fungerar bara på värddatorn.

## Designstatus

- Fas 1 klar: Manrope, färger, gemensamma kontroller och navigation.
- Fas 2 klar: startsida med AI-sökning, faktiska bilposter och redigerbara krav.
- Fas 3 klar: katalog, filter, gemensamma bilkort, cinematic bilsida och jämförelse.
- Fas 4 implementerad och testad: redaktionell nyhetsöversikt och artikelsidor,
  källor, köparperspektiv och kopplade canonical-bilar.
- Fas 5 klar för denna iteration: samlad QA, kontrast och rubrikstruktur,
  tangentbordsnavigering, responsiva fel- och filterlägen samt korrekt sökmetadata.
- Resultat och avgränsningar: `docs/ui-phase5-qa.md`.
- GitHub-kontrollen för `5d11e64` är grön, inklusive alla UI-sviter:
  https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/38911960798
- Nästa: konfigurera serverhemligheter och verifiera live-AI separat innan
  domänkoppling. Den externa UI-förhandsversionen är nu publicerad.
- Read-only driftkontroll: Supabase svarar med 66 publicerade, källbundna varianter.
  Den lokala exporten har 69; inget har skrivits till produktionsdatabasen.
- Extern preview är bekräftad; produktionsdomänen är inte kopplad.
  Se `docs/deployment-status.md`.

## Preview-automation 2026-10-17

- Separat GitHub-flöde för preview är implementerat och lokalt kontraktstestat.
- Kräver grön CI för exakt commit och stoppar publicering till produktionsgren.
- Verifierar den externa preview-adressen med befintliga skrivskyddade kontroller.
- Automatisk uppladdning är opt-in. Första preview publicerades med CLI 2026-10-18.
- GitHubs engångskoppling till Cloudflare återstår. Instruktioner finns i avsnitt 7 av
  `docs/cloudflare-deployment-checklist.md`. Inga produktfunktioner ändras av detta.

## Viktiga avgränsningar

- Inga databas-, insamlings- eller publiceringsändringar i designfaserna.
- Nyhetsmotorn har inte återstartats; publik nyhetsexport innehåller ännu inga
  artiklar. Fyllda nyhetsbilder i QA använder märkta testfixturer, inte riktiga
  publicerade nyheter.
- Bilder utan godkännande eller rätt modell ersätts inte med en annan bil.
  Bild saknas fortfarande för Audi A6 e-tron, Cupra Tavascan, Kia EV6 och Volvo EX90.
- AI-flöden testas med kontrollerade API-svar. Ingen ny skarp AI-generation
  eller bedömning av driftens aktuella AI-nyckel gjordes under designarbetet.

## Kontrollkommandon

```text
npm run build
npm run verify:site-qa
npm run verify:deployment-contract
npm run verify:news-presentation
npm run verify:journal-ui
npm run verify:news-ui
npm run verify:home-ui
npm run verify:vehicle-ui
npm run verify:news
npm run verify:advisor-data
npm run verify:tco
npm run verify:images
```

Nyhets-, startsides- och biltester körs i Playwright på upp till fyra
skärmstorlekar. Lokala skärmbilder finns i `data/local/news-qa/` och
`data/local/design-qa/`; dessa kataloger är inte avsedda att versionshanteras.
Projektet saknar separata lint- och typecheck-skript.
