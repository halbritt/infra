# Google Home MCP recognition probe

Read-only client for the owner's October 7 request to test Google's familiar-face
API with a Heath doorbell ring. The client rejects all device-control tools before
loading credentials. The existing [Myra/Adam notification automation](../../../../devices/home-assistant-fernside/config/home-assistant-core/doorbell-notification-bridge.md)
remains the active unlock path. No API-to-lock automation is installed.

## Physical recognition test — 2026-10-08

After charging, live state at 10:32 PDT reported the doorbell online, attached,
fully charged and unplugged. The owner then rang the bell and confirmed "rang".
The API returned event `76515d74-aa7a-409f-8002-4bef92120ff6` with both a doorbell
track and a familiar-face track named **Heath**, category `FACE_CATEGORY_KNOWN`.

- Familiar-face track began at 11:02:23.403 PDT.
- Doorbell track began at 11:02:33.842 PDT.
- The containing history entry timestamp was 11:02:55.875 PDT.
- The successful retrieval was recorded at 11:03:28.632 PDT, 54.790 seconds after
  the ring. This is an upper bound on availability, not measured delivery latency.

The ten-minute capture at 10:32–10:42 PDT completed 53 successful polls without
events, before the owner rang at 11:02. A subsequent history query found the ring
and name together. This establishes fresh physical recognition through the API;
continuous-poll latency and recognition-to-unlock behavior remain unverified.
No device action was issued. The Myra/Adam Moto bridge remains the active unlock
source; the API probe has no connection to HA actions.

Private evidence is `~/.config/google-home-mcp/ring-recent.json` and
`ring-test-20261008T173227Z/summary.json`. Raw histories contain signed media URLs;
only the limited event/timing evidence above belongs in the repository.

## Setup evidence — 2026-10-07

- Enabled `home.googleapis.com` in existing Cloud project `heath-stuff`.
- Created Web OAuth client **Home doorbell test**, preserving existing `homeass`.
  The project's existing consent-screen name is **HA**. Added the owner as a test
  user; publishing status remains Testing.
- Authorized Fernside, exchanged the code and verified refresh-token operation.
  `list_homes`, `list_home_resources` and `list_home_history` succeeded against
  `https://home.googleapis.com/mcp`.
- Fernside structure: `1556b710-2026-4ef7-af91-fde7dc095d97`.
- Front door doorbell: `device@a260ebff-09f1-4e5b-b5f4-1f9986f0e42a`, reported as
  Nest Doorbell (battery), supporting `CameraHistory`.
- The initial six-hour history contained 16 entries, including named Heath and
  Adam events. This establishes named historical access, not fresh delivery speed
  or successful unlocking. The next day's owner-ring test is recorded above.
- At 23:49 PDT, after the owner completed Google's account re-verification,
  familiar-face sharing read back enabled. Confirm completed and redirected to
  the Fernside devices page without another challenge. Account setup is complete.
- Fresh camera testing was deferred for charging: the owner reported an exhausted
  battery, and the API reported critical charge, not charging and not plugged in.
  The device remained online. After loading, the web UI showed Camera idle (its
  initial Camera off placeholder was not the settled state). Recent history calls
  still succeeded, but no fresh named-ring latency test was performed.
- The callback unit exited successfully after token storage; its temporary
  Tailscale Serve route has been removed. It is needed only for OAuth renewal.

The setup used a dedicated Chrome profile on peecee,
`C:\Users\halbr\AppData\Local\GoogleHomeSetupAgent307`, launched by the on-demand
scheduled task `InfraGoogleHomeSetupAgent307`. After consent the dedicated browser
was closed, its task removed and its SSH tunnel stopped; CDP port 9227 no longer
listens. Ordinary Chrome windows were preserved. The signed-in setup profile
remains local for renewal; do not expose it or its download directory.

Google's [Home MCP guide](https://developers.home.google.com/mcp/home) documents
Home Premium Advanced eligibility, separate familiar-face consent, early-access
latency limitations, and prohibition of door unlocking through MCP. The observed
successful calls establish current access, not future entitlement. OAuth testing
mode can require renewed authorization; this is a test setup, not an unattended
production credential lifecycle.

## Canonical source and installed files

| Source | Installed path |
| --- | --- |
| `home_mcp.py`, `pyproject.toml`, `uv.lock` | `~/.local/share/google-home-mcp/` |
| `google-home-mcp-auth.service` | `~/.config/systemd/user/google-home-mcp-auth.service` |
| Runtime virtual environment | `~/.local/share/google-home-mcp/.venv/` |
| Downloaded OAuth client and token | `~/.config/google-home-mcp/{client,token}.json` |
| Private responses and request arguments | `~/.config/google-home-mcp/*.json` |

Credentials and camera responses are outside Git, files mode 0600 and config
directory mode 0700. Response files can include signed face-image URLs **even
with `includeMediaUrls: false`**; do not print raw histories, publish them, or
commit them. The probe does not fetch those images.

Install from this directory:

```sh
install -d -m 700 ~/.config/google-home-mcp ~/.local/share/google-home-mcp
install -m 644 home_mcp.py pyproject.toml uv.lock ~/.local/share/google-home-mcp/
uv sync --frozen --project ~/.local/share/google-home-mcp
install -m 644 google-home-mcp-auth.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

## Authorization and renewal

The callback is `https://proximal.tail0ecc2e.ts.net:8797/oauth/callback`, forwarded
by Tailscale Serve to loopback port 8797. It is tailnet-only, never Funnel. The
listener checks `Tailscale-User-Login: halbritt@gmail.com` and state freshness,
rejects repeated callbacks, never logs callback queries and exits after success
or one hour. It is an on-demand unit, not enabled at boot.

```sh
systemctl --user start google-home-mcp-auth.service
sudo tailscale serve --bg --https=8797 http://127.0.0.1:8797
```

Open `https://proximal.tail0ecc2e.ts.net:8797/login` in the owner's browser.
Google's Home scope is broad; this local client permits only the four read tools.
Use the existing `Home doorbell test` OAuth client, not the Home Assistant client.
The operator handles console setup; the owner handles Google's sign-in, passkey,
password and account-verification challenges. Never ask for those secrets in chat.

After `list_homes` identifies the structure, generate the separate consent link:

```sh
~/.local/share/google-home-mcp/.venv/bin/python \
  ~/.local/share/google-home-mcp/home_mcp.py face-consent \
  1556b710-2026-4ef7-af91-fde7dc095d97
```

After authorization, stop the callback if still active and remove only its Serve
route; other proximal Serve routes must remain untouched:

```sh
systemctl --user stop google-home-mcp-auth.service
sudo tailscale serve --https=8797 off
```

## Query and physical test

```sh
~/.local/share/google-home-mcp/.venv/bin/python \
  ~/.local/share/google-home-mcp/home_mcp.py tools \
  --output ~/.config/google-home-mcp/tools.json
~/.local/share/google-home-mcp/.venv/bin/python \
  ~/.local/share/google-home-mcp/home_mcp.py call list_homes \
  --output ~/.config/google-home-mcp/homes.json
```

Create a private JSON argument file for `list_home_history` with `structureId`,
`filter.resourceIds` restricted to the doorbell above, `startTime` set immediately
before the physical test, `includeMediaUrls: false` and `pageSize: 100`. Pass it
with `call list_home_history --arguments FILE --output PRIVATE_FILE`. Follow
`nextPageToken` if present, preserving the original query filters and time bounds.
An MCP error is saved privately and returns exit status 1; do not treat it as an
empty successful history.

Observed response path is
`structuredContent.entries.entries[].event.event.eventTracks[]`, with
`eventType: CameraHistory.HistoryItem` on the enclosing event. Named tracks had
`EVENT_TYPE_FAMILIAR_FACE`, `face.category: FACE_CATEGORY_KNOWN` and `face.name`.
Doorbell tracks had `EVENT_TYPE_DOORBELL`. Track start/end times are epoch
milliseconds; enclosing entries also have an RFC3339 timestamp and `eventId`.
Use immutable resource ID, not only its mutable display name.

For the owner test, record the UTC start time, ask Heath to ring while looking
at the doorbell, and query at a bounded interval. Record the first response time
that includes the new named event, its event/track timestamps, and any ring track.
Historical names alone do not establish current latency. Do not replay historical
events into HA, add Heath to the unlock allowlist, or lock the door to test this
read-only connection.

## Validation and rollback

```sh
~/.local/share/google-home-mcp/.venv/bin/python -m unittest discover \
  -s hosts/proximal/config/google-home-mcp -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_*.py'
scripts/validate-infra.py
```

The focused checks cover OAuth state, denial, missing refresh grants, replay,
private file permissions, callback owner checks, redacted exchange failures and
refusal of device actions. These are local checks; the successful live calls and
refresh exchange are separate evidence.

To retire the probe, stop its auth unit, remove only Serve port 8797, revoke the
new client connection through Google Home/account settings, then remove private
credentials and runtime files. Do not revoke the existing Home Assistant client.
The Moto bridge and HA lock rules are independent of this probe.
