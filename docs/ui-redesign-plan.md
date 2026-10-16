# Elbilsguiden UI redesign

## Scope and inspection

React/Vite, JavaScript/JSX, plain CSS. Shared components and routing currently live
in `src/main.jsx`; news UI is in `src/news.jsx`. Cars are read from the public
Supabase view or validated static export. The advisor uses `/api/advisor`, with
existing deterministic matching when the service cannot be reached. Official
model images use explicit model mappings; unavailable images need a neutral state.

The present homepage combines a three-column hero, full filtered catalog,
comparison report and methodological copy. Several successive CSS layers control
the same components. The redesign adds a deliberate shared token layer and a
separate homepage component instead of extending the old hero cascade.

## Phase 1: Design system and navigation

- Self-hosted Manrope, neutral canvas, teal primary actions, restrained sage accents.
- 8px spacing tokens, 1320px content width, consistent control sizes and focus rings.
- Existing logo and brand; navigation: Hitta elbil, Alla elbilar, Jämför, Nyheter.
- Clear active states, mobile navigation and a visible advisor action.
- Verification remains accessible in the footer and existing deep links.

## Phase 2: Homepage and advisor

- Controlled heading and a functional advisor form beside a real model preview.
- Functional example prompts and editable budget/range controls.
- Interpreted requirements and at most three source-matched vehicle recommendations.
- Explicit loading, empty, unavailable-AI and missing-data states.
- Exact existing canonical identities bridge API results to images, specs and compare.
- Homepage order: recommendations, need categories, published news, three service steps.
- No invented AI results, cars, news or photography. Empty data stays visibly empty.

## Preview checkpoint

After phases 1-2, run production build and relevant data/advisor contracts;
inspect desktop/mobile screenshots and test keyboard, example prompts, refinement,
API result binding, comparison actions and deep links. Present the homepage preview.
Do not proceed to phases 3-4 before this checkpoint is reviewed.

## Remaining phases

3. Listing/cards, cinematic details and comparison decision report.
4. Editorial news listing and long-form article treatment.
5. Broader accessibility, performance, responsive and regression QA.

No database, news publication or vehicle ingestion changes belong in this design task.

## Phase 1-2 implementation and QA

Implemented in `src/design-system.css`, `src/home.jsx`, `src/home.css` and the
existing app shell. Manrope is self-hosted under `public/fonts` with its OFL.
The old homepage-only hero, sample cars and process sections were removed.
The catalog, reports, TCO tools, detail routes and news routes remain available.

The homepage starts with no invented recommendations or preselected comparison
cars. Recommendations bind to exact canonical identities, and raw/unpublished
records are filtered out. AI outages are labelled as database matching rather
than presented as successful LLM interpretation. Users can refine an existing
search and compare the actual recommended variants.

Visual checks cover 1440x1000, 820x1180, 390x844 and 320x740. Screenshots are
stored locally in `data/local/design-qa/`. The source-mapped Audi A6 image was
removed because it showed an Avant beside a Sportback record. Missing images
remain neutral, including failed network image requests. The portrait Cupra
asset has a scoped crop position so the complete car remains in view.

Verification commands:

- `npm run build`
- `npm run verify:home-ui`
- `npm run verify:news-ui`
- `npm run verify:advisor`
- `npm run verify:advisor-data`
- `npm run verify:cloudflare`
- `npm run verify:tco`
- `npm run verify:images`

Browser tests exercise deterministic API fixtures only, not a paid live LLM
request. They cover responsive layout, contrast tokens, working suggestions,
editable requirements, exact-model binding, rejected unknown/unpublished models,
comparison, navigation, unavailable data and image failures. News fixtures stay
inside test transport and are never published. No lint/typecheck scripts are
configured in this JavaScript repository.

## Phase 3: Vehicle discovery, details and comparison

Status: implemented; frontend-only changes. Inspection found duplicated card
presentations, high badge density, fixed body-type options, weak mobile filter
access, stale comparison reports and success messages after failed report requests.

The smallest cohesive slice reuses a shared `VehicleCard` on the homepage,
catalog and similar-car sections. `src/vehicle-ui.jsx` also contains the catalog
frame, accessible native-dialog filter drawer and comparison selection cards.
`src/vehicles.css` extends the shared design tokens; it does not modify the news
editorial layouts or any database/ingestion/publication code.

- Catalog: sticky desktop sidebar, mobile drawer with Escape/focus restoration,
  search, existing filters/sorting, real brand/body options, card/table views.
- Cards: exact variant, meaningful price labels, four scannable metrics, discreet
  source/date and comparison state. No arbitrary match scores or badge stacks.
- Details: cinematic image hero and four glass-panel metrics, bright grouped
  specifications, clearly labelled database assessment, optional source details,
  relevant news and consistent alternatives. Unknown seats/battery/charging stay
  unknown. Explicit canonical zero remains distinguishable from null.
- Comparison: actual selected variants with images, add/remove controls, report
  generation, CSV, battery/charging/practicality table and unchanged TCO engine.
  Highlighting requires two distinct known comparable values. List/campaign/offer
  prices remain labelled and incompatible price types are not ranked together.
- Reports clear when selection changes, and late responses for old selections
  are ignored. Failure messages are honest and retryable. A generic report result
  is not presented as a universal personal winner. `/compare` aliases `/jamfor`.

Regression coverage: `npm run verify:vehicle-ui` covers four viewport sizes,
filters, sorting, native-dialog keyboard behaviour, both catalog views, comparison,
CSV downloads, report failure/stale state, details, explicit-zero/null rendering
and missing photos. API responses in browser tests are transport fixtures only.
Existing homepage/news UI, advisor/data/API, image and TCO contracts are retained.

Changed files: `src/vehicle-ui.jsx`, `src/vehicles.css`, `src/home.jsx`,
`src/main.jsx`, `scripts/verify_vehicle_ui.mjs`, `package.json` and this document.

Remaining: phase 4 editorial layouts, followed by phase 5 cross-site QA. The
paused automated news engine is not resumed by this design work.

## Phase 4: Editorial experience

Inspection: `src/news.jsx` contains the public reader, shared preview cards,
listing and article views; `src/news.css` is their isolated stylesheet. The
existing public export currently contains no articles and intentionally exports
`image: null`. Collection, verification, generation and publishing remain paused
and are outside this design phase.

Missing pieces: lead/secondary story hierarchy, topic navigation, reading layout,
vehicle cards, strong empty/error/loading states and optional rights-cleared
image presentation. Existing source links and article metadata must remain.

Implementation sequence:

1. Reuse Manrope/tokens; add a restrained, self-hosted editorial headline font.
2. Lead story plus two secondary stories, topic/brand filters and recent coverage.
3. Readable article typography, original paragraph order, clearly distinguished
   buyer perspective, source references and canonical related-vehicle cards.
4. Share the editorial teaser component with home and vehicle-detail previews.
5. Extend browser fixtures and contract tests for responsive layout, navigation,
   filtering, attribution, image rights, failures and real-data integration.

Only published public articles are rendered. A filled preview uses browser-test
fixtures, never seeded or mock production news. Without approved image metadata,
articles remain text-only; no related-car photo is silently substituted as news
imagery. Phase 5 cross-site QA follows this slice.

### Phase 4 outcome

Implemented: editorial lead plus two secondary stories, two-column recent
coverage, functional topic/brand filtering, self-hosted Newsreader headlines,
readable article body, source sidebar, grouped buyer perspective, share link,
canonical vehicle cards and related stories. Home and car-detail previews reuse
the same editorial teaser. Article paragraph order and wording are unchanged.

`useNews` retains the existing public-view/static-export loading logic. No schema,
API, collection, extraction or publication code was modified. The public export
still contains no articles. Filled screenshots explicitly use isolated browser
fixtures; tests verify that the public JSON remains unchanged.

Optional article image presentation requires an object with `url`, `alt`,
`credit`, `source_url`, `license_url` and `rights_status: approved`. URLs must be
HTTPS without credentials. This is a UI metadata gate, not a license grant or
independent legal verification. Rights approval must happen upstream before an
image is exported. Missing, unapproved or failed images produce text-only news.
There is no fallback to another article/model image. Existing Kia EV6 image
mapping was removed after visual inspection identified a paint swatch, not a car.

Verification: `verify:news-presentation`, `verify:journal-ui`, `verify:news-ui`,
`verify:home-ui`, `verify:vehicle-ui`, news engine unit tests, public advisor data,
TCO and image contracts. The journal suite covers 1440x1000, 820x1180, 390x844
and 320x740; approved-image/error states use test transport, never production
news. No paid live AI requests or news collection runs were made.

Changed: `src/news.jsx`, `src/news.css`, `src/news-presentation.js`, the minimal
`src/main.jsx` bindings, Newsreader font/OFL, presentation/browser tests,
`package.json` and planning/status documents. Next: phase 5 cross-site QA.
Repository sharing and snapshot status are recorded in `docs/PROJECT_STATUS.md`.
