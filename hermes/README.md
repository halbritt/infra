# hermes — Hermes Agent CLI (self-improving agent harness)

[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent) (MIT) — a
terminal agent harness with a built-in learning loop: it writes skills from experience,
curates its own memory, searches past sessions, and can run headless behind a messaging
gateway. Installed on `proximal` **2026-07-28** as a third local agent harness alongside
`opencode` and `openclaw`.

- **Version installed:** `0.19.0` (`2026.7.20`), upstream commit `30526baa` (see `SOURCE_COMMIT`).
- **Install method:** official `install.sh` → git clone + **uv-managed private venv**
  (Python 3.11.15, deps hash-verified against the repo's `uv.lock`). Not npm-global — this
  is the one agent tool on the box that does *not* follow the global-npm convention,
  because upstream ships it as a Python package with a bundled node/TUI side-car.
- **Not under systemd.** It's an interactive CLI; nothing resident, nothing listening.
  `hermes gateway install` would add a user service (messaging + cron) — deliberately
  not done, see **Deliberately not enabled** below.
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

## Deliberately not enabled

- **Gateway** (`hermes gateway install`) — Telegram/Discord/Slack/WhatsApp/Signal bridge plus
  a cron scheduler, as a resident user service. Not installed: it would put an
  externally-reachable message path in front of an agent with `--yolo`-capable shell access,
  and this box already has a reviewed Slack path via Praxis. Revisit deliberately, not by default.
- **Nous Portal** (`hermes setup --portal`) — a second inference subscription. OpenRouter
  already covers model access for this host.
- **Its own STT** — `stt.local.model: base` would pull a second Whisper onto the 3090, which
  is already shared by `llama-27b` (~23 GiB) and `whisper-stt` (~0.95 GiB). If STT is ever
  wanted here, point it at the existing `:8910` / shim `:8082` path in
  [`whisper/`](../whisper/README.md) instead of loading another model.

## Verify

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

## Rollback

`hermes uninstall` (upstream-provided), or remove `~/.hermes/` and
`~/.local/bin/hermes`. Nothing outside those two paths is touched except the apt-installed
ffmpeg, which is independently useful and can stay. No systemd units, no listeners, no
changes to `~/.bashrc` — `~/.local/bin` was already on `PATH`.
