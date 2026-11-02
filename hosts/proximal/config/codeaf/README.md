# codeaf

## Retired 2026-11-02

The owner rejected codeaf after inspection because its human-facing workflow
overlaps with Herdr and does not fill the desired tool-running harness role.
Although codeaf has headless commands, no additional role justified keeping it.

Removed `/home/halbritt/.local/bin/codeaf` and the clean upstream checkout at
`/home/halbritt/git/codeaf`. The checkout had no local changes, ignored files,
additional worktrees or unpublished branch commits. No codeaf process or systemd
unit was present, and `/home/halbritt/.codeaf` did not exist. Retain the historical
installation evidence below; it does not describe an active installation.

## Historical installation

Installed on 2026-11-02 at the owner's request to clone codeaf into `~/git`
and install it on Proximal.

- Upstream: <https://github.com/Agent-Field/CodeAF>
- Source checkout: `/home/halbritt/git/codeaf`, upstream default branch `dev`,
  initially at `7e1b9a6c09b5ffb78d6300d593f128c3d5fba1db`.
- Installed executable: `/home/halbritt/.local/bin/codeaf`, stable `v0.8.2`
  for Linux amd64. This is the published release, independent of the dev checkout.
- Binary SHA-256:
  `681d9813f2517addc86fb644d313e3f7cf0ab60be708c8e8b13d77fb16a6798c`.
- Runtime state defaults to `/home/halbritt/.codeaf`; credentials stay outside Git.

## Installation and verification

The initial `make build` failed because the module requests Go 1.26.5 while
the installed toolchain is Go 1.23.4 and `GOPROXY=off` prevents automatic
toolchain downloads. The host Go configuration was left unchanged. Installed
the published stable release with the reviewed upstream installer instead:

```sh
cd /home/halbritt/git/codeaf
bash scripts/install.sh --version v0.8.2 \
  --dir /home/halbritt/.local/bin --no-modify-path --no-start
```

The installer verified the release checksum. `codeaf version`, `codeaf --help`
and `codeaf doctor` exited successfully; a fresh login shell found the command
on PATH. The version reports `v0.8.2`, built 2026-10-23 with Go 1.26.5.
No source changes or shell profile edits were needed.

## Usage and model routing

Run `codeaf` inside the project to open its terminal interface. Provider setup
and inference were not exercised during installation. `doctor` detected the
existing `OPENROUTER_API_KEY` environment variable; no credential was copied
or added. The graph database had not been created and no background timer
was installed.

The owner's subscription-routing policy applies: models covered by a subscription
must use that subscription route. Available OpenRouter credentials do not
authorize routing those models through OpenRouter. The CLI provides
`codeaf connect codex` for ChatGPT subscription sign-in. Authentication or quota
failure must stop the affected operation rather than fall back to OpenRouter.
