# LibreChat

The owner requested a self-hosted LibreChat at `https://librechat.harm.org` with Tailscale required. Proximal runs LibreChat 0.8.9 and the existing llama.cpp service supplies `qwen3.8-27b`. The app uses a local email/password account with self-registration closed.

## HTTPS route

The Cloudflare DNS-only A record for `librechat.harm.org` points to Talos at `100.73.54.127`. Its [socket proxy](../../../talos/config/librechat-ingress/README.md) forwards the TLS stream over Tailscale to Proximal port 13081. Tailscale Serve in TCP mode passes it to Caddy on loopback. Caddy terminates TLS and proxies HTTP to LibreChat on `127.0.0.1:3080`. This leaves Proximal's existing port 443 available for its original service. There is no public Cloudflare Tunnel ingress for LibreChat.

Certbot obtains the certificate through the DNS-01 challenge using its Cloudflare plugin. The root-only DNS credential is at `/etc/librechat/certbot-cloudflare.ini`. The system Certbot timer handles renewal. The deploy hook refreshes Caddy's systemd credentials for this certificate.

## Installed files and data

| Source | Installed path |
| --- | --- |
| `compose.yaml`, `librechat.yaml`, `Caddyfile` | `/etc/librechat/` |
| `librechat.service`, `librechat-https.service` | `/etc/systemd/system/` |
| `renew-https` | `/etc/letsencrypt/renewal-hooks/deploy/librechat-https` (0755) |

The Compose file pins each image by digest. MongoDB stores accounts and conversations, Meilisearch indexes chat history, and the retrieval API uses its own pgvector container. The data services have no published ports. Document embeddings run on CPU using `sentence-transformers/all-MiniLM-L6-v2` at revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Its tokenizer, pooling config and safetensors weights are mounted read-only from `/var/lib/librechat/models/all-MiniLM-L6-v2`.

Preserve the `librechat_*` Docker volumes and root-only environment files together when backing up or moving the service. Provision `api.env` with `CREDS_KEY` (32 random bytes in hex), `CREDS_IV` (16), `JWT_SECRET`, `JWT_REFRESH_SECRET`, and `MEILI_MASTER_KEY`. Use the same Meilisearch key in `search.env` and the same JWT secret in `rag.env`. `vector.env` holds `POSTGRES_DB=librechat`, `POSTGRES_USER=librechat`, and a generated password. All four files live in `/etc/librechat` with mode 0600. The first administrator was created with LibreChat's `config/create-user.js` command.

## Operations

After installing the files and secrets, enable the units and the persistent Tailscale forwarding rule.

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now librechat.service librechat-https.service
sudo tailscale serve --bg --tcp=13081 tcp://127.0.0.1:13081
sudo docker compose -f /etc/librechat/compose.yaml ps
curl --fail https://librechat.harm.org/health
```

Apply Compose changes with `sudo docker compose -f /etc/librechat/compose.yaml up -d --wait`. Stop the application with `sudo systemctl stop librechat` to preserve its volumes. To retire the route, remove only the LibreChat DNS record, Talos socket, Proximal TCP 13081 Serve rule and the two LibreChat units.

[Upstream Docker installation](https://www.librechat.ai/docs/local/docker) · [LibreChat 0.8.9 source](https://github.com/LibreChat-AI/LibreChat/tree/d4e85d2205c78413ee27d631d7e3b7313556f21d)
