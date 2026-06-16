# Connection

How to reach the PostgreSQL instance on **proximal**. **No passwords here** — use
`~/.pgpass` or `PG*` environment variables for credentials.

| field | value |
|---|---|
| host | `localhost` (proximal; also LAN `192.168.1.92`, tailnet `100.85.100.81`) |
| port | `5432` |
| database | _TBD — confirm on first inventory run_ |
| roles | _TBD — prefer a read-only role for inventory_ |

A read-only role is preferred for the inventory/evidence-gate phase; the
apply phase needs a role that can run `ALTER SYSTEM` and `pg_reload_conf()`.
