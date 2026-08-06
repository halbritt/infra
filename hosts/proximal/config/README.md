# proximal host configuration

Durable, inspectable, cross-agent **provenance and desired-state for the host
`proximal`** — the workstation + home-lab node (`192.168.1.92` / tailnet
`100.85.100.81`). This is the host-specific `config/` partition of the
infrastructure repository: one directory per subsystem.

This is operational state, not a codebase. Its job is to remember — across runs and
across agents (claude, codex, gemini, opencode-local) — what each service on this box
looks like, what config it should run, and what was already tried and rejected. Live
box facts (hardware, ports, the LLM service) live in `~/CLAUDE.md`; this partition is the
versioned, auditable record of how the system is *configured and maintained*.

## Subsystems

Each directory beside this file is one subsystem, self-contained with its own `README.md` /
`AGENTS.md`. Canonical config copies live here; the box runs installed copies (under
`/etc/…`, systemd units, etc.) — edit here, then re-install.

| dir | subsystem | what it tracks |
|---|---|---|
| [`postgres/`](postgres/) | PostgreSQL 17 (`:5432`) | GUC baseline/desired/known-bad, inventory snapshots, tuning reports, pg-repack maintenance, vendored best-practices skill |
| [`observability/`](observability/) | Prometheus + Grafana + exporters | node_exporter (host) + postgres_exporter (PG) + nvidia_gpu_exporter (RTX 3090) → Prometheus → Grafana dashboards; all systemd, tailnet-bound |
| [`cloudflared/`](cloudflared/) | Cloudflare Tunnel edge for `harm.org` | public hostname ingress to selected loopback services, including `plane.harm.org` -> Plane on `127.0.0.1:8190`; tunnel credentials stay root-only under `/etc/cloudflared` |
| [`harm-enterprises/`](harm-enterprises/) | `harm.org` static site | **retired 2026-07-25** after moving to Cloudflare Pages; origin content and rollback unit remain preserved, public ingress was removed, and the `:8890` Tailscale Serve mirror was torn down 2026-07-29 |
| [`llama/`](llama/) | llama.cpp inference (`:8081`) | `llama-27b.service` + the live 35B-APEX drop-in override, revert-to-27B path; the box's primary LLM endpoint |
| [`ollama/`](ollama/) | Ollama inference (`:11434`) | systemd unit + tuning drop-in, model inventory; secondary to the llama.cpp server (`:8081`) |
| [`whisper/`](whisper/) | STT (`:8910` + shim `:8082`) | `whisper-stt.service` (whisper.cpp, GPU) + `praxis-stt-shim.service` and the shim script — Praxis's live loopback-only STT path |
| [`garage/`](garage/) | Garage S3 (`:3900-3904`) | `garage.service` + secret-free `garage.toml`, LUKS-backed storage chain (crypttab/fstab), token files referenced never stored |
| [`wezterm/`](wezterm/) | Headless WezTerm SSH multiplexer | pinned user-local mux binaries and server config, plus the matching cross-platform client profile for native persistent tabs |
| [`cellular/`](cellular/) | Quectel EC25-AF LTE modem + RedPocket AT&T line (510-520-4061) | attach-APN `RESELLER` fix + persistent NV state, ttyUSB/QMI access map, SMS verified two-way, voice blocked on IMS (firmware suspect), bring-up gotchas (RCS hijack, ttyUSB2 re-enum race) |
| [`cooling/`](cooling/) | Corsair Commander PRO fan/pump control | channel map (**fan4 = Alphacool loop pump — never throttle**; fan1–3 case fans), all-channels-100% policy, `corsair-cpro` hwmon + setconf tool pointers |
| [`striatum/`](striatum/) | `striatumd` workflow daemon — **RETIRED 2026-07-21** | system unit (`User=halbritt`), `/run/striatum` runtime layout, shell/tailscale/warmtier glue; kept as historical record + DB-reclaim path |
| [`striatum-next/`](striatum-next/) | striatum-next wake fleet (live) | user-scope `striatum-wake-*` liveness-floor timers for 7 graphs + `striatum-warmtier-autoingest`, verbatim unit/drop-in mirror; known fragilities ledger |
| [`praxis/`](praxis/) | `praxisd` executive-function daemon + connectors | systemd user units (`praxisd` + `praxis-slack` Socket Mode listener), peer-auth `praxis` DB, secret var-names (values in `~/.config/praxis/praxisd.env`, uncommitted), the said/inferred wall rationale |
| [`plane/`](plane/) | local/private Plane CE pilot | Docker Compose Plane CE `v1.3.1`, loopback-only proxy ports, Tailscale Serve `:10000`, systemd wrapper, MCP wrapper and non-secret API config posture |
| [`plane-public/`](plane-public/) | public-intended Plane CE for `plane.harm.org` | separate Plane CE `v1.3.1` stack, loopback proxy ports, system PostgreSQL, host Redis, Garage S3, Docker-bridge state proxies |
| [`caplab-runtime/`](caplab-runtime/) | standalone CAPLAB P4 host integration | fail-closed batch host bootstrap, expiring credentials, access disablement, and pre-effect empty rollback; no resident runtime |
| [`caplab-dashboard/`](caplab-dashboard/) | CAPLAB study-results dashboard | tailnet-only, read-only inspection surface for a historical Study 001 aggregate; exact committed app bytes from `books` in immutable releases, loopback `:3021` + Tailscale Serve HTTPS `:8784`; no mutation endpoint |
| [`caplab-p6/`](caplab-p6/) | CAPLAB P6 admission host surface | pinned CAPLAB source (`137d0724`) + forward migration 0003 into `caplab` PG, expiring writer/verifier Garage keys; independent PASS 2026-07-17, all roles now `NOLOGIN` / access revoked |
| [`caplab-p7/`](caplab-p7/) | CAPLAB P7 recomputation host surface | pinned read-only Study 001 recompute commit (`bf6de2b`), temporary `caplab_reader` expiring read-only access, expiry backstop timer; no live execution without separate CAPLAB authority |
| [`wigolo/`](wigolo/) | local-first web-research layer (MCP) | keyless `wigolo` MCP server (Tavily replacement) with synthesis wired to GLM 5.2 via OpenRouter (rewired from llama.cpp `:8081` 2026-07-21); pre-adoption security audit, install/config posture, opt-in-feature guardrails |
| [`hermes/`](hermes/) | Hermes Agent CLI + Slack gateway | `NousResearch/hermes-agent` `0.19.0` in a uv-managed private venv; wired to GLM 5.2 via OpenRouter with the local llama.cpp `:8081` path documented as the on-box alternate; Slack gateway live since 2026-08-04, other messaging platforms/Portal/STT not enabled |
| [`tailscale-index/`](tailscale-index/) | `tailscale.harm.org` landing page | the hand-maintained index of tailnet service URLs, its user unit, and a link sweep; served **directly from the checkout** (no installed copy) on `127.0.0.1:3912`, fronted by the tunnel |
| [`plant-praxis-bridge/`](plant-praxis-bridge/) | watering alerts → Praxis reminders | hourly user timer; reads plant soil moisture from the HA appliance's InfluxDB add-on, files a work item in the harm Plane `PRAXIS` project (→ Praxis via ADR-0014 sync) when a plant crosses its rewater threshold; no HA change, tokens stay on proximal |
| [`intero/`](intero/) | intero blind-spot ledger timers | two `--user` timers — daily `ledger.py` (blind-spot ranking) + weekly `--drift` read — printing per-repo `.intero.json` status; Layer 0 of the `showerthoughts` coordination spine; stateless, zero-GPU, never gates anything |
| [`systemd-user/`](systemd-user/) | systemd user manager config (`user@1000`) | env for every `--user` unit: PATH fix (`~/.local/bin` + `~/.npm-global/bin`, the stale-root-claude fix) + the striatum-next wake-unit `KillMode` drop-in (pattern superseded 2026-07-21, kept for record) |
| [`vitae-elicitation/`](vitae-elicitation/) | Vitae RFC 0007 elicitation interview | tailnet-only web interview mining the Principal's episodic memory into the `vitae` graph; defined in `~/git/vitae`, enacted here as a user unit on loopback `:8909` + Tailscale Serve; loopback-only bind enforced |

Agents using either Plane instance should load
[`../PLANE_AGENT_GUIDE.md`](../PLANE_AGENT_GUIDE.md) before reading or writing Plane data.

Add a directory here when a subsystem's config is worth versioning; do not
pre-create empty ones. Command examples that begin with `subsystem/path` assume
this directory as the working directory:

```sh
cd ~/git/infra/hosts/proximal/config
```

## The one rule

**Values and config, never credentials.** Commit settings, GUC values, unit files,
dashboards, and rationale. Never commit passwords, `.pgpass`, `pg_hba.conf`,
secret-bearing DSNs/connection strings, `*.env`, or keys. Secrets live only in
root-only files on the box (e.g. `/etc/default/*` at `0600`). The root
[`.gitignore`](../../../.gitignore) catches the obvious cases; you enforce the rest.

## Conventions

- **One infrastructure repo, one directory per host, one directory per subsystem.**
  Host-wide concerns get their own directory here; per-instance state nests under
  the relevant subsystem.
- **Canonical-in-repo, installed-on-box.** The repo holds the source of truth; the box
  holds running copies. Each subsystem's README maps repo files → install paths.
- **Commit and push often.** This repo's value is its history — never end a turn with a
  dirty tree or unpushed commits (`origin` = `github.com/halbritt/infra`).

Start at the subsystem you're working on. For agents, read
[`../AGENTS.md`](../AGENTS.md) and any nested subsystem instructions.
