# cyber-escalation-watch

An instrument, not a mood. Answers one question: **is the world verifiably trending
toward widespread state-level cyber conflict?** — and stays silent when it isn't.

Built 2026-11-19 after a week of unrelated US outages (Microsoft 365, FAA ground stop,
Workday, AWS us-east-1, Chase, United, NSA internal network) was widely read as
"coordinated attack". Every organisation involved ruled out malicious activity, and the
FBI/DNI said the same on the record. The point of this monitor is to separate that
kind of reliability decay from an actual escalation — and to prove the separation on
data rather than vibes.

## Two instruments, deliberately separate

**1. Tripwires** — discrete, citable events. No scoring. Any hit raises ORANGE.
- ≥3 CISA KEV additions in 7 days with EPSS ≥ 0.7 (mass exploitation of a perimeter product)
- A national CERT / government advisory using sabotage/wiper/destructive + attribution language in the last 36h

**2. Breadth index** — per-domain z-score against that domain's own trailing baseline.
A domain only counts as breached at ≥2σ, and escalation needs corroboration across
**independent** domains. A single cloud provider outage is one domain, one vendor — it
can never fire this instrument alone. That is the structural defence against exactly
the false positive that motivated the build.

## Domains

- **exploitation** — CISA KEV additions per 7 days. Backfilled from KEV's own `dateAdded`
  history (1,786 entries, 2021-11 → now), so this domain is scored from day one.
- **extortion** — ransomware leak-site posts per 24h (ransomlook). Cold until 8 daily buckets exist.
- **posture** — conflict/attribution language in CISA and CERT-FR advisory feeds per 7 days. Cold until 8 weekly buckets.
- **routing** — worst visibility drop across anycast canaries (1.1.1.0/24, 8.8.8.0/24, 9.9.9.0/24,
  208.67.222.0/24, 104.16.0.0/12) via RIPEstat. Cold until 14 days of hourly samples.

Cold domains are excluded from scoring and labelled `cold` in output — never counted as
healthy, never counted as breached. Missing history is never zero-filled (a zero-filled
bucket from absent data would read as a calm day and deflate the baseline).

## Levels

- **GREEN** — nothing corroborated
- **YELLOW** — 2+ hot domains ≥2σ, held ~20h before it counts (one noisy day is not a trend)
- **ORANGE** — 3+ hot domains ≥3σ (or `min(3, hot)` while domains are still warming), or any tripwire
- **RED** — defined, not reachable automatically: requires ORANGE sustained 48h plus a physical
  effect (grid, fuel, transport). That call stays human.

Escalation is immediate. De-escalation requires **5 consecutive clean days**. A monitor
that has stopped collecting raises a distinct "blind" alert after 6h — silence must never
be indistinguishable from calm.

## Verified state at install (2026-11-19)

```
level=GREEN  last_ok=None
• exploitation: 7 (kev_adds_7d, z=-0.9, baseline 9.0)
• extortion: cold (1/8 buckets, 98)
• posture: 0 (conflict_advisories_7d, z=-0.6, baseline 0.6)
• routing: cold (0/8 buckets, None)
```

Full breadth takes ~2 weeks of warm-up (extortion 8 days, routing 14). Until then the
index can reach YELLOW on exploitation+posture alone and ORANGE only via tripwire.

## Backtest gate (`backtest.py`)

Point-in-time replay: each day is scored using only data that existed that morning.

- **[A] 2026-11-12..17, mundane outage cluster — GREEN, 0/6 days breached.** PASS.
  KEV z peaked at +1.3: a single hot domain, so nothing fires. This is the requirement
  that matters most — the week that prompted the build must not alarm the instrument.
- **[B] 2026-02-16..22, Cloudflare BYOIP withdrawal — GREEN, 0/7.** PASS.
  KEV z reached +2.9 (11 additions/7d vs baseline ~6); still one domain, still silent.
- **[C] IRGC sabotage of French refrigeration controllers, 11–12 Oct 2026 — not detectable
  by this backtest.** Revised after measurement: the verifiable signal (France's
  attribution, CERTFR-2026-CTI-009) was published 9–10 Nov, not on 11–12 Oct. Any feed
  that carries publication dates will spike in November, not October, so the original
  gate ("elevated on 11–14 Oct") was testing the calendar, not the instrument. The
  detection path for that event is the advisory tripwire, verified by fixture
  (`tests.py`, "tripwire -> ORANGE") — not by history, because no free historical
  advisory archive was available to replay.

Consequence worth stating plainly: v1's index sees **exploitation-driven** escalation
well and **pure ICS/sabotage** escalation only through the advisory tripwire. That gap
closes with Cloudflare Radar (outage + BGP hijack/leak events), which needs a free
API token — see below.

## Fixtures (`tests.py`)

Twelve behavioural tests, all passing: green is silent; a single domain never fires;
YELLOW holds before firing; three domains escalate to ORANGE; a tripwire alone
escalates; de-escalation blocked before 5 days and fires after; blind monitor alerts;
cold domains labelled; zero-fill guard holds.

## Feeds — status verified 2026-11-19 from proximal

- Works anonymously: CISA KEV JSON, FIRST EPSS API, CERT-FR advisories RSS, CISA news RSS, RIPEstat
- Needs a token: Cloudflare Radar (free tier, Account:Radar Read). Add it to unlock the
  outage and BGP-hijack domains — the biggest single improvement available.
- Rejected during build: `ransomwatch` posts.json (stale at 2025-06-16 — would have
  reported "0 posts/week" forever and counted as a healthy domain), `api.ransomware.live/v2`
  (404), IODA events endpoint (500; the signals endpoint still works and is the next
  candidate), GDELT doc API (429 at 1 req/5s), abuse.ch URLhaus/ThreatFox (401 without a key).

## Ops

```bash
python3 watch.py --status     # current scores, no alerting, no level change
python3 watch.py              # one collection cycle (silent unless level changes)
python3 backtest.py --verbose # replay the gate windows
python3 tests.py              # behavioural fixtures
```

- State: `~/.local/share/cyber-escalation-watch/` (`history.db` holds samples, advisories, routing, levels)
- Cron: `no_agent` job `03276a976584` ("cyber-escalation-watch", every 2h) running
  `~/.hermes/scripts/cyber-escalation-watch.py`
  (a thin launcher; the implementation lives here). `deliver=local` because the script
  posts its own alerts to `slack:#ai-blather` via `hermes send` — the adapter delivery
  path is known to report success while dropping messages.
- Revert: remove the cron job, `rm -r ~/.local/share/cyber-escalation-watch`, and delete
  `~/.hermes/scripts/cyber-escalation-watch.py`. Nothing else is touched.

## Known limits

- Exploitation and extortion volume both correlate with attention and reporting, not only
  with capability. The z-score normalises against the domain's own history, which damps
  but does not remove that.
- The posture feed only holds what the RSS feeds currently serve; its baseline is partial
  and will firm up as history accumulates.
- No domain measures *effect* (customers offline, hospitals diverting, grid frequency).
  A pure-kinetic or pure-ICS campaign can be large and still leave this index green until
  a government says the word. The tripwire is the answer to that, and it is a lagging one
  by design — attribution takes weeks.
