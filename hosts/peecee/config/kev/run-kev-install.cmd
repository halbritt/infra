@echo off
rem One-shot install runner for the KevInstall scheduled task (SSH sessions on Windows kill their
rem process tree on exit, so the installer must run under the Task Scheduler, not the shell).
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\kev\install-kev.ps1" > "%USERPROFILE%\kev\logs\install.log" 2>&1
