# Streaming transcription and speaker diarization on peecee

Peecee runs NVIDIA's Nemotron streaming ASR and four-speaker Sortformer v2.1
on the RTX 3090 Ti in WSL2. English uses the English-only Nemotron Speech
Streaming model; every other language, and automatic language selection, uses
the multilingual Nemotron 3.5 ([why](#model-choice-on-2026-11-25)). From proximal, the launcher claims peecee's existing
`marker` batch GPU lease and releases it when the command ends. The models load
on demand. The ReSpeaker's Whisper service uses its own port, 8910.

## Transcribe a recording

Run from the infra checkout on proximal with a 16 kHz mono PCM WAV. Output JSON
includes the transcript and each word's start time, end time, and speaker number.
Use a locale such as `en-US`, or omit it for automatic language selection.
`en` and `en-*` select the English model; anything else, including an omitted
locale, selects the multilingual model.

```bash
hosts/peecee/config/nemo-speech/peecee-speech meeting.wav en-US > meeting.json
```

The launcher copies the WAV to a private temporary directory on peecee, streams
it through the recognizer in 160 ms chunks, retrieves the result and removes
the temporary files. Exit 75 means the fleet could not provide or retain the lease.

## Stream live audio

From proximal, start the foreground server and SSH tunnel with:

```bash
hosts/peecee/config/nemo-speech/peecee-speech --serve          # English model
hosts/peecee/config/nemo-speech/peecee-speech --serve auto     # multilingual model
```

The server loads one ASR model for its lifetime, chosen by that argument with the
same rule as for a recording.

Open `http://127.0.0.1:18921/` on proximal for the playground. A client can
connect to `ws://127.0.0.1:18921/v1/audio/transcriptions/realtime`. Both ends of
the tunnel bind to loopback. Ctrl-C stops the server and releases the GPU. When
the launcher runs without a terminal, end its `ssh` child with SIGTERM; SIGINT
to that process does not reach the server.

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
source weights, installed executable and the three runtime models. An existing
`0.3.0` install that lacks the English model receives it in place. It stages a fresh
install under `~/.local/share/peecee-speech/` before publishing version `0.3.0`.
The CLI is available as `~/.local/bin/nemo-speech` inside WSL. The runtime,
models and Python conversion environment are stored outside Git.

| Component | Installed source |
|---|---|
| NeMo-Speech.cpp 0.3.0 | [NVIDIA CUDA release](https://github.com/NVIDIA/NeMo-Speech.cpp/releases/tag/v0.3.0), converter commit `20999cc921d2b14aa58708f61756a8b2e787ba20` |
| Nemotron 3.5 ASR Streaming 0.6B | [NVIDIA Q8_0 GGUF](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b/tree/ea30d66debe3740a08b573244286791d423d6b3e) |
| Nemotron Speech Streaming English 0.6B | [NVIDIA Q8_0 GGUF](https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b/tree/ebe59e5a817142986528bbbee5dba8db7b38ed50) |
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

## Model choice on 2026-11-25

The owner asked for a speech front end for a live conversation coach, which needs
committed words quickly, on far-field audio. Five recognizers were compared on one
222-second ReSpeaker Core v2 recording (one reader, 459 reference words, the board
playing speech over the reader twice), each on four microphone front ends, scored
with `earshot-bench` from `~/git/earshot`. Word error rate in percent:

| Recognizer | One microphone | Delay-and-sum | Superdirective | Superdirective with null |
|---|---|---|---|---|
| Parakeet CTC 1.1B, whole file | 7.6 | 3.5 | 4.6 | 3.7 |
| Whisper `large-v3-turbo` on port 8910, audio cut at pauses | 7.2 | 5.2 | 5.7 | 5.2 |
| Nemotron Speech Streaming English 0.6B, streamed | 9.2 | 7.4 | 6.1 | 7.2 |
| Nemotron 3.5 multilingual, streamed | 18.5 | 14.6 | 12.6 | 11.8 |
| Parakeet TDT 0.6B v3, whole file | 13.7 | 14.2 | 20.0 | 17.4 |

On this recording a difference below about 2.5 points is not distinguishable from
the recognizer's own spread.

- **Chosen for English: Nemotron Speech Streaming English.** It is within that
  spread of Whisper and streams. A word was complete in the stream a median 0.64 s
  after its end (90th percentile 1.2 s, 99th about 2.2 s), measured against
  Parakeet CTC word timings with 160 ms chunks. No completed word changed in 2,778
  updates. Processing took 3–5 ms per chunk.
- **Nemotron 3.5 multilingual** made about twice the errors on English and stays
  for other languages.
- **Parakeet CTC** was the most accurate and the only one reporting a word
  confidence other than 1, but it does not stream and emits no punctuation. It
  is not installed by `install.sh`.
- **Parakeet TDT** left out stretches of 6–17 s of the long file.
- **Whisper** given the whole file in one request repeated one sentence 16 times
  (26–58% errors). Its row above is the per-pause result.
- Neither Nemotron model marks sentence ends: the English one emitted a few commas,
  the multilingual one nothing.

Limits: one recording of one person reading a poem. Two real talkers and
conversational speech were not tested. The three models tried and not chosen
remain in `~/.cache/nemo-speech/models` in WSL (2.5 GB with a second copy of the
English model) from `nemo-speech pull`; nothing depends on them.

Verified through the launcher after the change:

- `install.sh` added the English model to the existing install and all four
  checksums passed.
- `peecee-speech RECORDING.wav en-US` on the superdirective-with-null recording
  returned 467 timestamped words on two speakers, 7.2% word error rate.
- `peecee-speech RECORDING.wav` on the AMI excerpt above still returned 124 words
  on three speakers from the multilingual model.
- `peecee-speech --serve` reported the English model with `diarization=on`. A
  WebSocket client sent 60 s of the same recording at real-time pace and received
  355 partial updates, never more than 0.13 s behind the audio sent, and a final
  transcript of 146 timestamped words on two speakers.
- Afterwards port 18921 had no listener in WSL and Whisper `/health` returned ok.
