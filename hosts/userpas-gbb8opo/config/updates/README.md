# Windows updates

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
