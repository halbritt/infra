# cellular

LTE modem + cellular line on **proximal**: a **Quectel EC25-AF** (USB `2c7c:0125`,
mini-PCIe module on a USB adapter) carrying a **RedPocket AT&T-network** SIM.
Intended role: on-box SMS (and eventually voice) carrier — a local-first
alternative/complement to the Android SMS gateway used by Praxis (RFC 0019).

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

No systemd units yet — nothing on the box consumes the modem automatically.
When Praxis grows a connector for it, its unit + env contract belong here.
