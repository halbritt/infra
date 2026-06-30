# proximal/harm-enterprises instructions

This subsystem records the public `harm.org` / `www.harm.org` static website
served from host `proximal`. Read `README.md` before changing anything here.

## Boundaries

- Commit the systemd unit, non-secret static server code, public hostnames,
  ports, and verification commands.
- Keep public ingress changes in [`../cloudflared`](../cloudflared/); this
  subsystem owns the local origin service and its desired state.
- Do not commit private business data, analytics credentials, Cloudflare
  credentials, or generated TLS material.
- Keep the origin bound to loopback (`127.0.0.1:18888`) unless the exposure
  model is deliberately changed and documented.

## Operational Rule

The repo holds desired state; installed copies run on the box. If you change the
unit or server script here, install them to the mapped paths, reload or restart
the affected service, verify local origin plus public HTTPS, and update the root
changelog.
