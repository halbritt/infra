# systemd-user

Host-level configuration of the **systemd user manager** (`user@1000.service`) —
the environment every `systemctl --user` unit inherits.

## PATH for user units (2026-07-07)

`environment.d-50-user-path.conf` → installed at
`~/.config/environment.d/50-user-path.conf`. Prepends
`~/.local/bin:~/.npm-global/bin` to the user manager's PATH.

**Why (root cause, worth remembering):** the box carries two Claude Code
installs — `/usr/local/bin/claude` (root npm install, **v1.0.60**, July 2025,
stale: its default model `claude-opus-4-20250514` is retired and its MCP
handling 400s on current tool configs) and `~/.local/bin/claude` (**v2.x**,
current). The systemd user manager's default PATH has no `~/.local/bin`, so any
user unit that execs `claude` silently got the stale 1.0.60. This broke every
**striatum-next LLM lane** launched from a wake-timer drive: the lane runtime
died with API errors (`model not found` / MCP tool-name 400) recorded only in
the submission's exhaust transcripts, surfacing as `runtime_crash` /
`bounds_exhausted` escalations on the graph. The claude-code backend's version
*probe* runs in the dispatching shell's env and reported v2.x, masking the
mismatch.

Diagnosed 2026-07-07 while driving the gpu-fleet graph; verified with
`backend-conformance -smoke` (fails on default PATH, green with this file).
Applied immediately via `systemctl --user set-environment PATH=…`; this file
makes it survive reboot.

Alternative rejected for now: deleting the stale root install (`sudo npm -g rm
@anthropic-ai/claude-code`) — destructive, and other things may pin it; the
PATH fix is additive and sufficient. If the root install is ever removed, this
file is still correct.
