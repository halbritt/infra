# wigolo — local-first web-research layer for agents

[`KnockOutEZ/wigolo`](https://github.com/KnockOutEZ/wigolo) — a keyless, local-first
web-intelligence **MCP server** (search / fetch / crawl / extract / cache / find-similar
/ research / agent / diff / watch). Adopted on `proximal` as the **Tavily / generic
research-service replacement** for local agent work. Core search/fetch/crawl/extract/cache
are fully keyless and on-box; only the `research` / `agent` synthesis step calls out to an
LLM (see **Synthesis model** below).

- **Version audited & installed:** `0.2.1` (npm), source commit `180ac3d` (see `SOURCE_COMMIT`).
- **Install method:** global npm (`~/.npm-global/bin/wigolo`), matching the box's global-tool
  convention (node 24 / npm 11). **No `postinstall`** — browser + models download at `warmup`.
- **Data dir:** `~/.wigolo/` (cache DB, browser engine, embeddings, plugins).

## Why it's here (fitness + security conclusion)

Cloned and audited before adoption (static source review of ~72k LOC). **Verdict: clean —
no evidence of malicious behavior, no prompt injection in its own instructions, no
install-time code execution, no phone-home.** Genuinely local-first and privacy-conscious.
Full shareable audit: <https://gist.github.com/halbritt/74225e8f58787bf81ae4eac17806ce3d>

(Audit highlights: no lifecycle scripts; checksum-verified installer; keychain→AES-GCM→env
key store; unwired telemetry; single-registry deps; redirect-aware SSRF guard. Only real
supply-chain weakness is the opt-in SearXNG backend — avoided, see guardrails.)

## Synthesis model — GLM 5.2 via OpenRouter (chosen 2026-07-21)

`research`/`agent` synthesize a cited report from fetched pages. wigolo's synthesis path is:
**(1)** MCP host sampling (host LLM writes it) → **(2)** the configured `WIGOLO_LLM_PROVIDER`
→ **(3)** a heuristic deterministic "brief" template. Claude Code does not expose sampling,
so tier 2 (the wired model) is what runs; tier 3 is the fallback when tier 2 fails.

**Key finding (benchmarked, not assumed):** wigolo caps synthesis at `reportChars/3` tokens
(`src/research/synthesize.ts`) with **zero headroom for model "thinking" tokens**. Every
current model is a *reasoning* model, so this mismatch bites:

| Model | Behavior in wigolo | Verdict |
|---|---|---|
| **GLM 5.2** (`z-ai/glm-5.2`, OpenRouter) | OpenRouter returns reasoning in a *separate* field, so wigolo's `content` is always clean prose — full, accurate, well-cited report at `comprehensive`; terse-but-correct at `standard` | ✅ **chosen** |
| Local 35B MoE (`:8081`) | reasoning tokens starve the content budget → **collapses to the tier-3 template** on large source sets; fine only at `quick` depth | ⚠️ fallback |
| Gemini 3.x flash (`@google/genai`) | thinking scratchpad **leaks into the report**; Gemini 2.5 gated for our key | ❌ rejected |
| Qwen 27B (peecee) | not yet benchmarked | ⏸ pending |

**Operational guidance:** prefer **`depth: "comprehensive"`** with GLM 5.2 — the larger token
budget (~2000) fits its reasoning and yields a full report; `standard` runs correct but terse.
Cost is ~1–2¢ per research call. Fetched pages are public web content, so nothing private
leaves the box; only that public content + the question reach OpenRouter for synthesis.
To stay fully keyless/on-box for a run, drop to core `search`/`fetch` (no LLM) or use
`quick` depth with a local model.

## Configuration (how it's wired)

Registered as a Claude Code MCP server at **user scope** (all projects). Uses the `openai`
provider pointed at OpenRouter — the OpenAI Node SDK reads `OPENAI_BASE_URL` from env, and
wigolo's `openai` adapter has no base-URL override, so this env is the redirect:

```bash
claude mcp add wigolo -s user \
  -e WIGOLO_LLM_PROVIDER=openai \
  -e OPENAI_BASE_URL=https://openrouter.ai/api/v1 \
  -e WIGOLO_LLM_MODEL=z-ai/glm-5.2 \
  -e OPENAI_API_KEY=<OpenRouter key> \
  -- /home/halbritt/.npm-global/bin/wigolo
```

- **The key** is the OpenRouter key from [`~/.config/striatum/openrouter.env`](file) (var
  `OPENROUTER_API_KEY`, shared with striatum's judgment lanes). It is passed into the MCP env
  block, which lands **plaintext in the user-local `~/.claude-harm/.claude.json`** (not in git).
  wigolo's encrypted keystore would be cleaner but is only settable via its interactive
  wizard (`wigolo config`), not headless — revisit if you'd rather not have it in `.claude.json`.
- Canonical block for other MCP clients (opencode/codex/etc.): [`mcp-config.json`](mcp-config.json).

## Reproduce the setup

```bash
npm install -g wigolo            # global install (no postinstall; safe)
wigolo warmup                    # chromium engine + core search bootstrap (~30s, ~1.5GB in ~/.wigolo)
wigolo doctor                    # health probe
# then the `claude mcp add …` above
```

## Operational notes / guardrails

- **Backend:** default `core` (direct multi-engine + RRF + ML rerank). **Do not** set
  `WIGOLO_SEARCH=searxng` / `hybrid` — that path downloads an **unpinned `master` tarball +
  `pip install`** with no checksum (the audit's only real supply-chain weakness).
- **Retrieval is keyword-sensitive.** Natural-language questions with words like "tradeoffs"
  can mis-retrieve (an early test pulled an NPR "Tradeoffs" podcast). Keyword-dense phrasing
  and `include_domains` help; the wired model correctly *refuses to fabricate* on bad evidence.
- **CLI exit hang:** `wigolo research …` from the shell can finish its work but hang on process
  teardown. Wrap CLI/headless invocations in `timeout` (the JSON is flushed before the hang).
  Irrelevant under the persistent MCP server.
- **`wreq-js`** (TLS-fingerprint impersonation) and **`use_auth:true`** (reuses a logged-in
  Chrome session) are opt-in / off by default; `use_auth` is powerful — enable per-call only.
- `watch` webhooks and all fetches are SSRF-guarded.

## Update / remove

```bash
npm update -g wigolo             # bump; re-run `wigolo warmup` if a new engine ships
claude mcp remove wigolo -s user # unwire from Claude Code
wigolo config --uninstall --yes  # wipe ~/.wigolo entirely
```

Re-audit on major version bumps — record the new commit in `SOURCE_COMMIT`.
