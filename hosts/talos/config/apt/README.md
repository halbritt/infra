# apt sources on talos

`kicad-10.0-snapshot.sources` is installed at
`/etc/apt/sources.list.d/kicad-10.0-snapshot.sources`. It uses the same
Launchpad snapshot timestamp (`20261015T000000Z`) and signing key
(`/usr/share/keyrings/kicad-10.0-releases.asc`, a copy of agent-ee
`docker/kicad-10.0-releases.asc`, fingerprint FDA854F61C4D0D9572BB95E5245D5502FAD7A805)
as the agent-ee Dockerfile, but suite `resolute`, because talos runs Ubuntu 26.04.
The Dockerfile's `noble` packages are not installable on 26.04.

Installed and held from it: `kicad`, `kicad-symbols`, `kicad-footprints` and
`kicad-templates` at `10.0.7~ubuntu26.04.1` (the same build as peecee-wsl).
`kicad-packages3d` is not installed natively. ngspice, bubblewrap and
poppler-utils come from the stock Ubuntu 26.04 archive.
