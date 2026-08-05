#!/usr/bin/env python3
"""quectel-sms-gateway — Praxis's SMS carrier over the on-box Quectel EC25-AF.

Replaces the Android (capcom6) SMS gateway: same HTTP wire contract, zero
off-box hops. Praxis's carrier code is untouched — only its URL changes.

    outbound:  POST /message  {"textMessage": {"text": ...},
                               "phoneNumbers": ["+E164"]}   (Basic auth)
               -> 202 {"id": ..., "state": "Pending"}; a worker thread sends
               via AT+CMGS in PDU mode (UCS2 + concat UDH, so emoji and long
               messages survive), retrying with backoff off the request path.
    inbound:   periodic AT+CMGL sweep (PDU mode) + immediate sweep on +CMTI;
               GSM7 and UCS2 decode, concatenated-SMS reassembly; each message
               POSTs the capcom6 ``sms:received`` webhook shape to the praxis
               listener (127.0.0.1:8850) and is deleted from modem storage ONLY
               after the webhook succeeds (the praxis dock is idempotent on
               messageId, so a re-read after a failed delete is a no-op).
    health:    GET /health -> cached registration/signal/queue state.

Design notes (the bring-up gotchas, see README.md):
  * The AT port is single-consumer: this daemon owns /dev/ttyUSB2 exclusively.
    One reader thread demuxes solicited responses from URCs; commands hold a
    lock. Nothing else on the box may open the port while this runs.
  * ``AT+CNMI`` resets on module reboot -> re-armed on every (re)connect, and
    the sweep never depends on URCs (they only accelerate it).
  * ``AT+CFUN=1,1`` drops the USB device ~10 s; opening the path in that window
    can find a REGULAR FILE (the mknod gotcha). The reopen loop stats for a
    char device before opening and backs off loudly otherwise.
  * Everything is UCS2 outbound (DCS 0x08): praxis copy leans on ⏰/✅/💡, and
    GSM7 septet-packing buys nothing on an unlimited-text plan.

Durability caveat (documented, accepted — capcom6 had the same shape): a send
is ACKed 202 on enqueue; the queue is in-memory, so a daemon crash between ACK
and radio submit loses that send after retries. Praxis's outbox retries cover
transport-level failures, not this window.

Config (env; unit sets non-secrets, /etc/default/quectel-sms-gateway the auth):
  QSMS_AT_PORT   serial AT port            (default /dev/ttyUSB2)
  QSMS_BIND      listen host:port          (default 127.0.0.1:8852)
  QSMS_WEBHOOK_URL  praxis inbound listener (default http://127.0.0.1:8850)
  QSMS_USER / QSMS_PASSWORD  Basic auth the carrier must present (required)
  QSMS_POLL_SECONDS  inbound sweep cadence (default 30)

Run ``--selftest`` for the offline PDU-codec checks (no modem, no network).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import queue
import random
import stat
import sys
import threading
import time
import urllib.request
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import serial  # pyserial

QSMS_AT_PORT = os.environ.get("QSMS_AT_PORT", "/dev/ttyUSB2")
QSMS_BIND = os.environ.get("QSMS_BIND", "127.0.0.1:8852")
QSMS_WEBHOOK_URL = os.environ.get("QSMS_WEBHOOK_URL", "http://127.0.0.1:8850")
QSMS_USER = os.environ.get("QSMS_USER", "")
QSMS_PASSWORD = os.environ.get("QSMS_PASSWORD", "")
QSMS_POLL_SECONDS = float(os.environ.get("QSMS_POLL_SECONDS", "30"))

#: Give up reassembling a concatenated inbound after this long and deliver the
#: parts we have (SMSC retries can spread parts over minutes).
CONCAT_TIMEOUT_SECONDS = 300.0
#: Outbound retry policy: attempts x backoff, then a loud drop.
SEND_ATTEMPTS = 5
SEND_BACKOFF_SECONDS = 60.0
#: Per-segment radio submit can take seconds; this bounds one AT+CMGS exchange.
CMGS_TIMEOUT_SECONDS = 35.0

_MAX_BODY = 64 * 1024


def log(msg: str) -> None:
    print(f"quectel-sms-gateway: {msg}", file=sys.stderr, flush=True)


# ============================ PDU codec (pure) ================================
# UCS2-only SUBMIT encode; GSM7 + UCS2 DELIVER decode with UDH concat.

GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXT = {
    0x0A: "\x0c", 0x14: "^", 0x28: "{", 0x29: "}", 0x2F: "\\",
    0x3C: "[", 0x3D: "~", 0x3E: "]", 0x40: "|", 0x65: "€",
}


def _swap_nibbles_bcd(digits: str) -> bytes:
    if len(digits) % 2:
        digits += "F"
    return bytes(
        (int(digits[i + 1], 16) << 4) | int(digits[i], 16) for i in range(0, len(digits), 2)
    )


def _unswap_nibbles_bcd(raw: bytes, ndigits: int) -> str:
    out = []
    for octet in raw:
        out.append(f"{octet & 0x0F:x}")
        out.append(f"{octet >> 4:x}")
    return "".join(out)[:ndigits]


def _segment_ucs2(text: str) -> list[bytes]:
    """Split ``text`` into UTF-16BE chunks that fit SMS user data.

    Single part: 140 bytes (70 units). Concatenated: 134 bytes (67 units) after
    the 6-octet UDH. Never splits a surrogate pair (astral emoji are 2 units).
    """
    data = text.encode("utf-16-be")
    if len(data) <= 140:
        return [data]
    chunks: list[bytes] = []
    limit = 134
    i = 0
    while i < len(data):
        end = min(i + limit, len(data))
        # back off one unit if the boundary would split a surrogate pair
        if end < len(data):
            last_unit = data[end - 2 : end]
            if 0xD800 <= int.from_bytes(last_unit, "big") <= 0xDBFF:
                end -= 2
        chunks.append(data[i:end])
        i = end
    return chunks


def encode_submit_pdus(to_e164: str, text: str, ref: int | None = None) -> list[str]:
    """SMS-SUBMIT TPDUs (hex, ``00`` stored-SMSC prefix included) for ``text``.

    Always UCS2 (DCS 0x08). Multi-segment messages carry an 8-bit concat UDH
    with a shared random reference. The AT+CMGS length argument is
    ``len(pdu_hex)//2 - 1`` (the TPDU byte count, excluding the SMSC octet).
    """
    digits = to_e164.lstrip("+")
    if not digits.isdigit():
        raise ValueError(f"not an E.164 number: {to_e164!r}")
    chunks = _segment_ucs2(text)
    multi = len(chunks) > 1
    if ref is None:
        ref = random.randrange(0, 256)
    pdus: list[str] = []
    for seq, chunk in enumerate(chunks, start=1):
        first_octet = 0x01 | (0x40 if multi else 0x00)  # SUBMIT, VPF=00, UDHI if concat
        tpdu = bytearray([first_octet, 0x00, len(digits), 0x91])
        tpdu += _swap_nibbles_bcd(digits)
        tpdu += bytes([0x00, 0x08])  # PID, DCS=UCS2
        if multi:
            udh = bytes([0x05, 0x00, 0x03, ref, len(chunks), seq])
            tpdu.append(len(udh) + len(chunk))
            tpdu += udh + chunk
        else:
            tpdu.append(len(chunk))
            tpdu += chunk
        pdus.append("00" + tpdu.hex().upper())
    return pdus


def _gsm7_unpack(ud: bytes, udl_septets: int, skip_septets: int) -> str:
    septets: list[int] = []
    for i in range(udl_septets):
        bit = i * 7
        byte, off = bit // 8, bit % 8
        value = ud[byte] >> off
        if off > 1 and byte + 1 < len(ud):
            value |= ud[byte + 1] << (8 - off)
        septets.append(value & 0x7F)
    chars: list[str] = []
    esc = False
    for s in septets[skip_septets:]:
        if esc:
            chars.append(GSM7_EXT.get(s, " "))
            esc = False
        elif s == 0x1B:
            esc = True
        else:
            chars.append(GSM7_BASIC[s])
    return "".join(chars)


def _decode_scts(raw: bytes) -> str:
    def bcd(o: int) -> int:
        return (o & 0x0F) * 10 + (o >> 4)

    yy, mo, dd, hh, mi, ss = (bcd(o) for o in raw[:6])
    # tz: nibble-swapped BCD quarter-hours; bit 3 of the low nibble is the sign
    tz_octet = raw[6]
    tz_quarters = bcd(tz_octet & 0xF7)
    sign = "-" if tz_octet & 0x08 else "+"
    tz_min = tz_quarters * 15
    return (
        f"20{yy:02d}-{mo:02d}-{dd:02d}T{hh:02d}:{mi:02d}:{ss:02d}"
        f"{sign}{tz_min // 60:02d}:{tz_min % 60:02d}"
    )


def decode_deliver_pdu(pdu_hex: str) -> dict | None:
    """Decode one SMS-DELIVER PDU -> ``{from, text, scts, concat}`` or ``None``.

    ``None`` for anything that is not a DELIVER (status reports etc.) or that
    fails to parse — callers log the raw hex and clear it from storage rather
    than re-reading a poison pill forever. ``concat`` is ``(ref, total, seq)``
    or ``None``.
    """
    try:
        raw = bytes.fromhex(pdu_hex.strip())
        i = 0
        smsc_len = raw[i]
        i += 1 + smsc_len
        fo = raw[i]
        i += 1
        if fo & 0x03 != 0x00:  # not SMS-DELIVER
            return None
        udhi = bool(fo & 0x40)
        oa_digits = raw[i]
        i += 1
        toa = raw[i]
        i += 1
        oa_octets = (oa_digits + 1) // 2
        oa_raw = raw[i : i + oa_octets]
        i += oa_octets
        if (toa & 0x70) == 0x50:  # alphanumeric sender, GSM7-packed
            sender = _gsm7_unpack(oa_raw, oa_digits * 4 // 7, 0)
        else:
            sender = _unswap_nibbles_bcd(oa_raw, oa_digits)
            if (toa & 0x70) == 0x10:
                sender = "+" + sender
        i += 1  # PID
        dcs = raw[i]
        i += 1
        scts = _decode_scts(raw[i : i + 7])
        i += 7
        udl = raw[i]
        i += 1
        ud = raw[i:]
        # alphabet from DCS: general group (00xx) bits 2-3; F-group bit 2 (8-bit)
        if (dcs & 0xC0) == 0x00:
            alphabet = (dcs >> 2) & 0x03  # 0 gsm7, 1 8bit, 2 ucs2
        elif (dcs & 0xF0) == 0xF0:
            alphabet = 1 if dcs & 0x04 else 0
        else:
            alphabet = 0
        concat = None
        header_octets = 0
        if udhi and ud:
            udhl = ud[0]
            header_octets = 1 + udhl
            j = 1
            while j + 1 < header_octets:
                iei, iel = ud[j], ud[j + 1]
                ie = ud[j + 2 : j + 2 + iel]
                if iei == 0x00 and iel == 3:
                    concat = (ie[0], ie[1], ie[2])
                elif iei == 0x08 and iel == 4:
                    concat = ((ie[0] << 8) | ie[1], ie[2], ie[3])
                j += 2 + iel
        if alphabet == 2:
            text = ud[header_octets:].decode("utf-16-be", "replace")
        elif alphabet == 0:
            skip = (header_octets * 8 + 6) // 7 if header_octets else 0
            text = _gsm7_unpack(ud, udl, skip)
        else:
            text = ud[header_octets:].hex()
        return {"from": sender, "text": text, "scts": scts, "concat": concat}
    except (IndexError, ValueError):
        return None


# ============================ modem worker ===================================


class ModemWorker(threading.Thread):
    """Exclusive owner of the AT port: sends, sweeps, survives modem reboots."""

    def __init__(self) -> None:
        super().__init__(daemon=True, name="modem")
        self.sends: queue.Queue[dict] = queue.Queue()
        self.sweep_now = threading.Event()
        self.health: dict = {"state": "starting"}
        self._ser: serial.Serial | None = None
        self._resp: queue.Queue[str] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._partials: dict[tuple, float] = {}  # (from, ref, total) -> first-seen

    # --- serial plumbing ------------------------------------------------
    def _open(self) -> None:
        st = os.stat(QSMS_AT_PORT)
        if not stat.S_ISCHR(st.st_mode):
            raise OSError(
                f"{QSMS_AT_PORT} is not a character device — the re-enum race "
                "left a regular file? (see cellular/README.md, mknod fix)"
            )
        self._ser = serial.Serial(QSMS_AT_PORT, 115200, timeout=0.2)
        self._resp = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name="reader")
        self._reader.start()

    def _read_loop(self) -> None:
        """Demux port bytes into solicited responses vs URCs; detect the CMGS prompt."""
        ser = self._ser
        buf = b""
        while ser is not None and ser.is_open:
            try:
                chunk = ser.read(256)
            except (OSError, serial.SerialException):
                self._resp.put("<<PORT-GONE>>")
                return
            if chunk:
                buf += chunk
                while b"\r\n" in buf:
                    line, buf = buf.split(b"\r\n", 1)
                    text = line.decode("utf-8", "replace").strip()
                    if not text:
                        continue
                    if text.startswith(("+CMTI:", "+CMT:", "+CDS:")):
                        self.sweep_now.set()
                    else:
                        self._resp.put(text)
                if buf.endswith(b"> "):
                    buf = b""
                    self._resp.put("<<PROMPT>>")

    def _drain(self) -> None:
        try:
            while True:
                self._resp.get_nowait()
        except queue.Empty:
            pass

    def _cmd(self, command: str, timeout: float = 10.0, upto: str | None = None) -> list[str]:
        """Write one AT command; collect lines until OK/ERROR/<upto> or timeout."""
        assert self._ser is not None
        self._drain()
        self._ser.write(command.encode() + b"\r")
        lines: list[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self._resp.get(timeout=0.25)
            except queue.Empty:
                continue
            if line == "<<PORT-GONE>>":
                raise serial.SerialException("port vanished mid-command")
            lines.append(line)
            if line == "OK" or line.startswith(("ERROR", "+CMS ERROR", "+CME ERROR")):
                return lines
            if upto is not None and line == upto:
                return lines
        raise TimeoutError(f"{command}: no terminal response within {timeout}s: {lines}")

    def _init_modem(self) -> None:
        self._cmd("ATE0")
        self._cmd("AT+CMEE=1")
        self._cmd("AT+CMGF=0")  # PDU mode, both directions
        # store-and-notify; re-armed every (re)connect because CFUN=1,1 resets it
        self._cmd("AT+CNMI=2,1,0,0,0")
        self.health = {"state": "ready", "connected_at": datetime.now(UTC).isoformat()}
        log(f"modem ready on {QSMS_AT_PORT} (PDU mode, CNMI armed)")

    # --- outbound -------------------------------------------------------
    def _send_pdu(self, pdu_hex: str) -> None:
        tpdu_len = len(pdu_hex) // 2 - 1
        got = self._cmd(f"AT+CMGS={tpdu_len}", timeout=10.0, upto="<<PROMPT>>")
        if got[-1] != "<<PROMPT>>":
            raise RuntimeError(f"no CMGS prompt: {got}")
        assert self._ser is not None
        self._ser.write(pdu_hex.encode() + b"\x1a")
        lines = self._collect_submit()
        if not any(line.startswith("+CMGS:") for line in lines):
            raise RuntimeError(f"submit not confirmed: {lines}")

    def _collect_submit(self) -> list[str]:
        lines: list[str] = []
        deadline = time.monotonic() + CMGS_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                line = self._resp.get(timeout=0.25)
            except queue.Empty:
                continue
            if line == "<<PORT-GONE>>":
                raise serial.SerialException("port vanished during submit")
            lines.append(line)
            if line == "OK" or line.startswith(("ERROR", "+CMS ERROR", "+CME ERROR")):
                return lines
        raise TimeoutError(f"CMGS submit timed out: {lines}")

    def _do_send(self, job: dict) -> None:
        for pdu in encode_submit_pdus(job["to"], job["text"]):
            self._send_pdu(pdu)
        log(f"sent id={job['id']} to={job['to']} segments={len(_segment_ucs2(job['text']))}")

    # --- inbound --------------------------------------------------------
    def _sweep(self) -> None:
        lines = self._cmd('AT+CMGL=4', timeout=15.0)
        entries: list[tuple[int, str]] = []  # (index, pdu_hex)
        idx: int | None = None
        for line in lines:
            if line.startswith("+CMGL:"):
                idx = int(line.split(":", 1)[1].split(",")[0].strip())
            elif idx is not None and line not in ("OK",) and not line.startswith("+CM"):
                entries.append((idx, line))
                idx = None
        if not entries:
            return
        decoded = [(index, pdu, decode_deliver_pdu(pdu)) for index, pdu in entries]
        self._deliver_decoded(decoded)

    def _deliver_decoded(self, decoded: list[tuple[int, str, dict | None]]) -> None:
        # non-DELIVER / unparseable: log the raw hex, then clear (no poison pills)
        for index, pdu, msg in decoded:
            if msg is None:
                log(f"clearing non-deliver/unparseable slot {index}: {pdu}")
                self._cmd(f"AT+CMGD={index}")
        singles = [(i, m) for i, _p, m in decoded if m is not None and m["concat"] is None]
        parts = [(i, m) for i, _p, m in decoded if m is not None and m["concat"] is not None]
        for index, msg in singles:
            if self._webhook(msg["from"], msg["text"], msg["scts"]):
                self._cmd(f"AT+CMGD={index}")
        groups: dict[tuple, list[tuple[int, dict]]] = {}
        for index, msg in parts:
            ref, total, _seq = msg["concat"]
            groups.setdefault((msg["from"], ref, total), []).append((index, msg))
        now = time.monotonic()
        for key, members in groups.items():
            _sender, _ref, total = key
            complete = len({m["concat"][2] for _, m in members}) >= total
            first_seen = self._partials.setdefault(key, now)
            if not complete and now - first_seen < CONCAT_TIMEOUT_SECONDS:
                continue  # wait for the SMSC to retry the missing parts
            members.sort(key=lambda pair: pair[1]["concat"][2])
            text = "".join(m["text"] for _, m in members)
            scts = members[0][1]["scts"]
            sender = members[0][1]["from"]
            if not complete:
                log(f"concat timeout {key}: delivering {len(members)}/{total} parts")
            if self._webhook(sender, text, scts):
                for index, _ in members:
                    self._cmd(f"AT+CMGD={index}")
                self._partials.pop(key, None)

    def _webhook(self, sender: str, text: str, scts: str) -> bool:
        message_id = hashlib.sha256(f"{sender}|{scts}|{text}".encode()).hexdigest()[:24]
        payload = {
            "event": "sms:received",
            "payload": {
                "messageId": message_id,
                "message": text,
                "phoneNumber": sender,
                "simNumber": None,
                "receivedAt": scts,
            },
        }
        request = urllib.request.Request(
            QSMS_WEBHOOK_URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as resp:
                ok = 200 <= resp.status < 300
        except OSError as exc:
            log(f"webhook POST failed (message kept in modem storage): {exc}")
            return False
        if ok:
            log(f"inbound docked: from={sender} id={message_id} chars={len(text)}")
        return ok

    # --- lifecycle ------------------------------------------------------
    def run(self) -> None:
        pending: dict | None = None
        while True:
            try:
                self._open()
                self._init_modem()
                self.sweep_now.set()  # drain anything stored while we were down
                last_sweep = 0.0
                while True:
                    if pending is None:
                        try:
                            pending = self.sends.get(timeout=1.0)
                        except queue.Empty:
                            pending = None
                    if pending is not None and time.monotonic() >= pending.get("retry_at", 0.0):
                        job = pending
                        try:
                            self._do_send(job)
                            pending = None
                        except (TimeoutError, RuntimeError) as exc:
                            job["attempts"] = job.get("attempts", 0) + 1
                            if job["attempts"] >= SEND_ATTEMPTS:
                                log(
                                    f"DROPPING send id={job['id']} after "
                                    f"{SEND_ATTEMPTS} attempts: {exc}"
                                )
                                pending = None
                            else:
                                log(
                                    f"send id={job['id']} attempt {job['attempts']} failed ({exc});"
                                    f" retrying in {SEND_BACKOFF_SECONDS:.0f}s"
                                )
                                # keep the job but don't block the loop: inbound
                                # sweeps keep running through the backoff window
                                job["retry_at"] = time.monotonic() + SEND_BACKOFF_SECONDS
                                pending = job
                    elif pending is not None:
                        time.sleep(0.25)  # in backoff: don't busy-spin the loop
                    if self.sweep_now.is_set() or time.monotonic() - last_sweep >= QSMS_POLL_SECONDS:
                        self.sweep_now.clear()
                        self._sweep()
                        self._refresh_health()
                        last_sweep = time.monotonic()
            except (OSError, serial.SerialException, TimeoutError) as exc:
                self.health = {"state": "reconnecting", "error": str(exc)}
                log(f"modem loop error: {exc}; reopening in 5s")
                try:
                    if self._ser is not None:
                        self._ser.close()
                except OSError:
                    pass
                self._ser = None
                time.sleep(5)

    def _refresh_health(self) -> None:
        try:
            creg = next(
                (line for line in self._cmd("AT+CEREG?") if line.startswith("+CEREG:")), ""
            )
            csq = next((line for line in self._cmd("AT+CSQ") if line.startswith("+CSQ:")), "")
            self.health = {
                "state": "ready",
                "cereg": creg,
                "csq": csq,
                "queued_sends": self.sends.qsize(),
                "at": datetime.now(UTC).isoformat(),
            }
        except (TimeoutError, serial.SerialException):
            pass  # the main loop's error handling owns reconnects


# ============================ HTTP edge ======================================


def _auth_ok(header: str | None) -> bool:
    if not QSMS_USER or not QSMS_PASSWORD:
        return False  # refuse-by-default: creds must be configured
    if not header or not header.startswith("Basic "):
        return False
    expected = base64.b64encode(f"{QSMS_USER}:{QSMS_PASSWORD}".encode()).decode()
    return hmac.compare_digest(header[len("Basic ") :], expected)


def make_handler(worker: ModemWorker) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._json(200, worker.health)
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/message":
                self._json(404, {"error": "not found"})
                return
            if not _auth_ok(self.headers.get("Authorization")):
                self._json(401, {"error": "unauthorized"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > _MAX_BODY:
                self._json(413, {"error": "body too large"})
                return
            try:
                body = json.loads(self.rfile.read(length))
                text = body["textMessage"]["text"]
                numbers = body["phoneNumbers"]
                assert isinstance(text, str) and text
                assert isinstance(numbers, list) and numbers
            except (ValueError, KeyError, AssertionError, TypeError):
                self._json(400, {"error": "expected {textMessage:{text}, phoneNumbers:[...]}"})
                return
            job_id = uuid.uuid4().hex
            for number in numbers:
                worker.sends.put({"id": job_id, "to": str(number), "text": text})
            # 202 = accepted-for-delivery, the capcom6 semantic praxis expects
            # (_SEND_OK_STATUS = {200, 201, 202}); the radio submit is async.
            self._json(202, {"id": job_id, "state": "Pending"})

        def log_message(self, *_args: object) -> None:
            pass  # journal gets explicit lines from the worker instead

    return Handler


# ============================ selftest =======================================


def selftest() -> int:
    # single-part UCS2: BMP emoji survives
    pdus = encode_submit_pdus("+15105204061", "⏰ Reminder: stretch", ref=0x2A)
    assert len(pdus) == 1 and pdus[0].startswith("00")
    tpdu = bytes.fromhex(pdus[0])[1:]
    assert tpdu[0] == 0x01 and tpdu[2] == 11 and tpdu[3] == 0x91  # SUBMIT, 11 digits, intl
    assert tpdu[4:10].hex() == "5101254060f1"  # 15105204061 nibble-swapped, F-padded
    assert tpdu[11] == 0x08  # DCS UCS2
    assert tpdu[13:].decode("utf-16-be") == "⏰ Reminder: stretch"

    # multipart: astral emoji (💡 = surrogate pair) never split across segments
    long_text = "💡" * 40 + " end"  # 84 UTF-16 units -> 2 segments
    pdus = encode_submit_pdus("+15105204061", long_text, ref=0x2A)
    assert len(pdus) == 2
    rebuilt = ""
    for seq, pdu in enumerate(pdus, start=1):
        tp = bytes.fromhex(pdu)[1:]
        assert tp[0] == 0x41  # SUBMIT + UDHI
        assert tp[13:19].hex() == f"0500032a02{seq:02x}"  # UDH after the UDL octet
        rebuilt += tp[19:].decode("utf-16-be")
    assert rebuilt == long_text

    # DELIVER decode: GSM7 "hello" from +16509067435 (hand-built vector)
    fo, oa = "04", "0b916105097634f5"
    gsm7_hello = "e8329bfd06"  # "hello" packed
    pdu = "07916031231094f0" + fo + oa + "0000" + "62709211114080" + "05" + gsm7_hello
    msg = decode_deliver_pdu(pdu)
    assert msg is not None and msg["from"] == "+16509067435" and msg["text"] == "hello"
    assert msg["scts"].startswith("2026-07-29T11:11:04")
    assert msg["concat"] is None

    # DELIVER decode: UCS2 with 8-bit concat UDH (2/3)
    body = "⏰ ok".encode("utf-16-be")
    ud = bytes([0x05, 0x00, 0x03, 0x99, 0x03, 0x02]) + body
    pdu2 = (
        "07916031231094f0"
        + "44"  # DELIVER + UDHI
        + oa
        + "0008"
        + "62709211114080"
        + f"{len(ud):02x}"
        + ud.hex()
    )
    msg2 = decode_deliver_pdu(pdu2)
    assert msg2 is not None and msg2["text"] == "⏰ ok" and msg2["concat"] == (0x99, 3, 2)

    # status report (MTI=2) -> None (cleared, not docked)
    assert decode_deliver_pdu("079160312310940f" + "06" + "0b916056097934f5" + "00" * 10) is None

    # segmentation edge: exactly 70 units stays single-part
    assert len(encode_submit_pdus("+15105204061", "x" * 70)) == 1
    assert len(encode_submit_pdus("+15105204061", "x" * 71)) == 2
    print("selftest OK")
    return 0


# ============================ main ===========================================


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if not QSMS_USER or not QSMS_PASSWORD:
        log("QSMS_USER/QSMS_PASSWORD are required (refuse-by-default); set them in the env file")
        return 78
    worker = ModemWorker()
    worker.start()
    host, _, port = QSMS_BIND.partition(":")
    server = ThreadingHTTPServer((host, int(port)), make_handler(worker))
    log(f"listening on {QSMS_BIND} (webhook -> {QSMS_WEBHOOK_URL}, port {QSMS_AT_PORT})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
