# Doorbell notification bridge on Moto G

## Current status — 2026-10-07

The owner requested the same recognized-person unlock for Adam, and separately
requested that the front door remain unlocked until midnight tonight.

The notification bridge is delivering alerts. HA history for the preceding
seven days returned 137 records, including three **Adam seen** alerts on
October 5 and nine **Heath seen** alerts. No Myra alert appeared in that sample.
The earlier `unknown` state ended on October 5. This establishes delivery and
Google's labels, not an independent identification of the people pictured.

The observed fields differ from the October 5 provisional matcher:

| Attribute | Observed value |
|---|---|
| `package` | `com.google.android.apps.chromecast.app` |
| `channel_id` | `CameraChannel-<account>` |
| `android.title` | `Adam seen` |
| `android.text` | `Front door doorbell` |
| `post_time` | Millisecond Unix timestamp |

[`front-door-myra-unlock.yaml`](front-door-myra-unlock.yaml) now has the display
name **Front door unlock for Myra and Adam**. Its existing unique ID and entity
ID remain unchanged. One shared matcher accepts exactly `Adam seen` or
`Myra seen` (case-insensitive), the exact observed camera text, the Google Home
package, and a `CameraChannel-` prefix. Generic people, partial names, negation,
and unobserved multi-person or doorbell-press wording do not match. The 60-second
freshness, replay and cooldown checks, locked-state prerequisite, single mode,
and manual-action guard remain in place.

Installed config readback equals the canonical file and the automation is on.
Thirty strict, read-only fixture evaluations passed in HA, plus the manual-action
guard and three midnight boundary cases. The old matcher rejected the observed
field layout. The fixture suite covered valid names, case variation, other and
partial names, wrong source/camera/channel, swapped or null fields, stale/future
or invalid timestamps, wrong timestamp units, replay, cooldown, restored state,
and a missing trigger. These evaluations did not operate the lock. A fresh
named arrival followed by an automation trace and lock-state transition remains
unverified. ADB still reports `unauthorized` from proximal; ADB is not part of
the running notification path and is no longer blocking this field correction.

### October 7 hold through midnight

The lock was already `unlocked` when checked at about 16:06 PDT, following the
existing Heath-arrival automation. No manual unlock or test lock was sent.
The five-minute relock came from **Auto-lock door when away**. Both it and
**Lock front door when Heath leaves home** now reject runs before
`2026-10-08T00:00:00-07:00`. The absolute deadline survives reloads and does not
repeat tomorrow. Their other behavior is preserved. Canonical copies:

- [`front-door-auto-lock-away.yaml`](front-door-auto-lock-away.yaml), unique ID `1779281607573`.
- [`front-door-lock-on-departure.yaml`](front-door-lock-on-departure.yaml), unique ID `lock_on_heath_leave`.

The existing **Lock front door at midnight** automation remains on and unchanged.
At midnight the exceptions expire and normal locking resumes. This change
suppresses the two identified automatic relock paths; it does not override a
person deliberately locking the door. Rollback removes the dated condition from
these two automations through the config API with a fresh config hash.

### Phone-free API investigation

The existing path is Google Home notification → Moto Companion notification
listener → HA sensor → unlock automation. The Moto needs connectivity and the
notification listener; its USB debugging connection is only diagnostic access.

Google's older [SDM CameraPerson schema](https://developers.google.com/nest/device-access/traits/device/camera-person)
reports person events without a familiar name. Google's newer, early-access
[Home MCP documentation](https://developers.home.google.com/mcp/home), checked
October 7, explicitly supports separately consented familiar-face data. It
requires Home Premium Advanced, a Cloud project and OAuth setup. The
[history API](https://developers.home.google.com/reference/home/mcp/tools_list/list_home_history)
provides timestamped event queries. No account authorization or migration was
performed here. Access eligibility, the actual face-event payload and arrival
latency still need verification before replacing the Moto path. Google Home MCP
itself prohibits unlocking doors; it is only a candidate recognition source,
with authorized lock control remaining in HA.

## Historical status — 2026-10-05

The owner explicitly authorized completing and enabling front-door unlocking
when Google Home recognizes Myra. This supersedes the earlier decision to leave
actuation unconfigured while investigating notifications.

[`front-door-myra-unlock.yaml`](front-door-myra-unlock.yaml) is installed through
the HA configuration API as `automation.front_door_unlock_for_myra`, unique ID
`front_door_myra_google_home`. Readback verified state `on`, canonical config
equality, and `last_triggered: null`. HA Core 2026.9.4 configuration validation
passed. No test unlock was issued.

**This is enabled configuration, not a verified working arrival automation.**
The notification entity still reads `unknown`, unchanged since October 2.
Google's exact notification title/text layout has not been captured. The Moto
is USB-connected but reports `unauthorized` even after reconnecting and
restarting the host ADB server. This status concerns USB debugging approval;
it does not establish whether the phone screen is locked. The owner says
screen locking is disabled.

The automation listens for changes to
`sensor.moto_g_power_5g_2024_last_notification`, including attribute changes.
It requires all of the following:

- Package `com.google.android.apps.chromecast.app`, with `CameraChannel` or
  `DoorbellChannel` (both channel IDs were observed on the Moto on October 2).
- `android.title` starts with `Front door` or `Front door doorbell`, followed by
  the end of the title or a separator; `android.text` contains the complete name
  `Myra`, case-insensitively, and does not contain the word `not`.
- Android `post_time` is no more than 60 seconds old, not in the future, newer
  than the automation's last accepted run, and at least 60 seconds have elapsed
  since that run. A state restoration with no previous state is rejected.
- `lock.aqara_smart_lock_u200` currently reports `locked`.

The only device action is `lock.unlock` on that lock. `single` mode prevents
overlapping unlock calls; there is no queued delayed unlock. An action-level
trigger guard also prevents the UI's ordinary **Run actions** command from
unlocking without the notification trigger. No presence prerequisite or new
relock policy is introduced.

The title/text placement is provisional and must be reconciled against the
first actual Google alert. The title identifies the source camera rather than
matching the camera name anywhere in arbitrary notification text. The native
state trigger/lock condition cover what HA supports directly; a template is
needed to parse notification text and compare event timestamps.

Validation: 24 read-only fixture evaluations in HA's strict template engine
passed: named events, case variation, two people, both channels, both expected
camera titles, other names, partial names, wrong camera/app/channel, missing
fields, bad timestamps, old/future events, wrong timestamp units, restoration,
replay, cooldown, a later visit, and negated recognition. These fixtures do not
prove Google delivery or physical actuation. The 42 infrastructure tests and
repository validator passed separately.

Source for Companion notification attributes:
[NotificationListenerSensorManager at 8c246042](https://github.com/home-assistant/android/blob/8c246042957afce3414505b960047b553ded4727/app/src/main/kotlin/io/homeassistant/companion/android/sensors/NotificationListenerSensorManager.kt).
This upstream source confirms field semantics; it is not a readback of the
Moto's installed application. The matcher was evaluated by the live HA engine.

To finish: restore authorized ADB access, diagnose Google Home push delivery,
capture a real front-door familiar-name alert and adjust its field mapping if
necessary, then verify a real Myra arrival through the automation trace and
lock state. Keep the overall task incomplete until that chain is demonstrated.

Updates use `ha_config_get_automation` then `ha_config_set_automation` with the
returned `config_hash`, canonical config and current best-practices key.
Rollback: set `enabled: false` for unique ID `front_door_myra_google_home` through
`ha_config_set_automation`, or turn off **Front door unlock for Myra** in HA.
Removal should delete only that automation, not restore all automations.

## Purpose and scope

The owner wants to evaluate Google Nest familiar-face notifications as a trigger
for the front-door lock, initially for Myra. On 2026-10-02 the owner requested
notifications for Google Home and Home Assistant on the Moto G, and offered
recognition of their own face as a test. Notification setup is separate from
enabling an unlock automation. No unlock automation was installed or tested.

## Installed settings

The Moto G Power 5G (2024) already had Home Assistant Companion
`2026.6.5-full` and Google Home `4.29.26.1`. These settings live in Android and
the apps, not in the appliance's `configuration.yaml`.

- Android notifications: enabled for `com.google.android.apps.chromecast.app`
  (previously denied) and `io.homeassistant.companion.android` (already granted).
- Google Home: completed initial setup with the owner's existing on-device
  account. Verified the front-door doorbell is accessible. Its push notifications
  and People notifications (including familiar faces) are on; away-only
  notifications are off. These device notification settings were already on.
- Android notification access: enabled for Home Assistant's
  `.sensors.NotificationSensorManager`.
- Companion app: enabled **Manage sensors → Last notification**, allowing only
  Google Home (`com.google.android.apps.chromecast.app`). Keep the allow-list
  requirement enabled. The saved allow list reads **Home** after reopening the
  sensor settings. Validate source/timestamp attributes when the first event arrives.

## Verification and next step

Android permission readback and the app settings screens verify configuration.
HA exposes `sensor.moto_g_power_5g_2024_last_notification`; its state was
`unknown` at setup completion, so real Google Home notification delivery remains
pending.
A local Android shell notification initialized the sensor's settings; it was
not a Google Home event and does not establish end-to-end recognition delivery.
Capture a fresh named doorbell notification in HA before designing the unlock
trigger. Do not infer identity from camera images or generic person detections.
The HA lock entity observed during discovery is `lock.aqara_smart_lock_u200`.

Rollback: disable the Last notification sensor and revoke Home Assistant's
notification access. Google Home notification permission was previously off;
Home Assistant's own notification permission was already on.

## Follow-up observation — 2026-10-02, about 19:20 PDT

After the owner reported walking past the doorbell, the Google Home doorbell
event list showed two events labeled **Heath** at 19:16 (9 and 16 seconds), a
generic **Person** event at 19:16 (8 seconds), and another Person event at 19:13.
These are Google's event labels; no independent visual identity inference was
made. Named recognition therefore occurred during the test window, but not for
every listed event.

The Moto's HA Last notification entity remained `unknown`, last updated at
18:49:41 PDT. Android showed no active Google Home notifications at inspection;
this does not establish that none were previously posted and dismissed.
The Home Assistant notification listener was both approved and live/bound.
Google Home camera and doorbell channels had importance 4, its account channel
group was not blocked, and background app operations were allowed for Google
Home and Google Play services. Push and People notifications remained enabled,
with away-only filtering off. The owner also reported no notification on their
usual phone for these walks. That points toward Google-side alert delivery or
suppression, but the exact cause remains unverified.

Google documents suppression of repeated similar activity alerts, independently
of video-history recording:
<https://support.google.com/googlehome/answer/9230439>.
This is a possible contributor, not a proven explanation of this test.
A physical doorbell press is the next useful delivery test because it does not
depend on face matching. Compare the usual phone, Moto, and HA sensor before
using notification text as an unlock trigger.
