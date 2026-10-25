# Striatum harness credential delivery

Talos receives access-only Claude profiles from proximal's existing
[`claude-oauth-refresh`](../../../proximal/config/claude-oauth-refresh/README.md)
timer. The Striatum harnesses must read those profile files through symlinks:

| Harness file under `~/.local/share/striatum/harness-config/` | Target |
|---|---|
| `claude-code/.credentials.json` | `~/.claude/.credentials.json` |
| `claude-harm/.credentials.json` | `~/.claude-harm/.credentials.json` |

After the scheduled mirror has delivered unexpired profiles, install from the
Talos infra checkout:

```sh
python3 hosts/talos/config/striatum/install-credential-links.py
```

The installer validates both source profiles before replacing credentials with
links. It refuses refresh-token fields, missing or expired access tokens, and
permissions other than 0600. It prints no credential values. Running it again
verifies existing links. It does not log in, refresh credentials, start jobs,
clear exhaustion observations or restart services.

The source-only refresher remains on proximal. Never copy refresh credentials
onto Talos, and keep proximal's retired Striatum data read-only.
