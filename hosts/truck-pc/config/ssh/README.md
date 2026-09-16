# OpenSSH access

The owner enabled the Windows OpenSSH Server before this host was enrolled and
authorized installation of the operator's existing SSH public key on 2026-09-15.

- Account: `User`, member of Administrators; SSH sessions are elevated.
- Service: `sshd`, running, automatic startup at first observation.
- Administrator keys: `C:\ProgramData\ssh\administrators_authorized_keys`.
- Installed public key fingerprint: `SHA256:qlHbY20YFvEkRGYVLByKafHs1Psu8hpfNSA4bpq0xPo`
  (ED25519, `halbritt@proximal`).
- File permissions: inheritance removed, Administrators and SYSTEM have full control.
- Existing authorized keys were preserved. Private key and password remain outside Git.

Verified passwordless access from proximal over both LAN and Tailscale:

```bash
ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 User@100.121.157.17 whoami
```

The result is `userpas-gbb8opo\user`. The existing Windows OpenSSH firewall rule
was retained; no new public ingress was added. This is Windows OpenSSH over the
Tailscale network, not a Tailscale SSH server.

To revoke this key, remove only its line from the administrator authorized-key
file after confirming an alternative administrator access method.
