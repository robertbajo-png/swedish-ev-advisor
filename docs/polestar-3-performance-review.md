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

The local release branch now registers only the three verified media
files. Their original and publisher-size hashes match, the image
audit and production build pass, and the existing 92-record export
is unchanged. No Polestar variant has been written to production.

Next: repeat the read-only capture and isolated insertion on the
deployed CUPRA baseline. Keep the three files, registered rights
evidence and the scoped writer together, then prove the final code
with the exact-main browser check before any Polestar insertion.
