# OpenSSH access

The owner enabled the Windows OpenSSH Server before this host was enrolled and
authorized installation of the operator's existing SSH public key on 2026-09-15.

- Account: `halbritt` (renamed from `User` on 2026-09-16), member of Administrators; SSH sessions are elevated.
- Service: `sshd`, running, automatic startup at first observation.
- Administrator keys: `C:\ProgramData\ssh\administrators_authorized_keys`.
- User keys: `C:\Users\User\.ssh\` (`id_ed25519`, `id_ed25519.pub`, `authorized_keys`).
- Installed public key fingerprint: `SHA256:qlHbY20YFvEkRGYVLByKafHs1Psu8hpfNSA4bpq0xPo`
  (ED25519, `halbritt@proximal`).
- File permissions: inheritance removed, `halbritt`, Administrators, and SYSTEM have full control.
- Existing authorized keys were preserved. Private key and password remain outside Git.

Verified passwordless access from proximal over Tailscale:

```bash
ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 halbritt@truck-pc.tail0ecc2e.ts.net whoami
```

The result is `truck-pc\halbritt`. The existing Windows OpenSSH firewall rule
was retained; no new public ingress was added. This is Windows OpenSSH over the
Tailscale network, not a Tailscale SSH server. Outgoing SSH from `truck-pc` to
`proximal` is also configured and verified.

To revoke this key, remove only its line from the administrator authorized-key
file after confirming an alternative administrator access method.
