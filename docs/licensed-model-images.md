# Licensed Model Images

## 2026-10-27 Remediation

Thirty exact-model images were reviewed against Wikimedia Commons file metadata,
model/body/generation categories and five visual contact sheets. Discovery alone
never approves a photo. The reviewed manifest was bound to its exact SHA-256
before adoption; image bytes are separately hashed. No generative images, stock
lookalikes, wrong-model fallback or manufacturer-site availability-as-permission
were used.

The files are served from `public/media/vehicles/`. `src/image-rights.json` records
the author, file page, revision-pinned licence evidence, original asset, CC licence
URI, display changes and reviewed byte hash. `src/model-images.json` is the exact
brand/model lookup. Credits link to the file and licence at the image surfaces;
the contact page contains the complete credit register. Model images are not
claims of a particular trim, equipment specification or model year.

The reviewed registry was synced to the image fields of the 30 existing canonical
models in a single TLS-protected serializable transaction. The importer checked
the entire variant table unchanged and retained every non-image model field. It
does not promote model statuses or change prices, technical evidence, sources,
news, role grants or budgets. Existing public-view publication rules still apply.

Local transaction receipt: plan SHA-256
`e2e6e3b386746272fc453017cb8e97f31403a5270c9b7181ae1a52eb2a38e0e6`.
No paid API calls, new article publication or database schema changes occurred.

## Verification

- `verify:licensed-images`: invalid model, licence/host, incomplete scope,
  changed bytes, changed review and unsafe path rejection.
- `verify:image-sync`: fixture transaction rollback, stale scope protection,
  preservation of private/out-of-scope models and all variant fields.
- `verify:images`: exact model mapping and neutral null fallback contract.
- `python scripts/audit_image_rights.py --check`: every displayed asset must have
  specific licence evidence; local byte hashes and CSS image uses are checked too.

Do not edit the generated registry to label new candidates as documented. Repeat
discovery, source/visual review and hash-bound preparation for replacements. A
different trim/body/generation needs its own review; a Commons search hit is not
enough. Retain credits and the licence when reusing these assets elsewhere.

References:
[Commons reuse guidance](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia),
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
These are recorded licence checks, not a legal opinion about every possible use.
