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
