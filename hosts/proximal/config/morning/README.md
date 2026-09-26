# Morning household routine

Requested by the owner on 2026-09-26: a public web app for a school-day routine,
with spoken-code sign-in on the kid’s bedroom Mini and configurable schedules,
reminders, and voices.

Source: `/home/halbritt/git/announce/morning_app/`.
Documentation: `/home/halbritt/git/announce/docs/morning.md`.
Install `morning.service` to `~/.config/systemd/user/morning.service`, then
`systemctl --user daemon-reload` and `systemctl --user enable --now morning.service`.
The unit executes from the Announce checkout. Runtime uses Python's standard library.

Origin: `127.0.0.1:8878`. Public URL: `https://morning.harm.org`, through the
hostname-specific Cloudflare Tunnel ingress. Preserve the catch-all 404 rule.
Private configuration: `~/.config/announce/morning.json` (0600).
Bridge token: `~/.config/announce/morning-bridge-token` (0600), never committed.
Private state: `~/.local/share/announce/morning/morning.sqlite3` (SQLite WAL).

Authentication uses expiring, single-use, browser-bound spoken codes; all routine
state requires a session. HTTP `/healthz` reports scheduler liveness only.
Scheduled speech starts disabled. Login speech uses Luna through the existing
HA shared queue and respects quiet hours. Gemini reminders use the existing
Announce service; neither process nor HA policy is replaced.

Rollback: disable the Morning user unit, remove only its tunnel ingress from
both canonical configurations, reinstall both, and restart Cloudflared. Retain
private state for delivery review. Leave Announce and unrelated public routes intact.
