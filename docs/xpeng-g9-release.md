# XPENG G9 catalog release

The scope is two current Swedish factory versions: RWD Standard Range
20 tum and AWD Performance 21 tum. The Swedish configurator supplies
the starting prices. Exact identity, technical data and authorized Swedish
dealer evidence are rechecked by the intake; Mobility Sweden is used
only for the market model. The registered photograph is XPENG's G9
Black Edition press image, with a visible note that equipment may differ.

1. After any preceding model release, regenerate the readback and browser
   review against the exact current main, anonymous production view and
   deployed catalog. Browser QA must apply to the actual candidate,
   including the absence of retail-status badges. A registered press
   photo can be verified directly against the reviewed image; no preview
   overlay is needed for an already merged candidate.
2. Capture the same eight source records again after review. Run
   `publish_approved_xpeng_g9.mjs` with no write option for a read-only
   check. It replays the source bytes, verifies the registered image and
   its derivatives, and checks the exact catalog and reviewed facts.
3. Run `verify_xpeng_g9_scoped_release.mjs` against the reviewed scope
   and same fresh sources. Only the source snapshot is remote and
   read-only; the transaction rehearsal uses a new PGlite database.
4. Use the exact reviewed scope hash for any authorized commit. The
   transaction checks all pre-existing catalog rows and both exact public
   G9 IDs before committing. It writes a private attempt and commit receipt,
   not a catalog export or deployment. An unknown commit outcome requires
   inspection of the database and receipts before any retry.
5. Recover the export separately from the completed receipt. Confirm
   both exact IDs and all variant values with the anonymous view and
   preserve the previous exported rows. No ID columns are added to the
   public file. Reverify the resulting build, sitemap and deployment.

No migration or change to the advisor, news engine, availability flags or
other models is required.
