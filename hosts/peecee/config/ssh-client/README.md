# peecee SSH client route

[`config`](config) is the canonical proximal-side OpenSSH client configuration
for reaching peecee. It pins the `peecee` alias to the host's Tailscale address
instead of relying on LAN DNS, which can resolve to a stale address.

The private key remains in `~/.ssh/`; this repository records only its path.
Do not copy key material into this directory.

## Apply

On proximal, install the canonical file as halbritt's SSH client configuration:

```bash
install -m 0600 hosts/peecee/config/ssh-client/config ~/.ssh/config
```

The command replaces the complete user SSH configuration. If unrelated host
stanzas are added later, preserve them and install this file as an included
fragment instead.

## Verify

```bash
ssh -G peecee | grep -E '^(hostname|user|identityfile) '
ssh -o BatchMode=yes -o ConnectTimeout=10 peecee hostname
```

The expanded hostname must be `100.113.63.58`, and the remote hostname must be
`PEECEE`.
