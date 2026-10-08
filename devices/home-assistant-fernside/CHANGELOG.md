# Home Assistant at Fernside changelog

## 2026-10-08 — Subscribe to Nest events and resolve familiar faces inside HA

Installed native Nest Pub/Sub and the custom `google_home_faces` integration.
The owner's ring reached HA in 1.920 seconds; Heath's name was emitted 28.185
seconds after the ring, with the duplicate person/chime visit suppressed. The
Myra/Adam rule now consumes fresh named API events and retains its allowlist,
cooldown, replay, locked-state and manual-action guards. Physical Myra/Adam
unlock remains unverified. Published the OAuth app and renewed both grants to
remove Testing expiry. See [runbook and evidence](config/home-assistant-core/google-home-faces.md).

## 2026-10-08 — Confirm Heath recognition through the Google Home API

After charging, the owner rang the doorbell. The same API history event contained
the ring and a familiar-face track named Heath. The query retrieved it 54.790
seconds after the ring; the earlier capture had ended, so this is only an upper
bound on availability. No lock action ran and the phone bridge remains active.
See [physical test evidence](../../hosts/proximal/config/google-home-mcp/README.md#physical-recognition-test--2026-10-08).

## 2026-10-07 — Verify named history through Google Home's API

Authorized a separate read-only Google Home MCP probe on proximal. Live history
returned Heath and Adam face names for the front-door doorbell. Separate consent
was completed at 23:49 PDT after owner account re-verification. Fresh ring-to-event
timing is deferred until the critically low doorbell battery is charged; no API
event is connected to a lock action. The active notification bridge and midnight
exception were preserved. See the [probe runbook](../../hosts/proximal/config/google-home-mcp/README.md).

## 2026-10-07 — Add Adam recognition and hold the door unlocked until midnight

At the owner's request, added Adam to the existing Myra unlock rule. Recorded
Google Home alerts proved that the name is in `android.title`, the camera is in
`android.text`, and the channel carries an account suffix; corrected all three
assumptions. Preserved freshness, replay, cooldown and manual-action guards.
Thirty strict HA template fixtures passed; installed config readback matched.
Real notification delivery is now proven, but physical arrival unlock is not.

Added an absolute October 8 midnight PDT exception to the two existing
away/departure lock automations. The door was already unlocked; no test lock or
manual unlock was issued. The midnight lock remains enabled and unchanged.
HA Core configuration check, infrastructure unit tests and validation passed.
See [current status and rollback](config/home-assistant-core/doorbell-notification-bridge.md).


## 2026-10-05 — Enable Myra front-door unlock automation

Under explicit owner authorization, installed and enabled the Google Home
notification-triggered Myra unlock automation. Verified config readback, HA
state `on`, Core validation and 24 matcher fixtures. Real notification delivery
and recognition-to-unlock verification remain unresolved; Moto USB access now
requires authorization. No test unlock was issued. See
[current status and rollback](config/home-assistant-core/doorbell-notification-bridge.md).

## 2026-10-02 — Moto G doorbell notification setup

Enabled Google Home's Android notification permission and Home Assistant's
notification-listener access on the Moto G; HA's own notification permission
was already enabled. Completed Google Home initial account setup and verified
doorbell People/familiar-face push alerts are enabled without away-only filtering.
Enabled the Companion app Last notification sensor for the Google Home bridge.
See [configuration and verification limits](config/home-assistant-core/doorbell-notification-bridge.md).
Named-face delivery and lock automation remain unverified; no unlock action ran.


## 2026-09-26 — Stream Deck webhooks

Created `automation.stream_deck_peecee` (ten local-only webhook triggers), plus
`script.movie_mode` and `script.goodnight`, for the peecee Stream Deck. The
Red Light webhook was tested end-to-end from peecee. See
[Stream Deck webhooks](config/home-assistant-core/stream-deck.md).
## 2026-09-25 — Gemini announcement service

Added generated-media playback to the shared Announce script at the owner's
request. The proximal request service uses exact Gemini 3.8 Flash TTS with
selectable delivery styles, durable job/idempotency state and cached audio.
HA retains serialization, quiet hours and the persistent uncertainty latch.
Existing direct Luna calls remain compatible. See
[Announce operations](config/home-assistant-core/announce.md) for deployment,
verification, credentials locations and rollback. Config validation/readback,
25 tests and an urgent bedroom playback passed.


## 2026-09-08

### Added a daily plant watering summary to the iPhone

The owner found the morning watering alerts bundled with other notifications
and approved a daily daytime reminder while plants remain dry. Installed
`automation.plant_watering_daily_summary` (unique ID `1788880838740`) through
the HA config API from the canonical
[`plant-watering-daily.yaml`](config/home-assistant-core/plant-watering-daily.yaml).
It runs at 09:00 America/Los_Angeles, reads all six plants, and sends one
ordinary-priority summary directly to `notify.mobile_app_dont_panic` when any
plant is below threshold. It sends nothing for an empty dry-plant list and
excludes unavailable/nonnumeric readings. Ficus uses the deep probe below 30%.

Verified the installed configuration matches the canonical YAML and all ten
pre-existing automations retained their configuration. HA template checks
covered watered plants, exact thresholds, just-below thresholds, zero moisture,
unknown/unavailable/missing readings, invalid numbers, and empty-summary
suppression. The entity/threshold pairs match the bridge. `ha core check`
passed without a restart.

A manual run with conditions enabled at 08:21:22 PDT completed successfully,
listing Lisa 13.2%, fern 28.1%, and Michiko 10.8%. Trace
`15a9b7d725db75ef8d4f8fcf6a6a9c61` recorded the rendered message, the passing
condition, and the direct iPhone action; the phone notification entity advanced
to `2026-09-08T15:21:22.732990Z`. The owner confirmed receipt of this summary.
The first scheduled 09:00 run had not occurred at verification time.

### Investigated missing plant watering notifications

The enabled watering automation completed three runs at 05:08 PDT, and both
phone notification entities recorded sends. Receipt of those morning messages
remains unverified. The owner authorized a direct `Don't Panic` iPhone test at
08:15 PDT and confirmed it appeared; the service returned success and the
notification entity recorded the send without a matching system-log error.
Recorded the trace, current moisture values, bridge-to-Plane handoff, reminder
suppression, and Ficus configuration mismatch in the
[investigation report](config/home-assistant-core/plant-alert-investigation-2026-09-08.md).
No live configuration changed. The direct test did not reproduce the reported
missing notification, and the cause of the earlier missed alerts remains open.

## 2026-08-31

### Moved allowlisted telemetry writes to VictoriaMetrics

Changed the existing imported InfluxDB integration config entry from the local
InfluxDB add-on to proximal's authenticated VictoriaMetrics ingress at
`100.85.100.81:8427`. Connection credentials remain runtime-only. YAML now
owns a 34-entity numeric sensor allowlist, `max_retries: 3`, and millisecond
precision; this avoids exporting people, locks, trackers, or other unrelated
Home Assistant state.

The source InfluxDB history was copied before cutover and a final delta import
added 74 samples without retries. VictoriaMetrics retained all 34 expected
series, started at the same `2026-02-07T06:50:20.035Z` timestamp, and advanced
past the final InfluxDB sample after Core restarted. The InfluxDB add-on remains
running and its data was not deleted.

Recorder was not redirected. After cutover, the Core UI returned HTTP 200,
configuration validation passed, the Recorder WAL continued updating, no
Recorder/Influx write errors appeared, and the existing seven-entity 72-hour
native history card remained present. Config-entry and YAML rollback copies are
stored on the appliance with the `before-vm-cutover-20260831` suffix.

### Extended Recorder history and reduced SQLite commit frequency

Added explicit Recorder policy to the canonical Core configuration:
`purge_keep_days: 30` retains raw states and events for 30 days, and
`commit_interval: 30` replaces the five-second default to reduce routine disk
writes. Recorder remains the source for native Home Assistant History,
Activity, dashboard history cards, events, and long-term statistics; the
separate VictoriaMetrics migration does not replace it.

A full local appliance backup (`a84408eb`) was created before installation.
The live canonical file passed `ha core check`, Core restarted successfully,
the UI returned HTTP 200, and the Recorder WAL continued to advance without
Recorder/database errors. The pre-change configuration and full backup remain
the rollback paths.

## 2026-08-12

### Re-enabled the plant watering automation as a redundant channel

Turned `automation.plant_drying_rate_has_slowed` ("Plant needs water — per-plant
rewater point") back on, reversing the 2026-07-23 decision that made Praxis the
sole watering channel. Cause: the proximal `plant-praxis-bridge` stopped firing
for 5 days across the 2026-08-07 reboot and nothing surfaced the outage, so
Praxis is not yet trusted as a single path. Duplicate alerts with Praxis are
expected and deliberate; retire this again only once the bridge has proven it
survives reboots.

Two changes beyond flipping it on:

- Added the missing **Dracaena Michiko** trigger (`below: 20`, `for: 06:00:00`).
  That plant was paired 2026-07-29, six days *after* this automation was
  disabled, so it had never been represented here — re-enabling as-is would have
  silently left one plant uncovered on this channel.
- Set `initial_state: true` (was `false`). Left at `false` the automation would
  have switched itself back off at the next HA restart, which is precisely the
  silent-failure shape being guarded against.

Verified: state `on`, six `numeric_state` triggers, action `notify.notify`
fanning out to `notify.dont_panic` and `notify.moto_g_power_5g_2024`.

Known gap: this channel covers THIRSTY only. A dark sensor never crosses a
numeric threshold, so staleness detection remains exclusive to the bridge's DARK
check. `sensor.ficus_audrey_top_soil_moisture` reads `unavailable` right now
(silent since 2026-08-07 02:14Z) — a battery/sensor fault to chase separately.

## 2026-08-06

### Completed the live hostname migration

Changed the Supervisor host hostname from `homeassistant` to
`home-assistant-fernside` through an authenticated Terminal & SSH add-on shell.
Verified the new mDNS name, key-only SSH, LAN and Tailnet UI, Observer,
fixed-address InfluxDB and ha-mcp listener reachability, and the post-reboot
Tailscale node identity. No checked hostname consumer required a compatibility
alias.

### Installed all available updates

Created a protected pre-update backup, then updated Core to `2026.8.0`, HAOS to
`18.2`, OpenThread Border Router to `3.1.0`, ESPHome Device Builder to
`2026.7.4`, Matter Server to `9.1.1`, Home Assistant MCP Server to installed
version `8.1.1`, and the Midea U Window AC firmware to `0x00000038`.

Rebooted into the HAOS 18.2 slot and verified that Core, Supervisor, Observer,
the UI, and every installed add-on recovered. Supervisor reported no remaining
updates. The Midea OTA completed despite a client timeout and a transient ZHA
unknown-event warning; the update entity confirmed the new firmware with no
operation in progress.

The ha-mcp add-on recovered and its listener was reachable, but the active
Claude configuration lacked the intended user-scope registration and retained
only a legacy project-local entry. This client-side drift remains a separate,
credential-aware follow-up.

## 2026-08-05

### Renamed the installation for its site

Renamed the resource from `home-assistant-yellow` to
`home-assistant-fernside`. Fernside identifies the Home Assistant installation;
Yellow remains its current hardware model. Updated the desired hostname but did
not change the live appliance, which still reports `homeassistant`.

### Imported and assigned a stable resource name

Imported all eight commits from `github.com/halbritt/homeassistant` without
squashing. The infrastructure identity is `home-assistant-yellow` so additional
Home Assistant installations can receive distinct resource names. The live
hostname remains `homeassistant`; no appliance, network, integration, or
automation state changed during the import.

The clean standalone checkout was moved to desktop trash after its tip was
verified as an ancestor of pushed `infra/master`. Its GitHub repository remains
available as historical source provenance.

### Recorded the hostname migration boundary

Audited live mDNS and Tailnet identity plus the known Grafana,
plant-praxis-bridge, and ha-mcp consumers. The fixed-address consumers do not
depend on the generic hostname. Documented the authenticated Supervisor/CLI
operation and its before-and-after probes. The live hostname was not changed:
the registered agent surface does not expose host options and network SSH is
disabled.

## 2026-09-25 — Shared spoken announcements

Installed `script.announce` and the persistent playback-uncertainty helper via
HA config APIs. Reuses Google Translate TTS and Cast. The queue serializes speech,
suppresses progress and 22:00–07:00 requests, and expires stale requests. Two
authorized audible tests were heard by the owner. The second identified the
kid-bedroom Mini as `media_player.dining_room_speaker` (old room name), now the
default; the unavailable historical kid-bedroom entity is a different device.
See `config/home-assistant-core/announce.md` for source and recovery.

Follow-up: assigned the confirmed Mini’s device and entity to Bedroom 2 and set
both HA display names to Kid Bedroom Mini. Preserved the entity ID and verified
the registry records.

Voice follow-up: switched Announce to existing Home Assistant Cloud TTS, Sonia
(`en-GB`, `SoniaNeural`), at the owner’s request for a distinct female reminder
voice. Native voice discovery confirmed support; a sample completed on the
kid-bedroom Mini.

Final voice choice: after hearing Aria, Jenny and Luna sequentially on the bedroom
Nest Audio, the owner chose Luna. Set `en-US` / `LunaNeural` in Announce and
verified the live script matches its source.
