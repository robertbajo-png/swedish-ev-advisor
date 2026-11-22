# Polestar 3 Performance MY27: code review

Scope: the Swedish Performance MY27, motor DA and 22-inch wheels.
Polestar Sweden lists SEK 999,000. Its certified mixed WLTP interval
is 524 to 601 km, not a guaranteed 601 km for every configuration. The
catalogue retains existing scalar fields; the UI, adviser, static
description and structured data apply the interval when the exact
certification evidence is present. A strict request above 524 km and
at or below 601 km requires configuration confirmation.

The revalidated local readback and isolated insert preserved all 87
existing published variants and the existing registration history.
Late rollback, repeat application and the real image sizes passed.
The private build used the unaltered source frame and the two
publisher-supplied WebP sizes with the source credit.
These images, private receipts and the candidate catalogue are not
part of the code patch.

The adapter remains local-only. Do not use its fixture as the public
export, repurpose the Tavascan writer, publish the image variants, or
include Dual motor without a separate release scope and current proof.

The release-scope checks now reject drift in existing catalogue rows,
substituted combined WLTP or price evidence, a different commit, and
replacement images. Nine focused catalogue and readback tests passed.
The updated preview also passed at 390 and 1440 px against the earlier
isolated 88-variant candidate, loading the exact 746 and 1782 px
publisher WebP files. This is not proof against current main.

Next: repeat the read-only capture and isolated insertion on the
deployed CUPRA baseline, register only the verified image assets in
the release branch, and prove the final code with the exact-main
browser check before enabling a scoped Polestar transaction.
