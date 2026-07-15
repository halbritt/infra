# WezTerm subsystem agent guidance

Read `README.md` before changing this subsystem.

- This directory tracks the headless WezTerm mux installation on `proximal` and
  the client profile needed to attach to it. It does not contain SSH keys,
  agent sockets, host keys, or other credentials.
- Keep the client and server on the exact same WezTerm version. The `nightly`
  release URL is mutable; update both `WEZTERM_VERSION` and `WEZTERM_SHA256` in
  `install-user.sh` from the same downloaded asset.
- Do not stop `wezterm-mux-server` as part of an install. First inspect live
  panes with `wezterm cli --prefer-mux list --format json`; stopping the server
  terminates every process hosted by those panes.
- `server.lua` is canonical for
  `~/.config/wezterm/wezterm.lua` on `proximal`. `client-proximal.lua` is the
  canonical client profile for the operator's Mac and Windows machines.
- The client intentionally leaves `front_end` unset so WezTerm uses its default
  GPU renderer. Software rendering is a diagnostic fallback, not desired state.
- Re-run the verification and persistence checks in `README.md`, then commit and
  push. Never leave this repo dirty or ahead of `origin/master`.
