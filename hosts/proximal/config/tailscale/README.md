# Tailscale expiry warnings

On October 13, 2026, proximal was unreachable over Tailscale because its node key
had expired. The daemon reported `nodeKeyExpired=true` on October 12 after an
update restart. A later JSON response error obscured that original cause.
Owner reauthentication restored the same address, `100.85.100.81`, with expiry
April 11, 2027 at 23:51 UTC. Both SSH directions to peecee worked afterwards.

`expiry_alert.py` reads the current `tailscale status --json` every hour. It sends
an SMS on entry into the 14-day and 7-day windows, then once per UTC day with
three days or fewer remaining. An already-offline daemon gets a daily warning.
Renewing the key changes the observed expiry automatically. Null expiry means
expiry is disabled; missing or malformed fields fail the unit instead of
reporting a healthy observation. No expiry-policy change is made.

Delivery uses the same installed Praxis carrier library and local Quectel
gateway as `agent-usage-alert.service`; it does not require the retired Praxis
daemon. The egress privacy gate remains enabled. Credentials and the owner's
number come from the existing private environment file outside Git. No tailnet
connection is required for the local modem to send SMS.

Private JSON receipts and an exclusive lock survive restarts. Intent is fsynced
before sending. Explicit rejection can retry at the next hour; an uncertain
transport outcome remains pending and fails subsequent attempts for that warning
instead of risking duplicates. Inspect the gateway journal before clearing a
pending receipt. A new threshold/day can send a new warning. HTTP acceptance
means gateway enqueue, not confirmed handset receipt. The gateway's queue is
in-memory, so loss after enqueue remains a limitation. Timer/process failures
appear in the user journal; this monitor is not independently monitored.

## Install

From the infrastructure checkout:

```sh
install -Dm644 hosts/proximal/config/tailscale/expiry_alert.py ~/.local/lib/tailscale-expiry-alert/expiry_alert.py
install -Dm644 hosts/proximal/config/tailscale/tailscale-expiry-alert.service ~/.config/systemd/user/tailscale-expiry-alert.service
install -Dm644 hosts/proximal/config/tailscale/tailscale-expiry-alert.timer ~/.config/systemd/user/tailscale-expiry-alert.timer
systemctl --user daemon-reload
systemctl --user enable --now tailscale-expiry-alert.timer
systemctl --user start tailscale-expiry-alert.service
```

State: `~/.local/state/tailscale-expiry-alert/`, protected by service umask 0077.
Requires `/usr/bin/tailscale`, Python 3, `~/git/praxis/src`, the existing
`~/.config/praxis/praxisd.env`, and the running local SMS gateway.

```sh
python3 -m unittest discover -s hosts/proximal/config/tailscale -p 'test_*.py'
python3 hosts/proximal/config/tailscale/expiry_alert.py --dry-run
systemctl --user list-timers tailscale-expiry-alert.timer
journalctl --user -u tailscale-expiry-alert.service
```

Disable with `systemctl --user disable --now tailscale-expiry-alert.timer`.
