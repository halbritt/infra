# cellular

LTE modem + cellular line on **proximal**: a **Quectel EC25-AF** (USB `2c7c:0125`,
mini-PCIe module on a USB adapter) carrying a **RedPocket AT&T-network** SIM.
Role: **Praxis's live SMS carrier** (since 2026-07-29, via `quectel-sms-gateway`
below — the Android gateway is deprecated); voice is a future maybe (see Open
issue).

Brought up and diagnosed 2026-07-28/29; full story in the
[CHANGELOG](../CHANGELOG.md#2026-07-29). **Data + two-way SMS verified working.
Voice is blocked on IMS registration** (see "Open issue" below).

## Identifiers (captured 2026-07-29)

| what | value |
|---|---|
| module | Quectel EC25-AF(D), USB `2c7c:0125` |
| firmware | `EC25AFFDR07A10M4G_01.004.01.004` (2021-era; see Open issue) |
| IMEI | `865493045248656` (IMEI SV 23) |
| SIM ICCID | `8901280332208593973` |
| home PLMN | 310-280 (AT&T); attaches to 310-410 |
| line number (MSISDN) | **510-520-4061** |
| plan | RedPocket annual, active, renews 2027-07-28 |
| SMSC | `+13123149810` (AT&T) |

## USB layout & access

Enumerates as four `option` serial ports + one QMI interface:

| node | role |
|---|---|
| `/dev/ttyUSB0` | Qualcomm DM/diag |
| `/dev/ttyUSB1` | GPS NMEA |
| `/dev/ttyUSB2` | **AT command port** (primary interface) |
| `/dev/ttyUSB3` | PPP/AT modem port |
| `/dev/cdc-wdm2` + `wwan0` | QMI control + network device |

Serial ports are `root:dialout` and halbritt is **not** in `dialout` — use `sudo`.
QMI: `sudo qmicli -p -d /dev/cdc-wdm2 --nas-get-serving-system` (the `-p` proxy flag
allows concurrent users). The AT port is a single consumer at a time — a background
listener holding it will eat another session's responses.

## Desired modem state (persistent NV settings, applied 2026-07-28/29)

| setting | value | why |
|---|---|---|
| `AT+CGDCONT=1,"IPV4V6","RESELLER"` | attach APN = `RESELLER` | **Load-bearing.** The AT&T MBN defaults cid1 to `broadband` (postpaid APN); AT&T rejects the LTE attach itself for MVNO SIMs requesting an APN outside the subscription. Symptom of loss: `+CEREG: 0,3` (denied) forever while AT&T is visible in scans. Registered within 20 s once set. |
| `AT+QMBNCFG="AutoSel",1` | carrier profile auto-select | Picks the `VoLTE-ATT` MBN for this SIM (correct — RedPocket GSMA is AT&T-network). |
| `AT+QCFG="ims",1` | IMS force-enabled | Prerequisite for VoLTE; registration itself still failing (see Open issue). |
| SIM FPLMN cleared | `AT+CRSM=214,28539,0,0,12,"FF…FF"` | One-time fix, not standing config: pre-activation denials had blacklisted AT&T-family PLMNs (313-100 FirstNet, 312-680) on the SIM, blocking retries. Clear + radio bounce if the modem ever camps T-Mobile and won't try AT&T. |

## Status

**Working (verified 2026-07-29):**
- LTE attach + data bearer — `AT+QIACT=1` then `AT+QPING=1,"8.8.8.8"` → 4/4 replies
  ~30 ms; DNS via `AT+QIDNSGIP` works. (No host-side `wwan0` config yet; data was
  verified from the modem's own stack.)
- SMS both directions. Outbound delivers promptly. **Inbound can lag minutes** —
  first delivery attempts miss (no IMS; paging falls back), the SMSC retries on a
  backoff. Don't bounce the radio while waiting, and don't declare inbound broken
  without checking stored messages (`AT+CMGL="ALL"`).

**Open issue — voice:** IMS SIP registration never completes
(`AT+QCFG="ims"` → `1,0`; network grants the `ims` bearer *with P-CSCF addresses*,
then registration stalls), and AT&T has no CSFB → `ATD` returns `NO CARRIER`
immediately. Prime suspect: the 2021 `R07A10` firmware — newer EC25-AFFD builds
fixed AT&T IMS behavior post-3G-sunset. Path: request latest **EC25-AFFD** firmware
on forums.quectel.com (variant must match exactly), flash from this box with
QFirehose (`sudo ./QFirehose -f <fw_dir>`; stop consumers first; NV settings above
may need re-applying after). Discriminator not yet run: a voice call with the SIM
in a phone *now that the line is settled* — phone-works ⇒ firmware conviction;
phone-fails ⇒ RedPocket voice-entitlement ticket. (The 2026-07-28 phone test's
"line busy" was during mid-activation and proves nothing.)

## Gotchas (all bitten during bring-up)

- **RCS hijack:** while the SIM was in an Android phone, Google Messages registered
  the number for RCS; after moving the SIM back, texts from RCS-capable phones kept
  delivering to the *phone* over Wi-Fi (showing "delivered") and never touched the
  cellular network. Disable RCS on the phone (messages.google.com/disable-chat)
  before trusting any inbound test.
- **`AT+CNMI` resets on module reboot** — new-message URCs go quiet and messages
  accumulate silently in storage. Re-arm `AT+CNMI=2,1,0,1,0` after any
  `AT+CFUN=1,1`, or poll `AT+CMGL="ALL"`.
- **Reboot re-enumeration race:** `AT+CFUN=1,1` drops the USB device for ~10 s. A
  shell doing `exec 3<>/dev/ttyUSB2` in that window **creates a regular file** at
  that path, wedging the port. Fix: `sudo rm /dev/ttyUSB2 && sudo mknod
  /dev/ttyUSB2 c 188 2 && sudo chown root:dialout /dev/ttyUSB2 && sudo chmod 660
  /dev/ttyUSB2`. Guard scripts with `[ -c /dev/ttyUSB2 ]`, not `-e`.
- **SIM EF_MSISDN is a notepad, not authority** — `AT+CNUM` happened to be right
  here, but the dashboard/an SMS-from-the-line is the ground truth for the number.

## Quick reference

```bash
# registration / signal (QMI, safe alongside an AT consumer)
sudo qmicli -p -d /dev/cdc-wdm2 --nas-get-serving-system
sudo qmicli -p -d /dev/cdc-wdm2 --nas-get-signal-strength

# AT session pattern (single consumer!)
sudo bash -c 'exec 3<>/dev/ttyUSB2; printf "AT+CEREG?\r" >&3; timeout 3 cat <&3'

# send an SMS (text mode)
AT+CMGF=1
AT+CMGS="+1XXXXXXXXXX"   →  text, end with Ctrl-Z (0x1A)

# read / clear stored SMS
AT+CMGL="ALL"
AT+CMGD=1,4              # delete all
```

## quectel-sms-gateway — Praxis's SMS carrier (live 2026-07-29)

**This line IS Praxis's SMS channel now** — the Android (capcom6/Moto G)
gateway is deprecated. The daemon [`quectel-sms-gateway.py`](quectel-sms-gateway.py)
owns the AT port exclusively and re-speaks the capcom6 local-mode HTTP
contract, so praxis's carrier code needed only an env swap
(`PRAXIS_ANDROID_SMS_URL=http://127.0.0.1:8852` in `praxisd.env`; var names
kept for history). SMS bytes leave the box only over the radio itself.

| piece | where |
|---|---|
| daemon (canonical) | `cellular/quectel-sms-gateway.py` (run from the checkout) |
| unit (canonical → installed) | `cellular/quectel-sms-gateway.service` → `/etc/systemd/system/` |
| secrets | `/etc/default/quectel-sms-gateway` (0600, outside git) — the same Basic-auth pair praxisd presents (`PRAXIS_ANDROID_SMS_USER/PASSWORD`) |
| HTTP | loopback `127.0.0.1:8852`: `POST /message` (capcom6 shape, Basic auth, 202-on-enqueue), `GET /health` |
| inbound | PDU-mode `AT+CMGL` sweep every 30 s + immediate on `+CMTI`; GSM7+UCS2 decode, concat reassembly; POSTs the `sms:received` webhook to praxis's listener `127.0.0.1:8850`; deletes from modem storage only after a successful dock (praxis dedupes on messageId) |
| outbound | SMS-SUBMIT PDUs, always UCS2 + concat UDH — praxis's ⏰/✅/💡 copy survives; verified 3-segment loopback with astral emoji |

Ops: `sudo systemctl {status,restart} quectel-sms-gateway` ·
`journalctl -u quectel-sms-gateway -f` · `curl -s localhost:8852/health`.
Offline codec check: `python3 quectel-sms-gateway.py --selftest`.

⚠️ **The daemon is the port's single consumer.** `sudo systemctl stop
quectel-sms-gateway` before any hand AT session or a QFirehose flash, and
start it again after. It re-arms `AT+CNMI` and re-opens through modem reboots
on its own (guarding against the regular-file re-enum race).

Known limits (documented, accepted): sends are ACKed 202 on enqueue and the
queue is in-memory — a crash between ACK and radio submit loses that send
after 5 retries (capcom6 had the same window on the phone). The Android-era
webhook registration may still exist on the sleeping Moto G; its target
(`tailscale serve :8851`) is gone, so it is inert — unregister or uninstall
whenever the phone next wakes.
