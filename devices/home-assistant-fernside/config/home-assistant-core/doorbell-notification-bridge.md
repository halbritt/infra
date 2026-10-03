# Doorbell notification bridge on Moto G

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
