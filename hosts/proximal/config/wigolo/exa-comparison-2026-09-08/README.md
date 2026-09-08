# wigolo vs Exa — search & fetch comparison, 2026-09-08

**Verdict:** on this box, today, Exa's `auto` search is decisively better than wigolo's keyless
search for technical and research queries, roughly at parity for news and Council-style
queries, and ~5× faster. The gap is not wigolo's ranker — it is that wigolo's default engine
pool is two engines deep (Bing + DuckDuckGo) and **DuckDuckGo has been serving proximal its
anomaly-challenge page since ~19:40Z**, which wigolo reports as `duckduckgo:ok:0` rather than
as a blocked engine. With only Bing's HTML endpoint answering, rare-token queries (`sqlite-vec
vec0`, `patchright`, `lost in the middle`) come back with generic or wrong-topic pages.
Fetch is closer to a draw: wigolo matches Exa's full-text coverage once `max_tokens_out` is
raised above its ~14k-token default, and both fail on the same bot-walled/rate-limited URLs,
but Exa labels those failures cleanly while wigolo returned Reddit's block page as content.

## Method

- **Tools.** wigolo daemon (`wigolo.service`, upstream `main` c6ad4479, REST `/v1/search`
  with `force_refresh:true`, `max_results:10`) vs Exa `/search` (`type:auto`, `numResults:10`,
  `contents.highlights:true`); news queries were additionally run with `category:"news"`.
- **Queries.** 40, in `queries.json`: 8 *council* (the distinct `wigolo search` queries
  Council members actually issued, from `~/.council` transcripts), 11 *news* (AI-news
  monitoring), 11 *technical* (reference lookups matching this host's stack), 10 *research*
  (grounding questions, several targeting a known paper).
- **Judging.** Blind, pooled: the top-5 of every tool were deduped by URL, shuffled, and graded
  0–3 by the local Qwen3.8-27B (`:8081`, thinking off, temp 0, JSON) from title + URL +
  snippet only. Per-tool nDCG@5 / P@5 are computed on each tool's own ranking. One judge,
  one pass — treat differences under ~0.1 nDCG as noise.
- **Fetch leg.** 15 URLs (`fetch-urls.txt`), 9 of them URLs Council members actually
  fetched; wigolo `/v1/fetch` (`force_refresh`) vs Exa `/contents` (`text`, 200k cap).
- **Cost.** $0.37 for the whole exercise (51 searches + 15 contents calls), all on Exa's
  free credit. Sequential, well under the free tier's 5–10 QPS.
- **Files.** `run.py` (harness), `rerun.py` (paced wigolo re-run), `report.py` →
  `report.md`; raw `results-*.json`. Reproduce with `EXA_API_KEY` from `~/.config/exa/env`.

## Headline numbers (as run, 19:35–19:45Z)

| metric | wigolo | Exa auto | Exa news (11 news queries) |
|---|---|---|---|
| nDCG@5, mean over 40 | **0.538** | **0.939** | 0.983 |
| P@5 (grade ≥ 2) | 0.445 | 0.960 | 0.927 |
| top-1 grade (0–3) | 1.45 | 2.70 | 2.82 |
| median latency | 6.1 s | 1.2 s | 0.9 s |
| results with a published date | 17 % | 52 % | 90 % |
| per-query wins (tie ±0.05) | 5 | 29 | 6 ties |

| category | n | wigolo | Exa |
|---|---|---|---|
| council | 8 | 0.879 | 0.954 |
| news | 11 | 0.910 | 0.953 |
| technical | 11 | 0.346 | 0.915 |
| research | 10 | 0.069 | 0.936 |

Mean top-10 URL overlap between the two tools was under 1 URL per query — they are
searching different indexes, not re-ranking the same pool.

## Why wigolo collapsed on technical/research — and why it is not the ranker

Every one of wigolo's 16 zero-nDCG queries has `duckduckgo:ok:0` in its engine telemetry;
every query where DuckDuckGo returned results scored ≥ 0.64. The failures cluster in the
second half of the run (technical → research), i.e. DuckDuckGo began challenging the box's
IP part-way through — plausibly triggered by the run's ~80 DDG requests in four minutes
(wigolo fans each query out as 2 rewrites). A direct probe of `html.duckduckgo.com` returns
HTTP 202 with the anomaly/challenge page, still at 20:53Z, 75 minutes later.

Three separate wigolo weaknesses compound here:

1. **Engine breadth.** The default `general` pool is Bing + DuckDuckGo (+ Wikipedia, Mojeek,
   Marginalia, which returned 0 useful results across all 40 queries: Marginalia 429'd on 35/40,
   Mojeek returned nothing, Wikipedia nothing). Lose DDG and it is Bing alone.
2. **Bing's HTML endpoint loosens rare terms.** For `sqlite-vec vec0 virtual table example`
   Bing returned the SQLite homepage/download page; for `lost in the middle long context
   degradation` it returned the *Lost* TV series. The same happens on the previous npm release
   `0.2.1` (verified with `npx wigolo@0.2.1`), so this is not a regression from today's update.
3. **The challenge is reported as success.** DDG's anomaly page comes back as
   `outcome: ok, result_count: 0` with no `engine_warnings` entry, contradicting the README's
   "failed engines are reported" claim. An agent reading the telemetry cannot tell "DDG had
   nothing" from "DDG blocked us". Worth an upstream issue.

A paced re-run (`rerun.py`: waited 30 min for DDG to clear — it never did — then re-ran the
18 affected queries at one per 20 s) changed nothing: 17/18 still `duckduckgo:0`, mean wigolo
nDCG 0.09 → 0.15 (one query rescued by the arXiv/papers engines). `results-rerun.json`.

**Implication for Council.** Members issue searches in bursts from this same IP. Whenever
DDG is challenging the box, technical and paper lookups through wigolo will quietly return
junk with a confident-looking score, and the member has no signal to fall back on.

## Fetch leg

| finding | wigolo | Exa |
|---|---|---|
| clean pages (docs, blogs, HN, release pages) | ✅ full markdown, 0.2–2 s | ✅ compact text, ~0.1 s (cached) |
| JS/SPA pages (deepwiki, huggingface, nodejs.org) | ✅ via browser tier, 1.4–3.2 s | ✅ from Exa's cache |
| arXiv HTML paper (169k chars) | ⚠️ **56k chars, `[... content truncated]`** with the default `max_tokens_out` (~14k tokens); full 183k chars with `max_tokens_out:200000` | ✅ 169k chars |
| GitHub release page | 42k chars (includes page chrome) | 8k chars (compact) |
| reddit.com (bot-walled) | ❌ returned Reddit's "blocked by network security" page as content, flagged only `partial/thin_content`, not `blocked_by_challenge` | ❌ labeled `403 SOURCE_NOT_AVAILABLE` |
| Semantic Scholar API (rate-limited) | ❌ labeled `HTTP 429` | ❌ `CRAWL_LIVECRAWL_TIMEOUT` (10 s) |

Council members in the archive were working around the truncation by hand
(`--section "Introduction"`, `--max-tokens-out=4000`), which fits: the default budget cuts
papers off after section 3. The fix is a bigger `--max-tokens-out` in the member prompt.

## Recommendation

- **Search:** wire Exa in for Council members and any research-grounding path. At Exa's
  $7/1k, the $10/month free credit is ~1,400 `auto` searches — far above current Council
  volume — and the quality gap on exactly the query types Council issues is large.
  Keep wigolo `search` as the keyless fallback, not the primary.
- **Fetch:** either works; wigolo keeps pages on-box and handles JS pages live, Exa returns
  labeled failures. If wigolo stays, raise the fetch token budget in the member prompt.
- **wigolo hygiene:** file upstream (a) DDG challenge reported as `ok:0`, (b) Reddit block
  page returned as content. Re-check DDG availability before trusting a technical result.
- **Not measured:** Exa `deep*` types, `outputSchema` synthesis, wigolo `research`/`agent`,
  wigolo's cache hit path (all runs forced live), and any judge other than local Qwen.

---

## Raw report (`report.py` output)

# wigolo vs Exa — search leg

queries: 40  judge failures: 0

| metric | wigolo | exa (auto) | exa (news cat, news set only) |
|---|---|---|---|
| nDCG@5 (mean) | 0.538 | 0.939 | 0.983 (n=11) |
| P@5 grade≥2 (mean) | 0.445 | 0.96 | 0.927 (n=11) |
| top-1 grade (mean, 0–3) | 1.45 | 2.7 | 2.82 |
| median latency ms | 6114 | 1178 | 914 |
| results returned (mean of 10 asked) | 9.9 | 10 | 10 |
| empty result sets | 0 | 0 | 0 |
| errors | 0 | 0 | 0 |
| share of results with a published date | 0.17 | 0.52 | 0.9 |
| Exa spend this leg | – | $0.357 | |

mean URL overlap in top-10: 0.9

## Per-category nDCG@5

| category | n | wigolo | exa | exa news |
|---|---|---|---|---|
| council | 8 | 0.879 | 0.954 | – |
| news | 11 | 0.91 | 0.953 | 0.983 |
| technical | 11 | 0.346 | 0.915 | – |
| research | 10 | 0.069 | 0.936 | – |

## Wins by query (nDCG@5; tie within 0.05)

| cat | query | wigolo | exa | winner |
|---|---|---|---|---|
| council | Claude Code auto memory feature how it decides what to save | 0.744 | 0.794 | exa |
| council | Codex CLI memory feature AGENTS.md automatic memories | 0.948 | 1.0 | exa |
| council | Hermes Agent Nous Research memory system MEMORY.md self-cura | 0.922 | 1.0 | exa |
| council | GLM-5.3 model release | 0.862 | 1.0 | exa |
| council | Node.js current Active LTS version 2026 | 0.678 | 0.84 | exa |
| council | llama.cpp latest release notes | 0.944 | 1.0 | exa |
| council | striatum halbritt council escalation agents | 0.983 | 1.0 | tie |
| council | Home Assistant ha-mcp add-on MCP server | 0.949 | 1.0 | exa |
| news | Anthropic announcement this week | 0.752 | 1.0 | exa |
| news | OpenAI new model release September 2026 | 0.922 | 1.0 | exa |
| news | Qwen 3.8 open weights release | 0.843 | 1.0 | exa |
| news | EU AI Act general-purpose AI obligations enforcement 2026 | 1.0 | 0.936 | wigolo |
| news | NVIDIA quarterly earnings data center revenue AI | 1.0 | 1.0 | tie |
| news | Home Assistant 2026.9 release notes | 0.944 | 0.984 | tie |
| news | DeepSeek new model announcement | 0.983 | 0.872 | wigolo |
| news | Meta Llama 5 release | 0.928 | 0.695 | wigolo |
| news | Cloudflare AI crawler blocking policy news | 1.0 | 1.0 | tie |
| news | Mistral AI funding round 2026 | 0.645 | 1.0 | exa |
| news | Google Gemini 3.6 update | 0.991 | 1.0 | tie |
| technical | PostgreSQL logical replication slot failover | 0.895 | 0.991 | exa |
| technical | systemd Restart=on-failure versus Restart=always | 0.944 | 0.66 | wigolo |
| technical | Tailscale exit node setup Linux | 0.966 | 1.0 | tie |
| technical | sqlite-vec vec0 virtual table example | 0.0 | 1.0 | exa |
| technical | patchright vs playwright bot detection | 0.0 | 1.0 | exa |
| technical | Garage S3 multi-node cluster layout | 0.0 | 0.991 | exa |
| technical | Prometheus remote write receiver configuration | 0.0 | 0.813 | exa |
| technical | whisper.cpp CUDA build flags | 0.0 | 0.984 | exa |
| technical | npm allow-scripts config global install | 0.0 | 0.936 | exa |
| technical | Cloudflare tunnel static site origin loopback | 1.0 | 0.744 | wigolo |
| technical | llama.cpp MTP speculative decoding draft depth | 0.0 | 0.949 | exa |
| research | does speculative decoding change the output distribution | 0.0 | 0.936 | exa |
| research | position bias in LLM-as-a-judge evaluation | 0.0 | 1.0 | exa |
| research | sandbagging evaluations language models arXiv | 0.0 | 1.0 | exa |
| research | reciprocal rank fusion k parameter choice | 0.0 | 0.813 | exa |
| research | BGE-small-en-v1.5 embedding dimensions MTEB score | 0.0 | 0.948 | exa |
| research | GGUF quantization perplexity Q4_K vs Q5_K comparison | 0.693 | 0.788 | exa |
| research | lost in the middle long context degradation | 0.0 | 1.0 | exa |
| research | Model Context Protocol sampling specification | 0.0 | 1.0 | exa |
| research | agent memory consolidation survey 2026 | 0.0 | 1.0 | exa |
| research | reasoning model thinking tokens disable chat template Qwen | 0.0 | 0.872 | exa |

wigolo 5 · exa 29 · tie 6

## wigolo engine telemetry

| engine | ok | error/other | total results |
|---|---|---|---|
| bing | 35 | 0 | 520 |
| bing_news | 5 | 0 | 60 |
| duckduckgo | 40 | 0 | 281 |
| hn-algolia | 5 | 0 | 2 |
| lobsters | 0 | 5 | 0 |
| marginalia | 0 | 35 | 0 |
| mojeek | 11 | 8 | 0 |
| wikipedia | 35 | 0 | 0 |

# fetch leg

| url | wigolo ms | wigolo chars | wigolo status | exa ms | exa chars | exa status |
|---|---|---|---|---|---|---|
| https://arxiv.org/abs/2609.01595 | 148 | 1980 | http | 81 | 6376 | success |
| https://arxiv.org/html/2609.01595v1 | 24294 | 56399 | http | 129 | 168972 | success |
| https://arxiv.org/pdf/2609.01595v1 | 3732 | 59554 | http | 7379 | 146857 | success |
| https://code.claude.com/docs/en/memory | 1400 | 30663 | http | 96 | 30840 | success |
| https://codex.danielvaughan.com/2026/05/01/codex-cli-memories-persiste | 1599 | 19320 | http | 95 | 12728 | success |
| https://deepwiki.com/NousResearch/hermes-agent/4.3-memory-and-sessions | 3183 | 31640 | browser | 100 | 11435 | success |
| https://github.com/ggml-org/llama.cpp/releases/latest | 2046 | 42519 | http | 91 | 8137 | success |
| https://nodejs.org/en/about/previous-releases | 1419 | 4820 | browser | 103 | 4780 | success |
| https://api.semanticscholar.org/graph/v1/paper/arXiv:2609.01595?fields | 2493 | 0 | HTTP 500: {"ok":false,"error": | 10089 | 0 | error CRAWL_LIVECRAWL_TIMEOUT |
| https://www.postgresql.org/docs/current/logical-replication.html | 337 | 2479 | http | 81 | 3262 | success |
| https://www.reddit.com/r/LocalLLaMA/top/?t=week | 6681 | 233 | browser | 84 | 0 | error SOURCE_NOT_AVAILABLE |
| https://news.ycombinator.com/ | 335 | 4683 | http | 99 | 3943 | success |
| https://exa.ai/pricing | 408 | 4270 | http | 91 | 5231 | success |
| https://www.home-assistant.io/blog/ | 171 | 2639 | http | 92 | 6266 | success |
| https://huggingface.co/unsloth | 2250 | 6853 | browser | 123 | 3449 | success |

Exa spend this leg: $0.013
