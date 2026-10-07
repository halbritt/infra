# hermes — Hermes Agent CLI (self-improving agent harness)

[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent) (MIT) — a
terminal agent harness with a built-in learning loop: it writes skills from experience,
curates its own memory, searches past sessions, and can run headless behind a messaging
gateway. Installed on `proximal` **2026-07-28** as a third local agent harness alongside
`opencode` and `openclaw`.

Current CLI/gateway: upstream `d795726f` plus Cairn carry `fbfcb659`; see
[current generation and gateway repair](#current-generation-and-gateway-repair--2026-10-03).

- **Original version installed:** `0.19.0` (`2026.7.20`), upstream commit `30526baa` (see `SOURCE_COMMIT`).
- **Install method:** official `install.sh` → git clone + **uv-managed private venv**
  (Python 3.11.15, deps hash-verified against the repo's `uv.lock`). Not npm-global — this
  is the one agent tool on the box that does *not* follow the global-npm convention,
  because upstream ships it as a Python package with a bundled node/TUI side-car.
- **Gateway service (user systemd via `hermes gateway install`).** Added 2026-08-04
  to connect Slack (the box's second Slack bot, Agent-mode "hermes" app). Interactive
  CLI sessions run independently of it. See **Gateway: Slack enabled** below.
- **Data dir:** `~/.hermes/` (~2.0 GB — code, venv, node deps, Chromium, 70 bundled skills,
  sessions, memories).

## Why it's here

It came up while scoping a **pre-dispatch triage agent** that had to run local, as one of
`claw` / `hermes` / roll-our-own. Installing it makes that comparison concrete instead of
speculative. What distinguishes it from the harnesses already here is the closed learning
loop (autonomous skill creation + self-improving skills + FTS5 cross-session recall) and
provider portability — one config key repoints it between OpenRouter and the box's own
llama.cpp server, which is what makes it usable for both cloud-quality and
nothing-leaves-the-box work.

## Model wiring — GLM 5.2 via OpenRouter (chosen 2026-07-28)

Ships pointing at OpenRouter with no key, i.e. inert. Current desired state:

```yaml
model:
  provider: openrouter
  default: z-ai/glm-5.2      # 1,048,576 ctx · $0.769/M in · $2.42/M out
```

`base_url` and `api_key` are deliberately **unset** so the native OpenRouter provider path
runs (its own headers and error handling) rather than the generic `custom` endpoint path —
`base_url`, when set, takes precedence over `provider` and bypasses it.

**Why GLM 5.2 and not the local 35B:** this repeats a conclusion already benchmarked for
[`wigolo/`](../wigolo/README.md#synthesis-model--glm-52-via-openrouter-chosen-2026-07-21)
on 2026-07-21 — **OpenRouter returns GLM's reasoning in a separate field, so `content` is
always clean prose**, whereas the local reasoning model's thinking tokens compete with the
answer inside a fixed budget. Hermes is long-horizon and tool-heavy (500 max turns,
compression at 50% of context), so a 1M-context model whose reasoning never contaminates
tool-call output is worth the ~1–2¢/call more than a same-box endpoint is worth saving.

**The local endpoint works and is a first-class alternate** — verified on this install
before the switch (see below). To repoint at `llama-27b.service` on `:8081`:

```bash
hermes config set model.provider custom          # NOT "llamacpp" — see Known-bad
hermes config set model.base_url http://localhost:8081/v1
hermes config set model.default qwen3.6-35b-a3b
hermes config set model.api_key local-no-key     # llama-server ignores it; must be non-empty
```

Per-invocation instead of permanently — **the env var is required**, see the silent-fallback
known-bad below:

```bash
CUSTOM_BASE_URL=http://localhost:8081/v1 hermes --provider custom -m qwen3.6-35b-a3b
```

## Files → install paths

| repo file | install path | notes |
|---|---|---|
| [`config.yaml`](config.yaml) | `~/.hermes/config.yaml` | canonical desired state, secret-free |
| [`SOURCE_COMMIT`](SOURCE_COMMIT) | — | upstream commit of the installed clone |

Credentials are **not** in either file. `OPENROUTER_API_KEY` is already exported from
`~/.profile` and Hermes picks it up from the environment — the key is *not* copied into
`~/.hermes/.env` (which stays `0600` and uncommitted), so the box has one place to rotate it.

## Verified (2026-07-28)

- `hermes --version` → `0.19.0 (2026.7.20) · upstream 30526baa`, Python 3.11.15, OpenAI SDK 2.24.0
- **Local endpoint, before the switch:** `hermes -z` → `hermes-ok`; tool-call test
  (terminal tool running `uname -r`) → `6.8.0-124-generic` — so a fully on-box,
  nothing-leaves-the-machine configuration is proven, not assumed
- **GLM 5.2 via OpenRouter:** tool-call test (terminal tool running `hostname`) → `glm-ok proximal`
- `hermes doctor` → `✓ API key or custom endpoint configured`, `✓ OpenRouter API`;
  16 toolsets available (browser, code_execution, delegation, memory, session_search,
  skills, terminal, tts, vision, video, …); 70 bundled skills synced
- OpenRouter key state at cutover: `$50` limit, `$10.00` used

## Known-bad / gotchas

- ⚠️ **`provider: "llamacpp"` is rejected**, despite `config.yaml`'s own template comment
  claiming `"ollama"`, `"vllm"`, and `"llamacpp"` all alias to `custom`. The validator's
  provider list has no such aliases and `hermes doctor` errors with
  `model.provider 'llamacpp' is unknown`. Use `custom` + `base_url`. Upstream doc/code drift.
- ⚠️⚠️ **`--provider custom` silently bills OpenRouter when `base_url` is unset.** It does
  *not* error. The resolution order in `hermes_cli/runtime_provider.py` is
  `explicit base_url → $CUSTOM_BASE_URL → config base_url → $OPENROUTER_BASE_URL →
  OPENROUTER_BASE_URL`, so with our OpenRouter-default config the bare flag lands on
  **OpenRouter** while reading, to the operator, as on-box and free. Caught here by testing
  it: `hermes --provider custom -m qwen3.6-35b-a3b -z ...` returned a plausible answer while
  `journalctl -u llama-27b` showed **zero** requests — the local server was never contacted.
  Always pass `CUSTOM_BASE_URL=http://localhost:8081/v1` for a per-invocation local run, and
  confirm with the journal rather than trusting the reply. **Anything that must not leave the
  box should set `model.base_url` in config, not rely on the flag.**
- ⚠️ **`hermes config set` destroys the annotated config template.** It reserializes
  `config.yaml` from resolved values, rewriting the shipped 1622-line / 85 KB commented
  reference into a 158-line / 5 KB bare YAML dump. Values survive; every inline comment
  documenting the other options does not. The pristine template is preserved on the box as
  `~/.hermes/config.yaml.orig` (and the working local-endpoint config as
  `~/.hermes/config.yaml.local-bak`). Re-read options from upstream
  `~/.hermes/hermes-agent/`, not from the live file.
- The installer wants `sudo` for optional apt packages. On this box that installed
  **ffmpeg** (~85 dependency packages) — the only system-level change it made. `uv`, node,
  and ripgrep were already present and were reused rather than re-bundled.
- `hermes doctor` reports npm audit findings in the bundled `web` and `ui-tui` workspaces,
  and warns about absent optional integration keys (Discord, xAI, EXA/Tavily/Firecrawl).
  Both are upstream-bundled noise, not local misconfiguration — this box's web-research
  path is [`wigolo/`](../wigolo/README.md), not Hermes's `web` toolset.

## Gateway: Slack enabled (2026-08-04); other messaging platforms not

- **Slack** (`hermes gateway install`) — **LIVE** as the box's second Slack bot,
  connecting Hermes as its own **Agent-mode** app in the `gearheads` workspace
  (separate from the `openclaw` bot and the Praxis path). This *was* deliberately
  unenabled (an externally-reachable path in front of a `--yolo`-capable agent),
  and was revisited deliberately: a dedicated "hermes" app with open DM/group
  policy in the small personal workspace, `GATEWAY_ALLOW_ALL_USERS=true`.
  Full wiring, the two bring-up root causes (app must carry full scopes in Agent
  mode; `OPENROUTER_API_KEY` must live in `~/.hermes/.env` for the systemd
  gateway, not just `~/.profile`), and operation: [`SLACK_ONBOARDING.md`](SLACK_ONBOARDING.md).
- **Other gateway platforms** (Telegram/Discord/WhatsApp/Signal) — not enabled,
  same rationale as before: stands down by default unless deliberately revisited.
- **Nous Portal** (`hermes setup --portal`) — a second inference subscription. OpenRouter
  already covers model access for this host.
- **Its own STT** — `stt.local.model: base` would pull a second Whisper onto the 3090, which
  is already shared by `llama-27b` (~23 GiB) and `whisper-stt` (~0.95 GiB). If STT is ever
  wanted here, point it at the existing `:8910` / shim `:8082` path in
  [`whisper/`](../whisper/README.md) instead of loading another model.

## Slack reply display — 2026-10-02

At the owner's request, `display.platforms.slack` disables `tool_progress`,
`interim_assistant_messages`, and `live_status` tool details. Final replies remain
enabled. The static Slack working indicator can still appear.

Install these three keys from the canonical `config.yaml` into the same mapping
in `~/.hermes/config.yaml`, preserving unrelated live settings. The live file has
independent model and plugin changes, so do not overwrite it with this older
full snapshot. The running `hermes-candidate-0a374d16` gateway loads config and
resolves these settings on each turn; this change needs no restart and applies
to subsequent turns. Verified with that runtime's display resolver; no Slack
test message was sent.

### Suppress diagnostic preambles — 2026-10-06

The owner's screenshot showed a detailed working heartbeat and a final reply
prefixed with Cairn identity, inbox and memory diagnostics. The original three
quiet settings were still installed. Global `long_running_notifications: true`
and `busy_ack_detail: true` overrode Slack's quiet defaults; explicitly disable
both under `display.platforms.slack` as well.

The diagnostic paragraph was model-authored final-answer content, so display
controls cannot remove it. `agent.system_prompt` now adds Slack-specific guidance
to answer the request directly, perform required coordination silently, and omit
internal bookkeeping unless the user asks or needs to act on a concrete blocker.
Required approval requests and result-affecting failures remain visible. This is
model guidance, not a deterministic output filter.

Install the five Slack display keys and `agent.system_prompt` from the canonical
config into `~/.hermes/config.yaml`, preserving all unrelated live values. Before
installation, check for an existing custom prompt, personality or channel prompt
override; merge deliberately rather than replacing one. Backup for this change:
`~/.hermes/config.yaml.before-slack-diagnostics-agent288`.

Verified against the active `hermes-candidate-f16cbcde` source: its display resolver
returns all five quiet values, other platform display values are unchanged, the
prompt resolver includes the instruction, and the changed ephemeral prompt changes
the agent-cache signature. These settings apply on the next turn without restart.
Used the runtime's `hermes_yaml` parser (this generation no longer provides the
`yaml` import). No live Slack message or model-compliance test was sent.
All 42 infrastructure tests and repository validation passed. The tests required
an unsandboxed rerun because two fixtures create scratch directories in `/var/tmp`.

## Original installation verification — historical

```bash
hermes --version                      # 0.19.0, upstream commit
hermes config get model.provider      # openrouter
hermes config get model.default       # z-ai/glm-5.2
hermes doctor                         # provider + connectivity checks
diff ~/.hermes/config.yaml config.yaml # drift: live vs repo desired-state (empty = in sync)
                                      # NB: `hermes config show` is a pretty-printed
                                      # panel, not YAML — and it echoes a masked key.
                                      # Diff the file, don't diff that.
hermes --yolo -z 'run hostname via your terminal tool and reply with only its output'
```

## Original installation removal (historical; not generation rollback)

For current generation rollback, use the [port report](reports/HERMES_2026-09-29.md).
The following describes removal of the original installation.

`hermes uninstall` (upstream-provided), or remove `~/.hermes/` and
`~/.local/bin/hermes`. Nothing outside those two paths is touched except the apt-installed
ffmpeg, which is independently useful and can stay. No systemd units, no listeners, no
changes to `~/.bashrc` — `~/.local/bin` was already on `PATH`.


## Versioned CLI update — 2026-09-28

New `hermes` launches select upstream `79a6fd3e` with Cairn port `9b57ee21`
(Python 3.14.6), installed at `/var/lib/update-bot/staging/hermes-carry`.
[hermes-launcher](hermes-launcher) is canonical for `~/.local/bin/hermes`.
`SOURCE_COMMIT` names this default CLI generation. Preserve that directory as an
installed runtime; it is not disposable scratch.

The separate active CLI still uses the original `~/.hermes/hermes-agent` and its
venv; it was not restarted. The gateway was transitioned after native reversible
drain reported zero active chat/cron/API tasks. It now reports source9b57ee21,
running, and Slack connected. [gateway-generation.conf](gateway-generation.conf)
is installed as `~/.config/systemd/user/hermes-gateway.service.d/50-generation.conf`;
reload the user manager after editing. It selects the default launcher for future
starts. Preserve the old venv for the active CLI and the unit's existing
ExecStopPost cleanup. Receipt: `/var/lib/update-bot/hermes-gateway-activation.json`.
See [patch procedure and evidence](../update-bot/PATCHED-UPDATES.md).

## Previous generation — 2026-09-29

New CLI launches and the gateway select `aa50456d` on upstream `16c59d0e`,
with the preserved Cairn carry and Python 3.14.6, at
`/var/lib/update-bot/staging/hermes-gen-16c59d0e`. Native zero-work drain and
PID/source/Slack checks passed. See [the port report](reports/HERMES_2026-09-29.md)
for validation, baseline adapter failures and recovery. The old `hermes-carry`
generation remains for rollback. Legacy CLI source and cleanup venv remain
required dependencies, with review due 2026-10-06 or when that CLI exits.

The three shared Cairn plugin directories were hash-pinned and tested against
both generations, not replaced. Future plugin installs must repeat that matrix
or introduce versioned loading. No live Slack/model round trip was performed.

`install-stamp.json` installs beside the selected source (on September 29,
`/var/lib/update-bot/staging/hermes-gen-16c59d0e/install-stamp.json`). Its upstream
`updateMechanism: external` setting preserves update-bot's launcher and tested
venv. Generate a fresh stamp for every successor before its first launch using
`scripts/write_install_stamp.py --source update-bot --update-mechanism external`.
Verify launcher bytes and receipt again after startup.


## Current generation and gateway repair — 2026-10-03

CLI and gateway run `fbfcb659eb7c041be697e9d7e3704d08e58848b7` on upstream
`d795726f78e532ca31655f74656b4be63a907581`, the upstream main observed for this
update, at `/var/lib/update-bot/staging/hermes-candidate-d795726f` with Python
3.14.6. The Cairn carry was cherry-picked intact from the prior live generation,
`acf92f7e` on `0a374d16`. Retain that prior generation for rollback and existing
consumers. `SOURCE_COMMIT`, `hermes-launcher`, and `install-stamp.json` now name
the current generation.

Install `gateway-generation.conf` as
`~/.config/systemd/user/hermes-gateway.service.d/50-generation.conf`, then run
`systemctl --user daemon-reload`. It overrides **all three** runtime commands:
start through the canonical launcher; stop marking and cgroup cleanup through
the tested generation's `.venv/bin/python -m gateway.<module>`. Upstream's
source-local `.hermes/bin/hermes` PM shim could not resolve a committed
dependency environment on this externally managed installation. Both shutdown
helpers previously failed with `no dependency environment is committed`.
Future generation selections must update these helper paths together with the
launcher and retain the old source until its consumers exit. Upstream may refresh
the base unit at startup; the canonical drop-in preserves these overrides.

The earlier outage coincided with the entire user manager shutting down at
19:26 PDT on October 2. Systemd also recorded an OOM-killed process in
`user-1000.slice`; the initiating cause of the manager shutdown is not established.
The gateway had already recovered at 14:26 PDT October 3 before this repair.
Linger is enabled. This update does not claim to prevent a host/user-manager outage.

Validation: 497 Hermes tests passed, four skipped; 43 Cairn queue/cancellation
tests passed; two fixture gateway turns with a local HTTP provider and synthetic
Slack transport passed. A copy of the session database passed candidate open,
quick-check, and reopening with the previous generation (schema 31 unchanged).
Native zero-work drain, new PID/source, Slack connection, healthy session store,
and launcher/stamp/drop-in hashes were verified. No live Slack message was sent.
See [the repair report](reports/HERMES_2026-10-03.md) for evidence and recovery.

## Outbreak-watch gate — 2026-10-07

The daily watch now has an executable source/review/identity gate, following the
owner-requested independent review. Hermes proposes facts; fetched primary passages
and a complete Relay panel must affirm them before a durable one-time claim can
produce an alert. Closure is silent and stops later scans. The existing 07:00 Pacific
schedule and Slack thread are preserved. See [operation, installation and verification](outbreak_watch/README.md).
