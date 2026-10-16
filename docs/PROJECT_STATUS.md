# Projektstatus: Elbilsguiden

Datum: 2026-10-16. Denna rapport beskriver kodens status i denna snapshot.
En GitHub-push betyder inte att webbplatsen eller databasen har driftsatts.

## GitHub och delning

- Repo: https://github.com/robertbajo-png/swedish-ev-advisor
- Lokal gren: `main`.
- Bas före denna snapshot: `15eecb5`.
- Snapshoten omfattar UI-faserna 1-4, tidigare pipelinearbete, nyhetskod och tester.
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
- Nästa: fas 5, samlad visuell QA, tillgänglighet, prestanda och regressioner.

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
