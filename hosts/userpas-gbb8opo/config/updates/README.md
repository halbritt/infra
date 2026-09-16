# Windows updates

Current state after maintenance: Windows build **19045.7725**, all 11 selected
application upgrades complete, both restarts completed. The remaining recovery
update is not verified because WinRE is disabled and its partition is too small;
see the final verification and recovery findings below.

The owner requested software updates on 2026-09-15, including FORScan explicitly.
The initial Windows version was 22H2, build 19045.6396. Defender was enabled with
current signatures, but the newest installed OS hotfix date was September 2025.

[windows-update.ps1](windows-update.ps1) is installed at
`C:\ProgramData\Infra\windows-update.ps1` and run by the temporary SYSTEM task
`InfraWindowsUpdates-20260915`. It installs applicable, non-hidden software
updates offered by the configured Windows Update service, records each result at
`C:\ProgramData\Infra\windows-update-result.json`, and never initiates a reboot.
Remove the temporary task after it completes. Preserve the result locally.

The script accepts EULAs for offered updates under the owner's update instruction.
It does not select driver or firmware updates. Recheck offered updates after a
later authorized reboot; this first scan can be limited by pending prerequisites.

## FORScan

The official [download page](https://forscan.org/download.html) lists Windows
2.3.71, released 2026-05-08. Initial installed registration already reports
`2.3.71.release`. The executable is present at
`C:\Program Files (x86)\FORScan\FORScan.exe` but has no FileVersion or
ProductVersion resource. Installed registration matches the current public
release; there is no newer public installer to apply. No vehicle connection or
license changes were made.

## WinGet over SSH

WinGet 1.29.290 exists, but source refresh under the OpenSSH session failed:
`A specified logon session does not exist. It may already have been terminated.`
This is a package-source/session failure, not evidence that every app is current.
An elevated task with `LogonType Interactive` under the already logged-in `User`
account successfully refreshed the source and found 13 upgrades. No password is
stored in the task. Use that context for [application-updates.ps1](application-updates.ps1),
installed as `C:\ProgramData\Infra\application-updates.ps1` and run with the
temporary task `InfraApplicationUpdates-20260915` once Windows Update finishes.

The application recipe selects 11 observed upgrades (Creative Cloud, calibre,
Claude, Garmin Express, four VC++ runtimes, PC Health Check, and two Windows App
Runtime versions). The two .NET upgrades are handled by Windows Update. Each
WinGet result is recorded in `C:\ProgramData\Infra\application-update-result.json`
with detailed output in `application-update-log.txt`. A nonzero package result
requires inspection; completion of the loop is not proof that every upgrade worked.

Recheck vendor startup choices after installing. The task does not request a
reboot. Remove maintenance tasks after their recorded result has been inspected.

## Windows Update result — 2026-09-15

All six offered updates reported `ResultCode=2` (succeeded), `HResult=0`; the
aggregate result requires a reboot. [Per-update evidence](windows-update-result-20260915.json)
records KB5066747, KB5126106, KB5126104, Defender platform KB4052623, MRT KB890830,
and Windows cumulative KB5066791. The temporary Windows Update task was removed.

During cumulative-update processing, CBS logged missing `prjflt.sys` and
`0x800f0984`. Servicing subsequently succeeded without a separate repair attempt;
that intermediate log entry alone did not justify an additional DISM operation.
Defender platform now reports 4.18.26080.3 with real-time protection enabled.

The OS cumulative update offered was from October 2025. This does not establish
that Windows has current 2026 OS security patches. After reboot, rescan and check
Extended Security Updates enrollment. The observed licensing query returned the
active Windows Professional retail license and no active ESU product. Microsoft's
[Windows 10 release information](https://learn.microsoft.com/en-us/windows/release-health/release-information)
explains the distinction between the final standard updates and ESU updates.

## Runtime installer observation

While updating Windows App Runtime 1.7, an older bootstrapper remained at
`C:\Windows\SystemTemp\SupportAssistAgent\windowsappruntimeinstall-x64.exe`.
It had started at 16:51 local time, before the application-update batch, and its
SupportAssist parent was gone. After verifying that exact path and absent parent,
terminated only that orphaned process (PID 15064). The WinGet-owned runtime
installer was left running. This observation did not by itself prove which
process owned the deployment queue.

## Application result before restart — 2026-09-15

Nine installers returned exit 0: Creative Cloud, calibre, Claude, Garmin Express,
both VC++ 2013 architectures, both current VC++ v14 architectures, and PC Health
Check. [The saved result](application-update-result-20260915.json) preserves those
outcomes. Windows App Runtime 1.7 remained queued in AppX deployment, and 1.8 had
not started. No failure code identified the cause of that queue.

Stopped the temporary update task and its verified WinGet/runtime client
processes, preserved the successful results, and removed the task. Windows
deployment services were left running. Reapplied the manual-start policy because
the Garmin upgrade recreated its login entry. The result is `PausedForRestart`;
the two runtime upgrades are still pending.

After an owner-approved reboot, use the same elevated Interactive scheduled-task
context to run `C:\ProgramData\Infra\application-updates.ps1 -Resume` with
PowerShell's process-local `-ExecutionPolicy Bypass`. Resume retains recorded
successes and retries only the packages without an exit-0 result. Inspect any
nonzero result, including an already-current package, before declaring completion.
Then recheck startup policy, remove the temporary task, rescan Windows Update,
and verify Tailscale and SSH after boot. Two existing logged-in user sessions
require coordination before restarting to avoid discarding unsaved work.

## Approved restart and follow-up — 2026-09-15

The owner confirmed work was saved and approved restart. Windows booted at
17:43:44 local time into build 19045.6456. Tailscale and passwordless SSH started
before an interactive login; all seven optional services were Manual and Stopped.
Both disabled vendor tasks stayed disabled. Defender real-time protection and
all three firewall profiles remained enabled.

The next successful Windows Update scan offered September 2026 updates
KB5126146, KB5127070, and KB5122878. This supersedes the earlier concern that the
October 2025 cumulative update might be the last available: completing that
prerequisite exposed the current updates. The retail-license query alone did not
establish the machine's update eligibility.

WinGet source reads now work over SSH. Its upgrade inventory lists only Runtime
1.8, but Runtime 1.7 still has mismatched architectures: x64 7000.785.2325.0 and
x86 7000.676.1651.0. Use [runtime-updates.ps1](runtime-updates.ps1) for these two
remaining packages after Windows Update finishes. It runs Microsoft's complete
installers for 1.7.9 and 1.8.10, verifies their published hashes and Microsoft
signatures, and checks both x86 and x64 framework registrations before recording
success. Existing application outcomes are preserved. Installed path:
`C:\ProgramData\Infra\runtime-updates.ps1`; run in elevated PowerShell with
process-local `-ExecutionPolicy Bypass`.

Installer provenance: Microsoft WinGet manifests for
[1.7.9](https://github.com/microsoft/winget-pkgs/blob/master/manifests/m/Microsoft/WindowsAppRuntime/1/7/1.7.9/Microsoft.WindowsAppRuntime.1.7.installer.yaml)
and [1.8.10](https://github.com/microsoft/winget-pkgs/blob/master/manifests/m/Microsoft/WindowsAppRuntime/1/8/1.8.10/Microsoft.WindowsAppRuntime.1.8.installer.yaml).
Microsoft's [deployment guide](https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/deploy-unpackaged-apps)
documents the installer and architecture requirements.

All three September updates subsequently returned `ResultCode=2`, `HResult=0`,
with another restart required; see [second-pass results](windows-update-second-pass-20260915.json).
Removed the completed task. No interactive sessions had returned, so the second
restart continued the owner's approved maintenance window.

## Final verification — 2026-09-15

The second boot completed at 18:00:42 local time with build **19045.7725**, matching
September's KB5122878. Tailscale and key-authenticated SSH survived both restarts.
[Post-boot evidence](postboot-verification-20260915.json) records enabled Defender
and firewall profiles, seven stopped manual services, and disabled vendor tasks.
All temporary Infra maintenance tasks were removed after their results were saved.
The [final scan](windows-update-final-scan-20260915.json) shows no CBS or Windows
Update restart flag and only the recovery update below still offered.

[Final application results](application-update-final-20260915.json) contain all
11 successful installer exits. Runtime 1.7.9 now has healthy x86 and x64 frameworks
at 7000.785.2325.0; Runtime 1.8.10 has both at 8000.921.1539.0. WinGet's final
upgrade query lists no available upgrade. Older framework registrations can
remain for dependent applications; they were not forcibly removed.

## Remaining recovery issue

Windows Update re-offered KB5127070 after reporting success. One bounded retry
also [reported success without a reboot](windows-recovery-retry-20260915.json),
but the recovery image itself remains at build 19041.6094, modified 2025-09-25.
Do not equate this update's success result with a patched recovery image.

`reagentc /info` reports Disabled, including after the update task finished.
Disk 0 partition 4 is a 560,623,616-byte recovery partition with only 22,634,496
bytes free. Its existing `Recovery\WindowsRE\winre.wim` is 519,130,902 bytes.
Microsoft's [KB5127070 instructions](https://support.microsoft.com/en-us/servicing/os/windows/winre/2026/09/kb5127070-windows-10-22h2-standalone-exe)
require 250 MB free and a resulting WinRE version of at least 19041.7722.

The registration also refers to offset 253,496,918,016, while the current recovery
partition starts at 999,644,241,920. C: ends at 899,624,768,000, leaving about
100 GB unallocated before recovery. These facts suggest stale registration after
a disk-layout change; the cause and timing were not established. A separate
repair should preserve the existing recovery image, correct the registration,
and provide sufficient recovery space before retrying this update. No partition,
boot configuration, or recovery registration was changed in this maintenance pass.
