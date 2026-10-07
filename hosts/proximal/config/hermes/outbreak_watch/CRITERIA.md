# Outbreak Watch

Scope: the Irkutsk anti-plague institute worker death (October 2026) and its aftermath.
Schedule: daily 07:00 America/Los_Angeles. Keep the existing Slack thread destination.
The requester accepts silent failures and false negatives. Avoid unsupported alerts,
and never alert twice for the same facts.

## Evidence

Use original public-health agency documents, laboratory publications, or independently
verifiable original reporting. A government statement establishes what it claims; it
is not automatic proof of the underlying event. Attribute claims precisely. Exclude
anonymous claims repeated by other outlets, aggregators, commentary and social-media
speculation. An institution's own public statement may be primary evidence of its act.
Multiple rewrites of the same observation are ONE origin, not corroboration.

Each candidate needs the primary URL, publication date, publisher, original observation
identity, provenance explaining the citation chain, and an exact supporting passage.
The runner independently fetches the pages through Relay grounding. Quotes must occur
in fetched page excerpts. Search snippets, bare URLs, failed fetches and partial
retrieval never clear a candidate. Reviewers must inspect qualifications and provenance,
not infer truth from the publisher's name or the existence of a URL.

## Worry criteria

A new fact must establish one of these, with event-specific evidence:

- C1: a laboratory result confirms the suspected high-consequence pathogen. Identifying
  an ordinary/non-plague agent is not by itself a worry trigger.
- C2: an additional infection linked to this event establishes spread beyond the index
  case/exposure. A healthcare worker or out-of-region case needs evidence of that link;
  unrelated cases and ambiguous exposure histories do not suffice.
- C3: a public-health authority makes a substantive risk escalation for this event,
  including a WHO emergency declaration or an increased risk assessment. A publication,
  monitoring statement or unchanged travel advisory alone is not an escalation.
- C4: a further event-linked death, or event-linked infections after the relevant
  observation period, establishes uncontrolled disease. Establish the period from
  authoritative pathogen/exposure-specific evidence; never assume ten days.
- C5: a primary assessment/document specifically connects this event, facility or agent
  to an offensive biological program. Historical programs and speculative commentary
  do not establish this criterion.
- C6: primary evidence establishes containment failure. Quarantine length, opacity,
  declining assistance, protective equipment or response scale alone do not prove it.

These refine the existing six criteria to require evidence of the claimed consequence.
Propose future policy amendments in the local scan artifact for operator review. Do not
silently relax thresholds. Evidence-derived values such as the observation window
follow current authoritative sources and must be reviewed with the candidate.

## Independent committee

Use the configured Relay panel: fable, sol, agy and glm, with Relay's synthesizer.
Relay is the multi-model escalation API for agents. This panel is the job's review
committee. Council is the interactive frontier-model committee for humans and is not
used by this unattended job. Same-model delegated subagents are not a substitute.

Every member must affirm source support, criterion support and novelty against the
entire fact registry, and state a falsifier. Unsupported or unresolved evidence cannot
clear an alert merely because nobody disproved it. A refutation or match to previously
observed facts suppresses the candidate. A partial panel, absent synthesis, malformed
verdict or unresolved support remains pending and produces silence. Synthesis must
explicitly APPROVE with only NON_BLOCKING cautions; preserve those cautions in the alert.
Account failover does not guarantee service availability or a complete panel.

## Identity and transitions

state.sqlite3 is authoritative. LEDGER.json is the preserved pre-migration record;
never edit it to drive current behavior. Legacy observations and suppressions remain
in the registry and must not be reopened merely because routing changed to Relay.

A fact is a stable subject/predicate/object proposition. Use stable event, agency,
case or specimen identity. Publication dates, URLs, wording and criterion numbers do
not determine identity. Attach new publications as evidence for that same fact.
Reviewers compare meaning and aliases against the full registry; ambiguous identity
stays unresolved. A new assertion about another case or a changed substantive outcome
may be new; a new retelling is not. Semantic identity still requires judgment; the
runner enforces unique claims after identity resolution rather than claiming a hash
can prove semantic equivalence.

States: seen, pending-review, suppressed, fired, closed. New eligible candidates enter
pending-review before review. Pending candidates may transition to fired, suppressed,
or remain pending. Retry them first, excluding only that candidate from its own novelty
comparison. All other existing facts still count. Do not apply the new-fact exclusion
again to the candidate being retried. A cleared retry ends the run with one alert.

A process lock serializes runs. A transaction reserves the fact's sole alert before
returning output to the scheduler. Once reserved, do not retry delivery even if it may
have failed: a missed alert is acceptable. The scheduler also fences delivery per cron
execution. Neither a new source nor a new day resets the reservation.

## Closure and delivery

Close only when primary evidence establishes a negative/non-plague laboratory result,
no new event-linked cases throughout a justified observation window, and the last
relevant exposure date anchoring that window. Include evidence for all these fields.
The independent committee must support closure. The runner checks elapsed calendar
days, persists closed state, and returns [SILENT]. Closure is deliberately silent;
there is no exception to the trigger-only alert policy. Every later run exits before
scanning when the watch is closed.

Only the executable gate's stdout may become an alert. The collector cannot send one.
Hermes cron owns Slack delivery; do not call messaging tools. No trigger, failed checks,
unresolved review or closure means exactly [SILENT]. Operational failures remain local.
Alerts include criterion, dated new fact and primary links, member verdicts, synthesis
cautions, falsifier and stable fact ID. Maximum one alert per run.
