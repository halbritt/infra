# Whisper on peecee — GPU speech-to-text server

whisper.cpp `whisper-server` with `large-v3-turbo` on the RTX 3090 Ti, installed
2026-11-16 by owner direction as the STT backend for the ReSpeaker Core v2 mic array
(`respeaker`, a LAN client that posts short utterances). Same HTTP API as proximal's
`whisper-stt` ([`../../../proximal/config/whisper/`](../../../proximal/config/whisper/README.md)),
but this one listens on the network.

## Files

- [`install-whisper.ps1`](install-whisper.ps1) — downloads the prebuilt CUDA 12.4 build
  (`ggml-org/whisper.cpp` build `b5454`, published with v1.9.5) and
  `ggml-large-v3-turbo.bin` into `C:\Users\halbr\whisper`, verifying pinned SHA-256
  values. Idempotent. No Python, no git, no compiler.
- [`run-whisper-serve.cmd`](run-whisper-serve.cmd) — the task action; logs to
  `whisper\logs\server.log`.
- [`install-whisper-task.ps1`](install-whisper-task.ps1) — registers Scheduled Task
  `WhisperServer` (user `halbr`, S4U, AtStartup, no time limit, three restarts) and the
  firewall rule `whisper-server 8910 (LAN + tailnet)`.

## Serving contract

- Endpoint: `POST http://192.168.1.118:8910/inference` (LAN) or
  `http://100.113.63.58:8910/inference` (tailnet); multipart `file` (16 kHz mono WAV),
  `response_format=json`, `temperature`, `language`. No API key.
- Exposure: bound `0.0.0.0:8910`; the firewall rule admits only `192.168.1.0/24` and
  `100.64.0.0/10`. Narrower than ollama's `:11434` rule, which allows any remote address.
- Model: `large-v3-turbo`, default language `en` (`-l en` in the wrapper), 8 threads.
- VRAM: ~2.0 GB resident (card went 14,329 → 16,363 MiB on load, 2026-11-16, with Kev
  resident and no ollama model loaded).
- gpu-fleet: not a fleet slot and holds no lease.

**Co-tenancy warning.** With the desktop (6–7 GB), Kev (~8.5 GB) and ollama's
`qwen3-vl:8b` at 32768 (~8 GB) the card was already measured at ~0.7 GB free
([`../kev/README.md`](../kev/README.md)). Whisper's 2 GB does not fit beside all three:
if the 8B is loaded while Whisper is up, expect ollama to spill to CPU or fail to load.
Stop `WhisperServer` (or Kev) first when the 8B or a Marker job needs the card. This
conflict was not exercised on install day because ollama had no model resident.

## Install or refresh

From proximal (the host with key access to peecee):

```bash
scp hosts/peecee/config/whisper/{install-whisper.ps1,run-whisper-serve.cmd,install-whisper-task.ps1} peecee:whisper/
ssh peecee 'powershell -NoProfile -ExecutionPolicy Bypass -File whisper\install-whisper.ps1'
ssh peecee 'powershell -NoProfile -ExecutionPolicy Bypass -File whisper\install-whisper-task.ps1'
```

`run-whisper-serve.cmd` must have CRLF line endings on the box. The downloads (~2.3 GB)
finish inside one SSH session, so no install task is needed.

## Operate

```bash
ssh peecee 'Get-ScheduledTask WhisperServer | Select State; Get-Content whisper\logs\server.log -Tail 5'
ssh peecee 'Stop-ScheduledTask WhisperServer'    # frees ~2 GB VRAM; the ReSpeaker drops utterances meanwhile
ssh peecee 'Start-ScheduledTask WhisperServer'
curl -s http://192.168.1.118:8910/inference -F file=@sample.wav -F response_format=json
```

## Verified 2026-11-16

- Log shows `using CUDA0 backend`; task state `Running`.
- From archon over the LAN: `GET /` → 200.
- From the ReSpeaker over wifi: whisper.cpp's 11 s `jfk.wav` transcribed correctly in
  1.05 s wall time; live utterances of 2–6.5 s returned in 0.17–0.64 s.

## Client

The ReSpeaker Core v2 (`respeaker.local`, Debian 9 image `20180801` on eMMC) runs
`rsp-stt.service`: `arecord` on the 8-channel array, an energy VAD, and one POST per
utterance. Its source and flashing notes live outside this repository in
`archon:~/git/respeaker/`.
