# Changelog — proximal (system)

System-level and cross-subsystem changes to host **proximal**, newest first. Each
subsystem's `README.md` is its current-state reference; dense PostgreSQL cluster-config
history lives in [`config/postgres/CHANGELOG.md`](config/postgres/CHANGELOG.md). See `git log` for granular
history. **Values and config, never credentials.**

## 2026-08-20

### llama: Q5_K_M → UD-Q4_K_M, context 65536 → 131072

The Council `qwen-chair` turn on the long `quartermaster` topic renders ~85k tokens of input
and failed every dispatch against the 65536 slot. The [`llama-27b`](config/llama/) override now
serves `Qwen3.8-27B-UD-Q4_K_M.gguf` (~15.3 GiB) at 131072 context — the smaller quant pays for
the doubled q8_0 KV within the fail-closed `--fit off` residency policy (~21.6 GiB of 24 GiB
resident, MTP draft retained). Validated by a successful ~90k-token chair turn the same day;
long-context throughput not yet re-benchmarked. Prior config saved on-box as
`override.pre-q4km-ctx-20260820`.

## 2026-08-18

### Qwen3.8 serving now fails closed instead of spilling onto CPU

The Council chair workload exposed a severe throughput failure in the primary
[`llama-27b`](config/llama/) endpoint. With 196608 context and llama.cpp's default automatic
fitting, generation measured 8.317 tokens/s (about 7.6 tokens/s over a later long run), prompt
processing measured 13.870 tokens/s, and the process combined about 21.1 GiB of GPU residency
with another 6.57 GiB mapped on the host and about 4.9 GiB swapped.

After unloading the competing whisper.cpp and Ollama GPU residents and reducing context to
65536, generation reached 63.957 tokens/s. A confirming launch with the exact intended flags,
`-c 65536 -ngl all -ngld all --fit off`, reached 64.181 generation tokens/s and 137.200 prompt
tokens/s, accepted 35/42 MTP draft tokens, and used 22.676 GiB of GPU memory.

The canonical Qwen3.8 drop-in now records that exact configuration. Both the main-model and MTP
draft layers are pinned to the RTX 3090, and automatic fitting is disabled. GPU contention will
therefore surface as a load failure instead of silently degrading into CPU offload. The service
remains single-slot (`-np 1`); callers needing more than 65536 context must choose a smaller
model/KV representation or explicitly benchmark another configuration.

## 2026-08-12

### plant-praxis-bridge timer went silent at the 2026-08-07 reboot — moved to OnCalendar

Watering alerts stopped for 5 days. The
[`plant-praxis-bridge`](config/plant-praxis-bridge/) timer last triggered
`2026-08-07 18:05:02`, ~48min before the `18:52:50` reboot, and never fired
again — while still reporting `enabled` and `active`, which is why nothing
looked wrong.

Cause: the unit had only monotonic triggers, `OnBootSec=10min` +
`OnUnitActiveSec=1h`. After the reboot both evaluated as already-past
(`next_elapse=0`), so the timer went straight to `SubState=elapsed`, and
`OnUnitActiveSec=` had no in-session service activation to count forward from —
leaving `NextElapseUSecMonotonic=infinity`, i.e. enabled, active, and never
going to run again. `Persistent=true` was already set but is a no-op here: it
only applies to `OnCalendar=` triggers.

Fix: `OnCalendar=hourly` (keeping `RandomizedDelaySec=5min` and
`Persistent=true`). Wall-clock re-arming is reboot-proof, and `Persistent=` now
actually catches up a run missed during downtime. Verified: timer re-armed to a
real `NEXT`, and the catch-up run filed the alert that had been stuck behind the
outage — `PRAXIS-17`, Ficus Audrey soil sensor dark 134h (silent since
`2026-08-07 02:14Z`, a separate battery/sensor fault to chase).

Not a Grafana fault: the `plant-moisture` dashboard has no alert rules and never
did — it is visualization only, and its "red <30%" panel title is a gauge
display threshold, not an alert.

### HA watering automation re-enabled as a redundant channel

Reversed the 2026-07-23 "Praxis is the sole watering channel" decision: a
channel that can go silent for 5 days without anyone noticing has not earned
sole custody. `automation.plant_drying_rate_has_slowed` on the appliance is back
on, with the previously-missing Dracaena Michiko trigger added and
`initial_state` corrected to `true`. Duplicate alerts are deliberate; retire the
HA side again only once the bridge has demonstrably survived a reboot. Details
in the [appliance CHANGELOG](../../devices/home-assistant-fernside/CHANGELOG.md);
the two-channel threshold-sync contract is documented in
[`config/plant-praxis-bridge/`](config/plant-praxis-bridge/).

Note the coverage asymmetry: the HA side sees THIRSTY only. Staleness (DARK)
detection exists solely in the bridge, because a dead sensor never crosses a
numeric threshold.

### plant-praxis-bridge: an already-alerted dry plant logged nothing

Found while diagnosing the above. `file_item()` returns early once the dedup
flag is set, and the THIRSTY branch had no log call of its own — so a plant that
was dry *and* already alerted produced no output at all. Dracaena Lisa sat at
~2% for 9 days and was absent from every single run's logs; the driest plant on
the box was the least visible one. The THIRSTY branch now logs its state every
run, including how long it has been dry and the value it re-arms above.

## 2026-08-06

### wigolo synthesis switched to native gemini-3.6-flash (free tier)

Acting on the re-benchmark below: rewired the [`wigolo`](config/wigolo/) MCP
registration from GLM 5.2/OpenRouter to the native `gemini` provider with
`gemini-3.6-flash` — the round's best reports at both depths, leak-free, and
free-tier cost. The blocking caveat dissolved on inspection: ai-newsroom no
longer calls Gemini (its "gemini" grep hits are topic keywords and subreddit
names in `newsroom/sources/`), so the `GEMINI_API_KEY` in
`~/.config/ai-newsroom/env` is a leftover and wigolo is now effectively its
only consumer. Deliberately staying on the free tier — wigolo is low-volume;
watch billing to confirm it never charges. Canonical block updated in
[`config/wigolo/mcp-config.json`](config/wigolo/mcp-config.json); GLM 5.2
rollback block preserved in git history (`d3167f0`).

### wigolo synthesis re-benchmark: GLM 5.2 holds; DeepSeek V4 Flash unfit; Gemini leak gone

Re-ran the [`wigolo`](config/wigolo/) synthesis-model benchmark (8 headless
`research --json` runs, standard + comprehensive) against two challengers:
`deepseek/deepseek-v4-flash-0731` (~1/10 GLM 5.2's OpenRouter price) and
`gemini-3.6-flash` (both via OpenRouter and via the native gemini provider on
the ai-newsroom `GEMINI_API_KEY`).

Findings: DeepSeek is disqualified structurally — at the default `standard`
depth its reasoning starves wigolo's `reportChars/3` output cap to
`empty content in response` (template fallback), and at `comprehensive` its
51.7s synthesis rides within 14% of the hardcoded 60s timeout. Native
gemini-3.6-flash produced the best reports of the round and the July
thinking-leak did **not** reproduce, making it a viable challenger at
free-tier cost, but it would couple wigolo to the ai-newsroom key's rate
limits. Gemini via OpenRouter is 3× GLM's cost and wrote the weakest reports.
GLM 5.2 stayed solid at `standard` but truncated mid-sentence at
`comprehensive` this round. **Wiring unchanged: GLM 5.2 via OpenRouter.**
Full table in [`config/wigolo/README.md`](config/wigolo/README.md).

### Removed the idle local Qwen sentiment fallback

Traced the resident Ollama `qwen3:14b` runner to the
`memory-price-tracker-ingest.service` fallback chain. It had no active caller
and no generation request after the August 2 fallback run, but
`OLLAMA_KEEP_ALIVE=-1` retained it at about 2,990 MiB of GPU memory.

The canonical production chain is now peecee `qwen3.6:27b`, then proximal's
already-resident llama.cpp server, then the tracker's deterministic degraded
mode. The optional local Ollama fallback remains supported by application code
but is no longer configured in production. OpenRouter was not added: the
tracker has no current integration, and this change requires no credential.

Installed the versioned production drop-in, restarted only the ingest watcher,
and confirmed its effective environment no longer contains
`OLLAMA_FALLBACK_HOST` or `OLLAMA_FALLBACK_MODEL`. After `ollama stop
qwen3:14b`, Ollama reported only `nomic-embed-text:latest` resident and GPU free
memory increased from 1,463 MiB to 4,458 MiB. The ingest watcher returned to
active/running state with its 86,400-second schedule.

## 2026-08-05

### Host state moved into the fleet layout

The repository changed from a single-host root to a fleet structure. All 27
`proximal` subsystem directories moved intact to `hosts/proximal/config/`; this
host changelog, agent instructions, and Plane guide moved to
`hosts/proximal/`. Git moves preserve the existing content and commit graph.

Added a machine manifest, host notes, reusable `developer` / `linux` / `server`
roles, a shared configuration layer, SOPS/age migration policy, a documented
history-preserving import process, and lightweight manifest/reference
validation. The generic WezTerm mux server profile moved to
`shared/editor/wezterm/server.lua`; its pinned binary, client profile, and host
installer remain under `proximal`.

The pre-existing Windows `nvidia_gpu_exporter` configuration for `peecee` was
the one machine-owned exception nested inside `proximal` observability. It now
lives under `hosts/peecee/config/nvidia-gpu-exporter/`; `proximal` retains the
Prometheus scrape job, alert rules, and dashboards that consume it. The Windows
host was not changed or reverified during this repository-only reassignment.

Three installed units execute code directly from this checkout. Their canonical
and installed paths were updated together: `quectel-sms-gateway.service`,
`tailscale-index.service`, and `plant-praxis-bridge.service`. The SMS gateway and
tailnet index restarted active; the plant bridge timer remained active. The
tailnet index loopback origin returned successfully after the move. No secret
value or service configuration value changed.

Verification after the move: fleet validation passed for two hosts, four roles,
and the shared WezTerm reference; all 272 baseline tracked paths had an explicit
destination; 46 CAPLAB unit tests passed with the existing opt-in PostgreSQL
integration test skipped; Python, JSON, TOML, YAML, XML, shell, Prometheus,
Alertmanager, Cloudflared, and affected systemd syntax checks passed. The public
tailnet index sweep returned only expected 200/302 responses.

## 2026-08-04

### Root-FS pressure relieved; unused models archived to `/nvr/models-archive/` → `llama/`
A filesystem-full alert fired on root (`/` at 89%, 1.6T/1.8T). Cleaned up ~220G of
re-downloadable caches (`~/.cache/huggingface`, `uv`, `go-build`, pypoetry, pip, playwright),
and moved **all unused model quants + the raw bf16 build source (~305G)** from `~/models/` to
the spinning disk at **`/nvr/models-archive/`** (8.8T free). Root dropped to ~60% (712G free).

Only the two files actually in service remain in `~/models/`: the served `APEX-I-Compact.gguf`
and the `Striatum-FT/` symlink → the loaded LoRA adapter. Archive location and the restore path
documented in [`llama/README.md`](config/llama/README.md). Service verified: `llama-27b` active, `/health`
ok. (See `git log` for the move itself; the `~/.cache` clear was ephemeral cache, not versioned.)

### Hermes connects to Slack as its own Agent-mode bot → `hermes/`
Hermes joined Slack for the first time, as a dedicated **"hermes" app** in the
`gearheads` workspace (truckchat.slack.com, member `U0BMCL982NP`, bot
`B0BND7XHWFJ`) — separate from the `openclaw` app, so no Socket Mode conflict.
The Hermes messaging gateway was installed as a user systemd service
(`hermes gateway install`, linger on, `GATEWAY_ALLOW_ALL_USERS=true` + open
DM/group policy mirroring OpenClaw).

Running with DEBUG logs surfaced **two independent root causes** that both had
to be fixed before a DM round-tripped:
1. **The Slack app must carry the full manifest scopes + event subscriptions,
   in Agent mode.** The app was initially installed with only
   `chat:write`+`channels:history`, so DMs silently never reached the box
   (Socket Mode connected fine via the xapp token, but no `message.im` events).
   Fixed by reapplying `hermes slack manifest --name "Hermes"` (Agent mode by
   default) at Features → App Manifest and reinstalling.
2. **The gateway needs `OPENROUTER_API_KEY` in `~/.hermes/.env`, not just
   `~/.profile`.** systemd never sources a shell profile, so the LLM call failed
   with "OpenRouter credential pool has no usable entries" and the bot replied
   "Sorry, I encountered an unexpected error." Fixed by adding the key to
   `~/.hermes/.env` and restarting the gateway.

Verified round-trip: DM → `assistant_thread` event → Slack-origin session
(`platform=slack`) → `run_agent` via openrouter/deepseek-v4-flash-0731 →
reply posted to the Slack thread. DEBUG `-vv` reverted to default logging.
Full runbook + both root causes: `hermes/SLACK_ONBOARDING.md`.

## 2026-07-31

### Praxis systemd recovery no longer latches or rolls back transient failures → `praxis/`
The canonical and installed user units now disable the finite start-rate window
for the always-on daemon. A watchdog or dependency crash remains under
`Restart=always` instead of leaving Praxis failed after the default five-start
budget. The desired-state set now also includes `praxis-rollback.service`.
Its application-repo handler classifies the failed unit before acting: only the
guarded boot contract (`Result=exit-code`, `ExecMainStatus=78`) can move the
checkout; watchdog and ordinary runtime failures preserve the release. Status
78 is excluded from ordinary restart so the rollback handler is its sole
recovery owner and a loop-guard refusal cannot restart-spin.

## 2026-07-29

### Praxis SMS moved to the Quectel EC25; Android gateway deprecated → `cellular/`
The EC25 line (510-520-4061) is now **Praxis's exclusive SMS carrier**. New
`quectel-sms-gateway.service` (system unit, `User=halbritt` + dialout, loopback
`:8852`): owns the single-consumer AT port, re-speaks the capcom6 local-mode HTTP
contract (so praxis's carrier changed by env swap only — `PRAXIS_ANDROID_SMS_URL` →
`127.0.0.1:8852`), sends SMS-SUBMIT PDUs in UCS2 with concat UDH (emoji + long praxis
copy survive; verified 3-segment loopback with astral emoji), sweeps inbound in PDU
mode (GSM7+UCS2 decode, concat reassembly), and POSTs the `sms:received` webhook to
praxis's listener on `127.0.0.1:8850` — deleting from modem storage only after a
successful idempotent dock. SMS bytes now leave the box only over the radio itself.
Deprecated: the Moto G capcom6 gateway (unreachable/asleep at cutover; its webhook
target — the tailscale-serve `:8851` front — is removed, so the stale registration is
inert; unregister or uninstall when the phone wakes). Migration announced to the owner
by SMS from the new line. Praxis-side docs updated (praxis `12ba7a3`, docs-only).

### Praxis: register-full black-hole + watchdog starvation fixed → `praxis/`
Same-day follow-up to the entry below — both bugs it filed are now fixed and live
(praxisd on `0e167b4`, 06:48Z). **PRAXIS-24:** a due ⏰ now pages the owner even at
register cap — with an honest "stays parked" note — and the commitment takes a slot
silently when one frees; at-most-once rides the delivery ledger's existing attempt rows
(no new event kind — a new kind would crash a rolled-back release at boot).
**PRAXIS-25:** the Android SMS gateway gets a 3 s transport timeout
(`PRAXIS_ANDROID_SMS_TIMEOUT_SECONDS`) and the night-shift follow-through loop a 10 s
shared egress budget (`PRAXIS_FOLLOWTHROUGH_EGRESS_BUDGET_SECONDS`) — worst-case
blocking egress per tick is now well under the 30 s watchdog. Deploy lesson recorded:
the `praxis-release-prev` rollback tag had leaked to origin, so the cutover's
`git fetch --tags` failed with "would clobber existing tag" once the local tag moved —
the remote copy is deleted; that tag is local operational state and must never be pushed.

### Praxis: SMS is now the default ⏰ reminder outlet → `praxis/`
Owner directive: fired reminders now page the owner's SMS (the Android gateway carrier,
RFC 0019 v2) regardless of which connector the directive arrived on; acks and proposals
stay origin-routed. Praxis PRAXIS-23, deployed as `de9352b` via the release pipeline —
which took three attempts, all environmental: the preflight canary ran the *old* tree's
script pre-cutover (its `:8848` EADDRINUSE fix had to be hand-bootstrapped into the live
tree — a standing gotcha for any deploy-pipeline fix), and the live-smoke ⏰ fire gate
cannot pass while the owner's active register is at cap (7/7 today), now degraded loudly
instead of auto-rolling-back. Two praxis product bugs filed en route: **PRAXIS-24** (due
reminders black-hole silently when the register is full — they will not fire until a slot
frees) and **PRAXIS-25** (the 03:00Z watchdog double-SIGABRT + spurious auto-rollback of
master: sequential 10 s carrier POSTs to the sleeping phone gateway starve the 30 s
watchdog inside one tick). Also of note: praxisd had been silently running the rolled-back
prior ref since 03:00Z; this deploy returned it to master.

### Quectel EC25-AF + RedPocket AT&T line brought up → `cellular/`
A Quectel EC25-AF (USB `2c7c:0125`) with a freshly activated RedPocket AT&T-network SIM
(line **510-520-4061**, IMEI `865493045248656`) was brought from "registration denied" to
**working data + two-way SMS** over 2026-07-28/29. The root cause of the ~1.5 h attach
failure was the **LTE attach APN**: the AT&T MBN profile defaults PDP context 1 to
`broadband` (postpaid), which AT&T rejects for MVNO subscriptions —
`AT+CGDCONT=1,"IPV4V6","RESELLER"` registered the modem within 20 s. Secondary fixes:
cleared pre-activation FPLMN blacklist entries off the SIM (313-100, 312-680), enabled MBN
AutoSel, force-enabled IMS. Data verified end-to-end from the modem's own stack (QPING 4/4,
DNS); SMS verified both directions, with the documented caveat that inbound rides SMSC
retries and can lag minutes.

Two expensive red herrings are recorded in the subsystem README so they aren't re-chased:
the Moto G used for a SIM test kept its **RCS registration** after the SIM came out, so
inbound tests "showed delivered" while going to the phone over Wi-Fi; and RedPocket's
"plan expires tomorrow, make a payment" texts turned out to be mid-activation automation
noise (plan is annual, renews 2027-07-28). **Still open: voice.** IMS registration never
completes (bearer + P-CSCF granted, SIP registration stalls) and AT&T has no CSFB, so
calls fail instantly; prime suspect is the 2021-era `EC25AFFDR07A10M4G` firmware, with the
discriminating phone-voice-test and the Quectel-forum firmware request as the two next
moves. New subsystem dir [`cellular/`](config/cellular/) holds identifiers, desired NV state,
bring-up gotchas (including the `/dev/ttyUSB2` re-enumeration race that can wedge the AT
port), and a quick-reference for AT/QMI access.

### Tailnet landing page folded in → `tailscale-index/`, BinKeeper cards repaired
`tailscale.harm.org` had been serving from `~/git/tailscale-index`, a directory that was
**not a git repo** — no owner, no history, no link check. Consequence: all three BinKeeper
cards pointed at `https://…:8765/bin-photo/…` and returned 404. BinKeeper had left Engram's
port for its own service (`binkeeper.service`, `127.0.0.1:8766`) during the `BINK-11` /
`BINK-13` authority cutover, and mounts its authoring app at **root**, not `/bin-photo/`.
Repointed to `:8766/` (photograph + label), `:8766/register`, `:8766/bins/` — all `200` over
tailnet HTTPS. The move was weeks old; it surfaced only when someone tried to photograph a bin.

Fixed the class, not the instance. The page, `server.py`, the user unit, and a new
`bin/check-links.sh` now live in [`tailscale-index/`](config/tailscale-index/). Deliberate deviation
from **canonical-in-repo / installed-on-box**: `tailscale-index.service` was repointed
(`WorkingDirectory` + `TAILSCALE_INDEX_SITE_DIR` + `ExecStart`) at the checkout, so the file
the browser gets *is* the file in git — **one copy, no drift**. That split exists to give
root-owned `/etc/…` files a versioned source; it buys nothing for halbritt-owned files under
`~/git`, and a second copy is exactly the failure being fixed. `server.py` serves
`Cache-Control: no-cache`, so an edit is live on the next request. Verified after cutover:
unit active/enabled from the new path, origin on `127.0.0.1:3912`, `https://tailscale.harm.org/`
`200` and byte-identical to `site/index.html`.

The link sweep found **two more dead cards**, both serve-mapping-outlives-origin: Striatum Web
UI `:9443` and Harm Site Mirror `:8890` (502 — `striatumd` retired 7/21, `harm-enterprises`
stopped 7/25). Both **removed on the owner's call** later the same day, and recorded in the
subsystem README's "Removed cards" table so either is restorable if its subsystem is rolled
back. **The two serve mappings were then torn down** on the owner's call
(`sudo tailscale serve --https=<port> off`), so the ports no longer answer at all rather than
completing TLS and 502ing — `serve status` 22 → 20 mappings, both verified refusing
connections. The exact restore commands were captured from the live config first and written
into each subsystem's rollback path (`striatum/`, `harm-enterprises/`), since recreating a
serve mapping is part of reviving those services.

Also added a **BinKeeper: Sort a Stash** card (`:8766/stash`) — a live surface that had never
been listed despite getting its own operator tab in BinKeeper `6ee3001`. The page is now 14
cards with `check-links.sh` exiting `0`, the first time it has been all-green.

Supersedes `observability/tailscale-index-card.patch`, the workaround that recorded index
edits as an unapplied `.patch` because there was nowhere to version the real page. Kept for
history; the old `~/git/tailscale-index` is kept on disk with a MOVED banner and a rollback
path. Nothing deleted.

## 2026-07-28

### Hermes Agent installed as a third local agent harness → `hermes/`
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent) `0.19.0`
(upstream `30526baa`), installed via the official `install.sh` after reading it rather than
piping it blind. It lands in `~/.hermes/` (~2.0 GB) with a **uv-managed private Python 3.11
venv** — the one agent tool here that doesn't follow the box's global-npm convention,
because upstream ships it as a Python package with a bundled node/TUI side-car. Not under
systemd: interactive CLI, nothing resident, nothing listening, and `~/.local/bin` was already
on `PATH` so no shell rc was touched. Only system-level change was **ffmpeg** via apt
(the installer's one `sudo` need; `uv`, node 24, and ripgrep were already present and reused).

It was installed to make a real comparison possible: it had been floated as a candidate for a
**pre-dispatch triage agent** that must run local, against `claw` and roll-our-own. What it
brings that `opencode`/`openclaw` don't is the closed learning loop — autonomous skill
creation, self-improving skills, FTS5 cross-session recall.

**Wired to GLM 5.2 via OpenRouter** (`z-ai/glm-5.2`, 1M ctx, $0.769/M in / $2.42/M out),
reusing the `OPENROUTER_API_KEY` already exported from `~/.profile` — the key is deliberately
*not* copied into `~/.hermes/.env`, so rotation stays single-source. This re-applies a
conclusion already benchmarked for [`wigolo/`](config/wigolo/README.md) on 2026-07-21: OpenRouter
returns GLM's reasoning in a *separate* field, so `content` is always clean prose, whereas a
local reasoning model's thinking tokens compete with the answer inside a fixed budget — which
matters for a harness running up to 500 turns with compression at 50% of context.
**The local path was verified working first and is documented as a first-class alternate**
(`provider: custom` + `base_url http://localhost:8081/v1` + `qwen3.6-35b-a3b`), so a
nothing-leaves-the-box configuration is proven rather than assumed.

Verified: `hermes -z` → `hermes-ok` on the local endpoint; tool-call test on local
(`uname -r` → `6.8.0-124-generic`) and on GLM 5.2 (`hostname` → `glm-ok proximal`);
`hermes doctor` clean on provider + `✓ OpenRouter API`, 16 toolsets, 70 bundled skills.

⚠️⚠️ **Data-egress trap found while documenting the local-alternate path:** `--provider custom`
with `model.base_url` unset does **not** error — it silently resolves through to **OpenRouter**
(`explicit → $CUSTOM_BASE_URL → config → $OPENROUTER_BASE_URL → OPENROUTER_BASE_URL`) and bills
for it, while reading to the operator as on-box and free. Caught by checking
`journalctl -u llama-27b` instead of trusting the reply: the answer came back fine and the local
server had served **zero** requests. Per-invocation local runs must set
`CUSTOM_BASE_URL=http://localhost:8081/v1`; anything that genuinely must not leave the box
should set `model.base_url` in config rather than rely on the flag.

⚠️ **Two further upstream gotchas recorded as known-bad.** (1) `provider: "llamacpp"` is **rejected**
even though `config.yaml`'s own template comment claims `ollama`/`vllm`/`llamacpp` alias to
`custom` — doc/code drift; use `custom`. (2) `hermes config set` **reserializes the config
from resolved values**, collapsing the shipped 1622-line / 85 KB annotated reference into a
158-line / 5 KB bare dump: values survive, all inline option documentation does not. The
pristine template is kept on-box at `~/.hermes/config.yaml.orig`.

Deliberately **not** enabled: the messaging **gateway** (would put an externally-reachable
message path in front of an agent with `--yolo`-capable shell access, and Praxis already
provides a reviewed Slack path), **Nous Portal** (second inference subscription, redundant
with OpenRouter), and Hermes's **own Whisper** (`stt.local.model: base` would load a second
STT model onto a 3090 already shared by `llama-27b` and `whisper-stt` — point it at the
existing `:8910`/`:8082` path instead).

## 2026-07-25

### harm.org migrated off this host to Cloudflare Pages
The site is now an Astro build with Sveltia CMS, hosted on Cloudflare Pages from
[`halbritt/harm-org`](https://github.com/halbritt/harm-org) — a private repo whose
`main` branch auto-deploys, so publishing in the CMS *is* the deploy. `proximal` no
longer serves it. What changed here: the `harm.org` / `www.harm.org` ingress rules were
removed from **both** cloudflared configs (parity rule below), and
`harm-enterprises-site.service` was stopped and **disabled**. Nothing was deleted —
content root, unit, and `serve.py` remain on disk, and
[`harm-enterprises/README.md`](config/harm-enterprises/README.md) carries the rollback.

⚠️ **DNS gotcha worth remembering:** `*.harm.org` used to CNAME to the apex, and
`plane.harm.org` has **no explicit DNS record** — it resolved purely through that
wildcard. Pointing `harm.org` at Pages would therefore have dragged Plane onto Pages
and broken it. The wildcard was repointed at the tunnel *first*, then the apex moved.
Leave `*.harm.org` on the tunnel.

Verified after cutover: `harm_org=200` / `www_harm_org=200` served by Pages (Astro
generator tag present, the old origin's `X-Robots-Tag: noindex` gone);
`plane_public=200`, `plane_unauth=401`, `tokens`/`dram`/`tailscale` all `200`; zero
listeners on `127.0.0.1:18888`. Also on the account: Worker `harm-org-cms-auth` on
`auth.harm.org` (GitHub OAuth proxy for the CMS) and Pages project `harm-org`.
Cloudflare API token + account id live in `~/.config/cloudflare/harm-org.env` (0600).

### cloudflared: stale user-scope config resynced, parity rule recorded
A `harm.org` hosting walkthrough surfaced a latent footgun: `~/.cloudflared/config.yml`
— left over from the original `cloudflared tunnel login` — still carried only the
`tokens` and `dram` rules from June, missing `harm.org`, `www.harm.org`,
`plane.harm.org`, and `tailscale.harm.org`. Live traffic was never at risk (the unit's
`ExecStart` passes `--config /etc/cloudflared/config.yml` explicitly), but an ad-hoc
`cloudflared tunnel run` as `halbritt` would have silently dropped the site and Plane to
the catch-all `404`. Resynced the user-scope ingress to match `/etc` verbatim — only
`credentials-file` differs, and must, since the `/etc` credential is `root:root 0400`
while a user-scope run needs the `halbritt`-readable copy. Vendored it as
[`cloudflared/config.user.yml`](config/cloudflared/config.user.yml) so the drift is now visible to
the repo, and added a parity `diff` to the subsystem's Verify block. No restart — the
running tunnel does not read this file, and was left untouched (up since 2026-07-24).
Verified: both configs `validate OK`, parity diff empty, `harm.org`/`www.harm.org`/
`plane` public `200`, `plane` unauth `401`.

## 2026-07-21

### striatum-next wake fleet: fragilities fixed, drop-ins consolidated
Three fixes, verified live (all 7 wake services now show `KillMode=process` + the
openrouter `EnvironmentFile`, zero `/tmp` ExecStarts):
1. **hippo `/tmp` binary** — one drive fired from `~/git/striatum-next/bin/striatum`
   self-projected the current-generation unit with the durable path (ExecStart is
   self-referential: `wakeCommand` → `os.Executable()`, so unit-file edits are futile —
   the running binary's path is what persists); stale legacy short pair removed,
   scratchpad binary preserved as `~/.local/bin/striatum.bak-hippo-scratchpad-jul12`.
2. **Dead drop-ins** — the `striatum-wake-<repoid8>.service.d/` dirs never applied to
   long-named units (mid-token truncation ≠ dash-boundary prefix), so 4/7 graphs ran
   without KillMode/env. Replaced with one shared truncated-prefix
   `striatum-wake-.service.d/` covering the whole fleet; per-repoid8 dirs and 4 orphaned
   `timer.d` dirs deleted. `systemd-user/README.md` corrected.
3. Still open (recorded): 019f22ef/019f274c exec `~/.local/bin/striatum` vs the rest
   `~/git/striatum-next/bin/striatum` — two durable build channels, converge later.

### New subsystem: `striatum-next/` — wake-fleet unit specs captured
Vendored the live user-scope specs verbatim (33 files): 7 `striatum-wake-*` liveness-floor
service+timer pairs (striatum-next, praxis, engram, fleet-knowledge, vitae, gpu-fleet,
hippo) with their `KillMode`/openrouter drop-ins, plus `striatum-warmtier-autoingest` and
its corpus-bridge drop-in. Prompted by today's incident — nothing recorded that these
belong to a live system distinct from the retired striatumd. Capture surfaced real
fragilities (recorded in [`striatum-next/README.md`](config/striatum-next/README.md)): the hippo
wake unit execs a binary from a **Claude session scratchpad in /tmp** (dies on reboot),
two units lack the `KillMode=process` override, mixed build channels across the fleet.

### Striatum retired — daemon and all support units shut down
On the Principal's instruction, stopped + disabled `striatumd.service` and its system-scope
support timers: `striatum-lane-cred-resync.timer`, `striatum-worktree-gc.timer`,
`pg-repack-bloated.timer`. Port `:39201` closed, zero `striatumd_rw` backends.
**Correction (same day):** the user-scope `striatum-wake-*.timer` (×7) and
`striatum-warmtier-autoingest.timer` were swept up by the `striatum*` name match but belong
to **striatum-next** (separate, live) — restored enabled+active within the hour; each repo's
liveness floor fires at most one interval late.
Removed the `striatumd` Prometheus scrape job and the two striatum rule files from
`observability/prometheus/` (repo + `/etc/prometheus`, promtool-validated, reloaded — 7/7
remaining targets up) so the dead target can't page. **Not** destroyed: unit files, binary,
secrets, the 29 GB `striatum_daemon` DB, and the still-running `token-dashboard*` services.
Full retirement record + DB-reclaim path: [`striatum/README.md`](config/striatum/README.md).

### Linked observability surfaces on the tailnet index
Verified the [`observability`](config/observability/) recording still matches live (all 8 Prometheus
targets `up` — gpu×2/gpu-fleet/node/postgresql/prometheus/striatumd/llama — 0 rule errors,
`pg_up 1`) and added **Grafana / Prometheus / Alertmanager** cards to the tailnet landing page
`tailscale.harm.org` (`~/git/tailscale-index/site/index.html`). These three bind the tailnet IP
directly (not `tailscale serve`), so their links are plain `http://proximal.tail0ecc2e.ts.net:{3003,9091,9093}/`.
The index dir is not a git repo, so the added cards are recorded as
`observability/tailscale-index-card.patch` (mirroring the caplab-dashboard convention) and
documented in the observability README's new "Tailnet index" section.

### wigolo synthesis switched to GLM 5.2 (OpenRouter)
Benchmarked research-synthesis quality across models and rewired [`wigolo`](config/wigolo/) from
the local 35B MoE to **GLM 5.2** (`z-ai/glm-5.2`) via OpenRouter, using the OpenAI-compatible
path (`WIGOLO_LLM_PROVIDER=openai` + `OPENAI_BASE_URL=https://openrouter.ai/api/v1`; key =
`OPENROUTER_API_KEY` from `~/.config/striatum/openrouter.env`). Root-cause finding: wigolo
caps synthesis at `reportChars/3` tokens with no headroom for model "thinking", so every
reasoning model is starved — the local 35B collapses to wigolo's heuristic template on large
source sets, and Gemini 3.x flash leaks its thinking scratchpad into the report (Gemini 2.5
is also gated for our key). GLM 5.2 wins because OpenRouter returns reasoning in a separate
field, so wigolo only ever sees clean final content: full, well-cited reports at
`depth:"comprehensive"`, terse-but-correct at `standard`, ~1–2¢/call. The 35B stays the
box's default `:8081` model (chosen for throughput); this change affects wigolo only. Qwen
27B (peecee) benchmark still pending. Key currently rides the MCP env block (plaintext in
user-local `~/.claude-harm/.claude.json`, uncommitted) — wigolo's encrypted keystore is
interactive-only. Also noted: `wigolo research` CLI can hang on process exit — wrap headless
calls in `timeout`.

## 2026-07-20

### Added wigolo web-research subsystem (Tavily replacement)
Adopted [`wigolo`](config/wigolo/) `0.2.1` — a keyless, local-first web-intelligence MCP
server (search/fetch/crawl/extract/research/agent) — as the box's web-research layer
for local agent work, replacing reliance on Tavily/generic hosted research services.
Cloned and security-audited before adoption (static review of the public repo, source
commit `180ac3d`): clean — no install-time code execution, no prompt injection in its
own instructions, no phone-home, single-registry deps, sound credential handling, real
SSRF guards. Full write-up gisted (linked from the subsystem README). Installed globally
(`~/.npm-global/bin/wigolo`, no postinstall); `wigolo warmup` pulled the chromium engine +
core search bootstrap into `~/.wigolo/`. Synthesis (`research`/`agent`) wired to the local
llama.cpp server (`:8081`, model `qwen3.6-35b-a3b`) via `WIGOLO_LLM_PROVIDER` — base URL
without `/v1` (wigolo appends it) — so the whole path is local + $0/query; smoke-tested
keyless search and local-LLM cited synthesis both green. Registered as a Claude Code MCP
server at user scope; canonical block for other clients in `wigolo/mcp-config.json`.
Guardrail recorded: stay on the default `core` backend — `WIGOLO_SEARCH=searxng` pulls an
unpinned tarball + `pip install` (the audit's only real supply-chain weakness).

## 2026-07-15

### Added WezTerm thumbwheel scrollback bindings
Mapped horizontal mouse-wheel events in the canonical WezTerm client profile to
three-line vertical scrollback movement. This makes a mouse side wheel useful in
terminal panes while preserving the normal vertical-wheel bindings. Raised the
scrollbar thumb's contrast and minimum height so the enabled scrollbar is visible
against the default dark terminal background. Restored Claude Code's classic TUI
renderer on the host so interactive Claude output populates WezTerm's native
scrollback instead of an alternate screen buffer with application-owned history.

### Added pinned WezTerm SSH-mux desired state
Added [`wezterm/`](config/wezterm/) for the headless WezTerm multiplexer used to carry
persistent native tabs between macOS and Windows clients. Pinned the host's
user-local Ubuntu 24.04 x86_64 install to
`20260715-174104-3658b656`, recorded the mutable nightly asset's SHA-256, added
an idempotent no-root installer, and captured both the server config and matching
cross-platform client profile. Automatic client updates are disabled so a client
cannot silently outrun the server's mux protocol.

The live Mac/client and `proximal` server were installed at the same version.
Verification terminated and relaunched the Mac GUI while the remote mux PID and
PTY remained unchanged, then reimported the pane successfully. This establishes
session persistence across GUI loss; the original external-display wake rendering
incident still needs repeated sleep/wake observation in WezTerm before it can be
called resolved.

### Added the standalone CAPLAB P4 host desired state

Added [`caplab-runtime/`](config/caplab-runtime/) for the bounded, model-free CAPLAB
P4 synthetic round trip: a fail-closed host CLI, non-secret runtime config,
standalone-source pin, and a one-shot systemd expiry backstop. The tool keeps
PostgreSQL peer roles disabled until three campaign-scoped Garage credentials
are contained in role-owned files, records an irreversible pre-write boundary,
captures fixed store inventories around the idempotency conflict, and permits
bootstrap removal only after independent zero-state checks. The runtime is
pinned to reviewed standalone commit
`405efb136b221d1270578417c64b3f7878383f32`; regular-file blobs are read from
that Git tree into a hash-named virtual environment and verified against a
commit-bound host manifest.

The initial desired-state commit made no live change. The later authorized P4
execution installed the surface, completed one synthetic register, replay,
conflict refusal, retrieval, reconciliation, and cleanup-plan round trip, then
disabled all campaign access. It intentionally preserves the synthetic object,
independent copy, append-only metadata, cleanup plan, and lifecycle evidence;
it does not claim recovery fitness, purge correctness, or CAPLAB acceptance.

## 2026-07-07

### Captured the striatum garden token-refresh units
Vendored the systemd user units behind striatum-next's Vertex Model Garden
backends into [`striatum/`](config/striatum/): `striatum-garden-cred-refresh.{service,timer}`
(30-min rewrite of `~/.config/striatum/garden.env` with a short-lived Vertex
OAuth token, minted by impersonating the `striatum-garden` service account — no
key files) and the `garden-env.conf` drop-in installed on every
`striatum-wake-*.service` so autonomous drives see the credential. The refresh
script and the cloud-side rationale live in the new
[halbritt/gcp](https://github.com/halbritt/gcp) repo (the GCP-account
provenance repo, registered as a striatum-next fleet subject the same day).
Secrets file itself (`garden.env`) is never vendored.

### Added a shared Plane agent guide
Added [`PLANE_AGENT_GUIDE.md`](PLANE_AGENT_GUIDE.md) as an instance-neutral guide
for agents working with Plane from this host. It summarizes Plane's workspace,
project, work item, state, label, cycle, module, view, page, intake, MCP, and REST
model; records the local/private `plane` versus public-intended `plane-harm`
boundary; and documents safe import, verification, and destructive-operation
rules. Linked the guide from both Plane subsystem READMEs. The guide cites
official Plane docs and records only pointer paths and non-secret endpoint shapes.

## 2026-07-04

### Applied host package updates
Ran host software maintenance on Ubuntu 24.04.4: refreshed apt metadata, applied
the available non-held apt upgrades, reloaded systemd after package unit-file
changes, and refreshed snaps. Apt upgraded `iproute2`, `docker-compose-plugin`,
`gh`, `google-cloud-cli`, and `google-cloud-cli-anthoscli`; snap refreshed
`mesa-2404` to `25.0.7-snap211`.

Left the standing Kubernetes/PostgreSQL apt holds in place, and did not override
Ubuntu's phased `fwupd` rollout. `apt-get check` passed, all snaps reported up to
date, `striatumd`, `llama-27b`, Docker, and PostgreSQL were active, and
`localhost:8081/health` returned `{"status":"ok"}`. `nvidia-smi` remained healthy
on the RTX 3090 with driver `610.43.02`. The host still has a reboot-required
flag for `linux-image-6.8.0-134-generic` and `linux-base`, which was already
present before this maintenance run.

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
[`striatum/README.md`](config/striatum/README.md).

## 2026-06-23

### Captured the intero sense-organ surfacing timers (`intero/`)
New subsystem dir for the two `--user` systemd timers that run the `showerthoughts`
coordination/intero blind-spot ledger: `intero-ledger.{service,timer}` (daily, 09:00 —
the existing surface) and `intero-drift.{service,timer}` (weekly, Mon 09:15 — new this
day, reads each repo's `.intero.json` `history` ring for actual-vs-declared cadence).
Both `Type=oneshot`, `Persistent=true`, output to the journal + a digest under
`~/.local/state/intero/`. Canonical copies + file→install-path mapping in
[`intero/README.md`](config/intero/README.md). Stateless, zero-GPU, no daemon; not a cloud
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
(old name redirects). Full detail in [`postgres/CHANGELOG.md`](config/postgres/CHANGELOG.md).
