# talos

Read `machine.yaml`, `notes.md`, and the target subsystem README before changes.
Headless Ubuntu server with no assigned role yet; ask the owner before giving it
long-running workloads. It reaches the network only over Wi-Fi, so a networking
change can strand it. Keep a working Tailscale or LAN path, and prefer `netplan
try` over `netplan apply`. Credentials (Wi-Fi PSK in netplan, Tailscale state) stay
outside Git.
