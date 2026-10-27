# Artifact — public files and HTML reports

The owner requested this service on 2026-10-26: public `artifact.harm.org`, no
authentication for publishing or reads, short random IDs with original filenames,
and an agent CLI. This explicitly replaces the earlier private-service proposal.

| Item | Value |
| --- | --- |
| Software source | `~/git/artifact`, [halbritt/artifact](https://github.com/halbritt/artifact) |
| Public origin | `https://artifact.harm.org` |
| Local origin | `http://127.0.0.1:8879` |
| Service | `systemctl --user status artifact.service` |
| CLI / daemon | `~/.local/bin/artifact`, `~/.local/bin/artifactd` |
| Storage | `~/.local/share/artifact/{staging,published}` |
| Ingress | Existing Cloudflare tunnel; hostname-specific route in [cloudflared](../cloudflared/README.md) |

## Agent use

```sh
artifact publish report.html
artifact publish ./results/ --entry index.html --title "Benchmark results"
artifact publish board.step measurements.csv --json
```

The default server is the public origin. No credentials or tailnet access are
required. Returned URLs look like `https://artifact.harm.org/k320s7/report.html`.
IDs have six random lowercase letters/digits. HTML/JS runs directly, and folder
paths remain intact. Each publication has file download links, a ZIP, and a JSON
manifest with hashes. The homepage does not list publications.

Files are copied into immutable publications; later local edits do not change
published results. There is no automatic expiration. The upload limit is 90 MiB
including multipart overhead, with at most 1,000 files; the CLI allows 89 MiB of
file data. Detailed behavior and API documentation belong in the software repo.

## Installation

The software checkout is canonical for source. Binaries and the unit are installed:

```sh
make -C "$HOME/git/artifact" test install
mkdir -p "$HOME/.local/share/artifact"
install -m 0644 hosts/proximal/config/artifact/artifact.service \
  "$HOME/.config/systemd/user/artifact.service"
systemctl --user daemon-reload
systemctl --user enable --now artifact.service
```

After a binary update, restart `artifact.service`. Both Cloudflare configurations
are installed using that subsystem's documented paths and the system service is
restarted after changing ingress. Existing wildcard DNS already points to this
tunnel; no DNS change is necessary.

## Verification and operations

```sh
curl -fsS http://127.0.0.1:8879/healthz
curl -fsS https://artifact.harm.org/healthz
systemctl --user is-active artifact.service
journalctl --user -u artifact.service -n 30
```

Back up `~/.local/share/artifact/published/`. The files and manifests are sufficient
to recover existing publications; no database is involved. Run one writer process
per store. After a crash, stop the service before clearing abandoned `staging/`
directories. Request failures clean their staging directories automatically.

To withdraw one publication, remove its exact `published/ID/` directory on the
host. There is no public delete endpoint. To withdraw the service, stop/disable
its user unit, remove only its hostname-specific ingress from both Cloudflare
configs, install and restart Cloudflare, and update the index link. Preserve
published contents unless deletion is explicitly requested.

## Initial deployment verification

Software revision `0100361` is pushed to `halbritt/artifact` main. Installed binaries
were built from that revision. `make test` passed the Go race-enabled integration
suite and vet; infrastructure's 43 tests and structural validator passed.

Public CLI upload produced [the live example](https://artifact.harm.org/0a6tp9/my-file.html).
Chromium loaded HTML and relative CSS/JS, clicked the interactive button, downloaded
the CSV and ZIP, and verified every downloaded file against the receipt SHA-256.
No JavaScript errors or phone-width page overflow occurred. Restart retained the
publication and its public manifest. Both user service enabled/active and ingress
config parity were verified.

UIPass inspected homepage and file-list pages at 390x844 and 1280x900 with zero
blocking findings or warnings, followed by visual screenshot inspection.
[Browser report](https://artifact.harm.org/u5szvp/report.html) and
[review notes](https://artifact.harm.org/u5szvp/review.md).
