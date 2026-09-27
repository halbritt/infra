# Stream Deck (peecee) webhooks

Created 2026-09-26 at the owner's request. It backs the **Home** page of the
Stream Deck MK.2 on peecee (see
[hosts/peecee/config/stream-deck](../../../../hosts/peecee/config/stream-deck/README.md)).

## Objects

| Object | Purpose |
| --- | --- |
| `automation.stream_deck_peecee` (id `1790490815159`) | One webhook trigger per key → `choose` on trigger id. Mode `queued`, max 10 |
| `script.movie_mode` | Globe + Mushroom to 12 %, Color 1600 to 15 % at 2200 K; Akari, Arc, Tolomeo off. Mode `restart` |
| `script.goodnight` | Living room, hall, Elgato desk lamp, bedroom Lamp and Red Light off; `lock.lock` on the Aqara U200. Mode `single` |

Webhooks: `allowed_methods: [GET, POST]`, `local_only: true`. IDs are
`<prefix>-<key>`, with keys `desk-lamp`, `bedroom-lamp`, `red-light`,
`hall-light`, `living-room-off`, `dinner`, `bedtime`, `come-here`,
`movie-mode` and `goodnight`. The prefix is a private random value. It is kept
only in HA, in peecee's Stream Deck profile, and in proximal's
`~/.config/streamdeck-peecee/webhook-prefix` (mode 0600). It is never
committed. Treat it like a capability URL; rotating it means updating both
the automation and the Stream Deck page.

Deliberate exclusions:
- Nothing unlocks the front door.
- The Black Olive and garage grow lights keep their own schedules.
- Night lights and the kid's room (Bedroom 2) are left alone by Goodnight.

Announcement keys call `script.turn_on` → `script.announce` with speaker
`media_player.dining_room_speaker` (Kid Bedroom Mini). The call doesn't wait
for playback, so other keys aren't blocked. Announce's own rules still apply:
quiet hours 22:00–07:00 and the uncertainty latch.

| Key | Message | kind |
| --- | --- | --- |
| dinner | "Dinner's ready! Come to the table, please." | reminder |
| bedtime | "Bedtime in ten minutes. Start wrapping up." | reminder |
| come-here | "Come here, please. You're needed." | attention |

Rollback: delete the automation and the two scripts. No other config was
touched.
