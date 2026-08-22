# CAPLAB advisory leaderboard on `proximal`

Desired state for the tailnet-only, read-only review-capability leaderboard
of the CAPLAB advisory-selection campaign. A static HTML page generated in
the caplab repo; this subsystem records how it is served on this host.

Inspection surface only: no mutation endpoint, no public route, no evidence
admission. Rankings on the page are cohort-scoped (instrument × custody ×
seed) and never merged — see the page's own comparability rule.

## At a glance

| | |
|---|---|
| tailnet URL | `https://proximal.tail0ecc2e.ts.net:18082/` |
| local origin | `http://127.0.0.1:18082/` (loopback only) |
| tailnet front | Tailscale Serve HTTPS `:18082` → loopback `:18082` |
| unit | `caplab-leaderboard.service` (systemd **user** unit) |
| served file | `~/git/caplab/docs/leaderboard/index.html` (git-tracked) |
| regenerate | `make -C ~/git/caplab leaderboard` (no restart needed) |

The unit serves the git-tracked directory directly, so `make leaderboard`
(run after each sweep's claims land) refreshes the page with no service
action. Distinct from `caplab-dashboard` (`:8784`), which is the historical
study-results app from the `books` repo.

## Install / rollback

```bash
cp caplab-leaderboard.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now caplab-leaderboard
tailscale serve --bg --https=18082 http://127.0.0.1:18082

# rollback
tailscale serve --https=18082 off
systemctl --user disable --now caplab-leaderboard
```
