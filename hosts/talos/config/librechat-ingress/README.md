# LibreChat tailnet ingress

Talos provides the unused HTTPS port for `librechat.harm.org`. The DNS-only A record points to `100.73.54.127`. The systemd socket binds port 443 to that address on `tailscale0`. Its socket-activated proxy forwards encrypted TCP to `100.85.100.81:13081`. Proximal owns the certificate, application and databases. See the [LibreChat runbook](../../../proximal/config/librechat/README.md).

Install both unit files from this directory to `/etc/systemd/system/`, run `sudo systemctl daemon-reload`, then `sudo systemctl enable --now librechat-ingress.socket`. Test from a separate tailnet peer with `curl --fail https://librechat.harm.org/health`. To stop forwarding, disable and stop the socket and stop `librechat-ingress.service`.
