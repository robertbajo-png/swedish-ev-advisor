# Privacy Operations

## Owner Decision, 2026-10-27

Boleo AI approved the following operating policy in this chat:

- Search descriptions are used only to provide the requested advice.
- Abuse protection uses legitimate interests with a documented balancing assessment.
- Contact mail is deleted no later than 90 days after case closure unless a legal
  obligation requires longer retention of particular material.

This is an operating decision, not a legal compliance certification or permission
to delete unrelated mail. No production privacy-review flag has been enabled.

## Legitimate-Interests Assessment: Abuse Protection

Purpose: prevent automated misuse, preserve the shared AI allowance and keep the
public service available. The shared monetary ceiling alone cannot fairly limit
one abusive visitor. The daily keyed identifier permits bounded per-visitor use
without retaining a raw IP in the application ledger.

Necessity: the app does not need names, accounts, stable cross-day identifiers,
advertising profiles or stored prompt content for this purpose. A keyed daily
identifier and minimal reservation receipts are less intrusive than storing raw
connection logs or account verification. Provider requests fail closed if budget
or retention maintenance cannot be verified.

Balance: visitors reasonably expect a free public endpoint to resist abuse. An
identifier still constitutes pseudonymous data, not anonymous data. Mitigations:
daily rotation, removal of older identifiers before the next paid request, no
raw IP/prompt/response storage in the budget database, no cross-site use, no
advertising, and an accessible contact/information/objection route. A request
must be evaluated on its circumstances; do not promise unconditional erasure of
records that are needed to establish or defend a legal claim.

Review this assessment when identifiers, purposes, retention or providers change.
It does not establish the legal basis of every other processing operation.

## Mail Retention Procedure

The operator records the closure date when a contact matter is resolved and
reviews closed matters at least monthly. Delete the message, attachments and
unnecessary copies before closure + 90 days. Also remove them from Trash under
the mailbox provider's available controls. Log only the completion date and a
non-identifying case reference, not a copy of the deleted message.

If a legal retention obligation applies, record its basis, scope and expiry,
retain only the necessary material, and review at expiry. This document does not
run an inbox deletion job or authorize access to unrelated messages. Cloudflare
forwarding and the destination mailbox have their own service-level retention.

## Supplier Verification Still Required

- OpenAI: the existing locally stored production-approved key authenticated
  against the free models endpoint on 2026-10-27. This proves key validity only,
  not the organisation/project match, sharing settings or a successful paid call.
  A previous dashboard review showed sharing disabled in the viewed organisation,
  but the key's membership has not been bound to that review. `store=false` is
  used; it is not Zero Data Retention.
- Cloudflare: site hosting, daily budget storage and the approved contact-mail
  forwarder are used. Confirm the applicable account agreement and DPA.
- Supabase: published vehicle/news data and private ingestion controls. Strict
  client TLS and pooler-to-database TLS have been verified separately. Confirm the
  applicable DPA and transfer configuration, rather than infer them from TLS.
- Mail destination: the approved route points to Gmail. Do not describe this as
  Google Workspace or assert a Workspace DPA without evidence of that product.
  The actual supplier-role/contract review remains open.

Primary references (terms reviewed as reference material, no new agreement accepted):

- [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data)
- [OpenAI DPA](https://openai.com/policies/data-processing-addendum/)
- [Cloudflare DPA](https://www.cloudflare.com/cloudflare-customer-dpa/)
- [Supabase DPA](https://supabase.com/legal/customer-resources/data-processing-addendum)
- [IMY information rights](https://www.imy.se/privatperson/dataskydd/dina-rattigheter/ratt-till-information/)

Keep `PUBLIC_PRIVACY_REVIEWED` unset/false until these remaining factual checks
are completed. An owner's policy approval does not prove provider configuration.

## Supplier Terms Reference Check: 2026-10-27

The current primary contract pages were read again. Supabase's DPA (version 1,
2026-08-01) states that it forms part of the applicable service agreement and is
effective with that agreement. Cloudflare's DPA (version 6.4, 2026-04-03) forms
part of its main agreement, including self-serve agreements. OpenAI's DPA,
effective 2026-01-01, describes incorporation into the applicable services
agreement. These are existing standard-contract references, not new agreements
accepted on the owner's behalf or an account-specific audit.

Do not invent an extra paid DPA purchase requirement. Equally, do not infer the
actual contracting customer, local key's project-sharing settings, specific
transfer configuration or Gmail business processing terms from those public
pages. The browser control connection timed out during the account checks;
there is no new evidence justifying a true privacy-release flag.
