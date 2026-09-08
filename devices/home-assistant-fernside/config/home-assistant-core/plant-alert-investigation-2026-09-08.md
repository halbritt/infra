# Plant alert investigation, 2026-09-08

The owner reported missing plant watering notifications. Home Assistant's
automation executed and recorded sends to both registered phones. The owner
subsequently confirmed receipt of an authorized direct iPhone test at 08:15
PDT. Receipt of the earlier watering messages remains unverified. No live
configuration was changed.

## Observations

Checked Core `2026.9.1` through Terminal & SSH and ha-mcp on the Fernside
appliance. The repository baseline was
`b74d7d3a3fe46476bdf6242105bae04131e5a694`. Times below are PDT unless
explicitly marked UTC.

| Plant | HA moisture around 08:10 | Configured watering threshold |
|---|---:|---:|
| Dracaena Lisa | 13.07% | below 20% |
| Dracaena Michiko | 10.82% | below 20% |
| Kangaroo Paw Fern | 28.19% | below 45% |

`automation.plant_drying_rate_has_slowed`, unique ID `1778854323330`, was
enabled with `initial_state: true`. Its six numeric triggers each wait six
hours. It has no time trigger, startup check, or scheduled repeat reminder.

The five retained traces included three completed runs on September 8 at
05:08:33, one for each plant above, and two on September 7 at 09:13:32.
The inspected Michiko trace, run `8ef43df3e374d4de45f9640891cbcf45`, shows:

- Trigger: `sensor.dracaena_michiko_soil_moisture`, from `unavailable` to
  `10.67`, with the configured six-hour wait.
- Action: `notify.notify`, title `🌿 Water Dracaena Michiko soon`, and the
  rendered watering message.
- Execution: `finished`, no error in the trace.

`notify.dont_panic` recorded a send at `2026-09-08T12:08:33.918665Z` and
`notify.moto_g_power_5g_2024` at `2026-09-08T12:08:34.062056Z`. The current
structured system-log query for `notif` returned no entries. This is a bounded
log check; neither the trace nor the entity timestamps establish phone receipt.
Home Assistant documents a notify entity's state as the
[last send time](https://www.home-assistant.io/integrations/notify/#the-state-of-a-notify-entity).

The `Don't Panic` mobile-app registration identifies an iPhone running iOS
`26.6.1` and Companion `2026.9.0`. Its registration is enabled and contains a
push token and push URL; neither value was copied into this report. Battery
telemetry last reported at 00:26 on September 8. Its Focus sensor was
`unavailable`, so it cannot establish whether Focus hid the morning alerts.
The Moto registration is also enabled; its battery entity reported 1% with a
September 6 timestamp. That old value does not prove its current power state.

## Confirmed reliability gaps

The HA action uses generic `notify.notify`, with no explicit recipient or
interruption-level data. Both phone entities recorded sends this morning, so
there is no demonstrated wrong-recipient failure in that run. Explicitly
selecting the intended phone would remove dependence on the generic action's
routing; the [HA documentation](https://www.home-assistant.io/integrations/notify/#companion-app-notifications)
recommends a specific action or target.

The six-hour threshold triggers do not provide reminders for a plant that
stays dry. Their waits also reset on Core restart or automation reload, as
documented for [numeric state triggers](https://www.home-assistant.io/triggers/numeric_state/#good-to-know).

The Ficus configuration still differs between channels: HA watches
`sensor.ficus_audrey_top_soil_moisture` below 40%; the bridge watches the deep
`sensor.gw1200b_soil_moisture_1` below 30%. Their observed readings were 54.65%
and 43%, respectively. The August report that the top probe was stuck near
23% is historical; it was not stuck at that value during this check.

On proximal, `plant-praxis-bridge.timer` had a future next run at 09:02:08 and
the 08:00 service run read all six plants. It logged these three plants as
already alerted. The bridge's `alerted` flag means a Plane item was created;
the code does not check downstream Praxis delivery or owner acknowledgment.
It suppresses further items until moisture reaches threshold plus eight
percentage points. Read-only Plane CLI checks confirmed `PRAXIS-23` (fern,
September 5 at 10:00) and `PRAXIS-24` (Lisa, September 5 at 21:01) in Backlog.
Praxis import and downstream message delivery were not established by this
check. The bridge state dates Michiko's alert to August 26; its original item
was not independently retrieved.

## Direct phone test: received

After the initial investigation, the owner authorized the test below. At
08:15:41 PDT, `notify.mobile_app_dont_panic` returned success and
`notify.dont_panic` advanced to `2026-09-08T15:15:41.747475Z`. The subsequent
structured system-log query for `notif` returned no entries. The owner
confirmed that the test appeared on the phone.

This verifies ordinary-priority delivery through the direct iPhone action at
that time. It does not establish receipt of the morning automation messages,
explain their absence, or verify the generic action's delivery to each phone.
The reported failure was not reproduced by the direct test. Focus or
notification presentation remains a hypothesis, not a confirmed cause.

## Test action and remaining checks

The approved, ordinary-priority test sent directly to `Don't Panic` was:

```yaml
action: notify.mobile_app_dont_panic
data:
  title: Plant notification test
  message: This is a test of Home Assistant plant alerts. No watering action is required.
```

For the earlier missed messages, inspect Notification Center and Focus settings
for the 05:08 watering messages. Normal iOS alerts
do not override Focus; see the
[interruption-level documentation](https://companion.home-assistant.io/docs/notifications/notifications-basic/#interruption-level).
If a future direct test is absent, inspect iOS notification permission and the Companion
app's Settings → Companion app → Notifications diagnostics and counters,
following the [official troubleshooting guide](https://companion.home-assistant.io/docs/troubleshooting/faqs/).
Do not reset the push registration before collecting that evidence.

With direct phone delivery verified, a daytime daily dry-plant summary would
address the lack of repeat reminders. Selecting its time, changing recipients,
and aligning the Ficus trigger are separate configuration decisions. The
current investigation does not establish that any of these changes alone
would fix the reported missing phone notifications.
