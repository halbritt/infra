# maintenance/

Runnable ops artifacts for the proximal cluster. The repo holds the **canonical**
copies; the box runs installed copies (paths below). Edit here, then re-install.

## pg-repack-bloated — monthly heartbeat/chain-table bloat reclaim

`striatum_daemon`'s heartbeat/chain tables (`process_supervisor_pointers`,
`daemon_supervisors`, `process_supervisors`, `repo_event_chain_heads`) accumulate
physical bloat from constant `UPDATE` churn that outpaces in-page HOT reuse. Autovacuum
holds dead tuples ~0 but can't shrink the file; only `pg_repack`/`VACUUM FULL` reclaims it
(first done manually 2026-06-18 — see `../reports/REPACK_supervisor_tables_2026-06-18.md`).

This timer automates the periodic reclaim, **online and fail-safe**:
- `pg-repack-bloated.sh` repacks a listed table only if it exceeds `THRESHOLD_MB` (16 MB;
  healthy is ~2 MB). Uses `pg_repack --no-kill-backend` — if it can't get a clean lock it
  **skips and retries next month** rather than ever disrupting the daemon.
- Runs as `postgres` (superuser, peer auth) via a systemd timer, monthly at 13:00 UTC
  (~06:00 PDT, the verified low-activity window).

### Install / update on the box

```bash
sudo install -m 0755 maintenance/pg-repack-bloated.sh /usr/local/bin/pg-repack-bloated.sh
sudo install -m 0644 maintenance/pg-repack-bloated.service /etc/systemd/system/
sudo install -m 0644 maintenance/pg-repack-bloated.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pg-repack-bloated.timer
```

### Operate

```bash
systemctl list-timers pg-repack-bloated.timer     # next scheduled run
sudo systemctl start pg-repack-bloated.service    # run now (off-schedule)
journalctl -u pg-repack-bloated.service -n 50     # last run's log
```

Tunables live at the top of the script: `THRESHOLD_MB`, `WAIT_TIMEOUT`, the `TABLES` list
(deliberate — the job never auto-discovers). Adding a table means vetting it first, the way
the 2026-06-18 run did. Requires the `pg_repack` extension in `striatum_daemon` and the
`postgresql-17-repack` package.
