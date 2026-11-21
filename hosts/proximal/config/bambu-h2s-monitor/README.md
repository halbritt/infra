# bambu-h2s-monitor

Read-only status checks of the Bambu Lab H2S from proximal. Set up 2026-11-20 (owner-approved, agent-2440).

## Current state

- **Not polling yet.** `bambu-h2s-monitor.timer` is installed but disabled, because the printer's LAN access code is not stored on proximal. No printer status has been read.
- Source: `~/git/bambu-studio-ai`, a clone of `heyixuan2/bambu-studio-ai` at `cdc26987d5bf1052a055d9403e3cb9630959dd08` (detached). Virtualenv `~/git/bambu-studio-ai/.venv` (Python 3.14.6) with `paho-mqtt` 2.2.0 and `requests` only; the model-generation dependencies are not installed.
- Settings: `~/.bambu-studio-ai/config.json` (mode 0600, directory 0700) holds the model (`H2S`), the printer IP (`192.168.1.96`, found from the printer's own LAN discovery broadcast) and the serial number. The access code goes in `~/.bambu-studio-ai/.secrets.json` and is never recorded here.
- Units (copies in this directory, installed in `~/.config/systemd/user/`): `bambu-h2s-monitor.service` runs `scripts/monitor.py --once --json` once; `bambu-h2s-monitor.timer` runs it every two minutes. Lingering is on for `halbritt`, so an enabled timer keeps running after logout.
- Output: events append to `~/.local/state/bambu-h2s-monitor/monitor/events.jsonl`; each run's stdout and stderr go to the user journal (`journalctl --user -u bambu-h2s-monitor.service`). State between runs: `~/.bambu-studio-ai/monitor-state.json`.

## What the monitor does on the network

It opens MQTT over TLS to the printer on port 8883, subscribes to the report topic and publishes one `pushall` request, which asks for a full status report. It sends no other command. The printer stays in cloud mode.

## Finish the setup

1. On the printer touchscreen, read the LAN access code (Settings → Network).
2. Store it without echoing it: `cd ~/git/bambu-studio-ai && read -rs CODE && printf '%s' "$CODE" | .venv/bin/python scripts/configure.py secret access_code; unset CODE`
3. Check one read: `.venv/bin/python scripts/bambu.py status`, then `systemctl --user start bambu-h2s-monitor.service`.
4. Enable polling: `systemctl --user enable --now bambu-h2s-monitor.timer`.

## Remove

`systemctl --user disable --now bambu-h2s-monitor.timer`, delete the two unit files, `systemctl --user daemon-reload`, then remove `~/.bambu-studio-ai`, `~/.local/state/bambu-h2s-monitor` and `~/git/bambu-studio-ai`.
