# Dropbox on Linux

Each enrolled host runs the official x86-64 Linux daemon as the owner.
The user service starts with the systemd user manager. On these hosts
login lingering starts that manager at boot, including on headless Talos.
Each daemon has its own account link and uses Dropbox's default folder.

## Installation

Use the [Dropbox Linux distribution](https://www.dropbox.com/download?plat=lnx.x86_64)
and the [official CLI](https://linux.dropbox.com/packages/dropbox.py).
For a fresh installation, verify the archive's [detached signature](https://www.dropbox.com/download?plat=lnx.x86_64&signature=1)
with the Dropbox signing key included in the official CLI. Extract the
verified archive into the owner's home directory to create
`~/.dropbox-dist/`. Install the CLI as `~/.local/bin/dropbox` (0755).
Install and start the unit from the infra checkout as the owner:

```sh
install -Dm644 shared/dropbox/dropbox.service ~/.config/systemd/user/dropbox.service
systemctl --user daemon-reload
systemctl --user enable --now dropbox.service
~/.local/bin/dropbox status
```

On first start, open the per-host URL printed by the status command in a
browser signed into the desired Dropbox account. Account approval starts
sync. Check available space on the target filesystem before linking.
Keep pairing URLs, account state (`~/.dropbox/`) and synced files outside Git.

## Verification and rollback

Use `systemctl --user is-enabled dropbox` and `systemctl --user is-active dropbox`
to check startup and runtime. Use `~/.local/bin/dropbox status` to check
account linking and sync progress. To stop synchronization and disable startup,
run `systemctl --user disable --now dropbox.service`. Leave the synced folder
in place to preserve local files.
