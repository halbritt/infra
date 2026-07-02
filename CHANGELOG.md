# Changelog — proximal (system)

System-level and cross-subsystem changes to host **proximal**, newest first. Each
subsystem's `README.md` is its current-state reference; dense PostgreSQL cluster-config
history lives in [`postgres/CHANGELOG.md`](postgres/CHANGELOG.md). See `git log` for granular
history. **Values and config, never credentials.**

## 2026-07-02

### Reconciled local `halbritt/*` checkout `AGENTS.md` Plane routing
Swept local GitHub-origin checkouts under `/home/halbritt/git` whose `origin`
points at `github.com/halbritt/*` and reconciled their `AGENTS.md` files to the
local/private Plane workspace. Created missing minimal `AGENTS.md` files where a
local checkout had none, refreshed older marked Plane tracking blocks, and fixed
active Striatum/Genome-Core agent instructions that still named GitHub Issues as
the tracker. This was a local checkout reconciliation only; several repositories
were intentionally left unsynced or uncommitted because they already had unrelated
behind/ahead or dirty state.

Verification:

- every matching local checkout has an `AGENTS.md` with `Issue tracker: Plane`
- no matching local `AGENTS.md` still contains active `GitHub is the issue
  tracker`, `open GitHub issues`, or `file or update a GitHub issue` guidance
- `git diff --check -- AGENTS.md` passes for every matching local checkout

## 2026-06-30

### Captured the `harm.org` static site origin
Added a `harm-enterprises/` subsystem for the static site served at
`https://harm.org` and `https://www.harm.org`. Captured the root-owned systemd
unit, the loopback-only Python static server, install paths, Cloudflare ingress
relationship, and the Tailscale Serve mirror at
`https://proximal.tail0ecc2e.ts.net:8890/`. The origin remains
`127.0.0.1:18888`; Cloudflare routing stays in `cloudflared/`, and site content
continues to live under `/home/halbritt/sites/harm-enterprises/public`.

### Reconciled local Ollama residency with the primary MoE server
Confirmed proximal's system Ollama service is still needed as the local
`nomic-embed-text:latest` embedding endpoint for Hippo / striatum-warmtier ingest
on `127.0.0.1:11434`; it is not the primary chat/agent model path. Unloaded the
stale `qwen3:14b` Ollama runner that had been pulled in by sentiment work, then
warmed and verified `nomic-embed-text:latest` with a 768-dimension `/api/embed`
probe. Verified the intended coexistence state after cleanup:

- `llama-server` on `:8081` serves `qwen3.6-35b-a3b` at 262144 context, reported
  by `/v1/models` as 34,660,610,688 parameters, using ~20,190 MiB VRAM.
- Ollama `/api/ps` reports only `nomic-embed-text:latest` resident; `nvidia-smi`
  shows the Ollama process using ~490 MiB VRAM.
- `whisper-server` remains resident at ~1,004 MiB VRAM.
- `memory-price-tracker-ingest.service` is running with the peecee sentiment
  drop-in (`OLLAMA_HOST=http://peecee:11434`, `OLLAMA_MODEL=qwen3.6:27b`), so
  future sentiment ingest should not reload proximal `qwen3:14b`.

## 2026-06-29

### Upgraded system packages and installed sqlite3 CLI
Ran system package updates (`apt-get update` and `apt-get upgrade`) and installed
the `sqlite3` CLI tool on the host. Verified `sqlite3 --version` outputs 3.45.1.

### Wired local MCP/Praxis access for `plane.harm.org`
Documented the `plane.harm.org` local-agent access pattern: keep the public URL
as `https://plane.harm.org`, but send local MCP and Praxis runtime API calls to
`http://127.0.0.1:8190` through `PLANE_INTERNAL_BASE_URL` /
`PRAXIS_PLANE_INTERNAL_BASE_URL`. Created the `Praxis` project (`PRAXIS`) in the
`harm` workspace and recorded its non-secret project id
`978fcda1-c9c1-4437-b83a-5c3d6de0178e`. Token values remain only in mode-`0600`
files under `~/.config/plane/`.

### Enabled public Cloudflare Tunnel ingress for `plane.harm.org`
Added a `cloudflared/` subsystem for the existing `token-dashboard` Cloudflare
Tunnel and routed `plane.harm.org` to the second Plane instance on
`http://localhost:8190`. The Plane container proxy remains loopback-only on
`proximal`; public TLS and DNS terminate at Cloudflare Tunnel. Verified public
Plane API checks over `https://plane.harm.org`. Tunnel credentials remain only in
`/etc/cloudflared`, not in git.

### Added public-intended Plane stack for `plane.harm.org`
Added a separate `plane-public/` subsystem for a second Plane CE `v1.3.1`
instance intended for `plane.harm.org`, without reusing the local/private
`plane/` pilot's state. The new stack uses system PostgreSQL 17, host Redis, and
Garage S3 instead of bundled Compose Postgres/Redis/MinIO, while retaining bundled
RabbitMQ. Installed host `redis-server`; PostgreSQL, Redis, and Garage remain
loopback-only, and containers reach them through per-service Docker-bridge
`socat` units bound on `172.17.0.1`. Verified the local proxy/API checks on
`127.0.0.1:8190`. Secrets stay in the generated `plane.env` on the box, not in
git.

### Marked GitHub Issues deprecated in repo `AGENTS.md`
Updated the marked Plane tracking block so repo agents keep the GitHub repository
link but treat GitHub Issues as deprecated. New issue tracking, claims, reviews,
and issue-state changes should go through Plane work items. Reran the scaffold
against the 31 current `halbritt/*` repos with Plane projects: 30 remote
`AGENTS.md` files updated and `proximal` updated locally for this commit.
Verification fetched the 30 remote files through the GitHub API and confirmed
`GitHub Issues: deprecated` in each. Evidence:
`/tmp/plane-agents-github-issues-deprecated-rollout-2026-06-29.json` and
`/tmp/plane-agents-github-issues-deprecated-verify-2026-06-29.tsv`.

### Marked Plane as the issue tracker in repo `AGENTS.md`
Updated the marked Plane tracking block so every repo-backed Plane project says
plainly that its issue tracker is Plane in the local/private `Proximal` workspace.
Reran the scaffold against the 31 current `halbritt/*` repos with Plane projects:
29 remote `AGENTS.md` files updated, `memory-price-tracker` got a new `AGENTS.md`,
and `proximal` was updated locally for this commit. Verification fetched the 30
remote `AGENTS.md` files back through the GitHub API and confirmed the
`Issue tracker: Plane` line in each. Evidence:
`/tmp/plane-agents-issue-tracker-line-rollout-2026-06-29.json` and
`/tmp/plane-agents-issue-tracker-line-verify-2026-06-29.tsv`.

### Migrated open Striatum GitHub issues into Plane
Imported the 24 open `halbritt/striatum` GitHub issues into the local/private Plane
`Striatum` project (`STRIATUM`) as work items with stable `external_source=github`
and `external_id=halbritt/striatum#<number>` values. Mirrored the seven GitHub labels
currently present on open issues (`bug`, `enhancement`, `needs-triage`,
`ready-for-agent`, `ready-for-human`, `rfc-0091`, `security`) and preserved issue
bodies plus the 31 open-issue comments as description snapshots. GitHub was not
mutated or closed.

State mapping for the import: `ready-for-agent` -> `Ready`, `ready-for-human` ->
`Blocked` plus `authority-required`, everything else -> `Backlog`. Live result:
5 `Ready`, 6 `Blocked`, 13 `Backlog`. The idempotence check re-ran the importer and
reported 24 unchanged items. Evidence:
`/tmp/plane-striatum-gh-issue-migration-2026-06-29.json`,
`/tmp/plane-striatum-gh-issue-migration-idempotence-2026-06-29.json`, and
`/tmp/plane-striatum-work-items-after-migration-2026-06-29.json`.

## 2026-06-28

### Scaffolded Plane tracking for `halbritt/*` repos
Bulk scaffolded the local/private Plane workspace for all 66 GitHub repositories under
`halbritt/*`: one Plane project per repo, common agent workflow states/labels, and a
marked Plane tracking block in repo `AGENTS.md` where the repo had a default branch.
`proximal` and `praxis` were handled through local checkouts; `memory-price-tracker`
and `saltitall` had no default branch for remote `AGENTS.md` writes at rollout time.

Created the separate `Praxis Plane Connector Lab` project (`PXLAB`) for local Praxis
Plane connector development and wrote a dedicated token to the uncommitted pointer
`/home/halbritt/.config/plane/repos/praxis-pxlab.env` (`0600`). The token value was not
printed or committed. Praxis `AGENTS.md` now points at that file. Raised the local
Plane pilot's `API_KEY_RATE_LIMIT` to `600/minute` because the default `60/minute`
rate limit throttled the bulk local scaffold; this is local/private automation
posture, not public-service posture.

After owner review, deleted 35 stale/fork GitHub remotes from `halbritt/*` and deleted
their matching Plane projects by `external_id`; `export-chatgpt` was explicitly kept.
Plane now has 32 projects: the 31 remaining GitHub repositories plus `PXLAB`. Deletion
evidence is in `/tmp/halbritt-delete-results-2026-06-28T21-43-24Z.tsv` and
`/tmp/plane-project-delete-results-2026-06-28T22-15-37Z.tsv`; both contain only names,
project IDs, status, and HTTP result codes.

### Captured the local/private Plane CE pilot (`plane/`)
New subsystem for the local Plane Community Edition pilot on `proximal`, intended for
Striatum/meta-operator issue-tracker experiments and explicitly separate from any future
public `plane.harm.org` deployment. Live state verified before capture: Plane CE `v1.3.1`
running from `/home/halbritt/services/plane-selfhost`, proxy ports bound only to
`127.0.0.1:8090` and `127.0.0.1:8091`, Tailscale Serve `:10000` proxying to the loopback
HTTP port, and bundled Compose Postgres/Valkey/RabbitMQ/MinIO in use.

Captured only non-secret desired state: public URL/port values, the loopback proxy patch,
the stdio MCP wrapper, verification commands, and stop conditions. The real Plane env file
and MCP API token stay outside git (`plane.env` and
`~/.config/plane/proximal-mcp.env`, respectively). Added `plane-selfhost.service` as the
host lifecycle wrapper so the pilot is managed by systemd like other long-running local
infra while still running the official generated Docker Compose stack.

## 2026-06-24

### Captured the striatum worktree-GC timer (`striatum/`)
New root oneshot + 6h timer (`striatum-worktree-gc.{sh,service,timer}`) that periodically
reclaims terminal-run git worktrees and keeps `git gc` working on the `~/git/striatum`
checkout. Lanes run as `striatum-lane` and leave lane-owned files in each worktree and its
reflog; the operator-side daemon/`git` (both `halbritt`) then can't remove them, so worktrees
accumulated to 240 and `git gc --auto` was silently failing on `HEAD.lock` permission errors.
The timer runs the daemon-blessed `striatum worktree gc` (over the socket, refreshing the CLI
capability-token cache from the live runtime token so it survives boot-epoch rotation), then —
**only when zero runs are active** — `chown`s the worktree trees back to the operator and
re-sweeps, then `git gc --auto`. First run: 240 → 74 worktrees, clean `git gc`. Operational
backstop for [striatum#612](https://github.com/halbritt/striatum/issues/612) (retire when the
daemon-side ACL/staging fix lands). Canonical copies + file→install-path mapping in
[`striatum/README.md`](striatum/README.md).

## 2026-06-23

### Captured the intero sense-organ surfacing timers (`intero/`)
New subsystem dir for the two `--user` systemd timers that run the `showerthoughts`
coordination/intero blind-spot ledger: `intero-ledger.{service,timer}` (daily, 09:00 —
the existing surface) and `intero-drift.{service,timer}` (weekly, Mon 09:15 — new this
day, reads each repo's `.intero.json` `history` ring for actual-vs-declared cadence).
Both `Type=oneshot`, `Persistent=true`, output to the journal + a digest under
`~/.local/state/intero/`. Canonical copies + file→install-path mapping in
[`intero/README.md`](intero/README.md). Stateless, zero-GPU, no daemon; not a cloud
routine. Capturing them keeps the sense organ's own liveness auditable and
reimage-survivable.

## 2026-06-21

### Authored alerting rules for node / gpu / postgres / infra
Phase 2 of the alerting work (Phase 1 was the routing path, 2026-06-20). The exporters had
dashboards but no alerts; now they do — 18 proximal-authored rules under
`observability/prometheus/rules/{node,gpu,postgres,infra}-alerting.rules.yml`, routing to Slack
`#proximal-alerts` through the same Alertmanager pipe.
- **node** (7): filesystem low (<15%) / critical (<5%) space, low inodes, read-only fs, memory
  <10%, OOM kills, load >2.5×cores. Pseudo-filesystems excluded; read-only mounts excluded from
  the space alerts; load normalized by core count via `group_left`.
- **gpu** (3): high (>84°C) / critical (>90°C) temp, HW thermal throttling — fires per-GPU
  (proximal 3090 + peecee 3090 Ti). **No VRAM alert on purpose**: the local LLM pins ~22.8 GiB, so
  a VRAM-full rule would fire permanently; temperature + the driver thermal-slowdown flag are the
  honest hardware-risk signals.
- **postgres** (7): pg down, connections >80/90% of max_connections, deadlocks, long-running txn
  (>10m), XID wraparound warn/crit. Caught two metric quirks: wraparound is **XID age** not
  seconds (thresholds vs the 2³¹ limit), and the long-txn "oldest" series is a Unix **timestamp**
  so age = `time() - it`, guarded by `count>0` to avoid a stale-timestamp false fire.
- **infra** (1): `TargetDown` for any `up==0` (10m) across all jobs.
- **Verified**, not just installed: all 32 rule groups evaluate `health=ok`, nothing false-fires
  (thresholds sit clear of live readings), and every label-matching expr (`group_left`/`and`/
  `scalar`) was checked to return non-empty so no rule can silently never-fire. Both severity tiers
  already proven live end-to-end — `DoctorRed` (page) and `LivenessMarginCollapse` (warning) are
  routing to `#proximal-alerts` right now via the identical path.

## 2026-06-20

### Stood up Alertmanager → Slack alert routing
Closed the gap where alerting rules evaluated but went nowhere (`alerting.alertmanagers: []`).
Routing decided with the operator: every alert → one Slack channel `#proximal-alerts` via a
**dedicated** Slack app `proximal-alerts` (workspace gearheads), isolated from the praxis app.
- **Alertmanager** installed from apt (`prometheus-alertmanager 0.26.0`), same house pattern as
  the rest: ARGS in `/etc/default/prometheus-alertmanager` bind the tailnet IP
  `100.85.100.81:9093` (HA cluster listener disabled — single node, nothing on `:9094`), a
  `10-tailnet-bind.conf` drop-in orders it `After=tailscaled` + `network-online.target` with
  `Restart=on-failure`. Config `observability/alertmanager/alertmanager.yml` → `/etc/prometheus/`.
- **Routing:** one receiver, channel `#proximal-alerts`. The two striatumd severity tiers share
  the channel but differ in urgency — `page` (NecrosisRate/DoctorRed/SupervisorOriginFlood) waits
  10s and re-alerts hourly; `warning` batches 30s and re-alerts every 4h. An inhibit rule
  suppresses a `warning` when a `page` for the same alertname+instance is already firing.
- **Prometheus** wired: `alerting.alertmanagers` → `100.85.100.81:9093`; verified at
  `:9091/api/v1/alertmanagers` (active). Live `LivenessMarginCollapse` + `WedgeAgeTail` now reach
  AM (`:9093/api/v2/alerts`); AM attempts Slack delivery — proven end-to-end.
- **Secret:** the Slack incoming-webhook URL is the one credential — never in git. AM reads it from
  `/etc/alertmanager/slack_webhook_url` (0640 root:prometheus) via `slack_configs.api_url_file`;
  repo has `slack_webhook_url.template` + the app manifest (`proximal-alerts.slack-manifest.json`).
- **Live + verified.** Created the `proximal-alerts` app (`app_id A0BBJQQPGQ7`, workspace gearheads)
  via `apps.manifest.create` (`--data-urlencode manifest@…`), added an Incoming Webhook to
  `#proximal-alerts`, stored the URL in the file above. End-to-end verified 2026-06-20: a synthetic
  page alert plus the two live striatumd alerts delivered to the channel
  (`alertmanager_notifications_total{slack}` rising, `failed_total` flat), and both a silence
  (active → suppressed → expired → active) and a resolve round-trip succeeded.

### Wired the `striatumd` RFC 0137 exporter into Prometheus + Grafana
The local workflow daemon's lifecycle/liveness exporter (15 families, RFC 0137) is now scraped,
ruled, and dashboarded. Cross-subsystem (`observability/` + `striatum/`).
- **Pinned the scrape target.** `/metrics` rides the daemon's MCP/HTTP listener, which binds a
  **random port per boot** — no stable target. Fixed with
  `Environment=STRIATUM_DAEMON_MCP_HTTP_ADDR=127.0.0.1:9464` in `striatum/striatumd.service` (the
  default for the daemon's `-mcp-http-addr` flag). Loopback-only + tokenless (RFC 0137 §4):
  Prometheus runs on this host and scrapes `127.0.0.1:9464` directly, no TLS/bearer; **not**
  exposed to the tailnet.
- **Scrape job** `striatumd` → `127.0.0.1:9464` in `prometheus/prometheus.yml`; target `up`
  (now 5 targets: gpu×2/node/postgresql/prometheus/striatumd).
- **Rules** vendored verbatim from the striatum repo (`go/pkg/metrics/rules/`) into
  `prometheus/rules/striatum-{recording,alerting}.rules.yml` and installed to
  `/etc/prometheus/rules/`: 5 recording + 9 alerting rules, all `health=ok` via `promtool`. They
  **evaluate but are not routed** — no Alertmanager on this box yet (`alertmanagers: []`); firing
  alerts show at `:9091/alerts`.
- **Dashboard** `grafana/dashboards/striatum-proximal.json` (uid `striatum-proximal`, folder
  "proximal"), generated by `build_striatum_dashboard.py`; 27 panels mapping 1:1 to the §3
  taxonomy (necrosis/apoptosis spine, wedge/liveness forewarning, #417 supervisor flood, leases,
  exporter health). Verified live through Grafana's datasource proxy.
- **Incident (recovered):** the port-pin restart re-exec'd the committee-drifted on-disk
  `striatumd` (`202c1cc5`, `LatestDaemonDBVersion = 40`), which crash-looped against the
  migration-42 DB (`schema version 42 is newer than supported 40`) — the prior "any migration-40
  build runs clean" claim was wrong; that only held for the still-resident 42-capable process.
  Rebuilt from a clean worktree off `origin/main` (ceiling 42) and installed just the daemon
  binary (never `make install`, #509). See `striatum/README.md` (#503 / binary-drift).

### Captured the `praxis/` subsystem
New top-level subsystem for **Praxis** (the local-first executive-function daemon at
`~/git/praxis`). Captures the host integration — two systemd **user** units and the
secret handling — not the codebase.
- **Units:** `praxisd.service` (the daemon; Type=notify, 30s watchdog, `Restart=always`,
  peer-auth `praxis` DB) and the new `praxis-slack.service` (Type=simple Socket Mode
  listener — an outbound WebSocket to Slack, *no public ingress*; `Restart=on-failure`
  because a missing token is a deliberate fail-closed exit 78). Both `enabled`, lingering.
- **Connector went live:** RFC 0020 two-way Slack dialog, verified end-to-end on the box
  — inbound (@mention, DM, **and plain private-channel message**) → `inbox` dock →
  `praxisd` drain → capture (`actor=[]`, `locality=cloud`, **0 attestations** → stays
  behind the said/inferred wall, I1/I3) → egress-gated (I4) ack posted back to
  `#praxis-chat`. Slack app `praxis` (`U0BC0EN59DF`, `A0BBS89SPGB`), team `gearheads`.
- **Slack scopes (via App Manifest API + config token):** added `channels:history` /
  `message.channels` then `groups:history` / `message.groups` — `#praxis-chat` is a
  *private* channel, so `groups:*` is the load-bearing pair (cost two reinstalls; a scope
  change forces an OAuth re-consent, event changes apply live). See `praxis/README.md`.
- **Secrets:** by name only. Values live in `~/.config/praxis/praxisd.env` (`0600`,
  user-owned, outside git), loaded via `EnvironmentFile=-`. Load-bearing cred is the
  `xapp-` app-level token (`connections:write` + Socket Mode toggled on). The Postgres
  DSN is peer-auth (no password) → config, not credential.

## 2026-06-19

### Added NVIDIA GPU exporter to the observability stack
GPU monitoring for the **RTX 3090** (shared by the `llama.cpp` server `:8081` and `whisper-stt`).
- **Exporter:** `utkuozdemir/nvidia_gpu_exporter` **v1.4.1**, installed from the upstream `.deb`
  (not in apt). Chosen over NVIDIA's official **DCGM exporter** because it shells out to
  `nvidia-smi` and works on consumer GeForce cards — DCGM targets datacenter GPUs (many fields
  unsupported on GeForce) and runs a heavier `nv-hostengine` daemon. Driver `610.43.02`.
- **Bind:** the `.deb` unit listens on all interfaces `:9835`; a `10-tailnet-bind.conf` drop-in
  clears its `ExecStart` and re-points it at `100.85.100.81:9835` (tailnet only, no host firewall),
  ordered `After=tailscaled` + `network-online.target`, `Restart=on-failure` — matching the other
  exporters. Runs as the unprivileged `nvidia_gpu_exporter` user (querying `nvidia-smi` needs no root).
- **Prometheus:** new `gpu` scrape job → `100.85.100.81:9835`, target `up`, 93 `nvidia_smi_*`
  series (VRAM, util, temp, power, fan, clocks). VRAM read ~22.8/25.8 GiB (the LLM, as expected).
- **Grafana:** vendored dashboard **ID 14574** (the exporter author's own), pinned to datasource
  `prometheus-proximal` + `job=gpu`, provisioned as "NVIDIA GPU — proximal" (folder proximal).
  Regenerate with `observability/grafana/dashboards/fetch_gpu_dashboard.py`.
- Exporter logs a few `level=ERROR … unexpected characters` lines for exotic `power_smoothing.*`
  `nvidia-smi` fields — best-effort parse warnings, harmless; metrics still serve.

### Captured the `ollama/` subsystem
New top-level subsystem documenting the **secondary** local inference service (primary is the
`llama.cpp` server). Ollama `0.9.5`, loopback `:11434`, models `qwen3:14b` + `nomic-embed-text`
(~8.9 GiB on disk). Captured the stock `ollama.service` + the tuning drop-in (q8_0 KV cache,
context 32768, flash-attention, `KEEP_ALIVE=-1`); exposure left loopback-only, unchanged.

### Reorganized into one-system-one-repo: `proximal-pg` → `proximal`
The repo became the per-host provenance for the **whole** system: PostgreSQL demoted to a
`postgres/` subsystem, observability promoted from `maintenance/observability/` to a top-level
`observability/` sibling, new whole-system `README.md` + `AGENTS.md`. GitHub repo renamed
(old name redirects). Full detail in [`postgres/CHANGELOG.md`](postgres/CHANGELOG.md).
