# Agent accounts on Archon

Owner-authorized replication from proximal on 2026-09-29. Each account keeps its
own credentials and session state. Skill source is `~/git/skillpack` on Archon.

## Launchers

Install `codex-harm` and `claude-harm` from this directory to `~/.local/bin/`
with mode 0755. They select `~/.codex-harm` and `~/.claude-harm` respectively,
then call the existing host launcher. Default `codex` and `claude` use the matching default proximal accounts.
Archon initially had the harm login in the default Codex profile; it was corrected. Archon's existing Codex coordination launcher is preserved.

## Providers and skills

Hermes uses `model.default: deepseek/deepseek-v4.1-flash`,
`model.provider: openrouter`, with `OPENROUTER_API_KEY` in `~/.hermes/.env`.
Set `skills.external_dirs` to `[/home/halbritt/git/skillpack/skills]` so Hermes
reads the full curated set. Preserve other Hermes configuration and skills.

Install `opencode.json` as `~/.config/opencode/opencode.json` (0600).
OpenCode uses the same Z.ai and OpenRouter provider accounts as proximal; its
default is `zai/glm-5.3`. Provider keys are separate 0600 files under
`~/.config/opencode/provider-keys/` (0700 directory), referenced with `{file:...}`.
Host-local providers are not copied as localhost URLs. File substitution is
[documented upstream](https://opencode.ai/docs/config/#files).

Merge `hermes-overrides.yaml` into `~/.hermes/config.yaml`. `external_dirs` must
be a YAML list, not a JSON-looking string: this Hermes version's `config set`
command stores the latter as a string. Native discovery verified all 52 skills.

Jevgrep 0.7.0 is also installed through Archon's mise-managed npm; its direct
TypeSafe credential is at `~/.config/jevgrep/credentials.json` (0600). `jg doctor`
passed. Updating skillpack does not install every skill's optional runtime tool.

Update the clean `~/git/skillpack` checkout with `git pull --ff-only`, then run
`./install.sh` and `./install.sh --check`. This installs the standard harness
skill directories. Do not re-enable the retired skill-hiding/router trial.

Credentials stay outside Git, mode 0600. Replication uses SSH transport and
copies only account credentials and selected settings, never session histories.
The existing default Claude login matched proximal and was preserved. Private rollback snapshots are
under `~/.local/state/agent-account-replication/20260929/` on Archon.

## Verification — 2026-09-29

- Installed versions: Codex 0.157.1; Claude Code 2.1.283; OpenCode 1.18.33;
  Hermes 0.19.0; Jevgrep 0.7.0.
- Default and harm Codex/Claude identities match their proximal counterparts.
- All six harness/profile probes produced `ARCHON_OK` with successful exits.
  Codex/Claude also confirmed Jevgrep in their available skills. Codex probes
  disabled Cairn MCP for the inference check; this is not a Cairn integration test.
- Skillpack at `49afc71`; deployment check passed. All 52 skill files match the
  checkout in both Codex, both Claude, and OpenCode locations. Native Hermes
  and OpenCode discovery each found all 52 skillpack names.
- Skillpack validation has no failures. Its warnings concern existing doctrine
  scaffolding, the Plane description length, and absent optional upstream source
  checkouts on Archon; vendored skill deployment works without those checkouts.
- Live probe logs and status summaries are in the private rollback directory's
  `checks/` subdirectory. Existing desktop and agent sessions were not restarted.

The first OpenCode probe failed because proximal's `{env:...}` references had no
matching environment on Archon. The final configuration uses private key files;
the repeated live probe passed. Both Codex profiles were rechecked after fixing
the initial default-account mismatch. Historical failure logs are retained.
