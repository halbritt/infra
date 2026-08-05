# Headless Ollama service on peecee

Ollama runs as the Windows Scheduled Task `OllamaServer` under `SYSTEM`, not as
the desktop tray application. The canonical lifecycle scripts are:

- [`install-ollama-service.ps1`](install-ollama-service.ps1), which configures
  machine-scoped Ollama variables, parks the desktop startup shortcut, writes
  `C:\ProgramData\Ollama\run-ollama-serve.cmd`, registers the startup task, and
  starts it; and
- [`uninstall-ollama-service.ps1`](uninstall-ollama-service.ps1), which removes
  the task, stops Ollama, restores the startup shortcut when present, and
  relaunches the desktop application.

The service listens on port `11434`, uses the existing user model store, and
logs server output to `C:\ProgramData\Ollama\server.log`. Model files, logs, and
credentials remain outside Git. GPU-fleet placement owns which model should be
resident; these lifecycle scripts do not select one.

## Apply

Copy the installer to peecee, then run it from an elevated PowerShell session:

```bash
scp hosts/peecee/config/ollama/install-ollama-service.ps1 peecee:
```

```powershell
.\install-ollama-service.ps1
```

This stops existing Ollama processes and replaces the Scheduled Task. It is an
operational change, not a harmless verification command.

## Verify

```powershell
Get-ScheduledTask -TaskName OllamaServer
Get-NetTCPConnection -LocalPort 11434 -State Listen
ollama ps
```

From proximal:

```bash
curl --fail --silent http://peecee:11434/api/tags >/dev/null
```

## Roll back

Copy and run [`uninstall-ollama-service.ps1`](uninstall-ollama-service.ps1) from
an elevated PowerShell session. The optional machine-environment cleanup in the
script remains commented out; removing those values is a separate deliberate
action.
