# PostgreSQL tuning plan — PROXIMAL_16_MAIN — 2026-06-16

**Author:** `CLAUDE_OPUS_4_8` · **Run type:** plan-only (no execution authority granted; nothing applied) ·
**Instrument:** `~/git/prompts/POSTGRES_TUNING.md` · **Provenance repo:** `proximal-pg`

This is the Proposal artifact for the read-only inventory captured 2026-06-16. No GUC
was changed. It proposes one reliability-neutral reload-class win, a restart-class
measurement-enablement step, and records the knobs that are honestly unmeasurable today.

## 1. Connection & provenance reference
- Cluster `16/main`, PostgreSQL 16.14, **`system_identifier 7628053153555146077`**.
- Snapshot: `inventory/2026-06-16/` (`pg_settings.tsv` — 343 rows; 24 non-default).
- Config checksums (sha256): `postgresql.conf` `a2a91ad2…ce35fe`; `postgresql.auto.conf`
  `0874e665…0c63ed` (empty — **no `ALTER SYSTEM` overrides applied to date**, so every
  revert below targets the captured value explicitly, never a blind `RESET` that could
  fall through to a different layer).
- Captured as `halbritt` (non-superuser, peer auth). Apply phase needs a superuser/
  `ALTER SYSTEM`-capable role — see §7.

## 2. Environment (redefines the knobs)
125 GiB RAM (92 GiB available, 76 GiB page cache at capture); i5-11400F, 12 threads;
Ubuntu 24.04.4 / kernel 6.8. **Storage: NVMe** (Samsung 990 PRO) — data dir + `pg_wal`
on the ext4 `/` LV with **~1019 GiB free (42% used)**. Extensions: `plpgsql`, `vector` 0.6.0.
`shared_buffers` 32 GB ≈ the whole ~40 GB working set; cache-hit 97–100%.

## 3. Topology, reliability frontier, durability
- **Standalone primary** (`pg_is_in_recovery()=false`; 0 replication slots, 0 WAL senders).
- **No reliability blocker:** archiver clean (`archive_mode=off`, 0 failed); `pg_wal` on a
  filesystem with ~1 TiB free vs `max_wal_size` 1 GB; max `relfrozenxid` age ~27.9 M ≪
  200 M `freeze_max_age`; autovacuum current (recent `last_autovacuum`, high
  `autovacuum_count`) on every churned table.
- **Durability: frozen, no waiver requested or needed.** `fsync=on`, `full_page_writes=on`,
  `synchronous_commit=on`, `wal_level=replica`. **No proposal below touches any of these.**
- **RTO/RPO: unspecified.** Working assumption (confirm): this is a single-node workstation
  where a crash-recovery time of a few minutes is acceptable. P1 below lengthens worst-case
  WAL replay; if a tight RTO exists, P1 must be re-sized against it.

## 4. Workload signal (instance/table-level only — `pg_stat_statements` NOT loaded)
- **Checkpoints are ~90% WAL-triggered:** `checkpoints_req=3402` vs `checkpoints_timed=390`
  over the 37.6 h since `stats_reset 2026-06-15 03:01` → **~1 checkpoint / 40 s**.
- **Background writer idle:** `buffers_clean=0`, `maxwritten_clean=0` while
  `buffers_backend≈4.09 M` rivals `buffers_checkpoint≈4.70 M` — backends evict their own
  dirty buffers; bgwriter contributes nothing.
- **WAL rate:** instantaneous sample 29 kB/s (a *quiet* window — not representative). The
  checkpoint cadence implies bursts filling the 1 GB budget every ~40 s (≈25 MB/s sustained
  during active periods, peaks higher). Precise sizing needs a busy-window measurement.
- Temp spills on `hippo` (6 files / 1845 MB, ~307 MB each > `work_mem` 256 MB). 19/100 client
  connections. `striatum_daemon`: 50 deadlocks + ~6% rollback rate — **application logic,
  out of scope** (handed off, not tuned here).

## 5. Proposal ledger

Ordered: reliability blockers (none) → low-risk reload-class win → restart-class enablement.
Columns: `id | parameter | current (value+source) | proposed | bottleneck + measurement | expected observable (confirm/refute) | headroom check | class | revert | risk`.

### Reload-class (context `sighup`/`superuser` → `pg_reload_conf()`, no restart)

**P1 — `max_wal_size`**
- current: `1 GB` (1024 MB), `configuration file` (`checkpoint_completion_target` already 0.9, `checkpoint_timeout` 300 s — both fine, unchanged).
- proposed: **`16 GB`**.
- bottleneck + measurement: 90% WAL-triggered checkpoints (`checkpoints_req 3402` vs `timed 390`, ~1/40 s). At ≈25 MB/s active, 1 GB fills in ~40 s ≪ the 300 s `checkpoint_timeout`, so checkpoints fire on WAL fill instead of on time. 16 GB holds ≈300 s of active WAL (and bursts), pushing most checkpoints to time-driven. **Compounding benefit:** fewer checkpoints → fewer post-checkpoint full-page images → less WAL → fewer requested checkpoints still.
- expected observable (confirm/refute): after a representative window, `checkpoints_req/checkpoints_timed` inverts toward time-driven; `buffers_backend` falls relative to `buffers_checkpoint`. Refute = ratio unchanged (WAL volume too high for 16 GB → re-measure busy-window rate and re-size).
- headroom: ~1019 GiB free; 16 GB WAL is 1.6% of free disk. Safe.
- class: **reload** (`sighup`).
- revert: `ALTER SYSTEM SET max_wal_size = '1GB'; SELECT pg_reload_conf();`
- risk: **larger crash-recovery WAL replay** (more WAL between checkpoints). Bounded by `checkpoint_timeout` (300 s) in practice; gated on the §3 RTO assumption.

**P2 — `wal_compression` (lower confidence; verify after P1)**
- current: `off` (default).
- proposed: **`on`** (consider only if P1 alone doesn't cut WAL volume enough).
- bottleneck + measurement: `full_page_writes=on` + frequent checkpoints ⇒ heavy full-page-image WAL. Compressing FPIs cuts WAL bytes → fewer requested checkpoints. Complementary to P1, which already reduces FPI count.
- expected observable: measured WAL bytes/checkpoint drop; CPU% per backend rises modestly. Refute = no WAL reduction, or CPU contention with the local LLM workload.
- headroom: CPU (12 threads) mostly idle outside LLM GPU work; acceptable.
- class: **reload** (`superuser`).
- revert: `ALTER SYSTEM RESET wal_compression; SELECT pg_reload_conf();` (prior source = default).
- risk: CPU overhead; reversible instantly.

**Deferred — bgwriter (`bgwriter_lru_maxpages` 100 / `bgwriter_delay` 200 ms / `bgwriter_lru_multiplier` 2, all default).**
`buffers_clean=0` is most likely *downstream* of checkpoint frequency (checkpoints flush
dirty buffers before the LRU scan matters). **Re-measure after P1**; only tune bgwriter if
`buffers_backend` is still high once checkpoints are time-driven. Verify-one-thing-at-a-time.

### Restart-class (context `postmaster` → maintenance window required) — measurement enablement

**R1 — `shared_preload_libraries`**
- current: `''` (empty) → `pg_stat_statements` **not loaded**.
- proposed: **`pg_stat_statements`**, then `CREATE EXTENSION pg_stat_statements;` (per-DB,
  in `postgres`/template1). Optional companions (reload-class once the library is loaded):
  `pg_stat_statements.max=10000`, `pg_stat_statements.track=top`.
- bottleneck + measurement: there is **no query-level signal today**; this blocks the three
  refusals in §6. Loading it is the prerequisite to lift them.
- expected observable: `pg_stat_statements` populates; top-N-by-total-exec-time becomes readable.
- headroom: ~few MB shared memory at `max=10000`; negligible per-statement overhead.
- class: **restart** (postmaster) — needs an explicit maintenance window; validate the config
  boots in a scratch instance first per the instrument.
- revert: `ALTER SYSTEM RESET shared_preload_libraries;` + restart (prior source = default).
- risk: low; the only restart-class item here — batch it with any future restart-class change.

## 6. Headroom math & honest refusals

Worst-case memory product (Preflight step 7):
`max_connections (100) × work_mem (256 MB) = 25.6 GB` for a *single* sort/hash node per
backend. Real queries have multiple sort/hash nodes; at, say, 3–4 nodes under peak
concurrency that is 77–102 GB, which against `RAM (125 GiB) − shared_buffers (32 GB) −
OS/page-cache reserve` does **not** provably stay within budget.

- `cannot-measure → refuse: work_mem` — peak concurrency and per-query node count are
  unmeasured (no `pg_stat_statements`; sampled a quiet 2-active window). Cannot prove the
  current 256 MB is safe *or* propose a change without falsely closing the calculation.
- `cannot-measure → refuse: random_page_cost` — NVMe storage suggests the default 4.0 is
  mis-costed (≈1.1 typical for SSD), but a planner-cost change requires `EXPLAIN` before/after
  on the top-N corpus to prove no high-traffic plan regresses, and there is no
  `pg_stat_statements` to identify that corpus.
- `cannot-measure → refuse: effective_io_concurrency` — `1` is low for NVMe (helps bitmap-heap
  prefetch), but the benefit needs bitmap-scan-heavy query evidence, unavailable until R1.

All three are unblocked by R1 + a busy-window re-inventory. That is the value of R1.

## 7. Operational prerequisite (not a GUC; gated on apply authority)
Inventory ran as non-superuser `halbritt`, which cannot read `data_directory`/`sourcefile`
(no `pg_read_all_settings`) nor run `ALTER SYSTEM`. Before the apply phase, create a
least-privileged monitoring role so future inventories are complete without superuser:
`CREATE ROLE pg_mon_ro LOGIN; GRANT pg_monitor TO pg_mon_ro;` (adds `pg_read_all_settings`,
`pg_read_all_stats`, `pg_stat_scan_tables`). The apply itself still needs a superuser or an
`ALTER SYSTEM`-granted role. This is a `CREATE ROLE`/`GRANT` (a DB write), not a GUC — out of
scope for this read-only run; listed so the next phase has it.

## 8. Checkpoint rule (stop condition)
Execution authority is **absent** and no reliability blocker fired → **stop after this plan.**
Apply order when authority is granted: (1) P1 reload + re-measure a representative window;
(2) decide P2 and bgwriter from that re-measurement; (3) batch R1 into a maintenance window,
then re-inventory with `pg_stat_statements` to lift the §6 refusals. Each change is verified
as a falsifiable hypothesis and paired with its revert before it is applied.
