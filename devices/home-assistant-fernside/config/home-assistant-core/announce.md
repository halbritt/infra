# Spoken announcements

Installed 2026-09-25 at the owner's request. Source and CLI live in
`/home/halbritt/git/announce`; `home-assistant/announce.json` there is the source
for `script.announce`. The installed `~/.local/bin/announce` command uses the
existing owner-only `~/.config/agent-board/ha-mcp-url` file. No new credentials,
daemon, integration, or wake-up schedule were added.

Home Assistant owns a FIFO queue of up to three requests. It suppresses progress
and quiet-hours requests (22:00–07:00 America/Los_Angeles), expires requests older
than 60 seconds, and waits for observed playback completion. The helper
`input_boolean.announce_playback_uncertain` is set before dispatch and cleared
after completion. Its state restores across restarts; an uncertain delivery
blocks later speech until the speaker is inspected and the helper is cleared.

## Verified speaker identities

| Physical location | HA entity | Cast UUID | Observed LAN IP |
|---|---|---|---|
| Kid bedroom, default | `media_player.dining_room_speaker` | `8b596c53-122b-9a27-9f0b-112f1dbc9fb8` | `192.168.1.200` |
| Owner bedroom | `media_player.bedroom_speaker` | `0998c4dd-04fe-780c-78a5-0cdfe7d24e83` | `192.168.1.198` |
| Dining room, first test | `media_player.dining_room_nest_mini` | `7b08182b-d9b3-f978-13d7-aa4476c98b82` | `192.168.1.103` |

The kid's current Mini advertises **Dining Room speaker** and is model
**Google Home Mini**. The owner heard the second authorized identification test
in the kid's bedroom. Do not confuse it with the unavailable historical
`media_player.kid_bedroom_speaker`, Cast UUID
`b3b25499-dfa3-9fcb-1a18-2a0c355d3620`, model Google Nest Mini. Entity IDs, area
assignments and Google Home names were not changed. IPs are observations; the
script targets HA entities.

## Verification and maintenance

`ha core check` passed. API readback matched the source. The owner heard
“Announce is ready” on the dining-room Mini and then explicitly authorized and
heard “Kid bedroom speaker test” in the kid's bedroom. Native progress and quiet
receipt suppression and request expiry were checked without speech. The CLI's
unit tests and linter passed. No simultaneous audible stress test was performed.

Use the project's README for commands, result semantics, update steps and
recovery. Changes go through `ha_config_set_script` with a fresh config hash and
the current best-practices acknowledgment. Preserve the helper's restored state.
No HA restart is needed. Rollback removes only `script.announce`, its uncertainty
helper, and the local command symlink. Never restore a whole configuration file
to undo this facility.
