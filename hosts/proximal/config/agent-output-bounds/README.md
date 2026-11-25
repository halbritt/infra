# Agent Tool Output Bounds (`PROXIMAL-15` / `C2a`)

Canonical output-bounding policy, surgical config sync script, and bounded command wrapper for `proximal` agent harnesses.

## Canonical-to-Installed Mapping

| Repo file (`hosts/proximal/config/agent-output-bounds/`) | Installed target / role |
|---|---|
| `policy.json` | Desired per-harness output caps (Codex, Claude Code, OpenCode) |
| `sync_bounds.py` | Idempotent surgical `--check` / `--apply` / `--revert` sync for `~/.codex*/config.toml`, `~/.claude*/settings.json`, `~/.config/opencode/opencode.json` |
| `bounded-exec` | `~/.local/bin/bounded-exec` — host command wrapper spooling full output to `~/.cache/bounded-output/` |

## Per-Harness Mechanisms & Caps

1. **Codex (`0.172.0` — `~/.codex/config.toml`, `~/.codex-harm/config.toml`, `~/.codex-3/config.toml`)**
   - Top-level TOML key `tool_output_token_limit = 6000` (placed before the first `[section]` header).
   - Codex truncates inline head+tail without spilling to disk; `6000` tokens (~24 KB) preserves error/stack context while eliminating multi-hundred-KB command floods.
2. **Claude Code (`2.1.332` — `~/.claude/settings.json`, `~/.claude-harm/settings.json`)**
   - `"bashOutputMaxChars": 12000` (clamped `4000..128000` by Claude Code; replaces `BASH_MAX_OUTPUT_LENGTH` and persists excess to disk with a preview + path).
   - `"env"`: `"BASH_MAX_OUTPUT_LENGTH": "12000"`, `"MAX_MCP_OUTPUT_TOKENS": "8000"`, `"CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS": "12000"`.
   - Note: `CLAUDE_CODE_MAX_OUTPUT_TOKENS` caps *model generation* tokens, not tool output, and is intentionally left untouched.
3. **OpenCode (`~/.config/opencode/opencode.json` + Cairn `opencode-install`)**
   - `"tool_output": {"max_lines": 500, "max_bytes": 16384}` (tightens OpenCode's native `2000` lines / `51200` bytes; excess spills to `~/.local/share/opencode/tool-output/`).
   - Cairn's OpenCode custom tools (`~/.config/opencode/cairn.json` + `~/.config/opencode/tools/cairn.ts`) are installed by `cairn opencode-install` (`tokens: 16000`, `max_tokens: 160000`, `output_max_bytes: 12000`).
4. **Agy (`CAIRN-825`)**
   - Per owner decision `CAIRN-825`, `~/.local/bin/agy` remains the raw ELF binary (never wrapped with `cairn-term-launch`). Agy already truncates tool output internally and inherits bounded Cairn MCP responses via `~/.local/bin/cairn-messaging-mcp` once re-pinned to the updated `cairn` build.
5. **Host Command Wrapper (`~/.local/bin/bounded-exec`)**
   - Defaults: `BOUNDED_EXEC_MAX_BYTES=16384`, `BOUNDED_EXEC_MAX_LINES=300`.
   - When exceeded, spools full stdout+stderr (`0600`) to `~/.cache/bounded-output/<ts>-<pid>.log` (never `/tmp`), and emits exit code/signal + head + unique error/diagnostic lines + tail + exact log path.

## Usage, Opt-Outs, and Rollback

Check drift without modifying host configs:

```sh
python3 hosts/proximal/config/agent-output-bounds/sync_bounds.py --check
```

Apply policy (writes pre-change backups under `~/.local/state/agent-output-bounds/`):

```sh
python3 hosts/proximal/config/agent-output-bounds/sync_bounds.py --apply
install -m 0755 hosts/proximal/config/agent-output-bounds/bounded-exec ~/.local/bin/bounded-exec
```

Opt-outs & rollback:

- **Per-command wrapper opt-out:** `BOUNDED_EXEC_RAW=1 bounded-exec ...` (or `BOUNDED_EXEC_MAX_BYTES=0`).
- **Per-run Codex override:** `codex -c tool_output_token_limit=30000 ...`
- **Per-run Claude override:** `BASH_MAX_OUTPUT_LENGTH=100000 MAX_MCP_OUTPUT_TOKENS=25000 claude ...`
- **Cairn MCP / CLI / OpenCode opt-out:** `CAIRN_UNBOUNDED_TOOL_OUTPUT=1` (or `--output-max-bytes 0`).
- **Full config revert:** `python3 hosts/proximal/config/agent-output-bounds/sync_bounds.py --revert`
