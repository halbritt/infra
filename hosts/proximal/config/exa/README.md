# exa — Exa search and page reading for agents (`exa-search`, `exa-fetch`)

[Exa](https://exa.ai) is the hosted neural web-search API adopted on `proximal` on
2026-09-08 as the **primary search backend for Council members and research grounding**,
after a blind 40-query comparison beat the on-box wigolo search decisively (nDCG@5 0.94 vs
0.54; write-up in [`exa-comparison-2026-09-08/`](exa-comparison-2026-09-08/README.md)).
Since 2026-11-11 it is the only web search and page reader on this host: the owner retired
wigolo, and `exa-fetch` replaced `wigolo fetch` (see **Retired: wigolo** below).

- **Account:** free tier (signed up 2026-09-08; $20 signup credit, $10/month non-rolling, no
  card on file, 10 QPS). `auto` search is $7 per 1,000 requests, so the monthly credit is
  ~1,400 searches. Check the dashboard occasionally: <https://dashboard.exa.ai>.
- **Key:** `~/.config/exa/env` (mode 600, `EXA_API_KEY=…`). Never in git, never in a member's
  environment — the CLI reads the file itself from the account's passwd home, so it works under
  Council's private per-member `HOME`.
- **Docs:** <https://exa.ai/docs/reference/search-api-guide-for-coding-agents> (canonical for
  search types, parameters, and response shape; the CLI follows it as of 2026-09-08).

## `exa-search` — the CLI

[`exa-search`](exa-search) is a stdlib-only Python wrapper over `POST /search`, installed by
symlink at `~/.local/bin/exa-search` (on the systemd user manager's PATH, which is where the
Council service resolves it). It always prints exactly one JSON object on stdout.

```bash
exa-search "<query>" [--max-results N] [--news] [--type auto|fast|instant|deep-lite|deep|deep-reasoning]
           [--include-domains a.com,b.org] [--exclude-domains …] [--max-age-hours H] [--text [--max-chars N]]

exa-search "systemd Restart=on-failure versus Restart=always" --max-results 5
exa-search "Anthropic announcement" --news
exa-search "position bias in LLM-as-a-judge" --type deep --max-results 10
```

Output: `{query, type, category, results:[{title,url,published,author,highlights[]}], result_count,
fetched_at, latency_ms, cost_dollars, request_id}`. `--text` swaps `highlights` for capped page
`text`. Errors print `{"error": …}` and exit non-zero (3 no key, 4 HTTP error, 5 network).

Reproduce: `ln -sfn ~/git/infra/hosts/proximal/config/exa/exa-search ~/.local/bin/exa-search`.

## `exa-fetch` — page reading

[`exa-fetch`](exa-fetch) is the same kind of stdlib wrapper over `POST /contents`, installed at
`~/.local/bin/exa-fetch`. It reads up to 10 URLs per call, including JS pages and PDFs.

```bash
exa-fetch <url> [<url> ...] [--max-chars N] [--fresh]

exa-fetch https://en.wikipedia.org/wiki/Systemd
exa-fetch https://arxiv.org/abs/2306.05685 --max-chars 60000    # papers (cap 200000)
```

Output: `{pages:[{url,title,published,author,chars,truncated,text} | {url,error}], page_count,
fetched_at, latency_ms, cost_dollars, request_id}`. The default cap is 20000 characters per page.
`--fresh` forces a live crawl (`maxAgeHours: 0`). A page Exa cannot read carries its
`statuses[]` tag as `error`. Exit codes: 3 no key, 4 HTTP error, 5 network, 6 no page read.
Measured 2026-11-11: $0.001 a page, ~0.2 s for a cached page.

Reproduce: `ln -sfn ~/git/infra/hosts/proximal/config/exa/exa-fetch ~/.local/bin/exa-fetch`.

## Where it is wired

- **Council** (`~/git/council` `2da200b`, deployed 2026-11-11): a member with `capabilities.web`
  searches with `exa-search` and reads pages with `exa-fetch` (renderer
  `council-native-member-input/11`). Isolated Claude members get `Bash(exa-search:*)` +
  `Bash(exa-fetch:*)`, and opencode policy revision 4 opens `bash` to `exa-search *` and
  `exa-fetch *`. The service resolves both CLIs from its own PATH and diagnoses a missing one
  as `web_capability_unavailable`.
- **Relay** (`~/git/relay` 0.8.0, `7dad9f8`): Exa is the only grounding provider, for search and
  for reading known URLs through `/contents`.
- **ai-newsroom** (`010b87d`): the `exa` source plus the daily brief's web searches (at most 5
  queries per brief).
- **Hermes** outbreak-watch collector: Hermes's `web` toolset with `web.backend: exa`.
  Hermes has no Exa key, so the gateway uses Exa's keyless free tier (`mcp.exa.ai`);
  the key was not copied into `~/.hermes/.env`. Adding it there would switch every
  Hermes session's web tools to the paid account.
- **Agents:** the skillpack `exa` skill documents both CLIs.

## Guardrails

- Queries and nothing else leave the box; Exa sees the query text and returns public web content.
  Do not route private material through it.
- Watch the free credit: at ~$0.007 a search, a runaway agent loop can burn a month's credit in
  ~1,400 calls. The CLI clamps `--max-results` to 20 and makes exactly one request per invocation.
- The key file is the only credential; rotating it in the Exa dashboard and rewriting
  `~/.config/exa/env` is the whole rotation.

## Retired: wigolo (2026-11-11)

The owner retired wigolo, the keyless local search/fetch MCP server that had stayed on as the
page fetcher and fallback search after this comparison. Removed from proximal: the global npm
package, the `wigolo.service` daemon (`:3333`), `~/.wigolo` (~1 GB), the `~/git/wigolo`
source checkout, its MCP registrations (claude-harm profile, Hermes), the skills and rules it
had installed into Cursor and Hermes, member caches under `~/.council`, and update-bot's
maintenance of it. No other host had it. `config/wigolo/` was deleted from this repo; its
last content (audit, synthesis-model benchmarks, MCP block) is at commit `86e8859`.
