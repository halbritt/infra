# peecee WHEA monitor

[`check-whea.sh`](check-whea.sh) is a proximal-side read-only probe for Windows
WHEA-Logger events on peecee. It runs every 30 minutes from halbritt's crontab,
queries the current Windows boot over BatchMode SSH, and writes local state under
`~/.local/state/peecee-whea/`.

The probe does not alert merely because boot-time corrected events exist. It
records the boot identifier and prior count, then creates `ALERT` only when the
count increases within the same boot. An unreachable host is logged and returns
success so this observation task does not become an actuator.

## Canonical and live paths

The script executes directly from the infrastructure checkout; there is no installed
copy:

```cron
*/30 * * * * /home/halbritt/git/infra/hosts/peecee/config/health/check-whea.sh
```

Required runtime tools on proximal are Bash, `timeout`, `ssh`, `iconv`, and
`base64`. The SSH alias `peecee` must support key-based BatchMode access.

## Verify

```bash
bash -n hosts/peecee/config/health/check-whea.sh
crontab -l | grep 'hosts/peecee/config/health/check-whea.sh'
```

Running the script writes monitoring state. Use the syntax and crontab checks
when a read-only repository verification is sufficient.
