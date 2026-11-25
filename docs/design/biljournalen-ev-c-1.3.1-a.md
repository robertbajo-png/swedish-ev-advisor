# Biljournalen EV-C-1.3.1 A

Versionsbunden design för Elbilsagentens lokala produktförhandsvisning. Utgår från produktrevision `1d547d84d2e0cfac117c7bb12b85cea33080cfa1` och Boleos befintliga designbaslinje, vars SHA-256 är `70e4e9fd6b4102956334b75bd8ddd6f11e6acfb3472994a87b936db8698cbcae`.

## Beslutsunderlag

- Granskat koncept `EV-C-1.3.1.html`, SHA-256 `df93799070758eb62fc9c4f35126649675f3db99c823b5f3d82509ef2e12a5bc`. Granskningsbevisets SHA-256 är `145f37a8891e4e7a95edd147fcdff463ac228ca61fb0fc239aec7a7cd6927c2d`. Enhetschefen bekräftade att exakt leverans verifierats och godkänts för förhandsvisning.
- Roberts besked efter eget datorprov var ”ok, kör nya designen, har testat på dator nu”. Valet var A, Newsreader, i `EV-C-typsnittsprov.html` med SHA-256 `4f271f1babfd1edc83edba8cff4901e83068c5843c82014325c1b5c4396974a3`.
- Det återgivna mandatet gäller lokal förhandsvisning. Aktivering av produktens designbaslinje och publicering är separata beslut.

## Form och beteende

- Varmt papper `#f4eddf`, marinblå yta `#192633` och rost `#a33515`. Newsreader bär huvudrubrik, redaktionella rubriker och logotyp. Brödtext och kontroller använder systemets sansserif. Newsreader levereras lokalt enligt SIL Open Font License.
- Startsidan har en sammanhållen omslagsyta med fotot av Hyundai Inster Prime i helbild. Körveckans linje binder ihop pendling, laddning och helgresa. Varje stopp öppnas med en inbyggd kontroll. Visa bilurval behåller valen och lämnar en kort motivering till sorteringen. Tidigare navigering, katalogfilter, modellvyer, jämförelse och rådgivare är tillgängliga.
- Nyhetslistan behåller huvudnyhet före övriga artiklar, rubrik före foto och stöd för bildlösa artiklar. Artiklar, katalogposter, RSS och sitemap läses från sparade kanoniska data. Pressevidens i bildregistret knyts till dokumenterat användningsområde. Bilder med helbildskrav visas omodifierade i helbild, även i miniatyrer. För det fristående offlinepaketet ingår bilder med dokumenterad öppen bildlicens. Kias och Renaults godkända Commons-ersättningar har explicit arkiv- och modellkontext.
- Sidfoten har en ingång för **Källor och bildkrediter**. Där finns originalkällor per artikel och exakt bilversion, inklusive prisunderlag, verifikationsdatum, relevanta mätvillkor och bildlicenser. Kontextlänkar kan flytta tangentbordsfokus till exakt rubrik. Frånpris, kampanjvillkor, WLTP och egna räkneantaganden står vid uppgiften.
- Kalkylen tar med körsträcka och laddmix. Enstaka resor räknas en gång. Kontantköp visar värdeminskning och drift. Lån jämförs med ränta och avgifter, med avbetalningar och slutbetalning i separat kassaflöde. Privatleasing kräver samma period, skiljer inkluderad drift från extra mil och håller slitage och avgiftsändring i en separat känslighet. Saknad offert visas. Egen inmatning är ett scenario. Laddförluster läggs endast till för inmatad förbrukning på bilsidan.

## Tillämpad designgranskning

Fastnålad OpenAI Frontend Design Skill `82d2c5b44ac234ec0f204f647562a4349d90ef43`, fil-SHA-256 `d367b2d22825d74c169475507e7ff109b81c1e9c20b2de3421fb19fcfbe3329b`. Skillen låg till grund för att låta en enda omslagsbild bära förstavy, hålla rutten som en arbetsyta och använda tunna skiljelinjer i stället för separata dekorativa kort. Omslagets lätta entré respekterar reducerad rörelse.

Den lokala UI/UX Pro Max-sökningen `keyboard focus cost responsive tables accessible comparison` gav konkreta träffar om tabellbredd, kontrollsemantik och fokus. Kalkylens fem skrivbordskolumner får synliga radetiketter på smala skärmar. Körvägens fält har inbyggda reglage och källvyn fokuserar mottagande rubrik. Färgerna och fotot kommer från godkänt underlag.

Edge/Playwright kördes på 320, 390, 768 och 1440 px från lokal byggd server och på 390 samt 1440 px från offlinefil. Kontroller omfattade faktisk Newsreader-glyphrendering i rubriken, kontrast, tangentbordsingång, layoutbredd, körvecka, filter, exakt variant, kassaflöden, jämförelse, rådgivning, nyheter och källor. Lokal förhandsvisning använder databaserad rådgivning inom katalogen. Skärmläsare, fysisk mobil och skarp publiceringskedja ingick inte.

Pris- och källvyn klarade axe på 390 och 1440 px med simulerad prispost. Länkar i källtexter har synlig understrykning.
