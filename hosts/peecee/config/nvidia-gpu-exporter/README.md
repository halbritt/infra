# nvidia_gpu_exporter on **peecee** (Windows 11)

A second GPU scrape target for the proximal Prometheus: the **peecee** workstation
(Windows 11 Pro, **RTX 3090 Ti**, tailnet `100.113.63.58`). Same exporter as proximal —
[`utkuozdemir/nvidia_gpu_exporter`](https://github.com/utkuozdemir/nvidia_gpu_exporter) v1.4.1,
which shells out to `nvidia-smi`, so it works on consumer GeForce and is cross-platform.
peecee runs the **native Windows x86_64 build**; proximal runs the Linux `.deb`.

The exporter service is canonical under the `peecee` host. It feeds
**proximal's** observability stack; the consuming scrape job remains in
[`hosts/proximal/config/observability/prometheus/prometheus.yml`](../../../proximal/config/observability/prometheus/prometheus.yml)
as job `gpu`, instance `peecee`.

## What's deployed on peecee

| item | value |
|---|---|
| exporter exe | `C:\Program Files\nvidia_gpu_exporter\nvidia_gpu_exporter.exe` (v1.4.1, `windows_x86_64`) |
| service wrapper | `nvidia_gpu_exporter-svc.exe` = [WinSW](https://github.com/winsw/winsw) v2.12.0 (`WinSW-x64.exe`, .NET 4.8) |
| service config | `nvidia_gpu_exporter-svc.xml` (canonical copy here) |
| Windows service | `nvidia_gpu_exporter`, **Automatic (Delayed Start)**, independent of the Tailscale service, restart-on-failure 5s |
| bind | `--web.listen-address=100.113.63.58:9835` (tailnet IP only — off the `192.168.1.x` LAN) |
| firewall | inbound allow TCP 9835, source scoped to tailnet `100.64.0.0/10` |
| logs | `C:\ProgramData\nvidia_gpu_exporter\logs\` (WinSW `.out/.err/.wrapper` logs, roll-by-size) |

Why a service wrapper: the exporter is a plain console binary (no SCM support), and Windows has no
package/unit equivalent of proximal's `.deb`. WinSW turns it into a real Automatic service with
SCM recovery actions — the closest analog to the Linux drop-in's `Restart=on-failure` /
`RestartSec=5`. The exporter deliberately has **no SCM dependency on Tailscale**. A Tailscale MSI
upgrade stops dependent services cleanly, which bypasses failure recovery, and does not restart
them afterward (observed 2026-08-08). Delayed automatic start gives Tailscale time to attach its
`100.x` address at boot; if the bind still races, WinSW exits nonzero and SCM retries after 5s.
SCM no longer stops the exporter when Tailscale restarts. The tailnet-only listener and
tailnet-scoped firewall remain the network boundary.

## Install / re-install (run from an elevated PowerShell on peecee)

```powershell
$dir = 'C:\Program Files\nvidia_gpu_exporter'; New-Item -ItemType Directory -Force $dir | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# 1. exporter (native Windows build)
$z = "$env:TEMP\nvge.zip"
Invoke-WebRequest -UseBasicParsing -OutFile $z `
  'https://github.com/utkuozdemir/nvidia_gpu_exporter/releases/download/v1.4.1/nvidia_gpu_exporter_1.4.1_windows_x86_64.zip'
Expand-Archive $z "$env:TEMP\nvge" -Force
Copy-Item "$env:TEMP\nvge\nvidia_gpu_exporter.exe" "$dir\nvidia_gpu_exporter.exe" -Force
# 2. WinSW service wrapper + config (nvidia_gpu_exporter-svc.xml from this dir)
Invoke-WebRequest -UseBasicParsing -OutFile "$dir\nvidia_gpu_exporter-svc.exe" `
  'https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe'
# copy nvidia_gpu_exporter-svc.xml next to the exe, then:
& "$dir\nvidia_gpu_exporter-svc.exe" install
# 3. firewall (tailnet sources only) + start
New-NetFirewallRule -DisplayName 'nvidia_gpu_exporter (Prometheus, tailnet)' -Direction Inbound `
  -Action Allow -Protocol TCP -LocalPort 9835 -RemoteAddress '100.64.0.0/10' -Profile Any | Out-Null
& "$dir\nvidia_gpu_exporter-svc.exe" start
```

The service's startup, dependency, and failure-recovery settings are install-time WinSW options.
To apply a changed XML file to an existing installation, copy it beside the wrapper and reinstall
the service definition:

```powershell
$dir = 'C:\Program Files\nvidia_gpu_exporter'
& "$dir\nvidia_gpu_exporter-svc.exe" stop
& "$dir\nvidia_gpu_exporter-svc.exe" uninstall
# Copy the canonical nvidia_gpu_exporter-svc.xml into $dir, then:
& "$dir\nvidia_gpu_exporter-svc.exe" install
& "$dir\nvidia_gpu_exporter-svc.exe" start
```

## Verify

```bash
# from proximal, over the tailnet:
curl -s http://100.113.63.58:9835/metrics | grep '^nvidia_smi_gpu_info'   # RTX 3090 Ti line, value 1
curl -s http://100.85.100.81:9091/api/v1/targets | \
  jq -r '.data.activeTargets[] | select(.labels.job=="gpu") | "\(.labels.instance) \(.health)"'  # peecee up
```

```powershell
# on peecee:
Get-Service nvidia_gpu_exporter         # Running / Automatic
sc.exe qc nvidia_gpu_exporter           # AUTO_START (DELAYED), no DEPENDENCIES
sc.exe qfailure nvidia_gpu_exporter     # RESTART after 5000 ms
Get-Content C:\ProgramData\nvidia_gpu_exporter\logs\nvidia_gpu_exporter-svc.wrapper.log -Tail 20
```

Stood up 2026-06-20. The exporter emits the same `nvidia_smi_*` metric names as proximal, so the
existing `nvidia-gpu-proximal` Grafana dashboard (job `gpu`) picks up `instance="peecee"` for free.
