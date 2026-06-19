# migration provenance

`user-unit-pre-migration/` is a verbatim copy of the systemd **user** unit that
ran striatumd before the 2026-06-19 system-unit cutover:

- `striatumd.service` — the user unit (socket under `%t/striatum` = `/run/user/1000/striatum`)
- `striatumd.service.d/*.conf` — the six drop-ins (auto-spawn, blob, lane-sandbox,
  path, rfc0110-v3, web-repo) whose contents are now folded inline into
  `../striatumd.service`

Kept for provenance and as the exact source for the revert path documented in
[`../README.md`](../README.md). Do not install these as-is alongside the system
unit — running both a user and a system striatumd against the same Postgres would
double-bind the runtime sockets and fight over the same DB state.
