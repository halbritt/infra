# AI Newsroom publication

The owner requested a public news page, Local Inference topic coverage, and a
weekly evidence-backed editorial on September 8, 2026.

- Application and canonical units: `/home/halbritt/git/ai-newsroom`.
- Public hostname: `https://newsroom.harm.org`.
- Origin: `http://127.0.0.1:3913`, `ai-newsroom-web.service` (user scope).
- Ingress: hostname-specific rule in `../cloudflared/config.yml` and its user
  parity copy. Existing wildcard DNS already points at this tunnel; no DNS
  mutation is needed.
- Public document root: `~/.local/share/ai-newsroom/site`, an atomically replaced
  symlink to a generated directory below `site-builds/`.
- Private archive: `~/.local/share/ai-newsroom/publication.db`. Draft JSON and HTML
  remain in `drafts/`, outside the served root. The HTTP process does not load
  the archive, credentials, or feedback database and exposes no write API.
- Weekly drafting: `ai-newsroom-editorial.timer`, Sunday 10:00 Pacific plus
  randomized delay. Collects bounded primary release notes and produces a
  private draft, with a separate model review. Publication requires the local
  `newsroom site publish ID` command; the timer does not publish drafts.
- Daily publication: the existing newsroom pipeline saves its selections and
  source excerpts before Slack delivery, then rebuilds the site. The Slack
  acknowledgment and feedback stores retain their separate meanings.

## Install and verification

Canonical units live in the application repo's `systemd/` directory. Install
`ai-newsroom-web.service`, `ai-newsroom-editorial.service`, and
`ai-newsroom-editorial.timer` into `~/.config/systemd/user/`, then daemon-reload.
Build the site before enabling the web service. Enable the web service and
weekly timer; do not manually trigger the daily Slack publisher for testing.

Use `newsroom site build` to regenerate from the archive. Verify the origin,
public HTTPS page, Local Inference page, CSS, and RSS. Requests for databases,
drafts, dotfiles, path traversal, and writes must fail. Install both Cloudflare
config copies and restart `cloudflared.service` for ingress changes, then check
existing public routes as well as the new one.

## Recovery

A failed build retains the previous complete generation. Rebuild from
`publication.db` after fixing the error. Preserve the archive and source packets;
they are not caches. To take the publication offline, stop its web service and
remove only its hostname-specific ingress rule from both Cloudflare copies.
Other tunnel routes and the daily Slack/feedback timers are unrelated.
