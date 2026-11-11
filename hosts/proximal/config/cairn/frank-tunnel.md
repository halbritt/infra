# Frank's Cairn messaging tunnel

The owner supplied `tunnel_6af3d023e590819194500a5bb31fe28e` on 2026-11-10 to
connect Frank (ChatGPT Dot) to resident agents on proximal. Frank sends requests
through Cairn and retrieves their replies; resident agents perform local work.

```text
ChatGPT plugin → OpenAI private tunnel → cairn mcp --messaging → Cairn API
```

## Installed files

| Source in this directory | Installed location |
| --- | --- |
| `frank-tunnel.py` | `~/.local/libexec/cairn-frank-tunnel.py` |
| `cairn-frank.yaml` | `~/.config/tunnel-client/cairn-frank.yaml` (0600) |
| `cairn-frank-tunnel.service` | `~/.config/systemd/user/cairn-frank-tunnel.service` |

The profile references the existing OpenAI runtime key file
`~/.config/missive/openai-tunnel-key`. The Cairn CLI uses the existing hosted
profile at `~/.local/share/cairn/hosted-agent.token`; neither credential is copied
into this repository. The tunnel opens only an ephemeral loopback health port.
The existing Missive tunnel remains a separate service and profile.

The dedicated Cairn executable is
`~/.local/share/cairn/deployments/frank-tunnel-20261110/cairn`, built from clean
Cairn commit `f662f198c87e14acfc927552272bc4d3f6896602`. Its SHA-256 is
`f9d4105010e610eebfed52d771526fb63b9f287715d5afb4192b55b9284992ce`.
This build reports no embedded VCS revision; the source pin and binary checksum
are retained here rather than claiming a runtime revision stamp. The shared
installed Cairn CLI, API and native session watchers are unchanged.

## Connector identity and lifetime

The supervisor registers binding `chatgpt-frank-tunnel`, with the actual tunnel
ID as its stable connector session ID and harness metadata `chatgpt`. This names
the connector, not an individual ChatGPT conversation. All callers of this plugin
share its Frank inbox; use it in the owner's intended workspace accordingly.

The supervisor registers before starting the tunnel and heartbeats every 25
seconds while its tunnel child is alive. A heartbeat failure stops that child
and fails the service. systemd retries after ten seconds. On a normal stop the
supervisor stops its child and marks the registered execution as left. If the
API cannot accept the leave, presence expires after 90 seconds. systemd owns
cleanup of the entire service cgroup. Stdio-child failure also exits the tunnel.

Restarting resumes the same inbox with a new execution UUID. Registration fences
the old execution; it does not replay requests. Session identifiers are recorded
at `~/.local/state/cairn-frank/session.json` for diagnosis. They may describe an
old execution when the service is stopped; prefer `cairn_agents` with `agent:self`.
Run only this systemd service as the supervisor for this connector.

The supervisor does not claim inbox deliveries or start model sessions. Frank
retrieves replies using `cairn_inbox` and acknowledges them with `cairn_ack`.
No automatic ChatGPT wakeup or push notification is provided by this service.
Resident agents retain their existing delivery and execution rules.

## Install and operate

After building the pinned executable and validating the changes:

```sh
install -Dm755 frank-tunnel.py ~/.local/libexec/cairn-frank-tunnel.py
install -Dm600 cairn-frank.yaml ~/.config/tunnel-client/cairn-frank.yaml
install -Dm644 cairn-frank-tunnel.service ~/.config/systemd/user/cairn-frank-tunnel.service
systemctl --user daemon-reload
systemctl --user enable --now cairn-frank-tunnel.service
tunnel-client health --url-file ~/.local/state/tunnel-client/cairn-frank-health.url \
  --require-control-plane-poll --json
```

Use `systemctl --user restart cairn-frank-tunnel.service` after replacing its
configuration. Disable with `systemctl --user disable --now
cairn-frank-tunnel.service`; retained messages remain in Cairn.

In ChatGPT Plugins, add a custom MCP server, choose Tunnel, select **Cairn**, and
choose **No authentication** for this stdio server. Workspace tunnel access
controls the cloud connection; Cairn's local hosted profile authenticates the
backend. Create/install the plugin for Frank. Confirm the tunnel is associated
with that workspace if it is absent from the selector.

Ask Frank to call `cairn_agents` with `agent:self`, then list resident agents.
For a task requiring a reply, send `kind:request` with a stable request UUID and
an exact recipient. A successful send is acceptance by Cairn, not completion by
the recipient. Inspect `cairn_event_status`, then receive and acknowledge the
reply. Preserve a request UUID and identical arguments after an uncertain send.

## Verification

Focused Cairn messaging tests passed in `mcpapi` and `cmd/cairn`. Ten supervisor
tests cover startup failure, heartbeat failure, shutdown, child exit, bounded
child termination, unsafe PID rejection and private session-file replacement.
All 78 infrastructure tests, repository validation and systemd unit verification
passed. The installed service's live tunnel and messaging checks are recorded
in the host changelog. A successful ChatGPT tool call is the final connection
check; host readiness alone does not establish that the plugin is installed.
