# Home featured editorial press photo proposal (2026-11-26)

Prepared locally on top of visual-layout candidate 538d8db. This is evidence
for a separate review, not a release, protected approval, catalog image
transaction, or licence opinion.

## Exact source and scope

- **BMW i4 eDrive40**: [BMW Group Norge image 3037471](https://www.mynewsdesk.com/no/bmw-no/images/nye-bmw-i4-edrive40-dot-jpg-3037471),
  linked by the [manufacturer release of 30 May 2024](https://www.mynewsdesk.com/no/bmw-no/pressreleases/vaarens-produktoppdateringer-fra-bmw-3326384).
  Original 4961 x 3308 JPEG and SHA-256
  `0f228bbc4a06bff7a3432d7fc0e4cf2232c69f3521cc516b426f3666dc796bff`.
  The original EXIF Artist and IPTC byline identify Fabian Kirchbauer;
  EXIF copyright limits it to editorial use. Credit photographer and BMW Group.
- **Electric Ford Explorer**: [Ford Sverige image 2732259](https://www.mynewsdesk.com/se/ford/images/2023-ford-newelectricexplorer-6-2732259),
  attached to the [European electric Explorer announcement of 21 March 2023](https://www.mynewsdesk.com/se/ford/pressreleases/ford-elektrifierar-en-ikonisk-modell-med-introduktionen-av-nya-helelektriska-explorer-utvecklad-och-byggd-i-europa-3241069).
  Original 5000 x 2606 JPEG and SHA-256
  `96d1dbd59dc4b8565750138d89fbdcbb33489070a362b4495ebf49f75dce9330`.
  No individual photographer is named on the image page or in its EXIF, IPTC,
  or creator/rights XMP fields; credit the publishing Ford Sweden entity.

Both exact image pages explicitly permit media reuse to convey/comment on the
publisher's information, **whole and unchanged**, with appropriate credit.
Independent factual consumer comparison is the proposed editorial scope, not
advertising, promotion, endorsement or a representation of an exact trim or
model year. No other use is granted by these records. Both filenames and
actual bytes were re-read and matched the prior visual comparison. The
originals are displayed intact with CSS contain, without cropping, derivative
encoding or retouching. The two lazy-loaded original JPEGs total about 6.2 MB; benchmark mobile performance before a release decision.
There is no source-based proof of current Swedish trim equipment in these
launch/renewal photographs, so the visible model-image qualification remains.

The frozen factual source candidate manifest is
`data/review/home-featured-photo-source-candidates.json` SHA-256
`b9e49640ae582e282c7f301ebf06dbe96a2c773694e37200b1d134ad4fc67b24`.
The initially collected Windows CRLF manifest was 29386debd4c8a615941632f7332cf38abddf7599290187bb4c6bd94c2f604fcf; only the line endings were normalized to LF to preserve the committed hash across checkouts. It records exact source page and related press-release hashes, author evidence
and the download and content bindings. The manifest remains a candidate;
`status: documented` in the generated display registry refers only to factual
rights evidence, not an independent release approval. The preparation tool
validates the manifest and both original files. For reproduction, copy the
manifest and two byte-identical original JPEGs into a private review folder,
run `scripts/prepare_home_featured_photos.py --manifest <file> --source-manifest-sha256 <hash>`
(dry run), then use `--apply-local` only in an isolated proposal worktree.

## Placement and regression

Two new exact, scoped publisher entries retain existing publisher policies.
The registration is not a model-images.json replacement, image source update
in the canonical database, or global rights exception. It applies only when
the exact home featured model's existing original image and generic note
match; otherwise ordinary model images and notes remain. The canonical model,
compare, advisor, catalog and article cards use the pre-existing assets.
The rights audit checks the two new local bytes, source manifest, author,
scope and protected original lookup independently from the canonical assets.

The common visible notice sits with the section heading; a contextual link
opens the existing consolidated Bildkrediter section. The three homepage
photographs appear first in that section, with original model-view credits
and other articles still available. CUPRA's inline WLTP qualification and all
price/fact dates stay in place. The pinned Frontend Design Skill informed
the photo composition, deliberate alignment, hierarchy grouping, restrained
spacing and keeping the existing interaction (no added animation).
## Follow-up: publisher's web sizes (local candidate)

The current two exact press pages advertise 746w and 1782w resources in their
own main image srcsets, using the identical asset identifiers as the licensed
original downloads. We re-fetched the literal advertised URLs with the
existing source fetcher, checked the unchanged per-image terms, page hashes,
title, original hash and author, and accepted **only the two 1782w** WebP files.
They are publisher-delivered bytes; no local encoding or cropping was done.

| Photograph | Publisher display size | Exact bytes | Max mean colour delta, quadrants / outer stripes |
| --- | --- | ---: | --- |
| BMW | 1782 × 1188 | 168746 | 1.020 / 0.947 |
| Ford | 1782 × 929 | 178890 | 1.029 / 0.994 |

BMW's original is sRGB; Ford's original is Adobe RGB (1998). The comparison
uses colour-managed decoded sRGB pixels, normalized geometry at 150px wide,
four quadrants and four edge strips. Both 1782 files meet the conservative
<2 quadrant and <3 edge mean-channel error thresholds. Ford's 746w file did
not meet the quadrant threshold (2.099), so it was not selected. The original
documents and photographer/publisher credits remain unchanged. All original
JPEG bytes stay available as source-audit evidence; the homepage requests
only the registered publisher WebP bytes, never the heavy original as a
fallback. The canonical model images remain untouched.

Exact source URLs and SHA-256s are in
`data/review/home-featured-publisher-web-evidence.json`, SHA-256
`ea09b49ac1c2846ef39064b635c5457e7f0e9ea44a6967240847529bcd15d63b`.
The existing scoped policy now binds both selected sources, sizes and hashes;
the separate rights audit verifies source, credit, evidence and byte identity.
The preparation tool `scripts/prepare_home_featured_web.py` accepts the frozen
manifest and matching publisher files from a private review directory, with
`--sha256` and an explicit `--apply-local` only for a local candidate.

The selected pair totals 347636 bytes versus 381696 for the earlier layout
candidate and 6209081 for the original-photo option. Mobile lab measurements
compare the preserved snapshots with a cold browser and throttled network;
they are not field measurements or production approval.
