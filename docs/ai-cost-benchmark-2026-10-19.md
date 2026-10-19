# Uppmatt AI-kostnad 2026-10-19

Fem syntetiska vanliga svenska bilsokningar kordes med riktiga API-anrop,
utan aterforsok. Samtliga gav `mode: openai` och rekommendationernas identitet
och kallor matchade det publicerade underlaget.

## Metod

- Oforandrad radgivarkod: `functions/_shared/advisor-core.mjs`.
- Modell: `gpt-5.4-mini`, standard-tier, max 2 400 output-tokens, `store: false`.
- Samma snapshot som AI-previewn: 69 publicerade, kallbundna varianter.
- Anropen gick direkt genom samma radgivarfunktion till OpenAI, inte genom
  webblasaren/Pages HTTP-routen, sa att provider-usage kunde matas utan att
  andra den publika API-responsen eller gora extra modellkorningar.
- Inga betalda verktyg, webbsokningar, databasskrivningar eller nyhetsskapande.
- Faktiska input/output/cache-tokenraknare fran varje Responses-svar sparades.
  Kostnaden ar beraknad fran dessa, inte avlast fran kontots saldo/faktura.
- Output inkluderar eventuella reasoning-tokens; dessa raknas inte en gang till.
- Alla fem svar hade noll cachade input-tokens.

Priser per miljon tokens: input 0,75 USD; cache-input 0,075 USD; output 4,50 USD.
Verifierat mot [OpenAI:s modellpriser](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

Formel: `((input - cached) * 0.75 + cached * 0.075 + output * 4.50) / 1000000`.

## Resultat

| Sokning | Input-tokens | Output-tokens | Kostnad USD | Ore vid 10 SEK/USD |
| --- | ---: | ---: | ---: | ---: |
| Familjebil under 600 000 kr | 10 752 | 600 | 0,010764 | 10,8 |
| Budget/pendling under 400 000 kr | 10 746 | 299 | 0,009405 | 9,4 |
| Langresor och snabbladdning | 10 749 | 536 | 0,01047375 | 10,5 |
| Husvagn 1 500 kg | 10 758 | 565 | 0,010611 | 10,6 |
| Fyrhjulsdrift och vinter | 10 757 | 583 | 0,01069125 | 10,7 |

Totalt: **0,051945 USD**, cirka **0,52 SEK**. Medel: **0,010389 USD/anrop**,
cirka **10,4 ore**. Tusen liknande anrop motsvarar ungefar 104 SEK och tiotusen
ungefar 1 039 SEK med samma antagna valutakurs.

SEK ar endast ett rakneexempel med 10 SEK/USD, inte en uppgift om aktuell
valutakurs. Moms, hosting, annan trafik och tidigare tester ingar inte.
Franvaron av cachetraffar i fem anrop garanterar inte framtida cachningsbeteende.
Detta ar en kostnadsmatning, inte en full kvalitetsutvardering av alla AI-pastaenden.

Den detaljerade lokala rapporten finns i den ignorerade katalogen
`data/local/ai-cost/2026-10-19T13-36-57-412Z.json`. Den innehaller syntetiska
testfragor, svar och tokenraknare, men inga API-nycklar eller HTTP-autentisering.

## Atertest

```powershell
bun run verify:ai-cost
bun run benchmark:advisor-cost
```

Forsta kommandot anvander enbart fixturer; andra visar en torrkorning. Verklig
korning maste valjas uttryckligen och kostar pengar:

```powershell
bun run benchmark:advisor-cost --live
```

Det gor hogst fem modellkorningar, sekventiellt och utan aterforsok. Korningen
stoppas vid providerfel, okand prissattning/usage eller fallback. Aven ett svar
som underkanns av radgivaren kan ha forbrukat tokens och maste raknas.
Modell, priser och publicerat underlag maste kontrolleras fore framtida tester.

Nasta rekommenderade driftsteg ar lopande serverbaserad tokenmatning och delad
anropskvot/kostnadskontroll. Detta matverktyg andrar inte produktionens skydd.
