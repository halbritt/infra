# Maintenance outcomes — proximal

## 2026-09-29 13:32 UTC — 57743817-6b0f-4ffe-b9a9-8feeb9aa28ca

Host: proximal. Policy: maintenance-v2. Run status: partial.

- **llama.cpp** — verified. Before: ~/git/llama.cpp clean on master at fc07d781e61f0d23764394e902b88d26a974e202 (upstream commit; on-disk llama-server build is this revision/later); git ls-remote upstream master=c85b92c69c955961621193cd51da194f3cbcedf3, GitHub compare fc07d781...c85b92c6 ahead_by=13 (tests/common/chat/vulkan/metal/ggml fixes); live inference PID 1126876 serving :8081 healthy. Canonical updater holds its native update.lock, refuses dirty/diverged trees, builds llama-server/cli/quantize in an isolated worktree and installs binaries atomically without restarting the live process.. After: master fast-forwarded to c85b92c69c955961621193cd51da194f3cbcedf3; llama-server/cli/quantize rebuilt and atomically installed, build 11256 commit c85b92c69; live server unchanged.
  Verification: install.log prints 'version: 0.5.0-dev (build 11256, commit c85b92c69)' and 'updated=c85b92c69c95...'; verify.log (exit 0) HEAD=c85b92c69 matches and :8081 returns {"status":"ok"}.
  Activation: installed (on-disk binaries advanced to build 11256); running inference PID 1126876 not restarted; new binary activates at the next managed llama-27b restart.
  Evidence: `/var/lib/update-bot/runs/57743817-6b0f-4ffe-b9a9-8feeb9aa28ca/operations/408ea616-ecbd-4066-a861-6c37320fc7d6`.

- **codex** — verified. Before: Global npm @openai/codex@0.158.0 (installed 2026-09-28 prior run, receipt f14095ec); npm view @openai/codex version=0.159.0; Cairn coordination shim /home/halbritt/.local/bin/codex present and unchanged; several codex app-server sessions may be running on the prior package bytes (they keep their loaded code).. After: @openai/codex@0.159.0.
  Verification: install.log 'changed 2 packages in 3s'; verify.log (exit 0) reports codex-cli 0.159.0 via the Cairn wrapper.
  Activation: installed (global npm package replaced on disk); already-running codex sessions keep their loaded code; launcher wrapper unchanged.
  Evidence: `/var/lib/update-bot/runs/57743817-6b0f-4ffe-b9a9-8feeb9aa28ca/operations/ccff6619-f517-419d-a3bc-01b715e07bb0`.

- **os** — verified. Before: Ubuntu noble (6.8.0-138). apt list --upgradable = 28 packages, all held-scope (pgdg postgresql-16/17 family + libpq5 + pgbackrest + postgresql-common, kubelet/kubeadm/kubectl/containerd.io, google-cloud-cli/anthoscli, nvidia/libnvidia-container-toolkit). reboot_required=true (kernels 6.8.0-139/142, libc6, linux-base). Prior helper receipt /var/lib/update-bot-os/latest.json applied python3-jwt and deferred 28 held packages. Fixed root helper refreshes metadata and applies only allowed Ubuntu updates.. After: libevent 2.1.12-stable-9ubuntu2.2 (6 packages) observed; 27 held-scope packages deferred; reboot_required=true.
  Verification: helper receipt /var/lib/update-bot-os/latest.json status=completed, selected=6 libevent packages (before/after observed), deferred=27; operation verify exit 0.
  Activation: installed by the fixed root helper; no package-script service restart and no reboot.
  Evidence: `/var/lib/update-bot/runs/57743817-6b0f-4ffe-b9a9-8feeb9aa28ca/operations/efe5f69f-e0be-4c39-9bbf-afbe97353629`.

- **hermes** — verified. Before: Installed Hermes generation is /var/lib/update-bot/staging/hermes-carry at 9b57ee21 (upstream base 79a6fd3e + 4 carried commits b8ae93b03/2c6121992/131e95b31/9904fd411 ported), selected by ~/.local/bin/hermes; gateway PID 785678 running from that generation. Upstream main advanced to fc042f1d67bc393bf43920e92d4eb5082eddedfb (committed 2026-09-29T13:07:11Z), 402 commits ahead of 79a6fd3e. This op only creates an isolated read-only upstream clone under /var/lib/update-bot/staging and trial-applies the carried patch; it does not touch the live install, launcher or gateway, builds nothing, and does not restart anything.. After: isolated clone /var/lib/update-bot/staging/hermes-candidate-fc042f1d pinned at fc042f1d (candidate base for the port); carried patch hermes.patch trial-apply FAILED (conflicts hermes_cli/cli_tui_runtime_mixin.py:13, tools/approval.py:22).
  Verification: operation envelope status=verified exit 0; apply log /var/lib/update-bot/staging/hermes-candidate-fc042f1d-apply.log shows base=fc042f1d and APPLY_CONFLICTS with the two conflicting files.
  Activation: none — preparation only; no binary built, no launcher/gateway change, existing generation and running gateway (PID 785678) untouched.
  Evidence: `/var/lib/update-bot/runs/57743817-6b0f-4ffe-b9a9-8feeb9aa28ca/operations/f2eee55c-a4c7-40d0-9df5-81a733aab738`.

## 2026-09-28 13:36 UTC — f3fd5201-ddc3-48d9-b33f-302b9f79548d

Host: proximal. Policy: maintenance-v2. Run status: completed.

- **llama.cpp** — failed. Before: read-only post-install verification of the already-finished original install operation a2f0b9b0-cd3a-45e1-927d-dcf37fe4609b (install exit 0, verification_exit_code 1 only because its verifier asserted the pre-fetch upstream target d77dd0806dc while the canonical updater's own fetch saw origin/master advance to f00a64c1472fb695f40ed4fd54cbe998ac7ce6c4). No installer rerun. Installed on disk: llama-server build 11234 commit f00a64c14; master HEAD f00a64c147; live server PID 1126876 still the old build on :8081, health ok. After: see operation receipt.
  Verification: native verification exit None.
  Activation: not established by this receipt.
  Evidence: `/var/lib/update-bot/runs/f3fd5201-ddc3-48d9-b33f-302b9f79548d/operations/632d13c0-0eb0-42a5-801a-2269928b5766`.

- **os** — verified. Before: Ubuntu 24.04.5 noble; apt list --upgradable = 28 packages, all inside the held scope (postgresql-16/17 pgdg + libpq5 + pgbackrest + postgresql-common, kubelet/kubeadm/kubectl/containerd.io, google-cloud-cli, nvidia/libnvidia-container-toolkit); no ordinary noble release/security/update packages pending; reboot_required=true carried from prior helper receipt; fixed root helper is the only permitted OS path. After: python3-jwt 2.7.0-1ubuntu0.2 (observed); 28 held packages still deferred; reboot_required=true.
  Verification: helper receipt /var/lib/update-bot-os/latest.json status=completed, selected=[python3-jwt 2.7.0-1ubuntu0.1->2.7.0-1ubuntu0.2 observed], deferred=28; operation verify exit 0.
  Activation: installed (system package upgraded by the fixed root helper; no package-script service restart, no reboot).
  Evidence: `/var/lib/update-bot/runs/f3fd5201-ddc3-48d9-b33f-302b9f79548d/operations/81961bc7-b41c-413f-89ee-7d73dcb42309`.

- **llama.cpp** — failed. Before: ~/git/llama.cpp clean on master at 4da6337767f973e2b4d0797e5b323d77d8565e4a; on-disk build/bin/llama-server build 11223 commit 4da633776; upstream master via git ls-remote = d77dd0806dc26fc418273ef99f88da11239ca41b (fast-forwardable, ahead of local); native update.lock free; live llama-server PID 1126876 build 10210 healthy on :8081 and will not be restarted; prior end-to-end build 2026-09-27 took ~9 min. After: master fast-forwarded to f00a64c1472fb695f40ed4fd54cbe998ac7ce6c4; llama-server/cli/quantize rebuilt and atomically installed, build 11234 commit f00a64c14; live server unchanged.
  Verification: install exit_code=0 (git ff + .new/mv binary install from the candidate worktree); verification_exit_code=1 only because the verifier asserted the pre-fetch target d77dd0806dc while the updater's own fetch saw origin/master advance to f00a64c147. Live :8081 health ok throughout; live process not restarted.
  Activation: installed (on-disk binaries advanced to build 11234); running process not restarted, still the prior build until its next managed restart.
  Evidence: `/var/lib/update-bot/runs/f3fd5201-ddc3-48d9-b33f-302b9f79548d/operations/a2f0b9b0-cd3a-45e1-927d-dcf37fe4609b`.

- **llama.cpp** — verified. Before: read-only post-install verification (corrected) of the finished original install operation a2f0b9b0-cd3a-45e1-927d-dcf37fe4609b (install exit 0). Two earlier checks failed only on a bad assertion string: llama-server --version prints the 9-char commit abbreviation f00a64c14, but the prior checks searched for 12/9-char prefixes that do not appear verbatim. No installer rerun and no ref changes. Installed: llama-server build 11234 commit f00a64c14; master HEAD f00a64c1472fb695f40ed4fd54cbe998ac7ce6c4; live server PID 1126876 still the prior build on :8081, health ok. After: confirmed on-disk commit f00a64c14, HEAD f00a64c1472fb695f40ed4fd54cbe998ac7ce6c4, and :8081 health {"status":"ok"}.
  Verification: read-only check exit 0 and its verifier exit 0; install.log prints build 11234 commit f00a64c14 and HEAD f00a64c1472fb695f40ed4fd54cbe998ac7ce6c4; verify.log commit=f00a64c14, HEAD=f00a64c1472fb695f40ed4fd54cbe998ac7ce6c4, health-ok.
  Activation: installed (running inference process intentionally unchanged; new binary activates at the next managed llama-27b restart).
  Evidence: `/var/lib/update-bot/runs/f3fd5201-ddc3-48d9-b33f-302b9f79548d/operations/b60b13c6-0fb6-444d-b0ae-b21f4dbd5ea2`.

- **codex** — verified. Before: installed @openai/codex@0.157.1 (npm ls -g); npm view @openai/codex version = 0.158.0 and GitHub openai/codex latest release rust-v0.158.0 (2026-09-28); Cairn coordination wrapper ~/.local/bin/codex unchanged and points at the npm package bin/codex.js; several codex app-server/remote sessions are running (PIDs 324942/505575/929161) and keep their already-loaded files, so no session is restarted. After: @openai/codex@0.158.0.
  Verification: install.log 'changed 2 packages in 3s'; verify.log codex=0.158.0 with wrapper-target-ok and the bin/codex.js + shim present.
  Activation: installed (global npm package replaced on disk); already-running codex sessions kept their loaded code, launcher wrapper unchanged.
  Evidence: `/var/lib/update-bot/runs/f3fd5201-ddc3-48d9-b33f-302b9f79548d/operations/f14095ec-3108-44cd-8090-e7c03bd9ac0e`.

## 2026-09-28 02:18 UTC — bb791a85-0619-4356-b2ee-4a133e7a7366

Host: proximal. Policy: maintenance-v2. Run status: completed.

- **os** — verified. Before: Ubuntu 24.04.5, kernel 6.8.0-138-generic, reboot pending from a prior run; apt list --upgradable shows 28 packages, all inside the helper's held scope (pgdg PostgreSQL 16/17/18 + pgbackrest + libpq5, kubelet/kubeadm/kubectl/containerd.io, nvidia-container-toolkit/libnvidia-container1, google-cloud-cli), so no ordinary noble-updates package is pending; helper's root-owned apt/native locks are free. After: see operation receipt.
  Verification: native verification exit 0.
  Activation: not established by this receipt.
  Evidence: `/var/lib/update-bot/runs/bb791a85-0619-4356-b2ee-4a133e7a7366/operations/50a8a8f8-82f6-453f-a22e-062bf47256b8`.

- **llama.cpp** — failed. Before: ~/git/llama.cpp clean on master at a97cce86a; origin/master (fetched locally) is 4da6337767, exactly 1 commit ahead; updater candidate worktree at a97cce86a; running llama-server PID 1126876 is build 10210 (000547513) on :8081, health ok; on-disk binary build 11222; native update.lock free; prior end-to-end build 2026-09-27 took ~9 min (10:32-10:41 PDT). After: see operation receipt.
  Verification: native verification exit 1.
  Activation: not established by this receipt.
  Evidence: `/var/lib/update-bot/runs/bb791a85-0619-4356-b2ee-4a133e7a7366/operations/561109fd-587d-4886-bac7-9453f5c883ae`.

- **llama.cpp** — failed. Before: post-update confirmation pass: ~/git/llama.cpp master already at 4da6337767 and on-disk build/bin/llama-server is build 11223 commit 4da633776; the preceding operation 561109fd-587d-4886-bac7-9453f5c883ae completed its install with exit 0 but its verify_argv failed only because it asserted the full 10-char hash while llama prints a 9-char commit; live server PID 1126876 still build 10210 on :8081 health ok; this pass is idempotent and should report 'already current'. After: see operation receipt.
  Verification: native verification exit 1.
  Activation: not established by this receipt.
  Evidence: `/var/lib/update-bot/runs/bb791a85-0619-4356-b2ee-4a133e7a7366/operations/6f7dc1a9-5b7c-448d-81c7-6b63a3b73249`.

- **llama.cpp** — verified. Before: second post-update confirmation pass: master and on-disk binary already at 4da6337767 / build 11223 commit 4da633776; the two preceding receipts (561109fd install exit 0; 6f7dc1a9 install exit 0 'already current') failed verification only because their assertions read llama-server's version from stdout while it prints to stderr; live server PID 1126876 still build 10210 on :8081, health ok; this pass is idempotent and reports 'already current'. After: master fast-forwarded to 4da6337767f973e2b4d0797e5b323d77d8565e4a; llama-server/cli/quantize rebuilt and atomically installed, build 11223 commit 4da633776; live server unchanged (still build 10210, health ok).
  Verification: installing op 561109fd-587d-4886-bac7-9453f5c883ae exit_code=0 (git ff + .new/mv binary install, live processes untouched); verified op 9f620ad7-2b2a-44c3-98d2-4f551eb16953 re-ran the native updater (no-op 'already current') with verification_exit_code=0 asserting on-disk binary commit 4da633776, HEAD=4da6337767f973e2b4d0797e5b323d77d8565e4a, and http://localhost:8081/health ok. Two earlier receipts (561109fd, 6f7dc1a9) had verification_exit_code=1 only because their assertions read llama-server's version from stdout while it prints to stderr; the update itself succeeded..
  Activation: installed (on-disk binaries advanced); running process not restarted — live server keeps build 10210 until its next managed restart.
  Evidence: `/var/lib/update-bot/runs/bb791a85-0619-4356-b2ee-4a133e7a7366/operations/9f620ad7-2b2a-44c3-98d2-4f551eb16953`.

## 2026-09-28 02:12 UTC — 563e6f35-0993-4491-8b46-8a71a866119e

Host: proximal. Policy: maintenance-v2. Run status: completed.

- **os** — verified. Before: Ubuntu 24.04.5, kernel 6.8.0-138; 39 packages upgradable incl. noble-updates security (apparmor/libapparmor1 4.0.1-0ubuntu0.24.04.8, dnsmasq-base, libaudit1, libpciaccess0, linux-firmware-amd-graphics, xserver-xorg-core/xvfb 21.1.12-1ubuntu1.8) alongside held scope (postgresql 16/17/18 pgdg, kubelet/kubeadm/containerd.io, nvidia-container-toolkit, google-cloud-cli, libpq5/pgbackrest); reboot pending since 2026-09-24 (kernels 6.8.0-139/-142, libc6). No active apt/dpkg transaction observed.. After: 13 packages upgraded and observed at targets (apparmor/libapparmor1 4.0.1really4.0.1-0ubuntu0.24.04.8, libaudit1/common 1:3.1.2-2.1ubuntu0.1, dmidecode 3.5-3ubuntu0.2, dnsmasq-base 2.91-0ubuntu0.24.04.1, dracut-install 060+5-1ubuntu3.4, libpciaccess0 0.17-3ubuntu0.24.04.3, linux-firmware-amd-graphics ...0ubuntu3.3, python3-requests 2. 31.0+dfsg-1ubuntu1.2, xserver-common/xserver-xorg-core/xvfb 2:21.1.12-1ubuntu1.8); 28 packages deferred; reboot_required=true (not taken).
  Verification: operation verify_argv asserted /var/lib/update-bot-os/latest.json status=='completed'; each selected package's observed version equals its target; receipt /var/lib/update-bot/runs/563e6f35-0993-4491-8b46-8a71a866119e/operations/c27398f3-4ce9-4bf3-b44e-e5eebf927b0c/result.json has exit_code=0 and verification_exit_code=0.
  Activation: installed (helper suppresses package-script service restarts; kernel/libc activation requires the deferred reboot, so those are installed but not yet active; userspace library packages took effect on install).
  Evidence: `/var/lib/update-bot/runs/563e6f35-0993-4491-8b46-8a71a866119e/operations/c27398f3-4ce9-4bf3-b44e-e5eebf927b0c`.



## 2026-09-28 — owner-directed patch carry and initial broader inventory

OpenCode is installed as 1.18.33+cairn.9797966 with all three carried patches.
Hermes's four changes are ported to upstream 79a6fd3e as 9b57ee21, selected for new
CLI launches through a versioned venv; existing CLI/gateway retain their original
files and processes. A narrowly required Cairn abort-client compatibility fix is
published as d08bba3 and installed without service restart. The policy now
requires staging/porting/testing rather than a patch-preservation hold, and the
role requires periodic broader Python/tool inventory. See VERIFICATION.md and
PATCHED-UPDATES.md for tests, failed-then-repaired checks, rollback and activation
limits. Initial inventory receipt: /var/lib/update-bot/inventory-2026-09-28.json.


Subsequent gateway activation in the same session: native reversible drain proved
zero active chat/cron/API tasks; SIGUSR1 transitioned the gateway to `9b57ee21`,
Slack reconnected, and the marker was removed. Separate interactive CLI preserved.
Receipt: /var/lib/update-bot/hermes-gateway-activation.json.


## 2026-09-28 — automatic native gateway activation

Added one fixed owner-user service to activate an already tested Hermes generation.
The bot can start it through narrow polkit authority; direct user-manager/profile
access remains unavailable. It requires fresh zero-work drain evidence, verifies
new runtime identity/Slack connection, preserves foreign drain ownership, and
records uncertain failures without force-killing or retrying. The deployed no-op
permission probe preserved the current gateway; 31 repository tests and validator
pass. Native operation receipts preserve the helper result and suppress no-op
publication. This closes the operator-only activation gap recorded earlier today.
