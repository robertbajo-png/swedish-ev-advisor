# Live-AI: avgransat betatest

## Aktuell status 2026-10-19

Live-AI ar verifierad i https://codex-ai-preview.seekev-ai-preview.pages.dev/.
Efter anvandarens pafyllning av API-krediter passerar `SMOKE_REQUIRE_AI=1`:

- API-health: `ok: true`.
- Radgivning: `mode: openai` betyder AI-tolkade krav. Kod filtrerar, rangordnar
  och skriver forklaringar fran canonical-poster; ingen bilkatalog skickas till AI.
- Smoketestets harda krav ger en saker traff: Polestar 2 Long range Single motor.
  Jamforelsen returnerar ocksa `mode: openai` och omfattar den valda varianten.
  Identitet, kallor, pris och WLTP matchar samma publicerade snapshot.
- Testet gor tva riktiga Responses-anrop. Ingen ny nyckel, bilpost eller
  nyhetsartikel behovde andras vid denna kodpublicering.

Verifierad runtime ar `125d0e7e70b054c13ef66c3e237e5640332223da`
med `gpt-5.4-mini`. Detta ar en avgransad beta, inte full produktionsberedskap.
Delad rate limiting/global kostnadskontroll, databasens 66/69-skillnad och
eventuell domankoppling aterstar som separata driftsteg.

## Status och plan 2026-10-19

- Responses API och strukturerade svar finns redan i Pages Functions.
- OpenAI accepterar nyckeln i lokal `.env.local` (modellkontroll HTTP 200).
  Filen har UTF-8 BOM; avlagsna BOM i minnet fore `node:util.parseEnv`, som
  annars missar forsta variabelnamnet. Sjalva hemlighetsfilen andras inte.
- Ingen AI-nyckel ar konfigurerad i det befintliga UI-preview-projektet.
- Fore pafyllningen gav ett minimalt Responses-anrop HTTP 429,
  `insufficient_quota`. Det hindret ar nu atgardat och bada verkliga AI-test
  passerar. Inga automatiska upprepningar eller modellbyten dolde felet.
- Separata Pages-projektet `seekev-ai-preview` ar skapat med produktionbranch
  `main`. Endast `OPENAI_API_KEY` har laddats till dess preview-secret-store
  genom CLI-stdin; inga Supabase-hemligheter har overforts.
- Behall `gpt-5.4-mini` och samma publicerade canonical-snapshot i frontend/API.
- Forbered timeout, tokenbegransning, fail-safe validering och anropsskydd.
- Testa utan riktiga provideranrop innan en nyckel konfigureras.
- Anvand ett separat Pages-projekt, `seekev-ai-preview`, for live-AI. Det
  befintliga `seekev-preview` ska fortsatt vara utan AI-/databashemligheter.
- Pages anvander projektets vanliga `wrangler.toml`; alternativa config-paths
  stods inte. Valj det separata projektet uttryckligen med
  `--project-name seekev-ai-preview` och preview-branchen `codex-ai-preview`.
- Nyckeln ska finnas i ignorerad `.env.local` och overforas till Cloudflares
  preview-hemlighet via CLI-stdin. Den far inte skrivas till kod, byggfiler,
  CLI-argument, webblasare eller chatt.
- Efter gron CI: publicera endast preview, kontrollera externa routes och kor
  tva begransade API-anrop med `SMOKE_REQUIRE_AI=1`. Fallback ar inte live-AI.

## Avgransningar

Ingen DNS, databas, datainsamling eller nyhetsautomation andras. Snapshoten
kommer fran validerade canonical-poster; detta steg ar inte en Supabase-synk.
Aktiverad LLM och uppdaterad databaskoppling ar separata driftkontroller.

Anropsskyddet ar ett enkelt betaskydd per Worker-isolat med kortlivade
IP-raknare och samtidighetsgrans. Det ar inte en distribuerad kvot eller ett
hart globalt kostnadstak. Produktion kraver dessutom delad rate limiting och
kontots kostnadskontroller. Inga IP-adresser eller anvandarfragor loggas av
skyddet. Nyckeln kan inte ersattas med en tidigare nyckel fran chatthistoriken.

## Implementerat och verifierat lokalt

- `bun run verify:live-ai` provar Responses-anrop och bada edge-routes med
  simulerade providersvar. Det gor inga riktiga eller betalda AI-anrop.
- Identitet och kallor binds tillbaka till publicerade poster med kallhash.
  Jamforelsens pris och rackvidd hamtas fran databasen, inte modellsvaren.
- Endast en komplett jamforelse med en giltig vinnare godtas som AI-rapport.
- Modellunderlaget skiljer okand tillganglighet, saknade varden, nollvarden,
  listpris, kampanjpris och aterforsaljarerbjudanden.
- Responses-anrop har 25 sekunders timeout och `store: false`. Radgivarens
  kravtolkning har hogst 512 output-tokens; jamforelsens oforandrade rapport
  har hogst 2 400. Tom fritext med enbart formularkrav gor inget AI-anrop.
- Externa serverfetches anvander `redirect: manual` och avvisar 3xx utan att
  skicka nyckeln vidare. Cloudflare Workers stoder inte `redirect: error`.
- Inkompletta svar, avvisanden, ogiltig JSON och providerfel ger reservrankning.
- Betaskyddet tillater fem anrop/minut och klient-IP, tva samtidiga anrop per
  isolat, samma origin och JSON. Serverloggar visar endast fasta felkoder,
  exempelvis HTTP-status eller timeout, inte providerfelens innehall.
- `SMOKE_REQUIRE_AI=1 bun run smoke:advisor` kraver riktiga AI-svar fran bada
  routes och kontrollerar resultat mot previewns publicerade snapshot.

## Publicerad beta 2026-10-19

- Kod: `125d0e7e70b054c13ef66c3e237e5640332223da`.
- Gron CI: https://github.com/robertbajo-png/swedish-ev-advisor/actions/runs/39265741684
- Preview: https://codex-ai-preview.seekev-ai-preview.pages.dev/
- Versionsbunden: https://9b3fb8af.seekev-ai-preview.pages.dev/
- Bada URL:er klarar alla atta externa GET-kontroller med 69 publicerade,
  kallbundna varianter, korrekt API-health och `noindex`.
- Externa skyddskontroller ger 403 for frammande origin, 415 for fel
  innehallstyp och 400 for null-body. De gor inga provideranrop.
- Det tidigare lokala testet stoppades av `insufficient_quota`. Efter
  pafyllningen passerar det externa verkliga AI-testet for bada routes.
- Ingen DNS, databas, UI-preview-hemlighet eller nyhetsautomation har andrats.

Live-AI ar bekraftad i betan. Vid behov kan bada routes atertestas med foljande
kommando; varje korning gor upp till tva betalda AI-anrop:

```powershell
$env:ADVISOR_API_BASE_URL='https://codex-ai-preview.seekev-ai-preview.pages.dev'
$env:SMOKE_REQUIRE_AI='1'
bun run smoke:advisor
```

Ett HTTP 200 med `deterministic_fallback` ar inte ett godkant AI-test.

## Kostnadsoptimering verifierad 2026-10-19

Samma fem fragor, modell och publicerade snapshot gav 93,1 procent lagre
beraknad API-kostnad efter bytet till enbart kravtolkning. Med antagna
10 SEK/USD motsvarar det cirka 0,72 ore per sokning eller 7,17 SEK per
1 000 liknande sokningar. Moms och hosting ingar inte. Det ar uppmatt
tokenforbrukning, inte kontoavlasning eller ett garanterat framtida pris.
Jamforelsens separata AI-rapport har inte optimerats i detta steg.
Detaljer: `docs/advisor-cost-reduction-results.md`.

## Referenser

- [Responses och autentisering](https://developers.openai.com/api/reference/overview)
- [Strukturerade svar](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [Modellens stod](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [Pages secrets](https://developers.cloudflare.com/workers/wrangler/commands/pages/)
