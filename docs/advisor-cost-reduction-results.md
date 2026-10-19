# Billigare AI-radgivning: uppmatt resultat

Matdatum: 2026-10-19. Modell och standardpriser ar oforandrade: `gpt-5.4-mini`.
AI tolkar nu bara text till krav. Servern filtrerar, rangordnar och skapar
forklaringar fran publicerade canonical-poster. Ingen katalog skickas till AI.

## Jamforbar matning

Samma fem testfragor och exakt samma publicerade snapshot (69 varianter,
verifierat med SHA-256) anvandes fore och efter. Alla fem slutliga anrop gav
`mode: openai`; det betyder AI-tolkade behov med regelbaserad bilmatchning.
Inga cachade input-tokens forekom i nagon av matningarna.

| Sokning | Fore USD | Efter USD | Efter ore vid 10 SEK/USD |
| --- | ---: | ---: | ---: |
| Familjebil | 0,010764 | 0,00072525 | 0,725 |
| Budget och pendling | 0,009405 | 0,00068025 | 0,680 |
| Langresor | 0,01047375 | 0,00071325 | 0,713 |
| Dragkrok och husvagn | 0,010611 | 0,00073875 | 0,739 |
| Fyrhjulsdrift och vinter | 0,01069125 | 0,000729 | 0,729 |

- Totalt fore: **0,051945 USD** (cirka 52 ore).
- Totalt efter: **0,0035865 USD** (cirka 3,6 ore).
- Minskning: **93,1 procent**.
- Ny medelkostnad: **0,0007173 USD**, cirka **0,72 ore per sokning**.
- 1 000 liknande sokningar: cirka **7,17 SEK**, mot tidigare 103,89 SEK.
- 10 000 liknande sokningar: cirka **71,73 SEK**, mot tidigare 1 038,90 SEK.
- Tokenforbrukning efter: **2 166 input**, **436 output** totalt.

Detta ar beraknad kostnad fran verkliga provider-usage-varden och
[publicerade standardpriser](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
inte saldoavlasning. SEK anvander antagna 10 SEK/USD, inte en marknadskurs.
Moms, hosting och annan trafik ingar inte. Svarslangd/priser kan andras.
Jamforelsens separata AI-rapport ar inte ombyggd och har inte denna kostnad.

## Resultatens korrekthet

- Budget och WLTP tolkades som i de fem testfragorna. Husvagnsfragans krav
  blev minst 1 500 kg dragvikt; vinterfragans explicita AWD-krav blev true.
- Familj/resa/drag/vinter gav tre matchande varianter vardera. Budgetfragans
  400 000 kr + 350 km gav inga sakra traffar i denna snapshot. Det innebar
  inte att svenska marknaden saknar sadana bilar, bara att underlaget inte
  kunde bekrafta en match. Ingen dyrare eller okandprissatt bil presenteras
  som att den uppfyller budgeten.
- Fordonsidentitet och kallor matchade publicerade poster. Matchningskoden
  bygger sjalv alla bilsiffror och forklaringar; modellen kan inte tillfora dem.
- Utrustning/andra egenskaper som inte kan kontrolleras markeras separat.
  Klassificeringen av ovriga onskemal kan vara bred och bor fortsatt utvarderas.
- Matningen ar inte en fullstandig kvalitetsutvardering eller garanti for
  framtida rekommendationer. Svenska vinteregenskaper far inte gissas fran WLTP.

## Tester och leverans

`verify:advisor-matching` provar harda krav, okanda varden, explicit noll,
prisgiltighet, marke/modell, determinism, negation, justerade reglage, orimliga
krav och den riktiga lokala Node-routen med simulerad provider.
`verify:live-ai` provar Pages-routes, strikt parser-schema, inget bilunderlag
till OpenAI, API-fel och oforandrad jamforelse. `verify:ai-cost` provar
cacheberakning, ingen dubbeldebitering av reasoning och max fem testanrop.
Homepage-testet omfattar tomma resultat, korrekta kravchips och justeringar.

Reproducerbar korning: `bun run benchmark:advisor-cost --live` (hogst fem
betalda anrop utan aterforsok). Raa lokala rapporter ligger i ignorerad katalog:

- Baslinje: `data/local/ai-cost/2026-10-19T13-36-57-412Z.json`.
- Forsta billigare iteration: `data/local/ai-cost/2026-10-19T13-59-13-036Z.json`.
- Slutlig matning: `data/local/ai-cost/2026-10-19T14-00-51-356Z.json`.

Tva billigare iterationer kordes, totalt tio direkta provider-anrop. Dessa
forbrukade tillsammans **0,007071 USD** (cirka 7 ore vid raknekursen), utover
tidigare baslinje och eventuella separata deployment-smoketest.

Implementationsplan: `docs/advisor-cost-reduction-plan.md`. Global anropskvot,
kostnadstak, databasens 66/69-skillnad och domankoppling aterstar separat.

Runtime `125d0e7` har gron CI (Actions `39265741684`) och ar publicerad pa
https://codex-ai-preview.seekev-ai-preview.pages.dev/ samt versionsbunden
https://9b3fb8af.seekev-ai-preview.pages.dev/. Bada adressernas atta GET-test
passerar. Ett separat externt smoketest gjorde tva riktiga AI-anrop och
verifierade radgivning och jamforelse mot samma publicerade snapshot.
Smoketestets kostnad ingar inte i tabellens jamforbara femfragorsmatning.
