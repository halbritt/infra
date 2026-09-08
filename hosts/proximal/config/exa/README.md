# exa — Exa search API for agents (`exa-search` CLI)

[Exa](https://exa.ai) is the hosted neural web-search API adopted on `proximal` on
2026-09-08 as the **primary search backend for Council members and research grounding**,
after a blind 40-query comparison beat the on-box wigolo search decisively (nDCG@5 0.94 vs
0.54; write-up in [`../wigolo/exa-comparison-2026-09-08/`](../wigolo/exa-comparison-2026-09-08/README.md)).
wigolo stays for page fetch and as the keyless fallback search.

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

## Where it is wired

- **Council** (`~/git/council`, release of 2026-09-08): a member with `capabilities.web` is told to
  search with `exa-search` and read pages with `wigolo fetch` (with a bigger `--max-tokens-out`
  for papers), falling back to `wigolo search` if exa-search fails. Isolated Claude members get
  `Bash(exa-search:*)` + `Bash(wigolo:*)`; opencode policy revision 3 opens `bash` to
  `exa-search *` and `wigolo *`. The service resolves both CLIs from its own PATH at startup and
  diagnoses a missing one as `web_capability_unavailable`.
- Not wired: wigolo's own engine pool (it has no Exa adapter), the Claude Code MCP layer.

## Guardrails

- Queries and nothing else leave the box; Exa sees the query text and returns public web content.
  Do not route private material through it.
- Watch the free credit: at ~$0.007 a search, a runaway agent loop can burn a month's credit in
  ~1,400 calls. The CLI clamps `--max-results` to 20 and makes exactly one request per invocation.
- The key file is the only credential; rotating it in the Exa dashboard and rewriting
  `~/.config/exa/env` is the whole rotation.
