# Kernel settings (proximal)

Host-wide `sysctl` values for this box. Each file here is installed under
`/etc/sysctl.d/` with the same name.

| Canonical file | Installed location | Setting |
|---|---|---|
| [`60-inotify-instances.conf`](60-inotify-instances.conf) | `/etc/sysctl.d/60-inotify-instances.conf` | `fs.inotify.max_user_instances = 1024` (kernel default 128) |

`kernel.apparmor_restrict_unprivileged_userns` is not recorded here. Its file
belongs to [shared/agent-ee](../../../../shared/agent-ee/README.md).

## inotify instance limit, 2026-11-27

**Why.** The kernel gives each user 128 inotify instances by default. On
2026-11-27 at 23:10 PST `halbritt` held all of them, and `inotify_init1`
returned `EMFILE` ("Too many open files") to every new caller. It showed up as
18 failures in `make test` of `~/git/cairn` at 44eff6ba (21:57 to 23:09 PST):
six lifecycle test modules create an inotify instance in their fixture, and each
failed there before the code under test ran. The log is
`~/.cache/cairn-sv-stream-logs/make-test-44eff6ba.log`.

Open inotify descriptors by process name at 23:10 PST, 124 counted:

| Process name | Processes | Descriptors |
|---|---|---|
| `bambustu_main` (Bambu Studio) | 19 | 38 |
| `agy` | 4 | 28 |
| `WebKitNetworkProcess` | 19 | 19 |
| `codex` | 9 | 18 |
| `language_server` | 1 | 7 |
| `claude` | 6 | 6 |
| `dbus-daemon`, `chrome-headless`, `wezterm` (2 each); `tail`, `dropbox` (1 each) | 8 | 8 |

Two causes:

- **Normal demand is close to the default.** An Agy session holds 7 instances,
  a Codex session 2 and a Claude session 1. Ten Agy, 20 Codex and 20 Claude
  sessions need 130.
- **Slicer GUIs that print jobs left running.** 21 Bambu Studio processes
  started under `xvfb-run` since 2026-11-24 were still running. Each holds 2
  instances and its WebKit network process holds 1. They were not stopped by
  this change. PROXIMAL-16 tracks them.

**Value.** 1024 is eight times the default. An idle instance costs little
kernel memory. The number of watches has its own limit
(`fs.inotify.max_user_watches`, 1004869 here, not changed).

**Applied live** by agent-3302 at 23:16:20 PST. No process was restarted.

```sh
sudo install -m 0644 -o root -g root sysctl/60-inotify-instances.conf /etc/sysctl.d/60-inotify-instances.conf
sudo sysctl -p /etc/sysctl.d/60-inotify-instances.conf
```

A new `inotify_init1` call succeeded right after. The six test modules were then
started again on the same tree; PROXIMAL-16 has the result.

**Check:**

```sh
cat /proc/sys/fs/inotify/max_user_instances
for f in /proc/[0-9]*/fd/*; do [ "$(readlink "$f" 2>/dev/null)" = anon_inode:inotify ] && echo "$f"; done | wc -l
```

The first command prints 1024. The second counts the open inotify descriptors
of the processes the caller can read. A descriptor shared after a fork is
counted once for each process, so the count can be above the kernel's count.

**Revert:**

```sh
sudo rm /etc/sysctl.d/60-inotify-instances.conf
sudo sysctl -w fs.inotify.max_user_instances=128
```

Processes keep the instances they already hold. With more than 128 in use, new
callers fail again until the count falls.
