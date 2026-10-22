# Idle stop and usage tracking for `agent-ee-gate-c4`

Owner request 2026-10-22: track the C4 host's use and shut it down when it goes
idle. Left running it costs about $1.31/h, about $955/month. Stopped, it costs
its disk only (about $63/month).

| Piece | Installed at | What it does |
|---|---|---|
| [infra-idle-stop](infra-idle-stop) | `/usr/local/sbin/` on c4 | Each minute: appends one usage sample to `/var/log/infra-usage/usage.jsonl`. After 30 consecutive idle minutes it runs `systemctl poweroff`, which stops the GCE instance |
| [infra-idle-stop.service](infra-idle-stop.service), [.timer](infra-idle-stop.timer) | `/etc/systemd/system/` on c4 | Runs it 1 min after boot, then every minute |
| [infra-usage.logrotate](infra-usage.logrotate) | `/etc/logrotate.d/infra-usage` on c4 | Monthly, 12 kept. The log lives on the persistent disk, so it survives stops |
| [install.sh](install.sh) | — | Installs the above (command in its header) |
| [c4-usage](c4-usage) | run from proximal | Status, start/stop/preempt history and run hours with estimated compute cost from the GCE audit log, and the busy share from the VM log |

## Idle rule

A sample is **busy** if any of these is true:

- a Docker container is running (gates, `ae-ci-exec`);
- a `halbritt` process older than 60 s is running. Login plumbing, plain
  shells, `sleep` and zombies don't count: `systemd`, `(sd-pam)`, `sshd`,
  `sshd-session`, `sftp-server`, `bash`, `sh`, `tmux`. Agent workers (`claude`,
  `codex`, `node`), `docker`, `python3`, `kicad-cli` and the like all count;
- the 1-minute load is 2.0 or more.

The 60 s age floor ignores the short probes that touch the host all day:
launch.py's `pick_host` (`cat /proc/loadavg; nproc`) and the 15-minute credential
mirrors (`python3 -I -c …`). A busy sample resets the idle clock. The clock lives
in `/run`, so each boot starts a fresh 30-minute window: a host started by hand
gets 30 minutes to receive work.

## When c4 is stopped

- launch.py's `pick_host` reports `agent-ee-gate-c4 unreachable` and places
  work on the other hosts. The credential mirrors log `remote mirror failed;
  retrying next tick` and catch up on the first tick after a start. Nothing
  starts c4 automatically.
- Start it with:

  ```sh
  gcloud compute instances start agent-ee-gate-c4 --zone us-central1-a --project heath-stuff
  ```

  A Spot start can fail with code 8 (no capacity); it did twice on 2026-10-22
  between 03:13 and 03:14 PDT. Retry later. Tailscale, the `ssh agent-ee-gate-c4` alias
  and the timer all come back on their own.

## Usage

```sh
~/git/infra/hosts/gcp-gate/config/idle-stop/c4-usage --days 7
ssh agent-ee-gate-c4 'journalctl -u infra-idle-stop -n 5 -o cat'   # live verdicts
```

First report, 2026-10-22 (3 days): created 2026-10-21 21:32 PDT, preempted
01:03, started 01:25, preempted 03:11, restarts failed for lack of capacity,
started 10:37. 7.3 h run time, about $9 compute.

Failed operations (`severity ERROR` or a non-zero status code) are skipped. They
include quota-refused creates and capacity-refused starts.

## Rollback

```sh
ssh agent-ee-gate-c4 'sudo systemctl disable --now infra-idle-stop.timer && sudo rm /etc/systemd/system/infra-idle-stop.{service,timer} /usr/local/sbin/infra-idle-stop /etc/logrotate.d/infra-usage && sudo systemctl daemon-reload'
```

The usage log in `/var/log/infra-usage/` can be kept or removed.
