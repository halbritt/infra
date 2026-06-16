# Known-bad settings ledger

Values tried on `proximal:5432` and reverted, with the evidence. The tuning
instrument reads this at preflight and must not re-propose a reverted value
without new evidence that overcomes the prior failure. Append a row whenever a
change is reverted (in the lab or in production).

| date | parameter | tried value | reverted to | why reverted | evidence |
|---|---|---|---|---|---|
| 2026-06-16 | `shared_preload_libraries` | set via `ALTER SYSTEM SET … = 'pg_stat_statements,pg_qualstats,pg_stat_kcache'` | same libs, but written to `postgresql.auto.conf` as the plain form `'pg_stat_statements,pg_qualstats,pg_stat_kcache'` | `ALTER SYSTEM` stored the comma-string as a **single double-quoted list element** (`'"a,b,c"'`); postmaster then tried to load one file literally named `a,b,c` → **`FATAL: could not access file "…"`**, server unbootable on restart | server log `2026-06-16 22:06:30 FATAL: could not access file "pg_stat_statements,pg_qualstats,pg_stat_kcache"`; fixed by `sed` on `auto.conf` + restart |

## Operational lessons (not value reverts)

- **Multi-value `shared_preload_libraries` (and other `GUC_LIST_QUOTE` params) via
  `ALTER SYSTEM` is unsafe.** A single comma-string literal is stored double-quoted as
  one element → unbootable. Set such lists by writing the plain comma form directly to
  `postgresql.auto.conf`/a conf file (scratch-boot-tested form), and **always be ready
  to hand-fix `auto.conf` + restart** if a restart-class change fails to boot. A
  fresh-`initdb` scratch boot test validates the *file* form but will NOT catch the
  `ALTER SYSTEM` mangling — test the actual `auto.conf` the server will read.
