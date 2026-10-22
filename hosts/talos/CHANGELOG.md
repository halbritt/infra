# Host changelog

## 2026-10-22 — agent-ee fleet worker host

Owner 2026-10-22, "delegate an agent to setup talos as a build host" (via the
coordinator). Set up to match peecee-wsl, archon and agent-ee-gate-c4; details
in README.md "Fleet worker host".

- Packages: docker.io 29.1.3 + docker-buildx 0.30.1 (held, enabled at boot,
  `halbritt` in `docker`), git, rsync, jq, zstd, apparmor-utils; KiCad
  10.0.7~ubuntu26.04.1 (held) from the Launchpad snapshot 20261015T000000Z
  with suite `resolute`; stock 26.04 ngspice 45.2, bubblewrap 0.11.1,
  poppler 26.01. The Dockerfile's `noble` snapshot cannot be installed on 26.04;
  tests rely on the CI image.
- Toolchain: node v24.22.0, npm 11.19.1, claude 2.1.307, codex 0.163.0 (full
  standalone tree from peecee-wsl), uv 0.13.4, git-wt/git-land wrappers.
- AppArmor profile `agent-ee-container` installed in `/etc/apparmor.d` and
  loaded. `ae-ci-exec` (`0e8cb9d2…015290`) built `agent-ee:exec-4ff2f011477682a7`
  in 430 s; `tests.test_tree_hygiene` 6 tests OK from a git-wt worktree.
- Repos: `~/git/agent-ee` pushed from proximal (new proximal remote `talos`),
  kicad-route pin 5f1c072, fome-mc 8c42f2ee, kicad-happy 06840467;
  `~/.cache/agent-worktrees/agent-ee/`.
- Credentials: added to `REMOTE_HOSTS` of claude-oauth-refresh and
  codex-auth-mirror; first push mirrored all five profiles (access tokens only).
  claude, claude-harm and codex-3 answered live probes; codex and codex-harm
  authenticated but are at their usage limit until 2026-10-27.
- Launcher: added to `HOSTS` and `REMOTE_ACCOUNTS` (all five accounts); test
  parallelism cap 3. Smoke worker via launch.py passed (exit 0, 13 s, sync_down
  and branch fetch OK) and was cleaned up.
- Added `config/apt/` (the KiCad snapshot sources file), which also supplies
  the `paths.config` directory machine.yaml names.

## 2026-10-22 — Initial record

Fresh Ubuntu Server 26.04.1 LTS install on an Intel NUC10i7FNH, recorded from a
read-only survey. No changes were made on the host.
