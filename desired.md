# Desired-state config

The canonical GUC set `proximal:5432` should run, as `ALTER SYSTEM` statements.
The live config converges to this; drift from it is a finding. Every line carries
a rationale and points at the report that justified it.

> Empty until the first reviewed change lands. Do not add a line here without a
> verification record under `reports/` and a matching pre-written revert.

```sql
-- ALTER SYSTEM SET <param> = '<value>';  -- rationale; reports/<file>
```

## Frozen — never weakened without a recorded waiver

`fsync`, `full_page_writes`, `synchronous_commit` (on a primary), `wal_level`.
