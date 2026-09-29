# Jevgrep on proximal

Installed at the owner's request on 2026-09-29 for behavioral code discovery
by coding agents. Use the direct TypeSafe API and the owner's existing credits.

- Package: `@dzhng/jevgrep@0.7.0`, installed with
  `npm install --global @dzhng/jevgrep@0.7.0`.
- Launcher: `/home/halbritt/.npm-global/bin/jg`.
- Runtime observed: Node.js 24.21.0; package requires Node.js 22 or newer.
- Provider: `typesafe`, endpoint `https://api.typesafe.ai/v1`, model
  `jev-1.13.0`. No OpenRouter or Vercel fallback.
- Credential source: `~/.config/typesafe/env`, reused internally without logging
  the value. Authenticated using `jg auth --provider typesafe --stdin`.
- Installed secret: `~/.config/jevgrep/credentials.json`, mode 0600 in a 0700
  directory. Jevgrep uses saved credentials and ignores provider environment
  overrides. Re-run auth after rotating the source credential.
- Skill source: `~/git/skillpack/skills/jevgrep/SKILL.md`; deploy with
  `~/git/skillpack/install.sh`. Skillpack owns the concise local skill;
  do not overwrite it with the separate `jg skill` installer.
- Deployment: Claude and Claude-harm, Codex and Codex-harm, OpenCode, Agy current
  and legacy locations, and Hermes. Existing processes discover it according to
  their harness reload behavior; no active sessions were restarted.

Search sends eligible source to TypeSafe. Choose the repository/subtree being
worked on; `jg files ROOT` gives an offline scope inventory. No database or
background service is required. Evaluation results are cached locally.

## Verification

`jg --version` returned 0.7.0. `jg doctor` verified connection through TypeSafe.
A live query against skillpack, excluding `skills/`, asked how deployment selects
symlinks versus copies and verifies installation. It returned `install.sh` with
verbatim source, README and related reading leads, completed with exit 0 and
`End context.`. Credential provider and permissions were checked without
printing the key. Skill validation and deployment checks passed.

## Maintenance

Upgrade through npm when authorized, then check version, `jg doctor`, and a
bounded source query. Update the skill independently through skillpack and run
its deployment check. This installation does not alter the maintenance bot's
update policy. CLI documentation: <https://github.com/dzhng/jevgrep>.
