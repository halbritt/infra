# Windows task and service startup appendix — 2026-09-23

Read-only snapshot from peecee after the Ollama and Evernote startup changes.
These entries complete the counts in [README.md](README.md). Task paths and
service names are live observations, not new desired state. A service with
Automatic startup can be stopped at the observation instant.

## Enabled boot/logon tasks in the Windows task tree (36)

| Task path and name | State |
| --- | --- |
| `\Microsoft\Windows\Active Directory Rights Management Services Client\AD RMS Rights Policy Template Management (Manual)` | Ready |
| `\Microsoft\Windows\AppxDeploymentClient\UCPD velocity` | Ready |
| `\Microsoft\Windows\Autochk\Proxy` | Ready |
| `\Microsoft\Windows\CertificateServicesClient\KeyPreGenTask` | Ready |
| `\Microsoft\Windows\CertificateServicesClient\SystemTask` | Ready |
| `\Microsoft\Windows\CertificateServicesClient\UserTask` | Ready |
| `\Microsoft\Windows\Data Integrity Scan\Data Integrity Check And Scan` | Ready |
| `\Microsoft\Windows\Device Information\Device User` | Ready |
| `\Microsoft\Windows\DeviceDirectoryClient\RegisterUserDevice` | Ready |
| `\Microsoft\Windows\Diagnosis\RecommendedTroubleshootingScanner` | Ready |
| `\Microsoft\Windows\DirectX\DirectXDatabaseUpdater` | Ready |
| `\Microsoft\Windows\DirectX\DXGIAdapterCache` | Ready |
| `\Microsoft\Windows\EnterpriseMgmt\MDMMaintenenceTask` | Ready |
| `\Microsoft\Windows\ExploitGuard\ExploitGuard MDM policy Refresh` | Ready |
| `\Microsoft\Windows\Hotpatch\Monitoring` | Ready |
| `\Microsoft\Windows\InstallService\SmartRetry` | Ready |
| `\Microsoft\Windows\International\Synchronize Language Settings` | Ready |
| `\Microsoft\Windows\LanguageComponentsInstaller\Installation` | Ready |
| `\Microsoft\Windows\LanguageComponentsInstaller\ReconcileLanguageResources` | Ready |
| `\Microsoft\Windows\Management\Provisioning\Logon` | Ready |
| `\Microsoft\Windows\MemoryDiagnostic\AutomaticOfflineMemoryDiagnostic` | Ready |
| `\Microsoft\Windows\Multimedia\SystemSoundsService` | Running |
| `\Microsoft\Windows\Network Connectivity Status Indicator\NcsiIdentifyUserProxies` | Ready |
| `\Microsoft\Windows\PI\Secure-Boot-Update` | Ready |
| `\Microsoft\Windows\Plug and Play\Device Install Reboot Required` | Ready |
| `\Microsoft\Windows\PushToInstall\LoginCheck` | Ready |
| `\Microsoft\Windows\Setup\PITRTask` | Ready |
| `\Microsoft\Windows\SpacePort\SpaceAgentTask` | Ready |
| `\Microsoft\Windows\SpacePort\SpaceManagerTask` | Ready |
| `\Microsoft\Windows\TextServicesFramework\MsCtfMonitor` | Ready |
| `\Microsoft\Windows\Windows Error Reporting\QueueReporting` | Ready |
| `\Microsoft\Windows\WindowsAI\Settings\InitialConfiguration` | Ready |
| `\Microsoft\Windows\WindowsColorSystem\Calibration Loader` | Ready |
| `\Microsoft\Windows\Wininet\CacheTask` | Running |
| `\Microsoft\Windows\Work Folders\Work Folders Logon Synchronization` | Ready |
| `\Microsoft\Windows\Work Folders\Work Folders Maintenance Work` | Ready |

## Other automatic services (74)

| Service | Display name | State |
| --- | --- | --- |
| `AppXSvc` | AppX Deployment Service (AppXSVC) | Running |
| `AsusUpdateCheck` | AsusUpdateCheck | Stopped |
| `AudioEndpointBuilder` | Windows Audio Endpoint Builder | Running |
| `Audiosrv` | Windows Audio | Running |
| `BFE` | Base Filtering Engine | Running |
| `BrokerInfrastructure` | Background Tasks Infrastructure Service | Running |
| `camsvc` | Capability Access Manager Service | Running |
| `cbdhsvc_3984b0` | Clipboard User Service_3984b0 | Running |
| `CDPSvc` | Connected Devices Platform Service | Running |
| `CDPUserSvc_3984b0` | Connected Devices Platform User Service_3984b0 | Running |
| `CoreMessagingRegistrar` | CoreMessaging | Running |
| `CryptSvc` | Cryptographic Services | Running |
| `DcomLaunch` | DCOM Server Process Launcher | Running |
| `DeviceAssociationService` | Device Association Service | Running |
| `Dhcp` | DHCP Client | Running |
| `DiagTrack` | Connected User Experiences and Telemetry | Running |
| `DispBrokerDesktopSvc` | Display Policy Service | Running |
| `Dnscache` | DNS Client | Running |
| `DoSvc` | Delivery Optimization | Running |
| `DPS` | Diagnostic Policy Service | Running |
| `DusmSvc` | Data Usage | Running |
| `EventLog` | Windows Event Log | Running |
| `EventSystem` | COM+ Event System | Running |
| `FontCache` | Windows Font Cache Service | Running |
| `gpsvc` | Group Policy Client | Running |
| `igccservice` | Intel(R) Graphics Command Center Service | Running |
| `IKEEXT` | IKE and AuthIP IPsec Keying Modules | Running |
| `Intel(R) Platform License Manager Service` | Intel(R) Platform License Manager Service | Stopped |
| `InventorySvc` | Inventory and Compatibility Appraisal service | Running |
| `iphlpsvc` | IP Helper | Running |
| `jhi_service` | Intel(R) Dynamic Application Loader Host Interface Service | Running |
| `LanmanServer` | Server | Running |
| `LanmanWorkstation` | Workstation | Running |
| `logi_lamparray_service` | Logitech LampArray Service | Running |
| `LSM` | Local Session Manager | Running |
| `MapsBroker` | Downloaded Maps Manager | Stopped |
| `mpssvc` | Windows Defender Firewall | Running |
| `nsi` | Network Store Interface Service | Running |
| `NVDisplay.ContainerLocalSystem` | NVIDIA Display Container LS | Running |
| `PcaSvc` | Program Compatibility Assistant Service | Running |
| `Power` | Power | Running |
| `ProfSvc` | User Profile Service | Running |
| `RpcEptMapper` | RPC Endpoint Mapper | Running |
| `RpcSs` | Remote Procedure Call (RPC) | Running |
| `RstMwService` | Intel(R) Storage Middleware Service | Running |
| `SamSs` | Security Accounts Manager | Running |
| `Schedule` | Task Scheduler | Running |
| `SENS` | System Event Notification Service | Running |
| `ShellHWDetection` | Shell Hardware Detection | Running |
| `Spooler` | Print Spooler | Running |
| `sppsvc` | Software Protection | Stopped |
| `StateRepository` | State Repository Service | Running |
| `StiSvc` | Windows Image Acquisition (WIA) | Running |
| `StorSvc` | Storage Service | Running |
| `SysMain` | SysMain | Running |
| `SystemEventsBroker` | System Events Broker | Running |
| `TextInputManagementService` | Text Input Management Service | Running |
| `Themes` | Themes | Running |
| `TrkWks` | Distributed Link Tracking Client | Running |
| `UserManager` | User Manager | Running |
| `UsoSvc` | Update Orchestrator Service | Running |
| `W32Time` | Windows Time | Running |
| `WbioSrvc` | Windows Biometric Service | Stopped |
| `Wcmsvc` | Windows Connection Manager | Running |
| `webthreatdefusersvc_3984b0` | Web Threat Defense User Service_3984b0 | Running |
| `whesvc` | Windows Health and Optimized Experiences | Running |
| `Winmgmt` | Windows Management Instrumentation | Running |
| `WlanSvc` | WLAN AutoConfig | Running |
| `WMIRegistrationService` | Intel(R) Management Engine WMI Provider Registration | Running |
| `WpnService` | Windows Push Notifications System Service | Running |
| `WpnUserService_3984b0` | Windows Push Notifications User Service_3984b0 | Running |
| `WSAIFabricSvc` | Windows AI Components Host | Running |
| `wscsvc` | Security Center | Running |
| `WSearch` | Windows Search | Running |
