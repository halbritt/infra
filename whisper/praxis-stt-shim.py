#!/usr/bin/env python3
"""Praxis STT shim — bridges praxis.voice.LiveWhisperSTT to whisper.cpp's server.

Praxis's ``LiveWhisperSTT`` POSTs raw audio as ``application/octet-stream`` and
expects ``{"text": str, "confidence": float}`` back (audio stays on-box, I4). The
on-box ``whisper-server`` (GPU-resident model) instead speaks multipart
``/inference`` and returns OpenAI-style ``verbose_json`` with per-word
probabilities. This stdlib-only shim translates between the two and derives a
**real** confidence = mean per-word probability (the A5 confidence floor routes on
it; no faked constant). On any internal failure it returns an empty, zero-confidence
result so the Praxis path degrades to "ask, don't assert" rather than crashing.

Run:  PRAXIS_STT_SHIM_PORT=8082 WHISPER_SERVER=http://127.0.0.1:8910 \
        python3 praxis-stt-shim.py
Then: export PRAXIS_STT_URL=http://127.0.0.1:8082/transcribe
"""

from __future__ import annotations

import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WHISPER_SERVER = os.environ.get("WHISPER_SERVER", "http://127.0.0.1:8910").rstrip("/")
PORT = int(os.environ.get("PRAXIS_STT_SHIM_PORT", "8082"))
TIMEOUT = float(os.environ.get("PRAXIS_STT_SHIM_TIMEOUT", "120"))


def _multipart(audio: bytes) -> tuple[bytes, str]:
    """Build a multipart/form-data body for whisper-server's /inference."""
    boundary = "----praxissttshimboundary7e1f"
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode()
        )

    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="audio.wav"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
    )
    parts.append(audio)
    parts.append(b"\r\n")
    field("response_format", "verbose_json")
    field("temperature", "0.0")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def _confidence(payload: dict) -> float:
    """Mean per-word probability across all segments — a real STT confidence.

    Falls back to 0.0 (below any sane floor => 'ask') when the response carries no
    word probabilities, so we never assert on an unknown-confidence transcript.
    """
    probs: list[float] = []
    for segment in payload.get("segments") or []:
        for word in segment.get("words") or []:
            p = word.get("probability")
            if isinstance(p, (int, float)):
                probs.append(float(p))
    if not probs:
        return 0.0
    return max(0.0, min(1.0, sum(probs) / len(probs)))


def _transcribe(audio: bytes) -> dict:
    body, boundary = _multipart(audio)
    request = urllib.request.Request(
        f"{WHISPER_SERVER}/inference",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = str(payload.get("text", "")).strip()
    return {"text": text, "confidence": _confidence(payload)}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (stdlib API name)
        length = int(self.headers.get("Content-Length", "0") or "0")
        audio = self.rfile.read(length) if length else b""
        try:
            result = _transcribe(audio) if audio else {"text": "", "confidence": 0.0}
        except Exception:  # degrade, never 500: empty + 0.0 => Praxis asks (A5)
            result = {"text": "", "confidence": 0.0}
        encoded = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - a /health liveness probe
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *args: object) -> None:
        pass  # quiet; the audio path stays on-box and we don't log payloads (I4)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    print(f"praxis-stt-shim on 127.0.0.1:{PORT} -> {WHISPER_SERVER}/inference", flush=True)
    server.serve_forever()
