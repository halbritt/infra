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
