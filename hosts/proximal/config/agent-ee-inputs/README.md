# agent-ee retained runtime inputs

AGENTEE-622/624 owns the user store at `~/.local/share/agent-ee/native-inputs/runtime`.
`installation.json` records the installed local manifest identity and input provenance;
external receipt bytes and the full local manifest stay outside public Git. The K91
receipt copies preserve their original identities; the verifier is an independent
clean Git checkout with its own objects. Selection is explicit per run, and a later
clean verifier revision is recorded rather than constrained by installed digests.

The reviewed nightly configuration must set `AE_CI_INPUT_MANIFEST` to the recorded
manifest and `AE_CI_EVIDENCE_DIR` to a fresh per-attempt durable directory. Set
`AE_CI_OUTCOME_FILE` to a unique host-only journal path outside the writable
worktree. CI owns the unit/consumer configuration; the lead owns activation and
native admission. This installation record is not native or operational acceptance.

Run input snapshots and before-cleanup test artifacts survive job scratch cleanup.
Do not delete active/reviewed evidence during branch cleanup. Retention across
nightly history remains a lead-owned operational policy; no evidence GC is enabled here.
