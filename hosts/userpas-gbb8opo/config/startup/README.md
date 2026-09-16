# Startup cleanup

The owner requested a broad startup audit and updates on 2026-09-15, reporting
severe slowness. They explicitly confirmed the Wacom tablet is no longer used.

## Observations before cleanup

Dell Latitude 7280, i7-7600U (2 cores / 4 logical CPUs), approximately 16 GiB RAM.
Samsung 990 EVO Plus 1 TB SSD reports Healthy; C: has approximately 572 GB free.
A 10-second process CPU-delta sample, normalized across all four logical CPUs,
observed System at 25.8%, Defender at 16.3%, and Dell support processes at roughly
19%. This sample overlapped a Dell SupportAssist update and is not an idle
baseline or proof of the cause of all reported slowness. Wacom services were
running despite the absent tablet.

## Wacom removal

Run [remove-wacom.ps1](remove-wacom.ps1) in an elevated Windows PowerShell session.
This is a one-time recipe transmitted from the canonical repository over SSH.
It uses the registered vendor uninstaller and checks the exit code. Verify
uninstall registration and remaining services afterward; deferred driver removal
may require a later reboot. Reinstall the vendor driver if a tablet returns.

Reference: [Wacom installer arguments](https://developer-docs.wacom.com/docs/icbt/windows/driver-install/installer-arguments/).

## Applied startup decisions — 2026-09-15

The owner explicitly chose: "Make optional helpers manual."

| Component | Decision and reason |
|---|---|
| Wacom Tablet 6.4.13-4 | Uninstalled: tablet no longer exists. Vendor exit 2 means success with reboot required; service and uninstall registration are gone. |
| Dell SupportAssistAgent, DellTechHub, DellClientManagementService | Manual; stop support/analytics work at idle. SupportAssist automatic update task disabled, apps remain available for deliberate maintenance. |
| SamsungMagicianSVC, CMigrationService | Manual; SSD utility and migration tool need not run continuously. Magician scheduled launch disabled. Migration service cannot accept stop requests and remains until reboot. |
| EpsonScanSvc | Manual per owner. Start with `Start-Service EpsonScanSvc` if the scanner app needs it. |
| CoworkVMService | Manual and stopped. Claude's packaged service denies SCM configuration even to SYSTEM, but the registry key grants Administrators full control; changed `Start` from 2 to 3 without changing its ACL. |
| Adobe Creative Cloud / CCXProcess | Removed machine-wide login entries; stopped desktop/cloud helper processes. AdobeUpdateService retained to preserve application updating. |
| Garmin Express | Removed User's minimized login launch. GarminUpdaterTask retained for application updates. |
| Spotify, Roblox | Removed Adam's tray/login launches; applications retained. |
| SSH, Tailscale | Automatic: remote administration must survive logout and reboot. |
| Windows Update, Defender, firewall, browser updaters | Retained: OS and security maintenance. |
| Alps touchpad, Intel graphics/thermal/storage/TPM, Realtek/Waves audio, Thunderbolt | Retained: hardware, power management, audio-jack handling, and platform security. |
| Credential Vault services | Retained: authentication hardware integration. |
| Bonjour, Print Spooler, Windows Image Acquisition | Retained: Apple-device and scanner/printer integration; usage is not disproven by the removed tablet. |
| Cold Turkey service/task | Retained: intentional user-configured blocking software. |
| OneDrive, Zoom, Firefox scheduled updaters | Retained: application updates and sync maintenance. |
| Other Windows automatic services | Retained pending specific evidence of a fault; names and observed states are recorded below. |
| Browser experience/default-browser tasks and Intel status tray | Retained in this pass; no measured contribution established, revisit after an idle baseline. |

The [automatic-service snapshot](automatic-services-after.csv) and
[non-Microsoft scheduled-task snapshot](scheduled-tasks-after.csv) enumerate the
remaining surface. These are observations, not instructions to re-enable services.
Claude's user StartupTask was already disabled (`State=0`).

Apply [manual-helpers.ps1](manual-helpers.ps1) in elevated PowerShell. It preserves
the first rollback snapshot at `C:\ProgramData\Infra\startup-before-20260915.json`
and can resume after a partial failure. Apply [manual-cowork.ps1](manual-cowork.ps1)
separately; its original registry setting is saved alongside the snapshot.
Canonical scripts are transmitted over SSH; installed working copies live under
`C:\ProgramData\Infra\`. Run [restore-helpers.ps1](restore-helpers.ps1) to restore
the recorded startup choices. Already closed tray processes return at next login
or when their application is launched.

Application upgrades can restore vendor startup entries or packaged-service
settings. Recheck and reapply this policy after upgrades. Manual services can be
started with `Start-Service SERVICE_NAME` from administrator PowerShell.

## First post-restart verification — 2026-09-15

After the owner-approved restart, all seven optional services were Manual and
Stopped, including CMigrationService. The Dell and Samsung launch tasks stayed
disabled. SSH and Tailscale were Automatic and Running before anyone logged in.
Wacom remained absent from installed-program registration. This verifies service
startup behavior; a desktop-login check and a settled CPU sample are separate
observations.

Windows' built-in `WacomPen` serial HID driver remains Manual and Stopped. Its
file metadata identifies Microsoft Corporation, version 10.0.19041.1. It is
separate from the removed vendor tablet package and contributes no running helper.

## Performance evidence limits

These changes remove owner-rejected startup work. A numerical speedup is not yet
established: the first measurement overlapped updates, and there is no controlled
before/after desktop workload. After the second restart and installer completion,
a [30-sample CPU observation](postboot-cpu-sample-20260915.json) at the login screen
averaged **2.12%** CPU, with a **26.81%** peak. Defender averaged approximately
1.46% across the four logical CPUs; the diagnostic PowerShell process used 0.59%.
The optional vendor helpers were absent. This establishes low background load in
that logged-out sample; it does not quantify desktop responsiveness after login.

Doctrine packet `pkt-e3f8ab89966107b9`, SHA-256
`e3f8ab89966107b9aadce75b8f31ce223c33a5cf93f5dc6d8a571d9b2ef1f98c`,
used `performance-profile-causal-bottleneck`, `performance-metric-semantics`, and
`universal-preserve-behavior-by-default`. Validated release commit
`d3e0c0d4ccd1920b2e045c156f1cf0db4fc5f04f`, corpus `corpus-2026-07-12-a11702cc9217`,
doctrine `doctrine-f6bbb5196a3f8bf9`, retriever `retriever-ec995ecdd083b2c8`.
Source locators: *100 Go Mistakes*, chapter 12, "Not using Go diagnostics tooling";
*Designing Data-Intensive Applications* (2nd ed.), chapter 2, "Average, Median,
and Percentiles"; *Efficient Go*, chapter 3, "Functionality Phase".
Its recommendation ceiling did not grant operational authority; the owner's
explicit cleanup/manual-start instructions did. Unmet benchmark, repetition,
causal attribution, and numeric-target obligations preclude a performance claim.
They are nonmaterial to the narrower owner-selected startup-policy change.
Stop before unapproved reboot, hardware/firmware changes, or loss of remote access.
