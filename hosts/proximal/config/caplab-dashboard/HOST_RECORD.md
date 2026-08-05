# CAPLAB dashboard host record — 2026-07-15

This record captures the first enactment of the read-only Study 001 dashboard
on host `proximal`. It records deployment observations and technical
verification. It does not admit CAPLAB evidence, perform CAPLAB recomputation,
make a capability inference, revise the ADR 0006 card selection, or record
CAPLAB acceptance.

## Authority and source binding

- Owner execution prompt:
  `/tmp/caplab-study-dashboard-build-prompt.md`, SHA-256
  `0a306a14f2148c4437fb89cc97b4add3eb112e05136b2dd1053c3fb0aee978ad`.
- Books branch: `agent/caplab-study-dashboard`.
- Exact books source commit:
  `e4636d2628adbbfca953734d4dc7cdfa91d72b04`; the pushed remote ref resolved to
  the same commit immediately before installation.
- Installed Study 001 projection SHA-256:
  `7b710b3188ab97228acbeb4c05066e3a7aefa31891bf160780337b177941a55d`.
- Proximal branch: `agent/caplab-study-dashboard-host`.
- Initial desired-state commit: `a779d9a`.
- User-unit compatibility correction: `d3ba0f7`.

## Captured before state

The following observations were recaptured immediately before the first live
change:

| Surface | Before observation |
|---|---|
| TCP `3021` | no listener |
| Tailscale HTTPS `8784` | no TCP or Web entry |
| `caplab-dashboard.service` | unit absent |
| `~/.local/share/caplab-dashboard` | absent |
| Tailscale Serve JSON | SHA-256 `0aca4fa0c6133b5942902a803527df1aa8a4c0af1e577e17006e17913d9f8947` |
| Tailscale Funnel | `AllowFunnel: null` |
| public-index source | `/home/halbritt/git/tailscale-index/site/index.html`, 6,085 bytes, mode `0664`, owner `halbritt:halbritt` |
| public-index SHA-256 | `7f2c961532eed79e51505ae67f19cccbd6ac563736a761695448fa86e9154c5f` |
| public index over HTTPS | byte-identical to the local before file |
| Cloudflare config | tracked and installed SHA-256 `f25f08d4bf4495476da693fa59e0359d17e644c91bdb2ad2e0a0a8c495b1e98f`; no CAPLAB, `3021`, or `8784` route |

The exact before-index bytes were retained during enactment at
`/tmp/tailscale-index-before-caplab-2026-07-15.html`. The durable reverse
operation is the committed [`tailscale-index-card.patch`](tailscale-index-card.patch),
whose forward and reverse hashes were independently exercised.

## Enacted state

- Release directory:
  `~/.local/share/caplab-dashboard/releases/e4636d2628adbbfca953734d4dc7cdfa91d72b04/`.
- Active symlink:
  `~/.local/share/caplab-dashboard/current` ->
  `releases/e4636d2628adbbfca953734d4dc7cdfa91d72b04`.
- Installed stamp: exact full source commit above.
- Installed unit:
  `~/.config/systemd/user/caplab-dashboard.service`, SHA-256
  `a4c7d9940ddfb85a85238b0a8181486aa28ddecbf90ed46ec763771eece8a0fa`;
  byte-identical to the canonical unit.
- Origin: `http://127.0.0.1:3021/`, with no wildcard, LAN, or tailnet-IP
  listener.
- Tailnet route: `https://proximal.tail0ecc2e.ts.net:8784/` ->
  `http://127.0.0.1:3021`.
- Public index: one card titled `Agent Capability Lab (CAPLAB)`, linked to the
  tailnet URL, with separate `study results` and `tailnet only` tags.

### User-unit compatibility observation

The first user-service start failed closed with `status=218/CAPABILITIES`.
Journal evidence named capability dropping before the Python process began.
`PrivateDevices=true` was the credible directive-specific rival because the
unit had already excluded the four kernel-object hardening directives known to
fail in this host's user manager. Removing only `PrivateDevices` in canonical
commit `d3ba0f7`, reinstalling that unit, and restarting produced an active
service with the same remaining user-safe hardening. The service was then
reset to a clean `Result=success`, `NRestarts=0` state. The application's
fail-closed loopback bind remains the network boundary.

## Route preservation evidence

- Serve JSON after adding CAPLAB SHA-256:
  `95da350a26d93cc0d00e87cd03992007d06481aaf86b9b598868696635982edb`.
- After deleting only `TCP["8784"]` and
  `Web["proximal.tail0ecc2e.ts.net:8784"]` from the after JSON, the canonical
  SHA-256 is exactly the before hash:
  `0aca4fa0c6133b5942902a803527df1aa8a4c0af1e577e17006e17913d9f8947`.
- The CAPLAB TCP entry is exactly `{"HTTPS": true}`.
- The complete CAPLAB Web entry contains only `/` proxying to
  `http://127.0.0.1:3021`.
- Existing `:443` remained `/` -> `http://127.0.0.1:8909`.
- `AllowFunnel` remained null.

This normalized equality is the model-free proof that every pre-existing Serve
route is unchanged.

## Index change and rollback identity

| State | SHA-256 |
|---|---|
| immediately before edit | `7f2c961532eed79e51505ae67f19cccbd6ac563736a761695448fa86e9154c5f` |
| immediately after edit | `8acec320a1bbb4d1bd6e591b0e7b124960c02776e91a35ab5acd058fd690d27a` |
| public `https://tailscale.harm.org/` after edit | `8acec320a1bbb4d1bd6e591b0e7b124960c02776e91a35ab5acd058fd690d27a` |

The exact semantic change is the single eleven-line CAPLAB article in
`tailscale-index-card.patch`: title, tailnet URL, and the two requested tags.
No study identity, aggregate, claim, evidence, or private locator was added.
The live file remained otherwise byte-identical.

The patch was applied to a copy of the captured before bytes and produced the
exact after hash. Applying the patch in reverse to that result reproduced the
exact before hash. This is a model-free rollback proof, not a claim that live
rollback was executed.

## Verification observations

- `caplab-dashboard/verify.sh` passed after publication. It re-archived the
  pinned Git commit and compared every installed application byte, compared the
  installed unit, checked the process working directory, required enabled and
  active state, required a loopback-only listener, exercised health/catalog and
  405 behavior, required the complete `:8784` route, rejected Funnel, and fetched
  the tailnet HTTPS health endpoint.
- User linger is `yes`; the unit is enabled under `default.target`, active, and
  running with `Result=success`, `NRestarts=0`.
- The service process working directory is the exact commit-named release's
  `app` directory.
- Local `/` returned 200 with no-store, noindex, CSP, nosniff, and no-referrer
  headers. Local `POST /` returned 405 with `Allow: GET, HEAD`.
- The catalog returned exactly `caplab-study-001` as available and retained the
  unavailable cross-study comparison state.
- Installed and books-source projection hashes both equal
  `7b710b3188ab97228acbeb4c05066e3a7aefa31891bf160780337b177941a55d`.
- Chromium rendered the public index card and the tailnet dashboard. Screenshot
  SHA-256 values are `67ca510b2f68ec5d718fee11975f9b6d33fbb5e19aeb8af99faf7a29c5121186`
  (`/tmp/caplab-live-public-index.png`) and
  `6d92b4a464a1d1a2a63e18181a0d7817e100e5bbd2cadd659ad8f0cae62baf4d`
  (`/tmp/caplab-live-tailnet-dashboard.png`).
- Remote-node HTTPS verification was attempted through the online `liminal` and
  `homeassistant` tailnet nodes; both refused TCP 22, so no remote shell was
  available. Same-host MagicDNS/TLS/browser verification is therefore the
  available route evidence and is explicitly weaker than a remote-node fetch.
- Tracked and installed Cloudflare config remained byte-identical at the before
  hash and validates successfully. The tailnet's wildcard DNS resolves
  `caplab.harm.org`, but HTTPS returns 404 through the existing terminal ingress
  rule; no CAPLAB public route exists.

## Explanatory-content update — 2026-07-15

The repository owner requested enough context for a first-time reviewer to
understand the study, its purpose, and its claim boundary. This update changed
only committed application bytes and the canonical source pin. It did not
change the Tailscale route, public index, systemd unit, Cloudflare ingress, or
CAPLAB evidence and review state.

### Source and release binding

- Previous books source:
  `e4636d2628adbbfca953734d4dc7cdfa91d72b04`.
- Updated books source:
  `3314c9fc47204542ebbb3ac473f5edafca022654`, pushed on
  `agent/caplab-study-dashboard`.
- Proximal source-pin commit:
  `b9182edf55029c9924153505a3eb57eba55de0b7`, pushed on
  `agent/caplab-study-dashboard-host` before installation.
- Active release: `releases/3314c9fc47204542ebbb3ac473f5edafca022654`.
- Previous release retained for rollback:
  `releases/e4636d2628adbbfca953734d4dc7cdfa91d72b04`.
- Updated Study 001 projection SHA-256:
  `c1a3555a900bca0b54c51eaee9efe8a71b1c00c43e04556995b351621ebc36b5`;
  installed and source bytes matched.

The updated projection uses `study-results-dashboard/2` and requires a
study-specific explanation of the scenario, selection rationale, question,
hypothesis, treatment arms, outcome, design, result, interpretation, metrics,
reading order, and glossary. The server rejects a projection missing that
context. The renderer presents it before the primary result and moves the full
status ledger behind the scientific reading path.

### Deployment observation

The installer created the immutable release, switched `current`, retained the
old release as `previous`, and restarted the unit. The first chained
`verify.sh --local-only` invocation then reported `nothing is listening on TCP
port 3021`. Twelve seconds after the restart, systemd reported the new process
active with `Result=success` and `NRestarts=0`; the journal contained one clean
stop/start pair, the expected loopback listener was present, and health
returned `ok`. Re-running local and full verification passed.

**Inference:** the first verification observed the interval between systemd's
successful process start and the socket becoming visible. A transient process
failure is the main rival; the absence of a failed unit state, restart, or
journal error and the later live process from the exact release oppose that
rival. This observation does not weaken or bypass the verification gate: the
deployment was considered technically verified only after both complete reruns
passed.

### Preservation and live verification

- Complete canonical Serve JSON SHA-256 before and after:
  `95da350a26d93cc0d00e87cd03992007d06481aaf86b9b598868696635982edb`.
  The `:8784` handler remained the one HTTPS proxy to
  `http://127.0.0.1:3021`, `:443` remained unchanged, and `AllowFunnel`
  remained null.
- Local and public index SHA-256 before and after:
  `8acec320a1bbb4d1bd6e591b0e7b124960c02776e91a35ab5acd058fd690d27a`.
  The file retained exactly one CAPLAB card and no study data.
- Canonical and installed user-unit SHA-256:
  `a4c7d9940ddfb85a85238b0a8181486aa28ddecbf90ed46ec763771eece8a0fa`.
- Canonical and installed Cloudflare configuration SHA-256:
  `f25f08d4bf4495476da693fa59e0359d17e644c91bdb2ad2e0a0a8c495b1e98f`;
  ingress validation passed.
- The service remained enabled and active with a loopback-only listener,
  `Result=success`, and `NRestarts=0`. Its process working directory resolved
  to the updated commit-named release.
- Local and tailnet API reads returned `study-results-dashboard/2` and the new
  title. Full `verify.sh` passed, including the tailnet HTTPS health read.
- Live Chromium loaded the tailnet URL, rendered the first-screen customer-harm
  summary, followed the overview jump link, opened the glossary, and rendered
  at 390 pixels without document-level overflow or console errors.
- Live screenshot SHA-256 values are
  `f588594df1afe6135004cb9512b7e0b48fca5a642a3a70fbf8240575b8a84013`
  (`/tmp/caplab-study-dashboard-live-top.png`),
  `b68dda92cd95136dfa7e0cfb8a78bcc7996017609fa9251120bbe73004ab7c11`
  (`/tmp/caplab-study-dashboard-live-overview.png`), and
  `f6e2e34f2c4aff81322d5515a2a154c541ff4fb27591f5028d25f504bd3f3d3c`
  (`/tmp/caplab-study-dashboard-live-narrow.png`).

The route itself did not change, so the initial enactment's remote-node
verification residual remains unchanged and was not re-tested. The exact
installed application bytes and same-host tailnet TLS path were reverified.

Application rollback now has an exact retained target: run `rollback.sh` to
switch to the previous `e4636d2` release, then restore the canonical
`SOURCE_COMMIT` to that full commit and run the installer and verification from
the matching pushed desired state. The Tailscale route and public index require
no rollback because this update did not change them.

## Subject-configuration update — 2026-07-15

The repository owner observed that the explanatory dashboard did not mention
the harness/model/effort tuple. This update makes the exercised subject
configuration required reviewer context and displays it before the treatment
arms. It changes committed application bytes and the canonical source pin only;
it does not change the Tailscale route, public index, user unit, Cloudflare
ingress, historical evidence, or CAPLAB review state.

### Source and release binding

- Previous books source:
  `3314c9fc47204542ebbb3ac473f5edafca022654`.
- Updated books source:
  `0900f04e484186a837cc8231d2756407fd31a9da`, pushed on
  `agent/caplab-study-dashboard`.
- Proximal source-pin commit:
  `a6320c53d17a4a15ea719cd6fa705f92ae017d94`, pushed on
  `agent/caplab-study-dashboard-host` before installation.
- Active release:
  `releases/0900f04e484186a837cc8231d2756407fd31a9da`.
- Previous release retained for rollback:
  `releases/3314c9fc47204542ebbb3ac473f5edafca022654`.
- Updated Study 001 projection SHA-256:
  `cea1f4004a11f5f3b443ff4d85e81fcfb4f2d2df02b0db11287900481f01e64f`;
  installed and source bytes matched.

The updated projection uses `study-results-dashboard/3`. Its required
`study_context.subject_tuple` records the harness profile `codex-luna-max`,
provider/model route `gpt-5.6-luna`, reasoning effort `max`, runtime
`Codex CLI 0.144.1`, and unavailable immutable model-weight identity. The
renderer places the tuple after the study question and before the B/V treatment
arms. The adjacent scope note says that the observed result does not transfer
automatically to another harness, model route, reasoning effort, runtime, or
model-weight identity.

### Deployment and verification observations

- The installer created the commit-named immutable release, switched `current`,
  retained the old release as `previous`, and restarted the user unit.
- Health, the loopback listener, and the active unit were ready on the first
  bounded poll after installation. The unit reported `Result=success` and
  `NRestarts=0`.
- Complete local and tailnet `verify.sh` runs passed. The service remained
  enabled and active, and its only TCP `3021` listener remained
  `127.0.0.1:3021`.
- The live tailnet API returned `study-results-dashboard/3` and the exact five
  subject-configuration values listed above.
- Complete canonical Serve JSON SHA-256 before and after remained
  `95da350a26d93cc0d00e87cd03992007d06481aaf86b9b598868696635982edb`.
  The `:8784` handler remained the one HTTPS proxy to
  `http://127.0.0.1:3021`, and Funnel remained absent.
- Local and public index SHA-256 before and after remained
  `8acec320a1bbb4d1bd6e591b0e7b124960c02776e91a35ab5acd058fd690d27a`.
- Canonical and installed user-unit SHA-256 remained
  `a4c7d9940ddfb85a85238b0a8181486aa28ddecbf90ed46ec763771eece8a0fa`.
- Canonical and installed Cloudflare configuration SHA-256 remained
  `f25f08d4bf4495476da693fa59e0359d17e644c91bdb2ad2e0a0a8c495b1e98f`;
  ingress validation passed before installation.
- Live Chromium rendered the tuple at 1440 and 390 pixels. Both views placed
  it before the treatment arms, showed the transfer warning, had no
  document-level overflow, and emitted no console or page errors.
- Live screenshot SHA-256 values are
  `81bcddb3578c6f3fd8c156b7fad695f7b6ea6e0b4dbfa36293f212913d131d9b`
  (`/tmp/caplab-study-dashboard-live-subject-tuple-desktop.png`) and
  `6254bab6e4cb8dbe815b98072f6ea6cc8c3a506d4039c96fae2382e75a48aead`
  (`/tmp/caplab-study-dashboard-live-subject-tuple-narrow.png`).

**Observation:** the historical record identifies the exercised harness
profile, provider/model route, effort, and runtime but does not contain an
immutable model-weight digest. Displaying `unavailable` preserves that evidence
limit; it is not an inference that the provider route uniquely identifies the
weights.

## Restore the captured before state

Stop if any compare-before-mutate check fails.

1. Require the live index to equal the recorded after hash. Dry-run, then
   reverse the committed patch:

   ```bash
   test "$(sha256sum /home/halbritt/git/tailscale-index/site/index.html | awk '{print $1}')" = 8acec320a1bbb4d1bd6e591b0e7b124960c02776e91a35ab5acd058fd690d27a
   patch --dry-run --reverse --batch -p1 -d /home/halbritt/git/tailscale-index < caplab-dashboard/tailscale-index-card.patch
   patch --reverse --batch -p1 -d /home/halbritt/git/tailscale-index < caplab-dashboard/tailscale-index-card.patch
   test "$(sha256sum /home/halbritt/git/tailscale-index/site/index.html | awk '{print $1}')" = 7f2c961532eed79e51505ae67f19cccbd6ac563736a761695448fa86e9154c5f
   ```

2. Run `caplab-dashboard/verify.sh` immediately before withdrawing publication;
   it refuses a changed handler or Funnel. Remove only the CAPLAB route, then
   require the complete Serve JSON to reproduce the before hash:

   ```bash
   caplab-dashboard/verify.sh
   tailscale serve --https=8784 off
   test "$(tailscale serve status --json | jq -S . | sha256sum | awk '{print $1}')" = 0aca4fa0c6133b5942902a803527df1aa8a4c0af1e577e17006e17913d9f8947
   ```

3. Require the installed unit hash above, then restore the absent unit state:

   ```bash
   test "$(sha256sum /home/halbritt/.config/systemd/user/caplab-dashboard.service | awk '{print $1}')" = a4c7d9940ddfb85a85238b0a8181486aa28ddecbf90ed46ec763771eece8a0fa
   systemctl --user disable --now caplab-dashboard.service
   rm /home/halbritt/.config/systemd/user/caplab-dashboard.service
   systemctl --user daemon-reload
   ```

4. The captured data-root state was absent. After checking that `current` and
   every release stamp name only the recorded source commit, remove
   `~/.local/share/caplab-dashboard`. This removal is intentionally separate and
   destructive; do not run it as part of ordinary application-version rollback.

The public index service itself is not restarted by either enactment or
rollback because it reads the current file on each request. Verify public bytes
after either operation.
