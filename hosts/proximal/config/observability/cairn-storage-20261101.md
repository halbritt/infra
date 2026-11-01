# Cairn storage investigation — 2026-11-01

## Measurements

VictoriaMetrics database-size history grew from 103.0 GiB on October 18 to
191.8 GiB on November 1: +88.8 GiB in 14 days, +17.5 GiB in seven days and
+1.9 GiB in 24 hours. SQL measured approximately 189 GiB in
`cairn.retrieval_candidate` (170 GiB table/TOAST, 19 GiB indexes), about 266 million
estimated live rows and 0.8 million estimated dead rows. `record_version` occupied
only 108 MiB. These are dated observations, not fixed capacities.

The candidate insert counter was 17,626,225 and the delete counter zero during
inspection. The statistics-reset timestamp was unavailable, so this does not
establish an insertion rate or a historical absence of deletion. Catalog estimates
also do not establish bloat. Scraped counters now provide ongoing rates.

The 83,891 receipts spanned September 7–November 1. A bounded query of the ten
latest receipts found 52,390 candidate rows: 30,342 NO_RETRIEVAL_MATCH, 8,713
KIND_FILTERED, 8,374 OPTIONAL_BUDGET, 4,911 NO_LEXICAL_MATCH, 44 INDEXED,
4 TOTAL_BUDGET and 2 WHOLE_PULL_BUDGET. This sample establishes thousands of
persisted candidates per request, mostly omitted candidates; it is not a full
historical reason distribution. The query used a five-second timeout and the
candidate receipt-key index; it did not scan all 266 million rows.

## Source and retention

The running API reports revision `b0ae063d364ebd5377ba157f5aa205acef14e107`.
The inspected checkout was `a6c8a051461a3105a5e538fa90e0f8222accc619`; the four
files below are unchanged between those revisions.

- `core/compiler.go`, `commitRetrieval`: copies every entry in `evaluations`
  into `retrieval_candidate`, with a serialized CandidateEvaluation JSON detail.
  The write set is broader than the returned selections/index.
- `core/schema/004_retrieval_explanation.sql`: rows belong to a receipt and
  record version through foreign keys. There is no age column or automatic
  deletion/cascade policy on this table; receipt `created_at` supplies age.
- `core/explanation.go`, `Explain`: historical explanation loads these details.
- `core/recompile.go`: historical recompilation reads the stored candidate details.

Searches of core, CLI, deployment and operational scripts found no automatic
retrieval-candidate or retrieval-receipt pruning implementation. Index-handle
expiry in `core/index.go` returns STALE_HANDLE; it does not remove candidate rows.
The separately named attempt-retention scripts manage worker evidence, not this
PostgreSQL table. These source findings and the live row sample explain ongoing
audit-data accumulation; PostgreSQL vacuum cannot remove live rows by age.

## Follow-up boundary

Monitoring and retention investigation are complete. No audit rows were deleted,
no retention duration was invented, and no database rewrite was run. A retention
implementation must define how long detailed candidate explanations remain
available, preserve receipt identity/idempotency and selected-use provenance,
and explicitly report expired/unavailable explanations instead of silently
returning an empty candidate set. It also needs bounded deletion and a separate
space-reclamation plan: ordinary DELETE/VACUUM does not guarantee returning the
existing relation allocation to the root filesystem.
