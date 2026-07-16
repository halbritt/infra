# WezTerm remote multiplexer

Desired state for the **headless WezTerm SSH multiplexer** on `proximal`, plus
the matching client profile used by macOS and Windows. Programs and scrollback
live in the mux on `proximal`; each client imports those remote windows, tabs,
and panes into its local WezTerm GUI.

Current pinned build: **`20260715-174104-3658b656`**, Ubuntu 24.04 x86_64.
The server is installed without root under `~/.local/opt`, with stable command
symlinks under `~/.local/bin`.

## Why this exists

On 2026-07-15, iTerm2 3.6.11 on macOS 26.3.1 rendered stale, cell-aligned ANSI
backgrounds after an LG 6K display woke. iTerm's Metal renderer was already
disabled. The macOS log showed WindowServer re-adding the external display and
moving windows between display spaces during wake, which forced rapid terminal
geometry changes. A cable reconnect forced a redraw but was not a sustainable
recovery path.

WezTerm was selected because one implementation supplies a native tab/pane UI
on both macOS and Windows and can attach those GUIs to a persistent headless mux
on `proximal`. This replaces the asymmetric iTerm `tmux -CC` versus Windows
Terminal arrangement. `tmux` remains installed and available as a fallback.

The initial verification proved mux persistence across a complete Mac GUI
termination and relaunch. It did **not** yet prove that the original display-wake
artifact is fixed; that requires repeated real sleep/wake cycles.

## Files and install paths

| repo file | installed to | owner/mode | notes |
|---|---|---|---|
| [`install-user.sh`](install-user.sh) | run from this checkout | `halbritt` 0755 | installs the pinned Ubuntu asset, stable symlinks, and server config; never restarts a live mux |
| [`server.lua`](server.lua) | `~/.config/wezterm/wezterm.lua` on `proximal` | `halbritt` 0644 | login bash, 100,000-line scrollback, automatic updates disabled |
| downloaded pinned asset | `~/.local/opt/wezterm-20260715-174104-3658b656/` | `halbritt` | SHA-256 checked before extraction |
| stable executable links | `~/.local/bin/{wezterm,wezterm-mux-server}` | `halbritt` symlinks | resolve through `~/.local/opt/wezterm-current` |
| [`client-proximal.lua`](client-proximal.lua) | Mac: `~/.config/wezterm/wezterm.lua`; Windows: `%USERPROFILE%/.wezterm.lua` | operator 0644 | canonical cross-platform client profile; assumes an SSH config host named `proximal` |

No SSH keys, agent sockets, host keys, or credentials belong in this repo.

## Install or reconcile the host

```bash
cd ~/git/proximal
./wezterm/install-user.sh
readlink -f ~/.local/bin/wezterm
wezterm -V
wezterm-mux-server --version
```

The installer is idempotent when the pinned target already exists. The GitHub
`nightly` asset URL is mutable, so a fresh install additionally requires its
download to match both the pinned SHA-256 and embedded WezTerm version. If the
upstream asset moves, the installer fails rather than accepting drift.

The installer deliberately does not stop a running mux. Replacing a mux server
terminates the shells and tasks in every hosted pane.

## Configure a client

Install the same WezTerm build as the server and install
`client-proximal.lua` at the client config path above. The client profile:

- opens directly into the `proximal` SSH mux
- uses `/home/halbritt/.local/bin/wezterm` as the remote executable
- leaves `front_end` unset, preserving WezTerm's default GPU renderer
- uses JetBrains Mono with Cascadia Mono and Menlo fallbacks
- shows a high-contrast scrollbar thumb with a three-cell minimum height
- maps horizontal thumbwheel events to three-line vertical scrollback movement
- disables automatic updates so protocol versions remain coordinated

The client reads connection details and authentication from its normal SSH
configuration. It expects a concrete `Host proximal` entry. Keep the SSH config
and all key material outside this repository.

Start or attach:

```bash
wezterm connect proximal
```

`Command-T` on macOS creates another tab in the current remote domain. Quitting
the GUI disconnects the client while leaving remote panes alive. Closing an
individual tab or pane intentionally terminates that remote pane's process.

### Scrollback and full-screen applications

The 100,000-line history applies to the terminal's normal screen buffer.
Full-screen applications can switch to the alternate screen buffer, which has no
native WezTerm scrollback. Claude Code's `tui: fullscreen` renderer does this.
Keep `tui` set to `default` in `~/.claude/settings.json`, or run `/tui default`
inside Claude Code, when terminal-native scrollback is required. Changing the
saved setting affects the next Claude process; an already-running full-screen
session must relaunch before it starts writing to normal scrollback.

## Verify persistence

On `proximal`, inspect the server and hosted panes:

```bash
pgrep -af wezterm-mux-server
wezterm cli --prefer-mux list --format json
```

Record the mux PID and a pane's `tty_name`, quit the client GUI, and confirm both
are unchanged. Relaunch WezTerm and confirm that it imports the same pane. The
2026-07-15 deployment passed this check: the Mac GUI PID changed while the mux
PID and remote PTY remained stable, and both local and remote logs contained no
warnings or protocol errors.

## Coordinated upgrades

WezTerm's SSH mux expects compatible client and server builds. Upgrade it as a
coordinated maintenance event:

1. Inspect `wezterm cli --prefer-mux list --format json` and wait until every
   remote pane can be terminated.
2. Download the intended Ubuntu 24.04 x86_64 nightly asset and record its
   embedded `wezterm -V` plus SHA-256.
3. Update `WEZTERM_VERSION` and `WEZTERM_SHA256` together in
   `install-user.sh`, then run the installer.
4. Stop the old mux only after the hosted work is disposable, and reconnect
   using clients installed from that same nightly build.
5. Repeat the persistence check, update this README/changelog, commit, and push.

Do not enable unattended upgrades on either side. A coordinated old version is
safer than an automatically mismatched client and server.
