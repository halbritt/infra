# peecee startup inventory

Observed on 2026-09-23 as user `halbr` after the Ollama, Evernote, LG installer,
and Teams changes.
This records user-facing startup registrations, enabled packaged-app startup
tasks, enabled boot/logon Scheduled Tasks outside `\Microsoft\Windows\`, and
automatic services whose executable is outside the usual Windows system
directories. The host also had 36 enabled Windows namespace boot/logon tasks
and 74 other automatic services whose executable paths match those system
locations. Their names and observed states are in the
[system inventory appendix](system-inventory-2026-09-23.md). A registration may
exit quickly after launch.

## Startup folders and Run keys

| Entry | Launch point |
| --- | --- |
| Tailscale tray | All-users Startup folder |
| Steam | `halbr` Run key |
| Signal | `halbr` Run key |
| Google Chrome (no startup window) | `halbr` Run key |
| Windows Security tray | Machine Run key |
| Zwift Launcher | 32-bit machine Run key |
| LG Switch | 32-bit machine Run key |

`Ollama.lnk.disabled` was in `halbr`'s Startup folder and was reported by
`Win32_StartupCommand` despite its suffix. It is now parked at
`C:\ProgramData\Ollama\Ollama-desktop.lnk`. The `OllamaServer` task continues
to own port 11434. The canonical install and rollback scripts in
[`../ollama/`](../ollama/) use this parked location.

The `LG Monitor App Installer` shortcut pointed to
`LGElectronics.LGMonitorApp_cfnzzhwkr8z5w!App`. That package was staged for
SYSTEM and provisioned, but was not registered for `halbr`. LG describes the
installer as a way to discover optional monitor apps and says removing it does
not affect basic display operation. The shortcut is parked at
`C:\ProgramData\Infra\startup-disabled\LG Monitor App Installer.lnk`.
The related `LGMonitorInstallManager` machine Run value was removed after its
command was saved in the same directory as `LGMonitorInstallManager.run.txt`.
`LG Monitor Software Notice Cleanup` was disabled in Task Scheduler. LG Switch
remains configured to start, and the LG UltraFine monitor device reports `OK`. See
[LG's support article](https://www.lg.com/us/support/help-library/how-to-uninstall-and-reinstall-the-lg-monitor-app-installer-CT10000030-20155428691646).

## Packaged-app startup tasks

Windows stores these under `HKCU\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\SystemAppData\<package>\<task>`.
State `2` was enabled in the live registry. The current WhatsApp package
manifest identifies its GUID task as the WhatsApp startup task.

| Enabled app | Task |
| --- | --- |
| WhatsApp | `2defd21c-0b9e-4e4e-873a-2a68c47d7da5` |
| Slack | `SlackStartup` |
| Intel Graphics Experience | `GCPStartupId` |
| 1Password | `1PasswordStartup` |
| Windows Cross Device | `CrossDevice.Start` |
| ChatGPT | `ChatGPT` |
| Spotify | `Spotify` |

Evernote's `EvernoteStartup` was state `2` and launched Evernote after the
2026-09-23 reboot. It is now state `1` (disabled by user). Its running process
was left alone. Microsoft Teams' `TeamsTfwStartupTask` was also changed from
state `2` to state `1` at the owner's request; Teams remains installed. Other
registered tasks observed disabled (state `0`) were an
older `WhatsAppStartupTask`, Claude, Xbox Gaming App, Office Hub, Windows
Terminal, and Phone Link.

## Enabled boot or logon Scheduled Tasks outside Windows' task tree

| Task | Trigger |
| --- | --- |
| `KevServer` | Boot |
| `OllamaServer` | Boot |
| `MicrosoftEdgeUpdateTaskMachineCore` | Logon and daily |
| `GoogleUpdaterTaskSystem152.0.7933.0{F2B82BB5-6D82-41C2-AA03-92CFA921DD9C}` | Logon and daily |

## Automatic services outside the usual Windows system directories

The live service manager reported 95 automatic services. These 21 had an
executable outside `Windows\System32`, `Windows\SysWOW64`, or `svchost.exe`:

| Service | Observed state |
| --- | --- |
| Aqua Computer Service | Running |
| Claude (`CoworkVMService`) | Running |
| Dell Client Management Service | Running |
| Dell TechHub | Running |
| Dell Peripheral Manager Service | Running |
| Microsoft Edge Update (`edgeupdate`) | Stopped |
| GameInput Redist Service | Running |
| Gaming Services (`GamingServices`) | Running |
| Gaming Services (`GamingServicesNet`) | Running |
| Google Updater Internal Service | Stopped |
| Google Updater Service | Stopped |
| Microsoft Defender Core Service | Running |
| `nvidia_gpu_exporter` | Running |
| OpenSSH Authentication Agent | Running |
| OpenSSH SSH Server | Running |
| Tailscale | Running |
| Thunderbolt Application Launcher | Running |
| Thunderbolt Peer to Peer Shortcut | Running |
| Microsoft Defender Antivirus Service | Running |
| Windows Subsystem for Linux installer | Stopped |
| WSL Service | Running |

Stopped means the service was not running at the inventory instant; its
startup type remained Automatic. No other startup registration was changed.
