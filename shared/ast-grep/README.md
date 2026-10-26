# ast-grep structural code search

Installed at the owner's request on 2026-10-26 alongside Probe and ugrep.
The code-search skill in `~/git/skillpack` selects the appropriate tool and
contains a tested ast-grep reference. Use `/usr/local/bin/ast-grep` explicitly;
the release's `sg` launcher is not installed because Linux may already provide
an unrelated group-switching command with that name.

## Installation and provenance

Upstream: <https://github.com/ast-grep/ast-grep>. GitHub's latest-release API
selected `0.51.0` on the installation date; this records the deployed version,
not an upgrade pin.

- Release asset: `app-x86_64-unknown-linux-gnu.zip`.
- Archive SHA-256, checked against GitHub asset metadata before extraction:
  `a7eead5552d3a8daad70f5d50d935da44bd0c138e946b5b0a96b1d38169fa639`.
- Installed `ast-grep` binary SHA-256:
  `99b5aeab1f47536789482b4517595b759de910f7f1f1d1f80c752824e894e38e`.
- Installed path `/usr/local/bin/ast-grep`, root-owned, mode `0755`.
- Matching version and binary digest verified on proximal, peecee-wsl, Talos
  and Archon. No agent configuration, alias, service or model provider added.

Reproduce on x86-64 Linux:

```sh
(
set -e
ast_stage=$(mktemp -d)
curl -fL https://github.com/ast-grep/ast-grep/releases/download/0.51.0/app-x86_64-unknown-linux-gnu.zip -o "$ast_stage/ast-grep.zip"
printf '%s  %s\n' a7eead5552d3a8daad70f5d50d935da44bd0c138e946b5b0a96b1d38169fa639 "$ast_stage/ast-grep.zip" | sha256sum -c -
unzip -q "$ast_stage/ast-grep.zip" ast-grep -d "$ast_stage"
sudo install -m 0755 "$ast_stage/ast-grep" /usr/local/bin/ast-grep
rm -rf "$ast_stage"
ast-grep --version
)
```

For an upgrade, select the current release and matching asset digest, then
repeat verification. Remove `/usr/local/bin/ast-grep` to uninstall.

## Verification

Seven disposable-fixture checks passed on each host: JavaScript call matching
across formatting while excluding string contents and ignored files, Python
metavariable capture, repeated metavariable equality, filename-only output,
YAML rule scanning, streaming JSON, and unchanged source bytes. JSON positions
were also checked as zero-based. All searches run locally without indexing.

For exact strings use rg; for ranked source context use Probe; for syntax use
`ast-grep run`; for reusable structural rules use `ast-grep scan --rule`.
Official usage: <https://ast-grep.github.io/guide/quick-start.html>.
