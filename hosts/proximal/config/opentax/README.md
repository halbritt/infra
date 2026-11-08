# OpenTax on proximal

Installed 2026-11-08 at the owner's request to clone OpenTax into `~/git` and
install it on this box. Project: [filedcom/opentax](https://github.com/filedcom/opentax),
the Filed US federal tax engine.

## Installed state

- Source: `/home/halbritt/git/opentax`, full upstream clone on `main` at
  `8f724d4b781e78a6f4d7ef1ba5e810375171ad66` at installation.
- Executable: `/usr/local/bin/opentax`, root-owned mode 0755, official
  `opentax-linux-x64` asset from release `v2.7.0`.
- SHA-256: `73474a7433d54a1a076c09359a28072513d30766ed8b8067d28ade52cc8d7194`.
  Matched both the release's `SHA256SUMS` manifest and GitHub asset digest before
  installation. This is an integrity check, not a publisher signature.
- The native binary includes its runtime; no Bun installation or source dependency
  installation was needed. Source files remain unchanged. No daemon or container.

## Usage and storage

```sh
opentax version
opentax --help
opentax node list
```

Run return commands from a dedicated job directory: the CLI stores returns in
`./.state/returns` relative to the current working directory. Keep actual tax
records outside source repositories. The update-check cache is
`~/.opentax/update-check.json`. No real tax records were used during installation.

The source checkout and installed release are independent. Refresh source with
`git -C ~/git/opentax pull --ff-only`. For binary upgrades, download the selected
Linux x64 release and its checksum manifest, verify the digest, then use
`sudo install -m 0755 <verified-binary> /usr/local/bin/opentax` and rerun checks.
The built-in `opentax update` replaces its executable and needs write permission
to `/usr/local/bin`; the explicit download-and-verify route preserves the checksum
check used for this install. No scheduled updater or version hold was added.

## Verification

`opentax version` returned `opentax 2.7.0`; help worked. The upstream README's
synthetic TY2025 single-filer example was run through the installed binary:
create return, add general facts and a W-2, retrieve computed return. Wages
55000 and withholding 5200 produced taxable income 39250, total tax 4475 and
refund 725, exactly matching the upstream example; `complete` was true with no
failed nodes. This is an installation smoke check, not a tax correctness audit
or filing/MeF/PDF validation. No IRS submission was made.

Local install evidence and the synthetic return:
`~/.local/state/opentax-install-20261108/` (release metadata, checksum manifest,
downloaded binary, and `smoke/result.json`).
