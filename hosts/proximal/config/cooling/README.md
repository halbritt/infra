# cooling

Thermal/fan control on **proximal**. The whole cooling system hangs off a single
**Corsair Commander PRO** (USB `1b1c:0c10`); every motherboard fan header
(CPU Fan, Pump Fan, System Fan #1–3 on the `nct6687`) is empty — 0 RPM.

## Hardware map (captured 2026-07-22)

| Commander PRO channel | device | reading @ 100% duty |
|---|---|---|
| fan1–fan3 (4-pin) | case/radiator fans | ~2,090–2,160 RPM |
| **fan4 (4-pin)** | **Alphacool water-loop pump** (owner-confirmed; DDC/VPP-family speed range) | ~4,500 RPM, steady within ~1% |
| temp1 | thermistor lead | ~34 °C |

The CPU (i5-11400F) is water-cooled by the Alphacool loop — there is no air
cooler and nothing on the board's CPU_FAN/PUMP headers.

⚠️ **Never slow channel 4.** It's the pump, not a fan. Any fan-curve work
applies to channels 1–3 only.

## Current policy

All four PWM channels pinned at 255 (100%). Deliberate simplicity: the pump
belongs at full speed, and the fans at full speed keep the 3090 + 11400F loop
unconditionally safe at the cost of noise. If quieter operation is ever wanted,
put a temp-driven curve on fans 1–3 and leave fan4 alone.

## Interfaces

- **Kernel driver**: `corsair-cpro` hwmon (`/sys/class/hwmon/hwmon*/name` =
  `corsaircpro`; index varies by boot — match on name). `fanN_input`,
  `pwmN` (0–255), `tempN_input`.
- **Config tool**: [`~/git/corsair-cpro-setconf`](https://github.com/halbritt/corsair-cpro-setconf)
  — owner's small C utility for configuring the Commander PRO.
- Board sensors (`nct6687`) and GPU fans are separate and self-managed.
