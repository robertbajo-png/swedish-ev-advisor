# Kravtolkning utan bilkatalog i AI-anropet

## Nulage och avgransning

Den uppmatta baslinjen fran 2026-10-19 ar fem sokningar, totalt 0,051945 USD.
Varje radgivar-anrop skickar 69 bilvarianter och genererar shortlist/forklaringar.
Den nya losningen behaller modell, datakallor, route och publikt svarskontrakt,
men AI far bara tolka sokkrav. Jamforelsens separata AI-rapport andras inte.
Ingen budgettjanst, DNS, databas, nyhetsmotor eller ny datainsamling ingar.

## Genomforande

1. Lagdokumenterad kravmodell: budget, WLTP, dragvikt, fyrhjulsdrift, saten,
   bagage, marke/modell, behov, prioritering och krav som inte kan kontrolleras.
2. Kort strikt Responses-schema utan bilposter, bildlankar eller kalltexter.
   Behall `gpt-5.4-mini`, satt lag output-grans och inga automatiska aterforsok.
3. Filtrera och rangordna publicerade, kallbundna varianter i serverkod.
   Bygg skal och kompromisser fran verifierade varden, inte AI-genererade fakta.
   Okand data uppfyller inte harda krav. Relaxera aldrig budget/dragvikt tyst.
4. Anvand samma motor i lokala Node-API:t och Pages samt vid offline-reservlag.
   Behall konsumentgranssnittet, jamforelse och befintliga deep links.
5. Testa schema, negation, explicita fritextvarden, saknad data/noll, inga
   traffar, oforandrade kallor, determinism och att inga bilposter nar OpenAI.
6. Kor samma fem tidigare fragor live, utan aterforsok, med samma snapshot och
   prislista. Redovisa faktisk tokenforbrukning, beraknad kostnad och resultat.
7. Efter grona tester/bygge/CI: publicera pa separata AI-previewn och kontrollera
   externa routes samt UI. Gamla UI-previewn ska inte fa AI-hemligheter.

## Viktiga kontrakt

- `mode: openai` betyder lyckad AI-tolkning av behov, inte AI-skapade bilfakta.
- `shortlist` innehaller noll till tre matchande varianter. Tomt ar ett giltigt
  och arligt resultat; inga billosa eller orelaterade reservforslag skapas.
- Explicita varden i fritext prioriteras fore formularets standardvarden.
  Manuellt justerade reglage prioriteras fore gamla tal i fritexten. Krav som
  inte namns anvander formularets varden. Negation maste respekteras.
- AI-resultat valideras mot tillatna falt, typer och gransvarden fore anvandning.
- Fordonsidentitet, kallor och siffror skapas enbart fran canonical-poster.
- Bortfall av AI gar till tydligt markerad regelbaserad reservtolkning, aldrig
  till den gamla dyrare katalogprompten.

## Kvar efter detta steg

Gemensam global kostnadskontroll/anropskvot ar ett separat steg. Kostnadsmatning
ar inte saldoavlasning. SEK ar fortsatt ett rakneexempel, inte valutakursdata.

## Lokal leveransstatus

Implementerat: kravschema, gemensam matchningsmotor, Pages/lokal Node/offline,
tomma resultat, reglageprioritet, fixturtester och ommatning av fem fragor.
Slutlig uppmatt kostnadsminskning ar 93,1 procent. Se
`docs/advisor-cost-reduction-results.md`. Publicering sker forst efter gron CI;
externa kontroller och nytt driftstatusunderlag aterstar da.
