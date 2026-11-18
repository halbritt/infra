# Development evidence tool

`development-evidence` is installed for user `halbritt` on proximal since
2026-11-17. Interface, receipt schema and limits are in
[`shared/development`](../../../../shared/development/README.md).

| Source | Installed |
| --- | --- |
| `shared/development/development_evidence.py` | `~/.local/bin/development-evidence` |

The installed file is a byte copy. Change the source, then install and verify:

```sh
python3 shared/development/install.py
python3 shared/development/install.py --check
```

It is a command-line tool only: no service, unit, timer or configuration file.
It reads the repository and the files a caller names, and writes only the
receipt the caller asks for. Rollback: reinstall from the previous infra
revision, or remove the installed file.
