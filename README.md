# proximal

Durable, inspectable, cross-agent **provenance and desired-state for the host
`proximal`** — the workstation + home-lab node (`192.168.1.92` / tailnet
`100.85.100.81`). One repo per system, one directory per subsystem.

This is operational state, not a codebase. Its job is to remember — across runs and
across agents (claude, codex, gemini, opencode-local) — what each service on this box
looks like, what config it should run, and what was already tried and rejected. Live
box facts (hardware, ports, the LLM service) live in `~/CLAUDE.md`; this repo is the
versioned, auditable record of how the system is *configured and maintained*.

## Subsystems

Each top-level directory is one subsystem, self-contained with its own `README.md` /
`AGENTS.md`. Canonical config copies live here; the box runs installed copies (under
`/etc/…`, systemd units, etc.) — edit here, then re-install.

| dir | subsystem | what it tracks |
|---|---|---|
| [`postgres/`](postgres/) | PostgreSQL 17 (`:5432`) | GUC baseline/desired/known-bad, inventory snapshots, tuning reports, pg-repack maintenance, vendored best-practices skill |
| [`observability/`](observability/) | Prometheus + Grafana + exporters | node_exporter (host) + postgres_exporter (PG) + nvidia_gpu_exporter (RTX 3090) → Prometheus → Grafana dashboards; all systemd, tailnet-bound |
| [`cloudflared/`](cloudflared/) | Cloudflare Tunnel edge for `harm.org` | public hostname ingress to selected loopback services, including `plane.harm.org` -> Plane on `127.0.0.1:8190`; tunnel credentials stay root-only under `/etc/cloudflared` |
| [`harm-enterprises/`](harm-enterprises/) | `harm.org` static site | `harm-enterprises-site.service` serving `/home/halbritt/sites/harm-enterprises/public` on `127.0.0.1:18888`; Cloudflare routes `harm.org` / `www.harm.org`, and Tailscale Serve mirrors it on `:8890` |
| [`ollama/`](ollama/) | Ollama inference (`:11434`) | systemd unit + tuning drop-in, model inventory; secondary to the llama.cpp server (`:8081`) |
| [`striatum/`](striatum/) | `striatumd` workflow daemon | system unit (`User=halbritt`), `/run/striatum` runtime layout, shell/tailscale/warmtier glue; the 2026-06-19 user-unit→system-unit migration + revert source |
| [`praxis/`](praxis/) | `praxisd` executive-function daemon + connectors | systemd user units (`praxisd` + `praxis-slack` Socket Mode listener), peer-auth `praxis` DB, secret var-names (values in `~/.config/praxis/praxisd.env`, uncommitted), the said/inferred wall rationale |
| [`plane/`](plane/) | local/private Plane CE pilot | Docker Compose Plane CE `v1.3.1`, loopback-only proxy ports, Tailscale Serve `:10000`, systemd wrapper, MCP wrapper and non-secret API config posture |
| [`plane-public/`](plane-public/) | public-intended Plane CE for `plane.harm.org` | separate Plane CE `v1.3.1` stack, loopback proxy ports, system PostgreSQL, host Redis, Garage S3, Docker-bridge state proxies |

Planned siblings as they get captured: `llama/` (the `llama-27b.service` LLM
server), `garage/` (S3 service desired-state), `whisper/` (STT). Add a directory when a subsystem's
config is worth versioning; don't pre-create empty ones.

## The one rule

**Values and config, never credentials.** Commit settings, GUC values, unit files,
dashboards, and rationale. Never commit passwords, `.pgpass`, `pg_hba.conf`,
secret-bearing DSNs/connection strings, `*.env`, or keys. Secrets live only in
root-only files on the box (e.g. `/etc/default/*` at `0600`). The root
[`.gitignore`](.gitignore) catches the obvious cases; you enforce the rest.

## Conventions

- **One repo per host, one directory per subsystem.** System-wide concerns get their
  own top-level dir; per-instance state nests under the relevant subsystem.
- **Canonical-in-repo, installed-on-box.** The repo holds the source of truth; the box
  holds running copies. Each subsystem's README maps repo files → install paths.
- **Commit and push often.** This repo's value is its history — never end a turn with a
  dirty tree or unpushed commits (`origin` = `github.com/halbritt/proximal`).

Start at the subsystem you're working on. For agents, read [`AGENTS.md`](AGENTS.md).
