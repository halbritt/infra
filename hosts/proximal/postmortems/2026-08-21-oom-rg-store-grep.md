# Postmortem — proximal OOM: runaway `rg` store-greps from agent harnesses

**Date:** 2026-08-21
**Updated:** 2026-08-23 (store composition, opencode backend, 2026-08-22 recurrence)
**Author:** hermes (Hermes Agent), at Principal request
**Severity:** host-wide memory exhaustion → repeated OOM kills (self-healing, no permanent damage)
**Status:** root-caused; two durable fixes outstanding (see [Plane `PROXIMAL-7`](#references) and "Follow-ups")

---

## Summary

`proximal` spent a ~24h window repeatedly invoking the OOM killer. Every kill
was a single process: `rg` (ripgrep), ballooning to **~84 GB anonymous RSS**
(`total-vm` 178–228 GB) before the kernel culled it. The `rg` processes were
spawned by two independent agent harnesses — **striatum-next execution backends**
and **CAPLAB's codex eval** — both grepping the entire content-addressed stores
on the box (`~/.local/share/striatum`, 349 GB → growing, plus `~/.cache`, 69 GB)
to *locate a blob by content hash*. 16 GB of swap saturated fully; free RAM
bottomed near 900 MB. The kills landed correctly on the disposable `rg` processes
(never on `llama-server`, postgres, or other residents), so nothing of value was
lost — but the failure was recurrent (it repeated 2026-08-22, see Timeline) and
will return until the two durables are fixed.

## What was observed

### Timeline (kernel log, `journalctl -k`)

- `18:34:24` — `driver.test` invokes the OOM killer; kills `rg` pid 125839
  (`anon-rss 84 574 388 KB`, `total-vm 178 418 480 KB`).
- `18:36:50` — postgres invokes the OOM killer; kills `rg` pid 132949
  (`anon-rss 84 902 432 KB`, `total-vm 228 724 528 KB`).
- Two further `rg` kills in the preceding 24h (pids 3914666, 3916533) — same
  signature. **4 total, all `rg`.**

### Recurrence (2026-08-22, ~21:18–21:20 UTC) — same signature, two more kills

- `21:18:10` — `opencode` invokes the OOM killer; kills `rg` pid 2480293
  (`anon-rss 80 738 876 KB`, `total-vm 102 860 812 KB`).
- `21:20:06` — `celery` (plane worker, in a docker scope) invokes the OOM killer;
  kills `rg` pid 2483129 (`anon-rss 77 559 392 KB`, `total-vm 103 047 376 KB`).

The `opencode` invoker is a striatum-next review backend firing the same
store-grep (see "Mitigations" — opencode is a third backend that evades the
`rg` cap). `celery` was a co-resident that happened to request memory with swap
already exhausted; the victim was again the disposable `rg`.

The "invoker" (`driver.test`, postgres) is just whoever asked for memory when
swap was exhausted; the *victim* — and the actual memory hog — was always `rg`.

### System state

- 125 GiB RAM; **swap 16/16 GiB saturated** (`vm.swappiness=60`).
- Free RAM oscillated: ~900 MB at kill-time → ~14 GB after reaping → 1.2 GB
  again by 19:30 (the pressure is cyclical, driven by re-dispatch).
- Memory PSI `avg300 ≈ 0.84` (full-stall path), high swap-in traffic (`si` spiking).
- Busiest residents: `striatum` driver (≈17.5 GB), `llama-server` (3.9 GB),
  token-dashboard ingest, ~15 `celery` (plane) workers, postgres, restic mid-run,
  several `claude` sessions.

## Root cause

### Cause A — striatum-next lanes re-grep the store (materialization is *fine*)

The striatum driver was actively compiling. Its execution backends
(`codex`/`claude-code`, and `opencode` — the latter fired the 2026-08-22 kills)
run an agent runtime inside a lane, and that agent shells out, e.g.:

```
codex-linux-sandbox --sandbox-policy-cwd <workspace> --apply-seccomp-then-exec \
  /bin/bash -c "rg -l --hidden '43f3d7e2…|887aa020…' \
                  /home/halbritt/.local/share/striatum /home/halbritt/.cache 2>/dev/null | head -100"
```

i.e. a full recursive `rg` over the **361 GB** of store+cache, searching for two
content hashes.

**This is not a materialization failure.** I verified the dispatch manifest
declares an exact materialized path per input (`inputs/00-…product-artifact`),
the blobs are actually written to `dispatch/<id>/inputs/` and copied into the
lane's `workspaces/<id>/work/inputs/`, and the sealed prompt explicitly says
*"not inlined; materialized at `inputs/…` — read it from there."* The lane already
has the blob at a known path. The agent greps anyway because:

1. the run-manifest hands it **bare `content_hash` strings** that are inert to the
   model — there is **no "open-by-hash" tool/affordance** in the lane surface; and
2. the exchange content-addressed store (`…/exchange/…/cas/`) is **empty** — the
   hash→blob primitive that should short-circuit the lookup was never populated.

So the model "resolves" a hash it already owns by brute-forcing the raw tree.

### Cause B — CAPLAB codex eval forces the grep by passing only a hash

A live CAPLAB eval (`codex exec -m gpt-5.6-sol`, cwd `~/git/caplab`) runs the
`REVIEW_PROMPT_V1_CHANGESET` contract (`src/caplab/advisory/calibrate.py`). That
prompt inlines the change-set's `files` but passes the object's `base` as **only
a bare `content_hash` — the base blob is never materialized into the sandbox**
(verified: `a2572d02…` exists nowhere as a file in the caplab workspace, only as
a hash field in the prompt and in `advisory/pool-runs/*/results.jsonl`).

The contract *itself* then obliges the model to go find the base:

> "Its ANCHORING IS INTACT … if the base it is anchored to is **absent**, the
> delivery is a free-standing tree"; "Its DECLARED METADATA MATCHES ITS CONTENT …
> any hash must equal what it actually describes."

Given only a hash string and no lookup primitive, a diligent agent must grep the
store to verify anchoring/hash integrity — **a guaranteed giant `rg` on every
change-set review**, replayed across many backends/models (agy-gemini, deepseek,
etc. per `advisory/pool-runs/`). This is a streaming, ongoing generator of the
same symptom, independent of the striatum lanes.

### Why `rg` reaches 84 GB

`rg -l` should stream in well under a gigabyte. ~84 GB *anonymous* RSS means an
invocation is reading a giant artifact into heap (or hitting a traversal/paging
pathology) while scanning the whole tree. Candidate large blobs on disk:
`driver-fold-v1.snapshot` (1.3 GB), `transcript-0` (1.1 GB), and multi-hundred-MB
sqlite state files under the harness config. Exact trigger per-kill not isolated;
the common factor is the full-store scan scope, not the file.

## What the "361 GB store" actually is (measured 2026-08-23)

The two grep roots are the striatum-next runtime directory plus the user cache —
not a single store, and only a sliver of it is content-addressed:

- `~/.local/share/striatum` — **349 GB** (was ~316 GB at incident time; grows with
  every dispatch)
  - `exchange/` **182 GB** — the compilation exchange. One exchange
    (`019f22ef-…`) holds 178 GB alone, of which `dispatch/` = **163 GB** (sealed
    dispatch manifests + per-lane inputs/artifacts/transcripts), `spool/` = 14 GB,
    `workspaces/` = 458 MB, and `cas/` = **4 KB (empty)** — the content-addressed
    store that should resolve hash→blob was never populated.
  - `harness-config/` **152 GB** — one HOME directory per backend agent runtime:
    `agy/` 144 GB (of which `.cache/go-build` = **137 GB**), `codex/` 4.5 GB,
    `claude-harm/` 1.2 GB, `claude-code/` 965 MB, `codex-harm/` 916 MB,
    `glm-zai/` 233 MB.
  - `graphs/` 12 GB, `fixtures/` 3.8 GB, `deploy-backups/` 1.4 GB.
- `~/.cache` — **69 GB** (was ~45 GB): `go-build/` = **65 GB**, `ms-playwright/`
  1.9 GB, `uv/` 875 MB, the rest < 300 MB each.

**~202 GB of the grep target is Go build cache** (137 GB in `agy`'s harness HOME
plus 65 GB in `~/.cache`) — compiled object files and cached test results that
can never contain a content hash, yet `rg -l --hidden` plows through all of it on
every hash lookup. Roughly half the bytes the OOM-ing scan reads are noise. The
directory that *would* make the lookup O(1) — `cas/` — is empty.

## Impact

- Recurrent, temporary host memory exhaustion and swap thrash.
- No permanent loss — the OOM killer correctly selected the disposable `rg`
  processes; long-running services (llama, postgres, garage, plane) survived.
- Compile/eval throughput degradation during each kill cycle (re-dispatch burn).
- Amplified risk: if a future `rg` fires during a deeper pressure trough, the
  killer may reach a *real* resident before the `rg` tops the anon-RSS list.

## What stayed working / corrective factors

- `vm.overcommit` + `oom_score_adj` defaults let the kernel cull `rg` first.
- striatum's materialization path proved sound under inspection — the fix is a
  *capability gap* (no hash→blob primitive), not a data-integrity bug.
- No credentials, secrets, or committed state were affected.

## Mitigations applied (and their known gaps)

**`rg` `--max-filesize=100M` via `RIPGREP_CONFIG_PATH`.** Applied 2026-08-21
(`~/conf/ripgreprc`, exported in `~/.bashrc` + `~/.profile`). Verified against
system `rg` 14.1.0 — `rg --debug` confirms the config is loaded and a 157 MB
file is skipped. This is a **partial mitigation only**:

- **claude-code is unaffected** — it uses a *built-in ripgrep* and has
  *removed support for custom ripgrep configuration* (its own changelog:
  "Use built-in ripgrep by default … Removed support for custom ripgrep
  configuration"), so it never reads `RIPGREP_CONFIG_PATH`.
- **codex is unaffected** — it ships a bundled `rg`
  (`…/@openai/codex-linux-x64/vendor/…/codex-path/rg`), prepends that `codex-path`
  to the sandbox `PATH` (so the sandbox `rg` resolves to the bundled musl binary,
  not `/usr/bin/rg`), and runs with a clean environment that does **not** carry
  `RIPGREP_CONFIG_PATH` (verified against the live process environ).
- **opencode is unaffected** — it bundles no ripgrep, so it shells out to the
  system `rg` on `PATH`, but its review lanes are launched with a *clean
  environment* that does not carry `RIPGREP_CONFIG_PATH` (verified against
  `/proc/<pid>/environ` of live opencode lanes on 2026-08-23). It was the invoker
  of the 2026-08-22 21:18 kill. Same net effect as claude-code/codex — the cap
  never reaches it — for a third, different reason (clean env, not a bundled
  binary).
- **The cap can mask the search target** — the blobs the agent greps for are the
  largest on disk (1.3 GB snapshot, 1.1 GB transcript); at `100M` those are
  skipped *silently*, so the agent gets "no match" instead of a resolved hash.
  That changes the failure mode (no giant read) but does not make the flawed
  lookup succeed, and may drive retries.

Net: the cap is worth keeping for interactive/system `rg` use, but it does **not**
reach either OOMing backend (claude-code *or* codex), and it does not replace the
two durable fixes below.

## Follow-ups (durable fixes)

1. **CAPLAB:** materialize the `base` blob into the eval sandbox ahead of
   `REVIEW_PROMPT_V1_CHANGESET` (or provide a hash→file resolve step), so the
   anchoring check never requires a raw store grep.
2. **striatum-next:** give each lane a content-address lookup ("open by hash")
   that resolves `content_hash` → the already-materialized `inputs/` path, and/or
   populate the empty `cas/` store; remove bare-hash prompts that encourage
   re-grepping.

Either is owned by its respective repo; infra's role here is the incident record
+ the host observation. See Plane `Infra` issue for tracking.

## References

- Kernel log: `journalctl -k --since '24 hours ago' | grep 'Out of memory'`.
- Store composition (2026-08-23): `du -sh ~/.local/share/striatum/{exchange,harness-config,graphs,fixtures,deploy-backups}` +
  `du -sh ~/.local/share/striatum/harness-config/*/` and `~/.cache/*`.
- striatum exchange: `~/.local/share/striatum/exchange/019f22ef-…/` (`dispatch/`,
  `workspaces/`, empty `cas/`).
- CAPLAB change-set review contract: `~/git/caplab/src/caplab/advisory/calibrate.py`
  (`REVIEW_PROMPT_V1_CHANGESET`, `profile_for_artifact`).
- Prior codex failure audit: `~/git/caplab/CAPLAB_FAILURE_MODE_AUDIT_CODEX_2026-07-16.md`.
- Plane tracking: `Infra` project (`PROXIMAL`), issue `PROXIMAL-7`.