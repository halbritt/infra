# wigolo — local-first web-research layer for agents

[`KnockOutEZ/wigolo`](https://github.com/KnockOutEZ/wigolo) — a keyless, local-first
web-intelligence **MCP server** (search / fetch / crawl / extract / cache / find-similar
/ research / agent / diff / watch). Adopted on `proximal` as the **Tavily / generic
research-service replacement** for local agent work. Core search/fetch/crawl/extract/cache
are fully keyless; `research` / `agent` / `format:answer` synthesis is wired to the box's
own **llama.cpp endpoint (`:8081`)**, so the whole path stays local and $0/query.

- **Version audited & installed:** `0.2.1` (npm), source commit `180ac3d` (see `SOURCE_COMMIT`).
- **Install method:** global npm (`~/.npm-global/bin/wigolo`), matching the box's global-tool
  convention (node 24 / npm 11). **No `postinstall`** — browser + models download at `warmup`.
- **Data dir:** `~/.wigolo/` (cache DB, browser engine, embeddings, plugins). Nothing leaves
  the box except the actual web fetches and the wired LLM (which is local).

## Why it's here (fitness + security conclusion)

Cloned and audited before adoption (static source review of ~72k LOC). **Verdict: clean —
no evidence of malicious behavior, no prompt injection in its own instructions, no
install-time code execution, no phone-home.** Genuinely local-first and privacy-conscious.

Full shareable audit write-up: <https://gist.github.com/halbritt/74225e8f58787bf81ae4eac17806ce3d>

Key points from the audit:
- No `postinstall`/`preinstall`/`prepare` in root or any nested `package.json`.
- Credentials: keychain → AES-256-GCM file → env; never written back to env, never logged;
  each provider key only ever reaches its own provider SDK. (Moot here — we run keyless + local LLM.)
- Telemetry is unwired scaffolding (off, no hardcoded endpoint, zero callers). No analytics hosts.
- All 735 lockfile deps resolve from `registry.npmjs.org`.
- Redirect-aware SSRF guard (blocks RFC-1918, loopback for `watch`, cloud-metadata `169.254/16`).
- The one inherent weakness (shared by every web→LLM tool): fetched page text flows unlabeled
  into internal synthesis prompts, so a malicious page can **poison a synthesized answer's
  content** (cannot escalate to SSRF/actions). Mitigated by running keyless where the host
  agent (already injection-aware) does synthesis, or by pointing synthesis at our trusted local LLM.

## Configuration (how it's wired on this box)

Synthesis points at the local llama.cpp server via env. **Critical:** the base URL must
**not** include `/v1` — wigolo's custom backend appends `/v1/chat/completions` itself
(`src/integrations/cloud/llm/run.ts`), so `.../v1` would double it.

```
WIGOLO_LLM_PROVIDER=http://localhost:8081     # NOT .../v1  → resolves to /v1/chat/completions
WIGOLO_LLM_MODEL=qwen3.6-35b-a3b              # llama-server ignores the model field anyway
```

These are set in the **Claude Code MCP registration** (user scope), so every project gets it:

```bash
claude mcp add wigolo -s user \
  -e WIGOLO_LLM_PROVIDER=http://localhost:8081 \
  -e WIGOLO_LLM_MODEL=qwen3.6-35b-a3b \
  -- /home/halbritt/.npm-global/bin/wigolo
```

For any **other MCP client / agent** (opencode, codex, gemini-cli, a self-hosted agent),
use the canonical block in [`mcp-config.json`](mcp-config.json).

> ⚠️ **Reasoning-model note.** `qwen3.6-35b-a3b` emits `reasoning_content` before `content`,
> and the current 35B config does **not** honor `enable_thinking:false`. wigolo reads only
> `choices[0].message.content` and throws if it's empty. Synthesis was smoke-tested and works
> (returns cited prose), but if a future model/config change makes synthesis come back empty
> (`finish_reason:length`), the fix is a larger `max_tokens` on the wigolo side or a
> non-thinking model — not a wigolo bug. Falling back to keyless (drop the two env vars) always works.

## Reproduce the setup

```bash
npm install -g wigolo            # global install (no postinstall; safe)
wigolo warmup                    # chromium engine + core search bootstrap (~30s, ~1.5GB in ~/.wigolo)
wigolo doctor                    # health probe
# then the `claude mcp add …` above (or mcp-config.json for other clients)
```

## Operational notes / guardrails

- **Backend:** default `core` (direct multi-engine + RRF + ML rerank). **Do not** set
  `WIGOLO_SEARCH=searxng` / `hybrid` — that path downloads an **unpinned `master` tarball +
  `pip install`** with no checksum (the audit's only real supply-chain weakness). `core` avoids it.
- **`wreq-js` (TLS-fingerprint impersonation)** and **`use_auth:true`** (reuses a logged-in
  Chrome session) are both opt-in / off by default. `use_auth` is powerful — a poorly-scoped
  agent call could read authenticated pages; enable per-call only when intended.
- **`watch` webhooks** and all fetches are SSRF-guarded (no loopback/RFC-1918/metadata targets
  for `watch`; `fetch`/`crawl` intentionally allow localhost for local dev servers).
- Shares nothing with the GPU beyond the LLM it calls — embeddings/reranker run on CPU (ONNX).

## Update / remove

```bash
npm update -g wigolo             # bump; re-run `wigolo warmup` if a new engine ships
claude mcp remove wigolo -s user # unwire from Claude Code
wigolo config --uninstall --yes  # wipe ~/.wigolo entirely
```

Re-audit on major version bumps — record the new commit in `SOURCE_COMMIT`.
