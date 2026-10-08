# Google Home familiar faces through Nest events

## Active design

The owner requested a phone-free Myra/Adam unlock and rejected continuous
five-second polling. Home Assistant Core 2026.9.4 now owns both stages:

1. Built-in `nest` maintains a Cloud Pub/Sub subscription and emits `nest_event`.
2. `custom_components/google_home_faces` accepts fresh person/chime events for
   the mapped front-door camera and queries Google Home MCP history on demand.
3. Matching named history tracks produce `google_home_familiar_face`.
4. `front-door-myra-unlock.yaml` accepts exactly Myra or Adam and unlocks
   `lock.aqara_smart_lock_u200` if locked. The existing automation identity is
   preserved: `front_door_myra_google_home` / `automation.front_door_unlock_for_myra`.

There is no separate subscriber process on proximal and no idle history poll.
The Moto notification listener is retained for rollback but is not the new
rule's trigger. ADB is not involved. Google Home MCP is used only for
`list_home_history`; lock control remains in HA.

## Managed resources and mapping

| Resource | Value |
|---|---|
| Cloud project | `heath-stuff` (`792817081075`) |
| New Device Access project | Fernside Home Assistant, `7529d30b-ec43-403e-8333-81fa807f5831` |
| Pub/Sub topic | `projects/heath-stuff/topics/fernside-doorbell` |
| Pub/Sub subscription | `projects/heath-stuff/subscriptions/home-assistant-DnpCYnaM9D` |
| Topic publisher | `sdm-publisher@googlegroups.com`, `roles/pubsub.publisher` |
| HA Nest entry | `01M4ECY2F9HKPJPSPBBJSFX75D` |
| HA Nest device ID | `47edf5f6c5b076ff9f9864f412bdb750` |
| HA face entry | `01M4ED5T19YRA73THM25MSD53Z` |
| Google Home structure | `1556b710-2026-4ef7-af91-fde7dc095d97` |
| Google Home camera | `device@a260ebff-09f1-4e5b-b5f4-1f9986f0e42a` |
| Diagnostic entity | `sensor.front_door_familiar_face` |

Native Nest consent grants home information and this doorbell's camera and
chime events. Livestream, snapshots, video clips and Living Room Display access
were not selected. The separate Google Home platform scope is broad; the custom
client exposes only a fixed history call. Familiar-face consent is separate.
Existing Device Access project **Gunn** and its old `nest` topic were preserved.
The subscription uses the native 31-day inactivity expiry; HA maintains it while
running. A prolonged retirement may require recreating the subscription.

## Event contract and freshness

`nest_event` carries the mapped HA `device_id`, `type`, timezone-aware
`timestamp`, and nonempty `nest_event_id`. Only `doorbell_chime` and
`camera_person` are accepted, within 30 seconds of occurrence (five seconds of
clock skew tolerated). Repeated source IDs are suppressed for one hour.

The lookup window is trigger minus 35 seconds through trigger plus 60 seconds,
restricted to the immutable camera resource, one page of at most 100 entries.
Pagination is an error, never an incomplete successful match. Chime triggers
must match a doorbell track start within five seconds; person triggers must
fall within a person track interval, allowing five seconds of skew. Names must
come from a known familiar-face track in that same camera-history entry, with
fresh finite track times near the trigger. Raw media URLs are never emitted.

One worker serializes requests; at most four triggers may wait. Each trigger
gets at most five attempts with incremental delays 0, 2, 5, 10 and 15 seconds,
subject to a 60-second source-age limit. Individual calls time out after 15
seconds. Transient HTTP/network exceptions, including SDK exception groups,
share that same attempt budget. A stale result never emits a face event.
There is no retry after the freshness window.

Recognition identity is history-event ID plus Google's face ID. The private HA
Store ledger is saved atomically **before** emitting an event. This gives
at-most-once publication: a crash between saving and firing can lose one event,
but must not replay an old visit after restart. Disk failure emits nothing.
The source-event queue is not persisted; fresh Pub/Sub redelivery can restart a
lookup, with the recognition ledger suppressing a second publication.

The automation adds independent exact-name, device/resource, trigger-type,
60-second source/face freshness, ten-second observation freshness, replay,
60-second cooldown and locked-state checks. Native trigger conditions also
block ordinary manual **Run actions**. `single` mode deliberately drops overlap
instead of queuing a delayed unlock. No new relock policy or Heath allowlist was
introduced. The October 7 midnight exception has expired.

## Installation and credentials

Copy `custom_components/google_home_faces/` to
`/config/custom_components/google_home_faces/`, excluding Python caches.
The manifest pins `mcp==1.26.0`, matching HA 2026.9.4's own MCP dependency.
Run `ha core check`, then restart Core to load Python changes. Integration
reload alone does not reload already imported Python modules.

Add **Google Home familiar faces** through Settings → Devices & services after
configuring the native Nest integration. Supply the mapping above and the
separately authorized Home OAuth client ID, secret and refresh grant. Credentials
live in HA's private config-entry storage and backups, never this repository.
The sensor reports requests, status and sanitized error classes. Auth failures
request HA reauthentication; its form accepts a newly authorized private grant.
Disable the face integration to stop targeted lookups.

Private operator files on proximal are under `~/.config/google-home-mcp/`:
`client.json` / `token.json` for Home, `nest-client.json` for Nest. Native Nest
stores its live grant in HA. Renew Home through the
[probe authorization procedure](../../../../hosts/proximal/config/google-home-mcp/README.md#authorization-and-renewal).
Do not paste secrets into chat, tool output, errors, or Git. Google may return
signed face-image URLs even with `includeMediaUrls: false`; discard them from
public events and keep any diagnostic response private.

Google Cloud's audience is now **In production**. The new UI required homepage,
privacy and terms links before enabling Publish. The real app-information pages
are at `https://harm.org/home-assistant/`, maintained in `halbritt/harm-org`
(commits `fc504e8`, `1389108`), with no camera data or household access details.
Both OAuth grants were renewed after publishing; the new Nest response omitted
`refresh_token_expires_in`, present on the Testing grant. This removes that
seven-day Testing expiry, not the possibility of later owner revocation.

During renewal, a rejected diagnostic config update echoed the Home client
secret; another secret appeared in a browser accessibility label. Both were
disabled and deleted. The final replacement secret was captured directly to
private files without output and a fresh token exchange verified it.
The two renewed config-entry credentials were replaced atomically with Core
stopped because no general config-entry data mutation API exists; all unrelated
entries and device/entry IDs were verified unchanged. The private before-copy
is `/config/.storage/core.config_entries.before-renewal-20261008`. It contains
obsolete credentials and is evidence, not a working credential rollback.

## Verification — October 8, 2026

The owner's physical ring proved native Pub/Sub delivery and the custom lookup:

| Observation | UTC timestamp |
|---|---|
| Person event occurrence | 18:55:15.068 |
| Person event fired by HA | 18:55:18.577 |
| Doorbell press occurrence | 18:55:31.995 |
| Doorbell event fired by HA | 18:55:33.915 |
| Last face-track observation | 18:55:41.389 |
| Familiar-face event fired by HA, name Heath | 18:56:00.180 |

Chime delivery took **1.920 seconds**; the named HA event arrived **28.185 seconds
after the ring**. The person event had already started lookup. Six requests total
served the person/chime pair; the second lookup resolved to the same recognition
and was suppressed. This is one measurement, not a guaranteed latency.
History event: `1d2e31ee-a16a-4844-bc47-3e891f6542b2`.
Private sanitized evidence:
`~/.config/google-home-mcp/ha-face-test-20261008T184258Z.json`.

A post-renewal event encountered an SDK transport exception; a direct live
history request with the renewed grant succeeded. Network failures now use the
same bounded retry budget as not-yet-published history, with explicit failure
status on exhaustion. No historical event was injected and no test lock action
was issued. A real Myra/Adam arrival-to-unlock remains unverified.

Final installed-byte hashes matched the canonical integration; both entries loaded
after restart, the automation was on with exact canonical readback and no
accepted unlock run. The 21 focused tests, 42 repository tests, repository
validator and Core configuration check passed.

Focused tests exercise real HA event delivery and disk persistence, stale/wrong
camera rejection, duplicates across restart, storage failure, auth failure,
retry exhaustion, transient transport errors and unload cancellation. Run with
Python 3.14 and HA 2026.9.4 plus its MCP dependency:

```sh
python -m pytest devices/home-assistant-fernside/config/home-assistant-core/tests_google_home_faces -q
python3 -m unittest discover -s tests -p 'test_*.py'
scripts/validate-infra.py
```

The automation matcher also passed 20 strict read-only live HA fixtures and two
native trigger-condition checks, including Myra/Adam, Heath rejection, stale,
future, wrong camera/device, replay, cooldown and manual execution guards.

## Rollback

Turn off `automation.front_door_unlock_for_myra` to stop recognized-person
unlocking. To restore the phone source, retrieve only
`front-door-myra-unlock.yaml` from commit `65860b3`, then use the HA automation
config API with a fresh config hash; preserve unrelated automations. Keep the
Moto listener available until the new path is accepted in ordinary use.

Disable/remove the custom face entry to stop its history calls. Disabling the
native Nest entry stops its subscriber. Removing the newly created Nest entry
may remove its subscription; do not delete the preserved Gunn project/topic.
Revoking Google Home access also breaks the proximal diagnostic probe because
it shares that client's grant. Do not restore the whole storage file over later
unrelated state, or revoke other pre-existing clients to undo this setup.

References: [HA Nest integration](https://www.home-assistant.io/integrations/nest/),
[SDM events](https://developers.google.com/nest/device-access/api/events),
[Google Home MCP](https://developers.home.google.com/mcp/home),
[OAuth branding](https://support.google.com/cloud/answer/15549049).
