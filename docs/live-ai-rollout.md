# Live-AI: avgransat betatest

## Status och plan 2026-10-19

- Responses API och strukturerade svar finns redan i Pages Functions.
- OpenAI accepterar nyckeln i lokal `.env.local` (modellkontroll HTTP 200).
  Filen har UTF-8 BOM; avlagsna BOM i minnet fore `node:util.parseEnv`, som
  annars missar forsta variabelnamnet. Sjalva hemlighetsfilen andras inte.
- Ingen AI-nyckel ar konfigurerad i det befintliga UI-preview-projektet.
- Ett minimalt Responses-anrop ger HTTP 429, `insufficient_quota`. Kontots
  API-krediter/kvot maste atgardas innan verklig AI kan verifieras. Inga
  automatiska upprepningar eller modellbyten far dolja det felet.
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
- Responses-anrop har 25 sekunders timeout, 2 400 output-tokens och `store: false`.
- Externa serverfetches anvander `redirect: manual` och avvisar 3xx utan att
  skicka nyckeln vidare. Cloudflare Workers stoder inte `redirect: error`.
- Inkompletta svar, avvisanden, ogiltig JSON och providerfel ger reservrankning.
- Betaskyddet tillater fem anrop/minut och klient-IP, tva samtidiga anrop per
  isolat, samma origin och JSON. Serverloggar visar endast fasta felkoder,
  exempelvis HTTP-status eller timeout, inte providerfelens innehall.
- `SMOKE_REQUIRE_AI=1 bun run smoke:advisor` kraver riktiga AI-svar fran bada
  routes och kontrollerar resultat mot previewns publicerade snapshot.

Kvar innan live-AI kan markeras som aktiv: API-kvot, gron CI, separat
preview-publicering samt godkant verkligt smoke-test. UI-previewn ar oforandrad.

## Referenser

- [Responses och autentisering](https://developers.openai.com/api/reference/overview)
- [Strukturerade svar](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [Modellens stod](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [Pages secrets](https://developers.cloudflare.com/workers/wrangler/commands/pages/)
