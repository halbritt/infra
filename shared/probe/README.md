# Probe code-search CLI

The owner requested Probe and a code-search skill on 2026-10-25. Use the native
Linux binary for local search, extraction, symbol listing and AST queries.
The managed skill is `~/git/skillpack/skills/code-search/SKILL.md`; deploy it
through skillpack's installer. Existing Jevgrep and codebase-memory skills own
their provider and graph-specific workflows.

## Installation

Upstream: <https://github.com/probelabs/probe>. The GitHub latest-release API
selected `v0.6.0-rc343` on 2026-10-25. This is the observed installation version,
not an upgrade pin. The native binary reports `probe-code 0.6.0`, omitting the
release-candidate suffix.

- Asset: `probe-v0.6.0-rc343-x86_64-unknown-linux-musl.tar.gz`.
- Archive SHA-256 from GitHub asset metadata, verified before extraction:
  `dfd8d92ba7f0067907b069c030fc2093eccdd20e2554537a824b1f9503b86ab4`.
- Installed binary SHA-256:
  `f39e259559b9c0b5fa921cbb9167dcef1226d58887a9929d59ed911143be0885`.
- Destination: `/usr/local/bin/probe`, mode `0755`, root-owned.

Reproduce this installation on x86-64 Linux:

```sh
(
set -e
probe_release=v0.6.0-rc343
probe_asset=probe-${probe_release}-x86_64-unknown-linux-musl
probe_stage=$(mktemp -d)
curl -fL "https://github.com/probelabs/probe/releases/download/${probe_release}/${probe_asset}.tar.gz" -o "$probe_stage/probe.tar.gz"
printf '%s  %s\n' dfd8d92ba7f0067907b069c030fc2093eccdd20e2554537a824b1f9503b86ab4 "$probe_stage/probe.tar.gz" | sha256sum -c -
tar -xzf "$probe_stage/probe.tar.gz" -C "$probe_stage" --strip-components=1 "$probe_asset/probe"
sudo install -m 0755 "$probe_stage/probe" /usr/local/bin/probe
rm -rf "$probe_stage"
probe --version
)
```

For an authorized upgrade, select the current upstream release and its matching
asset digest, then repeat installation and the checks below. Remove
`/usr/local/bin/probe` to uninstall. No package hold, service, global MCP server,
agent hook, model provider or login is configured by this installation.

## Verification and usage

The same binary digest was verified on proximal, peecee-wsl, Talos and Archon.
Ten checks passed on each host using disposable Python/JavaScript/log fixtures:
ranked Boolean search, AST query, extraction by symbol and line, symbol listing,
Probe ignore-file behavior, and ugrep Boolean/fuzzy/gzip/ignore-file behavior.
A real-source search and symbol listing also succeeded in the infra checkout.

Probe's default search output is an outline; request `--format json` for parsed
results. Tests are excluded by default; add `--allow-tests` when needed. Search
results and line-based extractions can be statements or merged neighbors;
extract by `#symbol` for a definition and read the source to verify ownership.
No LSP server or persistent index is needed for these
basic commands. Optional LSP behavior requires separate setup.

The skill selects `rg` for known strings/paths, Probe for code context and AST
patterns, ugrep for Boolean/fuzzy/compressed text, Jevgrep for behavior questions,
and codebase-memory for graph relationships. Availability is checked per host;
Jevgrep's existing proximal TypeSafe authorization is not copied elsewhere.
