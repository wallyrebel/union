# Fixed reviewed correction: unionnewsms.com, post 5020

This isolated branch corrects only the reviewed published post 5020. The host,
identity/publication fields, current rendered title/content/excerpt digests and
candidate payload digest are hard-coded in scripts/correct_post5020.py.
The fixed request file initially selects dry-run, which authenticates and
validates the same post, emits a receipt and never updates it.

After that exact managed Action succeeds and its artifact is independently
reviewed, copy its unmodified result.json to approved-dry-run.json in this folder.
Set the fixed request stage to apply and pin the receipt SHA256. The runner checks
that receipt's host, post, original snapshot, payload, fact ledger and unchanged
implementation hash, then performs fresh serialized authenticated reads before a
single update containing only title, content and native excerpt.

Publication ID/status/dates/slug/URL, author, taxonomy, featured media and other
identity fields are asserted unchanged. No creation, status changes, media edits,
SEO-plugin meta writes, arbitrary endpoint, publisher rerun or schedule change is
available. Credentials are used only from existing repository-managed Actions
secrets. Redirects and lookup errors fail closed.401/403 stops without retry.
Ambiguous update responses reconcile only the same post and never automatically
retry. Exact already-applied content is a no-op, avoiding duplicate notes.

Offline guard tests must pass before every managed stage. After apply, review the
exact sanitized Action artifact and independently verify the public full text,
title/H1, actual description, source link, canonical/indexability and unchanged
image. The native excerpt is updated because the current public description
contains the same false-absence claim; do not infer an SEO-plugin change.

The reviewed source facts and source-image hashes are in fact-ledger.json.
Student health or other sensitive source-quote material is excluded. Existing
images and their rights are preserved. This is not the separate status cleanup,
a general correction writer, or an RSS pipeline repair.
