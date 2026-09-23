@echo off
rem Wrapper for the KevServer scheduled task: sets the cache dir and logs to kev\logs.
set HF_HOME=%USERPROFILE%\kev\hf
set KEV_RUN=jaredpalmer/kev-4b
set KEV_PORT=8008
set KEV_HOST=0.0.0.0
rem KEV_MERGE=0: load the bf16 base and keep the LoRA unmerged. The default merge path moves the
rem base to the GPU in fp32 first (16 GB peak), which does not fit beside ollama and the desktop.
set KEV_MERGE=0
cd /d %USERPROFILE%\kev
"%USERPROFILE%\kev\.venv\Scripts\python.exe" "%USERPROFILE%\kev\kev-serve.py" >> "%USERPROFILE%\kev\logs\server.log" 2>&1
