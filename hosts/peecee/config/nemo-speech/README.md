# Streaming transcription and speaker diarization on peecee

Peecee runs NVIDIA's Nemotron 3.5 streaming ASR and four-speaker Sortformer v2.1
on the RTX 3090 Ti in WSL2. From proximal, the launcher claims peecee's existing
`marker` batch GPU lease and releases it when the command ends. The models load
on demand. The ReSpeaker's Whisper service uses its own port, 8910.

## Transcribe a recording

Run from the infra checkout on proximal with a 16 kHz mono PCM WAV. Output JSON
includes the transcript and each word's start time, end time, and speaker number.
Use a locale such as `en-US`, or omit it for automatic language selection.

```bash
hosts/peecee/config/nemo-speech/peecee-speech meeting.wav en-US > meeting.json
```

The launcher copies the WAV to a private temporary directory on peecee, streams
it through the recognizer in 160 ms chunks, retrieves the result and removes
the temporary files. Exit 75 means the fleet could not provide or retain the lease.

## Stream live audio

From proximal, start the foreground server and SSH tunnel with:

```bash
hosts/peecee/config/nemo-speech/peecee-speech --serve
```

Open `http://127.0.0.1:18921/` on proximal for the playground. A client can
connect to `ws://127.0.0.1:18921/v1/audio/transcriptions/realtime`. Both ends of
the tunnel bind to loopback. Ctrl-C stops the server and releases the GPU.

After `session.created`, send the following JSON and wait for `session.updated`.
Send mono little-endian PCM16 as binary frames, then send
`{"type":"input_audio_buffer.commit"}`. The server returns partial transcripts
and final words with timestamps and speaker numbers.
[NVIDIA's streaming protocol](https://github.com/NVIDIA/NeMo-Speech.cpp/blob/20999cc921d2b14aa58708f61756a8b2e787ba20/docs/api.md#websocket-v1audiotranscriptionsrealtime)

```json
{"type":"session.update","session":{"sample_rate":16000,"language":"en-US","word_timestamps":true,"speaker_diarization":true}}
```

## Reinstall

From proximal:

```bash
ssh -T peecee-wsl 'bash -s' < hosts/peecee/config/nemo-speech/install.sh
```

The installer verifies the SHA-256 of the CUDA release, converter source,
source weights, installed executable and both runtime models. It stages a fresh
install under `~/.local/share/peecee-speech/` before publishing version `0.3.0`.
The CLI is available as `~/.local/bin/nemo-speech` inside WSL. The runtime,
models and Python conversion environment are stored outside Git.

| Component | Installed source |
|---|---|
| NeMo-Speech.cpp 0.3.0 | [NVIDIA CUDA release](https://github.com/NVIDIA/NeMo-Speech.cpp/releases/tag/v0.3.0), converter commit `20999cc921d2b14aa58708f61756a8b2e787ba20` |
| Nemotron 3.5 ASR Streaming 0.6B | [NVIDIA Q8_0 GGUF](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b/tree/ea30d66debe3740a08b573244286791d423d6b3e) |
| Streaming Sortformer 4spk v2.1 | [NVIDIA v2.1 NeMo checkpoint](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2.1/tree/cd03eee90fbec18297ac31b8c21546e596b7f71c), converted locally using the release's F32 preset |

## Verification on 2026-11-24

- Standalone ASR reported `backend=CUDA0` and a 160 ms streaming step. It
  recognized both clauses of the upstream JFK test recording.
- The combined command returned 124 timestamped words with speaker labels 1–3
  on the 60-second AMI EN2002d excerpt. Standalone streaming diarization emitted
  23 RTTM segments across three speakers. The reference contains four speakers,
  including two brief turns totalling 0.73 s for the fourth speaker.
  [AMI test audio and annotations](https://github.com/NVIDIA/NeMo-Speech.cpp/tree/20999cc921d2b14aa58708f61756a8b2e787ba20/test_files/diar)
- The loopback server reported `backend=CUDA0 diarization=on`. A WebSocket
  client sent the same clip in 160 ms PCM frames with language `en-US`. It
  received 365 partial updates, a final transcript with 125 timestamped words
  labelled across three speakers, and the commit acknowledgement.
