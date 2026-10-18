# tmp-groom — /tmp age-out

Keeps `/tmp` (on the root LV, not tmpfs) from filling `/`. On 2026-10-17 it held
377G under Ubuntu's stock 30-day rule.

| File | Installed at |
|---|---|
| `tmp.conf` | `/etc/tmpfiles.d/tmp.conf` (shadows `/usr/lib/tmpfiles.d/tmp.conf`) |
| `systemd-tmpfiles-clean.timer.override.conf` | `/etc/systemd/system/systemd-tmpfiles-clean.timer.d/override.conf` |

Rule: `D /tmp 1777 root root amM:2d`. A file goes once it has been neither read
nor written for 2 days. A directory goes once it is empty and its mtime is
2 days old. ctime is deliberately ignored: tree moves and hardlinks refresh it,
and under the default `abcmABM` it kept 130G+ of untouched files. The stock
timer runs the cleaner daily; the override makes it every 6h.

Install / verify:

```bash
sudo install -m 644 tmp.conf /etc/tmpfiles.d/tmp.conf
sudo install -D -m 644 systemd-tmpfiles-clean.timer.override.conf \
  /etc/systemd/system/systemd-tmpfiles-clean.timer.d/override.conf
sudo systemctl daemon-reload && sudo systemctl restart systemd-tmpfiles-clean.timer
systemd-tmpfiles --cat-config | grep '^D /tmp'
sudo systemctl start systemd-tmpfiles-clean.service   # run now
```

Long-lived work that needs files idle in `/tmp` for more than 2 days should use
`/var/tmp` or a project directory instead.
