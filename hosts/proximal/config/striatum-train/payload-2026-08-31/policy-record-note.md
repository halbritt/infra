Principal, 2026-08-31, signed in "Principal Instruction — standing policy signature and follow-through (2026-08-31, r2)" §1 (recorded as RQ-339830), materialized verbatim as authorized: "Signing the uncorrected draft is not authorized. I authorize you to materialize the following as a ledger record and policy artifact verbatim." Policy text follows verbatim:

**Standing drain-deadlock policy (enacted 2026-08-31).** While any live frontier prevents
ordinary integration to `main`, a branch may merge and deploy without a per-instance
Principal grant iff ALL of:
(1) its gate is green at the merged tip, with the gate exit captured on that tip;
(2) independent review is complete with all findings dispositioned — no partial-review
merges;
(3) its consequence class, computed from the deploy-surface diff, is **code**: rendered
policy, catalog, registry, decision records, schema, and the semantic environment are
untouched;
(4) its computed consequence bill is ≤ N re-stamps and **0 regenerations**, where N
follows the signed derivation rule — largest code-class bill on record + 1, floor 3
(today N = 3); semantic-environment bills never enter N's calibration;
(5) it either unwedges a live frontier merge or delivers a defect fix whose dossier
**predates the merge record**;
(6) the merge record is written **before** the write, in the RQ-323669 form, and carries:
the exact deploy-surface diff, the consequence class and bill **as the diff script's
output, never prose**, the affected-frontier set, the recovery successor for each
affected frontier, and a reference to this policy record.

Every landing under this policy lists the policy record's ref in its authority proof.

**Refusal floor:** a blocked or uncomputable consequence is refused to every authority
kind — this policy prices computed consequences; it never waives computation.

**Variance, not void:** if a landing's actual consequence exceeds its recorded bill, the
merge remains history (the ledger is append-only); the variance immediately suspends
further use of this policy, writes a variance/retrospective record, and triggers a
docketed recovery route for the affected frontiers. Use resumes only after the variance
is adjudicated.

**Sunset:** this policy retires automatically when `maintenance-has-a-computed-
successor@1` registers its priced-admission guard; from that point the mechanical path
governs.
