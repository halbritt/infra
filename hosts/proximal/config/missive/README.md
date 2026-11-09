# proximal/missive — text-message archive

Desired state and provenance for **missive** on proximal: a durable, searchable archive of the
owner's iMessage/SMS/RCS history, served read-only to agents. Source code, design and
operations live in the repository `halbritt/missive` (`~/git/missive`, see its README).
Deployed 2026-11-09. Values only, no credentials.

## At a glance

| | |
|---|---|
| source | archon `imessage-vm-bb-readonly` gateway, `https://archon.tail0ecc2e.ts.net:8766` ([archon imessage-vm](../../../archon/config/imessage-vm/README.md)) |
| database | `missive` in the `18/main` cluster, owner `halbritt` (peer auth); extensions `vector`, `pg_trgm` |
| attachments | `~/.local/share/missive/attachments/` (content-addressed, 0700 dirs / 0600 files), in the home restic backup |
| embeddings | Ollama `nomic-embed-text:latest` (loopback `:11434`) |
| LLM | `qwen3.8-27b` via `gpu-fleet-run` exact-model lease (proximal slot 0, `localhost:8081`) |
| transcription | faster-whisper `small.en` int8 on CPU (model cached in `~/.cache/huggingface`) |
| agent endpoint | MCP `127.0.0.1:8770/mcp`; tailnet `https://proximal.tail0ecc2e.ts.net:8770/mcp` (`tailscale serve --https=8770`) |
| secrets (names only) | `~/.config/missive/bb-readonly-token` (gateway client token), `~/.config/missive/mcp-token` (MCP bearer), both 0600 |

## Units (system, `User=halbritt`)

| unit | role |
|---|---|
| `missive-sync.service` | ingestion loop: new messages every 15 s by ROWID cursor; recent window plus edits and unsends every 5 min; chats every 10 min; contacts every 6 h; full reconcile daily |
| `missive-worker.service` | identities, segments, embeddings, attachment downloads, voice-note transcripts (Nice 10, CPUWeight 50, MemoryMax 4G) |
| `missive-mcp.service` | read-only MCP server (10 tools) |
| `missive-enrich.timer` → `missive-enrich.service` | up to 5 min of LLM enrichment under a lease, then 10 min idle; exit 75 (slot busy) counts as success |

Install or refresh: `cd ~/git/missive && uv sync && sudo deploy/systemd/install.sh`.

Claude Code: user-scope MCP server `missive` on proximal (loopback URL) and archon (tailnet
URL). Both use the headersHelper `~/.local/bin/missive-mcp-headers` (from
`~/git/missive/client/`), so the token is not stored in `~/.claude.json`.

## Rollback

```sh
sudo systemctl disable --now missive-sync missive-worker missive-mcp missive-enrich.timer
sudo tailscale serve --https=8770 off
sudo rm /etc/systemd/system/missive-{sync,worker,mcp,enrich}.service /etc/systemd/system/missive-enrich.timer
sudo systemctl daemon-reload
claude mcp remove missive -s user          # also on archon
# Data is kept. To discard it as well: dropdb missive; rm -r ~/.local/share/missive
```

## Verification (2026-11-09)

- Backfill: 49,473 messages in about 70 s (2025-11-27 → now), 577 chats, 459 contacts with
  584 contact points, 1,785 attachments (4.1 GB of metadata, archived by the worker over the
  first hour). A full reconcile found 0 source deletions.
- Identity at first pass: 94.5 % of received messages came from addresses resolved by a
  Contacts card or rule. The first leased LLM run named 11 of 17 unknown senders, citing
  evidence (self-introductions, business notices).
- MCP: 401 without a token on loopback and the tailnet. With the token, `tools/list`
  returned 10 read-only tools. Every tool was exercised, including `not_found` and
  `invalid_argument` errors. Claude Code reports `✔ Connected` on proximal and on archon.
- Tests: `uv run pytest` passes 11 tests, including disposable-database tests of
  idempotent re-ingest, kept edit and unsend history, contact identity, and segment
  enrichment that survives rebuilds and is invalidated by edits.
