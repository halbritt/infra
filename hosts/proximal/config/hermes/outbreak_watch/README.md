# Outbreak-watch evidence and delivery gate

The October 7 independent review found that the agent prompt could authorize an
alert without retrieved source passages, hash the same fact differently after a
new publication, and disagree with its own retry/closure rules. The owner requested
implementation of the recommendations. This runner owns the alert decision and
state; Hermes still scans the web, Relay still supplies independent review, and
the existing Hermes scheduler still delivers to the existing Slack thread.

## Operation

The job is a Hermes `no_agent` script. That means the scheduler returns its stdout
without a final model rewrite; the script itself runs a bounded Hermes collector.
The collector has only the `wigolo` toolset and receives policy plus the entire
fact registry. Its structured answer cannot directly produce a Slack message.
It gets 12 tool iterations and a 300-second run budget (330-second process deadline).

The runner fetches the candidate's 1–3 source URLs with Relay's grounding adapter.
It verifies each exact quote in a fetched page excerpt with retrieval time and
content hash. It then passes those fetched excerpts, the candidate, current policy
and the entire registry to all four configured Relay members. Each must affirm
source support, criterion support and novelty. Unresolved is not supported.
Missing members, failed synthesis or malformed verdicts remain pending. Refuted
or duplicate facts are suppressed. The synthesizer must say `APPROVE`; all its
cautions must be explicitly `NON_BLOCKING` and are included in the alert.

Routing, credentials, account failover, deadlines and call reservations come from
the installed Relay configuration. This runner raises only its input bundle limit
to 64,000 bytes so the entire registry and fetched passages fit; it never truncates
the registry to make a candidate appear novel. An oversized bundle fails closed.
The expected roster is fable/sol/agy/glm; a different roster requires a policy update.
No Council calls or Hermes core changes are involved.

`state.sqlite3` contains facts, their attached publication records, and unique alert
claims. Identity is a normalized subject/predicate/object proposition. URLs,
publication dates and criterion numbers are not identity. The panel must compare
aliases and meaning with all previous observations, including legacy suppressions.
Semantic matching remains a model judgment; the database guarantees one claim per
resolved identity, not that a hash understands equivalent language.

The process lock covers scan/review/claim. SQLite commits the unique alert claim
before the script emits stdout. A crash after that commit can lose an alert, but
never authorizes a retry. This deliberately favors the requester's acceptance of
false negatives. An unreviewed candidate is persisted before provider calls and
retried first next run; it does not match itself during novelty review. A cleared
retry ends the run before scanning. At most one alert is emitted per run.

Closure needs a negative/non-plague result and a complete, source-supported window
without new event-linked cases, anchored to the last relevant exposure. There is no
fixed ten-day assumption. The panel reviews the evidence and the runner checks
elapsed days. Closure is silent and terminal: later runs stop before scanning.

Errors exit nonzero and are recorded locally; the job retains `failure_deliver=local`.
No-trigger/partial-review/closed results are exactly `[SILENT]`. The cron scheduler's
existing silence handling and execution delivery fencing apply. The runner never
calls a Slack messaging API. Criteria amendment proposals remain in local scan
artifacts for operator review; fetched evidence supplies dynamic parameter values.

## Source and installed files

| Source | Installed location |
| --- | --- |
| `../outbreak_watch_job.py` | `~/.hermes/scripts/outbreak_watch_job.py` |
| `__init__.py`, `core.py`, `runtime.py` | `~/.hermes/scripts/outbreak_watch/` |
| `CRITERIA.md` | `~/.hermes/watchdogs/outbreak-watch/CRITERIA.md` |

`LEDGER.json` is preserved byte-for-byte and imported once. It is historical evidence,
not the current mutable ledger. State, original job/criteria backups, fetched evidence,
review results and installation receipts stay under `~/.hermes/watchdogs/outbreak-watch/`
and are not committed. Tests and the installer remain in the repository.

Run with the active Hermes interpreter and source checkout, replacing these variables
with the current launcher paths:

```sh
export PYTHONPATH="$PWD/hosts/proximal/config/hermes"
HERMES_SOURCE="$hermes_source" "$hermes_python" -m unittest outbreak_watch.test_watch outbreak_watch.test_host -v
"$hermes_python" -m outbreak_watch.install --home "$HOME/.hermes" --hermes-source "$hermes_source"
"$hermes_python" -m outbreak_watch.install --home "$HOME/.hermes" --hermes-source "$hermes_source" --apply
```

Install only after committing the canonical files. The installer refuses an active
job, uses the same process lock, saves the previous definition and files, initializes
state once, and changes only the existing job's runner fields. It preserves schedule,
destination, enabled state and next run. It uses Hermes's supported job-store updater;
the scheduler reads that definition on its next tick, so no gateway restart is needed.
Reinstallation refuses changes to managed installed files; reconcile them in source.

Rollback requires the same lock and the saved job/files. Do not delete/reinitialize
state or roll its claims backward: that could repeat an alert. Restoring the old
prompt-driven job removes the guarantees added here and should be an explicit operator
decision. If deployment fails, inspect the backup and receipt before another apply.

## Verification

The tests cover supported output, new facts after previous alerts, republished facts,
alias duplicates, fetched-text mismatch, snippets/partial fetches, malformed/unresolved
votes, partial panels, synthesis holds/cautions, pending retries, concurrent claims,
crash-after-claim behavior, missing state, legacy import, and silent terminal closure.
Hermes integration runs its real `run_job` script path in temporary homes: an alert
returns once, the next run is silent, and failures resolve to local delivery. The
installer integration preserves schedule and legacy state and rejects concurrent edits.
These deterministic tests substitute collection/review results, not production behavior.

Live verification used the installed Hermes collector against the real policy and
copied registry; it returned no new facts. A separate historical fixture fetched a
WHO original announcement, obtained four affirmative Relay opinions and an approving
synthesis. The first response exposed a too-small parser limit for valid detailed
reasoning; the limit was corrected and the saved response replayed through the actual
claim/output path. An earlier headline-only quotation correctly failed the body-excerpt
check. These tests had isolated databases and no Slack delivery. They do not establish
current outbreak facts, future provider availability, or infallible semantic judgments.

A subsequent live test ran the full grounding and four-member Relay panel inside
Hermes's actual cron subprocess with isolated state and local-only output. It
produced one approved historical-fixture alert; the next identical run returned
`[SILENT]`. The actual collector session used only Wigolo search/fetch and Hermes's
tool-call bridge. No test used the real Slack destination or production fact state.
A second live cron test supplied a primary passage unrelated to a proposed Irkutsk
claim. All four members refuted it, synthesis returned `HOLD`, the fact became
`suppressed`, and output stayed `[SILENT]`. The isolated database still held only
one alert claim from the positive fixture. Final checks: 24 watch tests, 42 repository
validator tests, infrastructure validation and Ruff passed.
