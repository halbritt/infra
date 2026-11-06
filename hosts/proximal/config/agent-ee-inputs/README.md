# agent-ee retained runtime inputs

AGENTEE-622/624 owns the user store at `~/.local/share/agent-ee/native-inputs/runtime`.
`installation.json` records the installed local manifest identity and input provenance;
external receipt bytes and the full local manifest stay outside public Git. The K91
receipt copies preserve their original identities; the verifier is an independent
clean Git checkout with its own objects. Selection is explicit per run, and a later
clean verifier revision is recorded rather than constrained by installed digests.

The focused manifest in `installation.json` remains immutable for its recorded run.
The distinct `nightly-installation.json` records the separately provisioned module-scoped
`nightly-manifest.json`. Its three K91 variables apply only to
`test_routing_experiment_boundary`; `PCBSCHEMAGEN_ROOT` applies only to
`test_pcbschemagen_gate1` and `test_pcbschemagen_benchmark`. The consumer scan found
no additional test modules that require these inputs. Missing/incomplete inputs
become unavailable only for these modules; damaged/extra bytes or invalid policy
still refuse the whole preparation. The full manifests and captured bytes remain local.

The reviewed nightly configuration must set `AE_CI_INPUT_MANIFEST` to the exact
recorded nightly manifest and `AE_CI_EVIDENCE_DIR` to a fresh per-attempt durable directory. Set
`AE_CI_OUTCOME_FILE` to a unique host-only journal path outside the writable
worktree/Git directory, evidence directory and runner state (including scratch).
The outcome schema and complete/no-start identity contract are unchanged.
CI owns the unit/consumer configuration; the lead owns activation and
native admission. This installation record is not native or operational acceptance.

Run input snapshots and before-cleanup test artifacts survive job scratch cleanup.
Do not delete active/reviewed evidence during branch cleanup. Retention across
nightly history uses the lead's 2026-11-06 admission policy: before a new attempt,
CI refuses at at least seven retained runs or 20 GiB (21,474,836,480 bytes).
All states count. CI indexes attempt identities without double-counting references,
and counts regular-file sizes once per device/inode across nightly outputs, retained
worktrees and recorded scratch; links are not followed. Missing/corrupt accounting
is a visible failure rather than zero usage. One admitted finite run may cross the
threshold; its capture still completes, and the next attempt is held.

The dedicated history is `~/.local/share/agent-ee-full-suite/`, including
`runs/*/`, `retention-index.json` and `retention-check.json`. Kept scratch is
indexed by its authoritative runner path, normally `~/.cache/ae-ci-exec/tmp/run-*`;
other agents' unselected history is outside this accounting. A held admission
records counts/bytes (or unknown), reason and the lead reconciliation path, returns
service failure, and does not advance the baseline or last-tested SHA. The service
diagnostics are `Result`/`ExecMainStatus` and its journal; the CI owner implements
and tests these signals. No deletion, lossy compression, source-store GC, activation
or automatic unblocking is authorized by these records.
