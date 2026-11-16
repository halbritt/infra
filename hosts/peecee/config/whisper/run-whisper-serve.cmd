@echo off
rem Wrapper for the WhisperServer scheduled task: whisper.cpp whisper-server on the GPU,
rem large-v3-turbo, bound to all interfaces on :8910 (firewall rule scopes it to LAN + tailnet).
rem Speaks multipart POST /inference (same API as proximal's whisper-stt on :8910).
set WROOT=%USERPROFILE%\whisper
set /p WSERVER=<"%WROOT%\server-path.txt"
cd /d %WROOT%
"%WSERVER%" -m "%WROOT%\models\ggml-large-v3-turbo.bin" --host 0.0.0.0 --port 8910 -t 8 -l en >> "%WROOT%\logs\server.log" 2>&1
