# Spoken announcements

Installed 2026-09-25 at the owner's request. Source and CLI live in
`/home/halbritt/git/announce`; `home-assistant/announce.json` there is the source
for `script.announce`. The installed `~/.local/bin/announce` command uses the
existing owner-only `~/.config/agent-board/ha-mcp-url` file. The original CLI remains available. A Gemini request service was added later
on the same day (see below); no wake-up schedule was installed. The original TTS provider is
Home Assistant Cloud (`tts.home_assistant_cloud`), voice `LunaNeural`, language
`en-US`. The owner requested a distinct female voice because the initial Google
Translate voice sounded too much like Google Assistant.

Home Assistant owns a FIFO queue of up to three requests. It suppresses progress
and quiet-hours requests (22:00–07:00 America/Los_Angeles), expires requests older
than 60 seconds by default (explicit TTL up to 3,600 seconds for narration), and
waits for observed playback completion. The helper
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
`b3b25499-dfa3-9fcb-1a18-2a0c355d3620`, model Google Nest Mini. At the owner’s request, the working device and entity were renamed **Kid Bedroom
Mini** in HA and both assigned to **Bedroom 2** (`bedroom_2`). Readback verified
both records. Entity IDs and Google Home names were not changed. IPs are observations; the
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


## Gemini request service, added 2026-09-25

The owner requested a robust API and urgent/demanding delivery after hearing a
Gemini reading. `announce.service` now runs as a proximal user unit, exposing
bearer-authenticated HTTP on loopback and `100.85.100.81:8877`. Source, unit and
API documentation are in `/home/halbritt/git/announce` (`docs/service.md` and
`docs/gemini-tts.md`). Private token/configuration live in `~/.config/announce/`;
job history and audio are under `~/.local/share/announce/service/`.

The exact provider is `gemini-3.8-flash-tts` through Gemini Interactions.
Existing gcloud access retrieves the Gemini-restricted API key for project
`heath-stuff` into memory. Cloud TTS v1 rejected this model. The service records
usage, caches recordings, persists jobs and idempotency keys, and never
replays uncertain dispatches after restart. Default service voice is Kore;
original direct Luna requests are unchanged.

The native HA script gained optional `media_id`, `media_duration` and
`ttl_seconds`. SHA-256 IDs resolve only inside `/media/announce/`, populated by
SSH/SCP through existing add-on access. Generated recordings use the same
queue/latch/quiet checks as Luna. Completion timeout is recording duration plus
60 seconds (20-minute audio cap). An urgent style does not override quiet hours
or interrupt playback. Synthesis must finish completely before any playback;
provider rejection never silently switches models or speaks a partial result.

Verified config readback and `ha core check`, native quiet-hours and expiry
suppression, 25 tests, lint, API authentication, persisted restart state, cached
rendering, and an urgent 3.4-second test on `media_player.bedroom_speaker`.
HA returned `played`; this is observed playback, not confirmation of hearing.
The earlier 547.48-second Raven excerpt also completed and cleared the latch;
Gemini had refused its last two stanzas. Approximate duration-based cost of
that excerpt was $0.13, not a billing receipt.

Stop only the service with `systemctl --user disable --now announce.service` to
retain direct Luna operation. Preserve job state for uncertainty review and do
not remove recordings or reload the HA script during playback.
